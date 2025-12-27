import os
import logging
import asyncio
import re
import datetime
from aiohttp import web, ClientSession
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler
)

# Import Modules
import strings
import states
import handlers
import admin
import superadmin

# --- CONFIGURATION ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
PORT = int(os.getenv("PORT", 10000))
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL")

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- SELF PINGER (KEEP ALIVE) ---
async def self_pinger():
    """Pings the bot's own URL every 14 minutes to prevent sleep."""
    while True:
        await asyncio.sleep(14 * 60) # 14 minutes
        if WEBHOOK_URL:
             try:
                 url = f"{WEBHOOK_URL}/health"
                 async with ClientSession() as session:
                     async with session.get(url) as resp:
                         status = resp.status
                         logger.info(f"💓 Self-Ping: {status}")
             except Exception as e:
                 logger.error(f"⚠️ Self-Ping Failed: {e}")

# --- HELPER FOR FILTERS ---
def build_filter(key):
    """Builds a Regex filter that matches ANY language variation of a button"""
    options = strings.get_all(key)
    # Escape all options and join with OR (|)
    pattern = "^(" + "|".join([re.escape(opt) for opt in options]) + ")$"
    return filters.Regex(pattern)

# --- WEBHOOK & MAIN ---
async def main():
    application = ApplicationBuilder().token(TOKEN).build()

    # Dynamic Filters (Multi-Language)
    filter_check = build_filter('BTN_CHECK')
    filter_help = build_filter('BTN_HELP')
    filter_settings = build_filter('BTN_SETTINGS')
    filter_languages = build_filter('BTN_LANGUAGES')
    filter_clear = build_filter('BTN_CLEAR_HISTORY')
    filter_back = build_filter('BTN_BACK')
    filter_cancel = build_filter('BTN_CANCEL')
    filter_lang_en = build_filter('BTN_LANG_EN')
    filter_lang_ms = build_filter('BTN_LANG_MS')
    
    # Admin Filters (Usually Admin is one lang, but we support all just in case)
    filter_admin_manage = build_filter('BTN_ADMIN_MANAGE')
    filter_admin_del = build_filter('BTN_ADMIN_DEL')
    filter_admin_list = build_filter('BTN_ADMIN_LIST')
    filter_admin_search = build_filter('BTN_ADMIN_SEARCH')
    filter_admin_broadcast = build_filter('BTN_ADMIN_BROADCAST')
    filter_admin_stats = build_filter('BTN_ADMIN_STATS')
    filter_admin_check_pending = build_filter('BTN_ADMIN_CHECK_PENDING') # Keeping for backward compat logic if needed
    
    filter_admin_exit = build_filter('BTN_ADMIN_EXIT')
    
    # Superadmin Filters
    filter_sa_maint = build_filter('BTN_SA_MAINTENANCE')
    filter_sa_admins = build_filter('BTN_SA_ADMINS')
    filter_sa_health = build_filter('BTN_SA_HEALTH')
    filter_sa_refresh = build_filter('BTN_SA_REFRESH')
    filter_sa_logs = build_filter('BTN_SA_LOGS')
    
    # Superadmin Sub-menu Filters
    filter_sa_add = build_filter('BTN_SA_ADD_ADMIN')
    filter_sa_list = build_filter('BTN_SA_LIST_ADMIN')
    filter_sa_del = build_filter('BTN_SA_DEL_ADMIN')
    filter_sa_exit = build_filter('BTN_SA_EXIT')

    # User Config
    user_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filter_check, handlers.check_start),
            MessageHandler(filter_settings, handlers.settings_menu),
            MessageHandler(filter_languages, handlers.languages_menu)
        ],
        states={
            states.ASK_MATRIC: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filter_cancel, handlers.receive_matric)],
            states.ASK_IC: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filter_cancel, handlers.receive_ic)],
        },
        fallbacks=[
            MessageHandler(filter_cancel | filters.COMMAND, handlers.cancel),
            MessageHandler(filter_settings, handlers.settings_menu),
            MessageHandler(filter_languages, handlers.languages_menu)
        ],
    )
    
    super_conv = ConversationHandler(
        entry_points=[CommandHandler("superadmin", superadmin.start)],
        states={
            states.SUPER_MENU: [
                MessageHandler(filter_sa_maint, superadmin.toggle_maintenance),
                MessageHandler(filter_sa_health, superadmin.check_health),
                MessageHandler(filter_sa_admins, superadmin.manage_admins),
                MessageHandler(filter_sa_admins, superadmin.manage_admins),
                MessageHandler(filter_sa_refresh, superadmin.refresh_config),
                MessageHandler(filter_sa_logs, superadmin.view_logs),
                MessageHandler(filter_sa_exit, superadmin.exit)
            ],
            states.SUPER_ADMIN_MANAGE: [
                MessageHandler(filter_sa_add, superadmin.add_admin_start),
                MessageHandler(filter_sa_list, superadmin.list_admins),
                MessageHandler(filter_sa_del, superadmin.del_admin_start),
                MessageHandler(filter_back, superadmin.back_to_super),
                MessageHandler(filter_sa_exit, superadmin.exit)
            ],
            states.SUPER_ADD_ID: [
                MessageHandler(filter_cancel, superadmin.back_to_manage),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filter_cancel, superadmin.add_admin_save)
            ],
            states.SUPER_DEL_ID: [
                MessageHandler(filter_cancel, superadmin.back_to_manage),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filter_cancel, superadmin.del_admin_perform)
            ]
        },
        fallbacks=[CommandHandler("cancel", superadmin.exit)]
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
                CommandHandler("admin", admin.start) # Allow refresh
            ],
            states.ADMIN_MANAGE: [
                MessageHandler(filter_admin_del, admin.del_start),
                MessageHandler(filter_admin_list, admin.list_members),
                MessageHandler(filter_admin_search, admin.search_start),
                MessageHandler(filter_back, admin.back_to_admin),
                CommandHandler("admin", admin.back_to_admin) # Refresh to main admin
            ],
            states.DEL_MATRIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.del_matric)],
            states.SEARCH_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.receive_search_mode)],
            states.SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.search_perform)],
            states.BROADCAST_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.broadcast_confirm)],
            states.BROADCAST_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.broadcast_send)],
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
    application.add_handler(CommandHandler("check_pending", handlers.check_pending_now)) # Manual Trigger
    
    application.add_handler(MessageHandler(filter_help, handlers.help_command))
    application.add_handler(MessageHandler(filter_settings, handlers.settings_menu))
    application.add_handler(MessageHandler(filter_languages, handlers.languages_menu))
    application.add_handler(MessageHandler(filter_clear, handlers.clear_history))
    application.add_handler(MessageHandler(filter_lang_en, handlers.set_lang_en))
    application.add_handler(MessageHandler(filter_lang_ms, handlers.set_lang_ms))
    application.add_handler(MessageHandler(filter_back, handlers.start)) # Back goes to main menu
    
    # Global Logger (Group -1) - Runs for EVERYTHING
    application.add_handler(MessageHandler(filters.ALL, handlers.log_any_update), group=-1)
    
    # Job Queue
    if application.job_queue:
        application.job_queue.run_repeating(handlers.check_registrations, interval=60, first=10)
        # Daily Logs at 00:00 UTC (or server time)
        application.job_queue.run_daily(handlers.send_daily_logs, time=datetime.time(hour=0, minute=0, second=0))
    
    webhook_path = f"{WEBHOOK_URL}/telegram" if WEBHOOK_URL else None
    
    if WEBHOOK_URL:
        await application.bot.set_webhook(webhook_path)
    else:
        # Local Polling
        logger.info("📡 No WEBHOOK_URL found. Starting Polling...")
        await application.bot.delete_webhook(drop_pending_updates=True) # Good practice to clear old webhooks
        # Initialize updater explicitly if not using run_polling
        # But wait, run_polling handles signals. 
        # For simplicity in this async structure:
        # We need to start polling.
        # Note: application.initialize() initializes the bot, but maybe not updater if not built? 
        # ApplicationBuilder builds it.
        # Let's try use standard run_polling if we can? No we have a webserver too.
        # Fixed:
        await application.updater.initialize() 
        await application.updater.start_polling()
        
    # Set Bot Commands (Suggestions)
    from telegram import BotCommand
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Get help information"),
        BotCommand("settings", "Open Settings"),
    ]
    await application.bot.set_my_commands(commands)

    async def telegram_webhook(request):
        update_data = await request.json()
        await application.process_update(Update.de_json(update_data, application.bot))
        return web.Response(text="OK")

    async def health(request): return web.Response(text="Alive")

    app = web.Application()
    app.router.add_post("/telegram", telegram_webhook)
    app.router.add_get("/", health)
    app.router.add_get("/health", health) # Dedicated endpoint for self-pinger
    
    await application.initialize()
    await application.start()
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    
    # Start Self Pinger
    asyncio.create_task(self_pinger())
    
    # Keep alive loop
    while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
