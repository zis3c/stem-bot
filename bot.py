import asyncio
import base64
import datetime
import hmac
import logging
import os
import re
from contextlib import suppress
from zoneinfo import ZoneInfo

from aiohttp import ClientSession, web
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import admin
import handlers
import states
import strings
import superadmin
import stats_web
import demographic_stats_template
import membership_card_template
from security_utils import (
    DEFAULT_TELEGRAM_IP_RANGES,
    SECURITY_METRICS,
    env_bool,
    extract_client_ip,
    ip_allowed,
    log_security_event,
    parse_networks,
    sanitize_sensitive_text,
)

# --- CONFIGURATION ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
PORT = int(os.getenv("PORT", 10000))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").rstrip("/")
WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
WEBHOOK_IP_VALIDATE = env_bool("TELEGRAM_WEBHOOK_IP_VALIDATE", False)
TRUST_PROXY_HOPS = int(os.getenv("TRUST_PROXY_HOPS", "1"))
TELEGRAM_IP_RANGES = os.getenv("TELEGRAM_IP_RANGES", DEFAULT_TELEGRAM_IP_RANGES[0]).strip()
ALLOWED_TELEGRAM_NETWORKS = parse_networks(TELEGRAM_IP_RANGES)

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)
KL_TZ = ZoneInfo("Asia/Kuala_Lumpur")
DAILY_LOG_HOUR = int(os.getenv("DAILY_LOG_HOUR", "8"))
DAILY_LOG_MINUTE = int(os.getenv("DAILY_LOG_MINUTE", "0"))
DAILY_LOG_GRACE_MINUTES = int(os.getenv("DAILY_LOG_GRACE_MINUTES", "30"))
WEBHOOK_ERROR_ALERT_MAX_AGE_SECONDS = int(
    os.getenv("WEBHOOK_ERROR_ALERT_MAX_AGE_SECONDS", "300")
)


# --- SELF PINGER (KEEP ALIVE) ---
async def self_pinger():
    """Pings the bot's own URL every 14 minutes to prevent sleep."""
    while True:
        await asyncio.sleep(14 * 60)
        if WEBHOOK_URL:
            try:
                url = f"{WEBHOOK_URL}/health"
                async with ClientSession() as session:
                    async with session.get(url) as resp:
                        logger.info("Self-Ping status: %s", resp.status)
            except Exception as e:
                logger.error("Self-Ping failed: %s", e)


async def configure_runtime(application):
    """Configure Telegram commands and scheduled jobs once."""
    if application.bot_data.get("runtime_configured"):
        return
    application.bot_data["runtime_configured"] = True

    from telegram import BotCommand

    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Get help information"),
        BotCommand("settings", "Open Settings"),
    ]
    await application.bot.set_my_commands(commands)

    if application.job_queue is None:
        logger.error("JobQueue unavailable: daily log autosend is disabled.")
        return

    daily_log_time = datetime.time(
        hour=DAILY_LOG_HOUR,
        minute=DAILY_LOG_MINUTE,
        second=0,
        tzinfo=KL_TZ,
    )
    if not application.job_queue.get_jobs_by_name("send_daily_logs"):
        application.job_queue.run_daily(
            handlers.send_daily_logs,
            time=daily_log_time,
            name="send_daily_logs",
        )

    logger.info(
        "Scheduler started - daily logs at %02d:%02d (%s)",
        DAILY_LOG_HOUR,
        DAILY_LOG_MINUTE,
        getattr(KL_TZ, "key", str(KL_TZ)),
    )


# --- MAINTENANCE LOOP (ROBUST SCHEDULING) ---
async def maintenance_loop(application):
    """Checks every 15 minutes and sends daily logs only after 8:00 AM KL."""
    from database import db
    from handlers import send_daily_logs, send_superadmin_alert, ALERT_WEBHOOK_PENDING_THRESHOLD

    def _seconds_until_next_quarter(now_dt: datetime.datetime) -> float:
        """Return sleep seconds until the next 15-minute boundary."""
        elapsed = (now_dt.minute * 60) + now_dt.second + (now_dt.microsecond / 1_000_000)
        remainder = elapsed % (15 * 60)
        return (15 * 60) - remainder if remainder else (15 * 60)

    while True:
        try:
            now_kl = datetime.datetime.now(KL_TZ)
            expected_webhook_url = f"{WEBHOOK_URL}/telegram" if WEBHOOK_URL else ""

            # Webhook and queue health checks should run all day, not only after 08:00.
            if WEBHOOK_URL:
                try:
                    info = await application.bot.get_webhook_info()
                    webhook_issues = []
                    if info.url != expected_webhook_url:
                        webhook_issues.append("Webhook URL mismatch.")
                    if info.pending_update_count >= ALERT_WEBHOOK_PENDING_THRESHOLD:
                        webhook_issues.append(
                            f"Pending updates high: {info.pending_update_count}."
                        )

                    last_error_message = str(
                        getattr(info, "last_error_message", "") or ""
                    ).strip()
                    raw_last_error_date = getattr(info, "last_error_date", 0)
                    if isinstance(raw_last_error_date, datetime.datetime):
                        if raw_last_error_date.tzinfo is None:
                            raw_last_error_date = raw_last_error_date.replace(
                                tzinfo=datetime.timezone.utc
                            )
                        last_error_date = int(raw_last_error_date.timestamp())
                    else:
                        last_error_date = int(raw_last_error_date or 0)
                    if last_error_message:
                        now_utc_ts = int(
                            datetime.datetime.now(datetime.timezone.utc).timestamp()
                        )
                        error_age_seconds = (
                            now_utc_ts - last_error_date if last_error_date > 0 else None
                        )
                        is_recent_error = (
                            error_age_seconds is not None
                            and 0 <= error_age_seconds <= WEBHOOK_ERROR_ALERT_MAX_AGE_SECONDS
                        )
                        if is_recent_error:
                            webhook_issues.append(
                                f"Last error: {last_error_message[:120]}"
                            )
                        else:
                            logger.info(
                                "Ignoring stale webhook last_error_message (age=%ss): %s",
                                error_age_seconds,
                                last_error_message[:120],
                            )

                    if webhook_issues:
                        await send_superadmin_alert(
                            application.bot,
                            "webhook_health_issue",
                            (
                                "*Webhook Health Alert*\n"
                                + "\n".join(f"- {_}" for _ in webhook_issues)
                            ),
                            cooldown_seconds=900,
                        )
                except Exception as e:
                    logger.error("Webhook health check failed: %s", e)
                    await send_superadmin_alert(
                        application.bot,
                        "webhook_health_check_error",
                        (
                            "*Webhook Health Check Failed*\n"
                            "Error: `INC-WHCHK`"
                        ),
                        cooldown_seconds=900,
                    )

            # Basic sheets connectivity check.
            try:
                sheet_ok = await asyncio.to_thread(db.get_sheet, "Registrations")
                if not sheet_ok:
                    await send_superadmin_alert(
                        application.bot,
                        "sheets_connectivity_issue",
                        "*Sheets/API Error*\nCould not access `Registrations` sheet.",
                        cooldown_seconds=900,
                    )
            except Exception as e:
                logger.error("Sheets connectivity check failed: %s", e)
                await send_superadmin_alert(
                    application.bot,
                    "sheets_connectivity_check_error",
                    (
                        "*Sheets/API Check Failed*\n"
                        "Error: `INC-SHEET`"
                    ),
                    cooldown_seconds=900,
                )

            # Only allow fallback daily log dispatch in a short morning grace window.
            scheduled_minutes = (DAILY_LOG_HOUR * 60) + DAILY_LOG_MINUTE
            now_minutes = (now_kl.hour * 60) + now_kl.minute
            within_daily_log_grace = (
                DAILY_LOG_GRACE_MINUTES > 0
                and scheduled_minutes <= now_minutes < (scheduled_minutes + DAILY_LOG_GRACE_MINUTES)
            )
            if within_daily_log_grace:
                report_date = (now_kl.date() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
                last_date = await asyncio.to_thread(db.get_last_maintenance)

                if report_date != last_date:
                    logger.info(
                        "Daily log report due during grace window. Last run: %s, Target: %s",
                        last_date,
                        report_date,
                    )

                    class MockContext:
                        def __init__(self, bot):
                            self.bot = bot

                    await send_daily_logs(MockContext(application.bot))
        except Exception as e:
            logger.error("Maintenance loop error: %s", e)

        now_kl = datetime.datetime.now(KL_TZ)
        await asyncio.sleep(_seconds_until_next_quarter(now_kl))


# --- HELPER FOR FILTERS ---
def build_filter(key):
    """Builds a Regex filter that matches ANY language variation of a button."""
    options = strings.get_all(key)
    pattern = "^(" + "|".join([re.escape(opt) for opt in options]) + ")$"
    return filters.Regex(pattern)


# --- WEBHOOK & MAIN ---
async def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN is missing.")

    application = ApplicationBuilder().token(TOKEN).build()

    # Dynamic Filters (Multi-Language)
    filter_check = build_filter("BTN_CHECK")
    filter_help = build_filter("BTN_HELP")
    filter_settings = build_filter("BTN_SETTINGS")
    filter_languages = build_filter("BTN_LANGUAGES")
    filter_become_member = build_filter("BTN_BECOME_MEMBER")

    filter_back = build_filter("BTN_BACK")
    filter_cancel = build_filter("BTN_CANCEL")
    filter_lang_en = build_filter("BTN_LANG_EN")
    filter_lang_ms = build_filter("BTN_LANG_MS")

    # Admin Filters
    filter_admin_manage = build_filter("BTN_ADMIN_MANAGE")
    filter_admin_del = build_filter("BTN_ADMIN_DEL")
    filter_admin_list = build_filter("BTN_ADMIN_LIST")
    filter_admin_search = build_filter("BTN_ADMIN_SEARCH")
    filter_admin_broadcast = build_filter("BTN_ADMIN_BROADCAST")
    filter_admin_stats = build_filter("BTN_ADMIN_STATS")
    filter_admin_stats_registration = build_filter("BTN_ADMIN_STATS_REGISTRATION")
    filter_admin_stats_demographic = build_filter("BTN_ADMIN_STATS_DEMOGRAPHIC")
    filter_admin_check_pending = build_filter("BTN_ADMIN_CHECK_PENDING")
    filter_admin_exit = build_filter("BTN_ADMIN_EXIT")

    # Superadmin Filters
    filter_sa_maint = build_filter("BTN_SA_MAINTENANCE")
    filter_sa_admins = build_filter("BTN_SA_ADMINS")
    filter_sa_health = build_filter("BTN_SA_HEALTH")
    filter_sa_refresh = build_filter("BTN_SA_REFRESH")
    filter_sa_logs = build_filter("BTN_SA_LOGS")

    # Superadmin Sub-menu Filters
    filter_sa_add = build_filter("BTN_SA_ADD_ADMIN")
    filter_sa_list = build_filter("BTN_SA_LIST_ADMIN")
    filter_sa_del = build_filter("BTN_SA_DEL_ADMIN")
    filter_sa_exit = build_filter("BTN_SA_EXIT")

    # User Config
    user_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filter_check, handlers.check_start),
            MessageHandler(filter_settings, handlers.settings_menu),
            MessageHandler(filter_languages, handlers.languages_menu),
            MessageHandler(filter_become_member, handlers.registration_menu),
        ],
        states={
            states.ASK_MATRIC: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~filter_cancel,
                    handlers.receive_matric,
                )
            ],
            states.ASK_IC: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~filter_cancel,
                    handlers.receive_ic,
                )
            ],
        },
        fallbacks=[
            MessageHandler(filter_cancel | filters.COMMAND, handlers.cancel),
            MessageHandler(filter_settings, handlers.settings_menu),
            MessageHandler(filter_languages, handlers.languages_menu),
        ],
    )

    super_conv = ConversationHandler(
        entry_points=[CommandHandler("superadmin", superadmin.start)],
        states={
            states.SUPER_MENU: [
                MessageHandler(filter_sa_maint, superadmin.toggle_maintenance),
                MessageHandler(filter_sa_health, superadmin.check_health),
                MessageHandler(filter_sa_admins, superadmin.manage_admins),
                MessageHandler(filter_sa_refresh, superadmin.refresh_config),
                MessageHandler(filter_sa_logs, superadmin.view_logs),
                MessageHandler(filter_sa_exit, superadmin.exit),
            ],
            states.SUPER_ADMIN_MANAGE: [
                MessageHandler(filter_sa_add, superadmin.add_admin_start),
                MessageHandler(filter_sa_list, superadmin.list_admins),
                MessageHandler(filter_sa_del, superadmin.del_admin_start),
                MessageHandler(filter_back, superadmin.back_to_super),
                MessageHandler(filter_sa_exit, superadmin.exit),
            ],
            states.SUPER_ADD_ID: [
                MessageHandler(filter_cancel, superadmin.back_to_manage),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~filter_cancel,
                    superadmin.add_admin_save,
                ),
            ],
            states.SUPER_DEL_ID: [
                MessageHandler(filter_cancel, superadmin.back_to_manage),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~filter_cancel,
                    superadmin.del_admin_perform,
                ),
            ],
        },
        fallbacks=[CommandHandler("cancel", superadmin.exit)],
        allow_reentry=True,
    )

    # Admin Config
    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("admin", admin.start)],
        states={
            states.ADMIN_MENU: [
                MessageHandler(filter_admin_manage, admin.manage_menu),
                MessageHandler(filter_admin_broadcast, admin.broadcast_start),
                MessageHandler(filter_admin_check_pending, admin.check_pending_click),
                MessageHandler(filter_admin_stats, admin.stats),
                MessageHandler(filter_admin_exit, admin.exit),
                CommandHandler("admin", admin.start),
            ],
            states.ADMIN_STATS_MENU: [
                MessageHandler(filter_admin_stats_registration, admin.stats_registration),
                MessageHandler(filter_admin_stats_demographic, admin.stats_demographic),
                MessageHandler(filter_back, admin.back_to_admin),
                CommandHandler("admin", admin.back_to_admin),
            ],
            states.ADMIN_MANAGE: [
                MessageHandler(filter_admin_del, admin.del_start),
                MessageHandler(filter_admin_list, admin.list_members),
                MessageHandler(filter_admin_search, admin.search_start),
                MessageHandler(filter_back, admin.back_to_admin),
                CommandHandler("admin", admin.back_to_admin),
            ],
            states.DEL_MATRIC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin.del_matric)
            ],
            states.SEARCH_MODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin.receive_search_mode)
            ],
            states.SEARCH_QUERY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin.search_perform)
            ],
            states.BROADCAST_MSG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin.broadcast_confirm)
            ],
            states.BROADCAST_CONFIRM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin.broadcast_send)
            ],
        },
        fallbacks=[CommandHandler("cancel", admin.exit)],
    )

    # General Handlers
    application.add_handler(super_conv)
    application.add_handler(admin_conv)
    application.add_handler(user_conv)
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("help", handlers.help_command))
    application.add_handler(CommandHandler("settings", handlers.settings_menu))
    application.add_handler(CommandHandler("check_pending", handlers.check_pending_now))

    application.add_handler(MessageHandler(filter_help, handlers.help_command))
    application.add_handler(MessageHandler(filter_settings, handlers.settings_menu))
    application.add_handler(MessageHandler(filter_languages, handlers.languages_menu))
    application.add_handler(MessageHandler(filter_become_member, handlers.registration_menu))

    application.add_handler(MessageHandler(filter_lang_en, handlers.set_lang_en))
    application.add_handler(MessageHandler(filter_lang_ms, handlers.set_lang_ms))
    application.add_handler(MessageHandler(filter_back, handlers.start))
    application.add_handler(
        CallbackQueryHandler(handlers.how_it_works_callback, pattern="^how_it_works$")
    )
    application.add_handler(
        CallbackQueryHandler(handlers.help_back_callback, pattern="^help_back$")
    )
    application.add_handler(
        CallbackQueryHandler(admin.stats_registration_full_callback, pattern="^admin_stats_reg_full$")
    )
    application.add_handler(
        CallbackQueryHandler(handlers.review_accept_callback, pattern="^review_accept:")
    )
    application.add_handler(
        CallbackQueryHandler(handlers.review_reject_callback, pattern="^review_reject:")
    )
    application.add_handler(
        CallbackQueryHandler(handlers.review_renew_callback, pattern="^review_renew:")
    )
    application.add_handler(
        CallbackQueryHandler(handlers.review_do_accept_callback, pattern="^review_do_accept:")
    )
    application.add_handler(
        CallbackQueryHandler(handlers.review_do_reject_callback, pattern="^review_do_reject:")
    )
    application.add_handler(
        CallbackQueryHandler(handlers.review_do_renew_callback, pattern="^review_do_renew:")
    )
    application.add_handler(
        CallbackQueryHandler(handlers.review_cancel_callback, pattern="^review_cancel:")
    )
    application.add_handler(
        CallbackQueryHandler(handlers.review_detail_callback, pattern="^review_detail:")
    )
    application.add_handler(
        CallbackQueryHandler(handlers.review_back_callback, pattern="^review_back:")
    )

    # Global Logger (Group -1) - Runs for EVERYTHING
    application.add_handler(MessageHandler(filters.ALL, handlers.log_any_update), group=-1)

    # Job Queue
    if application.job_queue:
        application.job_queue.run_repeating(
            handlers.check_registrations, interval=60, first=10
        )

    app_ready = asyncio.Event()
    background_tasks = []

    async def telegram_webhook(request):
        if not app_ready.is_set():
            return web.Response(status=503, text="Starting")

        try:
            remote_ip = request.remote or ""
            xff = request.headers.get("X-Forwarded-For", "")
            client_ip = extract_client_ip(remote_ip, xff, TRUST_PROXY_HOPS)
            if WEBHOOK_IP_VALIDATE and ALLOWED_TELEGRAM_NETWORKS:
                if not ip_allowed(client_ip or "", ALLOWED_TELEGRAM_NETWORKS):
                    log_security_event(
                        "WEBHOOK_REJECT",
                        f"reason=ip_check ip={client_ip} remote={remote_ip}",
                    )
                    return web.Response(status=403, text="Forbidden")

            if WEBHOOK_SECRET:
                recv_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
                if not hmac.compare_digest(recv_secret, WEBHOOK_SECRET):
                    log_security_event("WEBHOOK_REJECT", "reason=bad_secret")
                    return web.Response(status=403, text="Forbidden")

            update_data = await request.json()
            await application.process_update(Update.de_json(update_data, application.bot))
            return web.Response(text="OK")
        except Exception:
            logger.exception("Webhook processing error")
            return web.Response(status=500, text="Webhook error")

    async def health(request):
        status = "Alive" if app_ready.is_set() else "Starting"
        return web.Response(text=status)

    async def demographic_report(request):
        token = request.match_info.get("token", "").strip()
        payload, err = stats_web.read_demographic_report(token)
        if err or not payload:
            return web.Response(status=404, text="Report link is invalid or expired.")

        course = payload.get("course_distribution", [])
        birth = payload.get("birth_year_distribution", [])
        stats_month_year = str(payload.get("stats_month_year", "-"))
        generated_at = str(payload.get("generated_at", "-"))
        total = int(payload.get("demographic_total", 0))

        course_labels = [str(item.get("label", "Unknown")) for item in course]
        course_vals = [float(item.get("pct", 0.0)) for item in course]
        birth_labels = [str(item.get("label", "Unknown")) for item in birth]
        birth_vals = [float(item.get("pct", 0.0)) for item in birth]
        favicon_tag = ""
        logo_path = os.path.join(os.path.dirname(__file__), "logostem.png")
        with suppress(Exception):
            with open(logo_path, "rb") as logo_file:
                logo_b64 = base64.b64encode(logo_file.read()).decode("ascii")
                favicon_tag = (
                    '<link rel="icon" type="image/png" '
                    f'href="data:image/png;base64,{logo_b64}" />'
                )

        html = demographic_stats_template.render_demographic_report(
            favicon_tag=favicon_tag,
            stats_month_year=stats_month_year,
            generated_at=generated_at,
            total=total,
            course_labels=course_labels,
            course_vals=course_vals,
            birth_labels=birth_labels,
            birth_vals=birth_vals,
        )
        return web.Response(text=html, content_type="text/html")

    async def membership_profile_report(request):
        token = request.match_info.get("token", "").strip()
        payload, err = stats_web.read_member_profile_report(token)
        if err or not payload:
            return web.Response(status=404, text="Profile link is invalid or expired.")

        import html as html_lib

        def esc(value):
            return html_lib.escape(str(value if value is not None else "-"), quote=True)

        membership_id = esc(payload.get("membership_id", "-"))
        name = esc(payload.get("name", "-"))
        matric = esc(payload.get("matric", "-"))
        program = esc(payload.get("program", "-"))
        register_date = esc(payload.get("register_date", "-"))
        expired_date = esc(payload.get("expired_date", "-"))
        status_raw = str(payload.get("status", "Verified")).strip().lower()
        if "expired" in status_raw:
            badge_class = "expired"
            badge_text = "EXPIRED"
        elif "pending" in status_raw:
            badge_class = "pending"
            badge_text = "PENDING"
        else:
            badge_class = "verified"
            badge_text = "VERIFIED"

        favicon_tag = ""
        logo_src = ""
        logo_path = os.path.join(os.path.dirname(__file__), "logostem.png")
        with suppress(Exception):
            with open(logo_path, "rb") as logo_file:
                logo_b64 = base64.b64encode(logo_file.read()).decode("ascii")
                logo_src = f"data:image/png;base64,{logo_b64}"
                favicon_tag = (
                    '<link rel="icon" type="image/png" '
                    f'href="{logo_src}" />'
                )

        html = membership_card_template.render_membership_card(
            membership_id=membership_id,
            name=name,
            matric=matric,
            program=program,
            register_date=register_date,
            expired_date=expired_date,
            badge_class=badge_class,
            badge_text=badge_text,
            logo_src=logo_src,
            favicon_tag=favicon_tag,
        )
        return web.Response(text=html, content_type="text/html")

    app = web.Application()
    app.router.add_post("/telegram", telegram_webhook)
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    app.router.add_get("/stats/demographic/{token}", demographic_report)
    app.router.add_get("/profile/membership/{token}", membership_profile_report)

    async def security_metrics_summary(_):
        summary = SECURITY_METRICS.snapshot()
        if summary:
            logger.info("Security metrics snapshot: %s", sanitize_sensitive_text(summary))

    if application.job_queue:
        application.job_queue.run_repeating(
            security_metrics_summary,
            interval=900,
            first=120,
            name="security_metrics_summary",
        )

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info("HTTP server started on port %s", PORT)

    try:
        await application.initialize()
        await application.start()

        if WEBHOOK_URL:
            if not WEBHOOK_SECRET:
                raise RuntimeError(
                    "WEBHOOK_URL is set but TELEGRAM_WEBHOOK_SECRET is missing. "
                    "Set TELEGRAM_WEBHOOK_SECRET to protect webhook authenticity."
                )
            webhook_path = f"{WEBHOOK_URL}/telegram"
            await application.bot.set_webhook(webhook_path, secret_token=WEBHOOK_SECRET)
            logger.info("Webhook configured: %s", webhook_path)
        else:
            logger.info("No WEBHOOK_URL found. Starting polling...")
            await application.bot.delete_webhook(drop_pending_updates=True)
            if application.updater:
                await application.updater.start_polling()

        await configure_runtime(application)

        background_tasks.append(asyncio.create_task(self_pinger(), name="self_pinger"))
        background_tasks.append(
            asyncio.create_task(maintenance_loop(application), name="maintenance_loop")
        )
        app_ready.set()

        while True:
            await asyncio.sleep(3600)
    finally:
        app_ready.clear()

        for task in background_tasks:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        with suppress(Exception):
            if application.updater:
                await application.updater.stop()
        with suppress(Exception):
            await application.stop()
        with suppress(Exception):
            await application.shutdown()
        with suppress(Exception):
            await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

