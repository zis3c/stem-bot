from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import BadRequest
from telegram.ext import ConversationHandler, ContextTypes
import strings
import keyboards
import states
from database import ACTIVITY_LOG_PATH, db
import stats_web
import logging
import hashlib
import re
import asyncio
import os
import time
import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo
from security_utils import RATE_LIMITER, log_security_event

logger = logging.getLogger(__name__)

KL_TZ = ZoneInfo("Asia/Kuala_Lumpur")
LOG_DATE_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2}\]")
TRUSTED_RECEIPT_URL_RE = re.compile(
    r"^https://(?:drive\.google\.com|docs\.google\.com|lh3\.googleusercontent\.com)/",
    re.IGNORECASE,
)
_DAILY_LOG_LOCK = asyncio.Lock()

_VERIF_WINDOW_SECONDS = 10 * 60
_VERIF_LOCK_SECONDS = 15 * 60
_VERIF_MAX_USER_ATTEMPTS = 6
_VERIF_MAX_MATRIC_ATTEMPTS = 12
_verif_user_state = {}
_verif_matric_state = {}
_alert_last_sent = {}
_pending_alert_cache = {}
_review_message_refs = {}
_review_message_lock = asyncio.Lock()

ALERT_COOLDOWN_SECONDS = int(os.getenv("ALERT_COOLDOWN_SECONDS", "900"))
ALERT_QUEUE_COOLDOWN_SECONDS = int(os.getenv("ALERT_QUEUE_COOLDOWN_SECONDS", "1800"))
ALERT_QUEUE_BACKLOG_THRESHOLD = int(os.getenv("ALERT_QUEUE_BACKLOG_THRESHOLD", "25"))
ALERT_WEBHOOK_PENDING_THRESHOLD = int(os.getenv("ALERT_WEBHOOK_PENDING_THRESHOLD", "50"))
GLOBAL_RATE_WINDOW_SEC = int(os.getenv("GLOBAL_RATE_WINDOW_SEC", "60"))
GLOBAL_RATE_MAX_REQ = int(os.getenv("GLOBAL_RATE_MAX_REQ", "25"))
MAX_INPUT_LEN_MATRIC = int(os.getenv("MAX_INPUT_LEN_MATRIC", "24"))
MAX_INPUT_LEN_SEARCH = int(os.getenv("MAX_INPUT_LEN_SEARCH", "80"))
MAX_INPUT_LEN_BROADCAST = int(os.getenv("MAX_INPUT_LEN_BROADCAST", "2000"))
APPS_SCRIPT_WEBHOOK_URL = os.getenv("APPS_SCRIPT_WEBHOOK_URL", "").strip()
APPS_SCRIPT_ADMIN_TOKEN = os.getenv("APPS_SCRIPT_ADMIN_TOKEN", "").strip()


def _public_base_url() -> str:
    # Public web origin for shareable cards and reports.
    return (
        os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
        or os.getenv("WEBHOOK_URL", "").rstrip("/")
    )


def _global_rate_guard(user_id: int, scope: str):
    key = f"{scope}:{user_id}"
    ok, retry = RATE_LIMITER.check(key, GLOBAL_RATE_WINDOW_SEC, GLOBAL_RATE_MAX_REQ)
    if not ok:
        log_security_event("RATE_LIMIT_HIT", f"scope={scope} uid={user_id} retry={retry}")
    return ok, retry


def _post_apps_script_action(action: str, row_idx: int):
    if not APPS_SCRIPT_WEBHOOK_URL or not APPS_SCRIPT_ADMIN_TOKEN:
        return {"ok": False, "error": "apps_script_not_configured"}

    payload = {
        "token": APPS_SCRIPT_ADMIN_TOKEN,
        "action": action,
        "row": int(row_idx),
    }
    req = urllib.request.Request(
        APPS_SCRIPT_WEBHOOK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw or "{}")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")
        except Exception:
            body = str(e)
        return {"ok": False, "error": f"http_{e.code}", "details": body}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def build_review_token(row_values) -> str:
    """Build a short token that identifies one specific registration submission."""
    fields = [
        str(row_values[idx]).strip() if len(row_values) > idx else ""
        for idx in (0, 2, 3, 16)
    ]
    raw = "\x1f".join(fields)
    return hashlib.blake2s(raw.encode("utf-8"), digest_size=4).hexdigest()


def _parse_review_callback_data(data: str, expected_action: str):
    parts = str(data or "").split(":")
    if len(parts) != 4:
        return None

    action, row_raw, matric, token = parts
    if action != expected_action:
        return None

    try:
        row_idx = int(row_raw)
    except Exception:
        return None

    return row_idx, str(matric).strip().upper(), str(token).strip()


async def _get_verified_review_row(row_idx: int, matric: str, expected_token: str):
    row_values, current_row = await run_db_call(db.get_member_by_row_or_matric, row_idx, matric)
    if not row_values:
        return None, None, "record_not_found"

    current_token = build_review_token(row_values)
    if current_token != str(expected_token).strip():
        return row_values, current_row, "stale_submission"

    return row_values, current_row, None


async def _mark_stale_review_message(query):
    await query.edit_message_text("This submission is no longer current. Refresh the admin queue.")


async def register_review_message(review_token: str, chat_id: int, message_id: int):
    token = str(review_token).strip()
    if not token:
        return

    ref = {"chat_id": int(chat_id), "message_id": int(message_id)}
    async with _review_message_lock:
        refs = _review_message_refs.setdefault(token, [])
        if ref not in refs:
            refs.append(ref)


async def _pop_review_message_refs(review_token: str):
    token = str(review_token).strip()
    if not token:
        return []

    async with _review_message_lock:
        return _review_message_refs.pop(token, [])


def _format_review_final_text(action: str, matric: str, actor_name: str, already: bool = False) -> str:
    safe_matric = _escape_md(matric)
    safe_actor = _escape_md(actor_name or "Admin")
    if action == "approve":
        title = "✅ Already Approved" if already else "✅ Approved"
        return (
            f"{title}\n"
            f"Matric: `{safe_matric}`\n"
            f"By: *{safe_actor}*"
        )
    if action == "reject":
        title = "🚫 Already Rejected" if already else "🚫 Rejected"
        return (
            f"{title}\n"
            f"Matric: `{safe_matric}`\n"
            f"By: *{safe_actor}*"
        )
    return (
        f"✅ Updated\n"
        f"Matric: `{safe_matric}`\n"
        f"By: *{safe_actor}*"
    )


async def _finalize_review_cards(context: ContextTypes.DEFAULT_TYPE, review_token: str, action: str, matric: str, actor_name: str, primary_chat_id: int, primary_message_id: int):
    refs = await _pop_review_message_refs(review_token)
    if not refs:
        return

    primary_text = _format_review_final_text(action, matric, actor_name, already=False)
    secondary_text = _format_review_final_text(action, matric, actor_name, already=True)

    for ref in refs:
        try:
            is_primary = ref["chat_id"] == primary_chat_id and ref["message_id"] == primary_message_id
            text = primary_text if is_primary else secondary_text
            await context.bot.edit_message_text(
                chat_id=ref["chat_id"],
                message_id=ref["message_id"],
                text=text,
                parse_mode="Markdown",
                reply_markup=None,
            )
        except Exception:
            continue


async def _delete_message_job(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    if not job:
        return
    chat_id = job.data.get("chat_id")
    message_id = job.data.get("message_id")
    if not chat_id or not message_id:
        return
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except BadRequest:
        # Message may already be deleted/expired.
        pass
    except Exception as e:
        logger.warning("Could not delete scheduled profile card message: %s", e)


def _touch_verif_state(store, key, now_ts):
    state = store.get(key)
    if not state:
        state = {"window_start": now_ts, "attempts": 0, "locked_until": 0}
        store[key] = state

    if now_ts >= state["locked_until"] and (now_ts - state["window_start"]) > _VERIF_WINDOW_SECONDS:
        state["window_start"] = now_ts
        state["attempts"] = 0
    return state


def _check_verif_limit(user_id: int, matric: str):
    now_ts = time.time()
    user_state = _touch_verif_state(_verif_user_state, user_id, now_ts)
    matric_state = _touch_verif_state(_verif_matric_state, matric, now_ts)

    user_retry = max(0, int(user_state["locked_until"] - now_ts))
    matric_retry = max(0, int(matric_state["locked_until"] - now_ts))
    retry_after = max(user_retry, matric_retry)
    return retry_after > 0, retry_after


def _mark_verif_attempt(user_id: int, matric: str, success: bool):
    now_ts = time.time()
    user_state = _touch_verif_state(_verif_user_state, user_id, now_ts)
    matric_state = _touch_verif_state(_verif_matric_state, matric, now_ts)

    if success:
        user_state["attempts"] = 0
        matric_state["attempts"] = 0
        user_state["window_start"] = now_ts
        matric_state["window_start"] = now_ts
        return

    user_state["attempts"] += 1
    matric_state["attempts"] += 1

    if user_state["attempts"] >= _VERIF_MAX_USER_ATTEMPTS:
        user_state["locked_until"] = now_ts + _VERIF_LOCK_SECONDS
    if matric_state["attempts"] >= _VERIF_MAX_MATRIC_ATTEMPTS:
        matric_state["locked_until"] = now_ts + _VERIF_LOCK_SECONDS


def _mask_sensitive_in_text(text: str) -> str:
    if not text:
        return ""

    val = str(text)

    # Mask email local-part.
    val = re.sub(r'([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})', r'\1***@\2', val)

    # Mask 4+ digit numeric chunks.
    def _mask_digits(match):
        s = match.group(0)
        if len(s) <= 4:
            return "*" * len(s)
        return s[:2] + ("*" * (len(s) - 4)) + s[-2:]

    val = re.sub(r"\b\d{4,}\b", _mask_digits, val)
    return val


def _format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    mins, secs = divmod(seconds, 60)
    if mins == 0:
        return f"{secs}s"
    return f"{mins}m {secs}s"


def _escape_md(text):
    return (
        str(text or "")
        .replace("\\", "\\\\")
        .replace("_", "\\_")
        .replace("*", "\\*")
        .replace("`", "\\`")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("(", "\\(")
    )


def _receipt_md_value(value):
    raw = str(value or "").strip()
    if raw.startswith("http") and TRUSTED_RECEIPT_URL_RE.match(raw):
        safe_url = raw.replace(")", "%29")
        return f"[View Receipt]({safe_url})"
    return _escape_md(raw)


def _safe_md_link(value, label):
    raw = str(value or "").strip()
    if raw.startswith("http") and TRUSTED_RECEIPT_URL_RE.match(raw):
        safe_url = raw.replace(")", "%29")
        return f"[{label}]({safe_url})"
    return _escape_md(raw)

def _parse_membership_datetime(raw_value):
    if raw_value is None:
        return None

    text = str(raw_value).strip()
    if not text or text == "-":
        return None

    try:
        iso_value = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso_value)
        return dt.replace(tzinfo=None)
    except Exception:
        pass

    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y",
        "%m/%d/%y %H:%M:%S",
        "%m/%d/%y",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
        "%d/%m/%y %H:%M:%S",
        "%d/%m/%y",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y",
        "%d-%m-%y %H:%M:%S",
        "%d-%m-%y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _format_membership_dates(raw_timestamp):
    registered_at = _parse_membership_datetime(raw_timestamp)
    if not registered_at:
        return "-", "-", False

    expires_at = registered_at + timedelta(days=365)
    today = datetime.now()
    is_expired = today >= expires_at
    return (
        registered_at.strftime("%d/%m/%y"),
        expires_at.strftime("%d/%m/%y"),
        is_expired,
    )


def _row_is_expired(row_values):
    status_raw = str(row_values[17]).strip().lower() if len(row_values) > 17 else ""
    if any(tok in status_raw for tok in ("expired", "expire", "tamat", "luput")):
        return True

    entry_raw = ""
    if len(row_values) > 13 and str(row_values[13]).strip():
        entry_raw = row_values[13]
    elif len(row_values) > 0:
        entry_raw = row_values[0]
    _, _, is_expired = _format_membership_dates(entry_raw)
    return is_expired


# --- HELPERS ---
def get_user_lang(context: ContextTypes.DEFAULT_TYPE):
    """Retrieve user language, default to EN."""
    return context.user_data.get('lang', strings.DEFAULT_LANG)

async def run_db_call(func, *args, **kwargs):
    """Runs blocking DB/sheets work on a thread so the event loop stays responsive."""
    return await asyncio.to_thread(func, *args, **kwargs)


async def send_superadmin_alert(
    bot,
    alert_key: str,
    text: str,
    cooldown_seconds: int = ALERT_COOLDOWN_SECONDS,
):
    """Send throttled operational alerts to superadmins."""
    now_ts = time.time()
    last_ts = _alert_last_sent.get(alert_key, 0)
    if (now_ts - last_ts) < max(1, cooldown_seconds):
        return False

    _alert_last_sent[alert_key] = now_ts
    sent_any = False
    for uid in db.superadmin_ids:
        try:
            await bot.send_message(chat_id=uid, text=text, parse_mode="Markdown")
            sent_any = True
        except Exception as e:
            logger.error(f"Markdown alert send failed '{alert_key}' to {uid}: {e}")
            try:
                await bot.send_message(chat_id=uid, text=text)
                sent_any = True
            except Exception as e2:
                logger.error(f"Fallback alert send failed '{alert_key}' to {uid}: {e2}")
    return sent_any

async def check_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Global keyword checker for main menu navigation (Multi-lingual matches)"""
    text = update.message.text.strip()
    
    # Check against all language variations
    if text in strings.get_all('BTN_CHECK'): return await check_start(update, context)
    if text in strings.get_all('BTN_HELP'): return await help_command(update, context)
    if text in strings.get_all('BTN_SETTINGS'): return await settings_menu(update, context)
    if text in strings.get_all('BTN_LANGUAGES'): return await languages_menu(update, context)
    if text in strings.get_all('BTN_BACK'): return await start(update, context) # Default back to main, but sub-menus might handle back differently
    return None

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.setdefault('lang', strings.DEFAULT_LANG) # Init lang if missing
    lang = get_user_lang(context)
    
    user = update.effective_user
    ok, retry_after = _global_rate_guard(user.id, "start")
    if not ok:
        await update.message.reply_text(
            f"Too many requests. Try again in {retry_after}s.",
            reply_markup=keyboards.get_main_menu(lang),
        )
        return ConversationHandler.END
    
    # Maintenance Check
    if db.maintenance_mode and not db.is_admin(user.id):
        await update.message.reply_text("🚧 *System Under Maintenance*\nPlease try again later.", parse_mode="Markdown")
        return ConversationHandler.END

    # Send Welcome Message with Main Menu (Includes Web App registration button)
    await update.message.reply_text(
        strings.get('WELCOME_MSG', lang).format(name=user.first_name), 
        reply_markup=keyboards.get_main_menu(lang), 
        parse_mode="Markdown"
    )

    # Log user for broadcast (Done in background to improve speed)
    try:
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, db.log_user, user.id, user.first_name)
    except Exception as e:
        logger.error(f"Log user fail: {e}")
    return ConversationHandler.END

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    await update.message.reply_text(
        "⚙️ *Settings*", # Header
        parse_mode="Markdown",
        reply_markup=keyboards.get_settings_menu(lang)
    )
    return ConversationHandler.END

async def languages_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    await update.message.reply_text(
        strings.get('MSG_SELECT_LANG', lang),
        parse_mode="Markdown",
        reply_markup=keyboards.get_language_menu(lang)
    )
    return ConversationHandler.END

async def registration_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    db.log_action(update.effective_user.first_name, "OPEN_REGISTRATION", "Viewed Benefits", role="USER")
    await update.message.reply_text(
        strings.get('REGISTRATION_MSG', lang),
        parse_mode="Markdown",
        reply_markup=keyboards.get_become_member_keyboard(lang)
    )
    return ConversationHandler.END

async def set_lang_en(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['lang'] = 'EN'
    db.log_action(update.effective_user.first_name, "SET_LANG", "English", role="USER")
    # Return to Settings Menu to show context
    await update.message.reply_text(
        strings.get('MSG_LANG_CHANGED', 'EN'),
        reply_markup=keyboards.get_settings_menu('EN')
    )
    return ConversationHandler.END

async def set_lang_ms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['lang'] = 'MS'
    db.log_action(update.effective_user.first_name, "SET_LANG", "Bahasa Melayu", role="USER")
    # Return to Settings Menu to show context
    await update.message.reply_text(
        strings.get('MSG_LANG_CHANGED', 'MS'),
        reply_markup=keyboards.get_settings_menu('MS')
    )
    return ConversationHandler.END



async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    await update.message.reply_text(
        strings.get('HELP_MSG', lang),
        parse_mode="Markdown",
        reply_markup=keyboards.get_help_inline_keyboard(lang)
    )
    return ConversationHandler.END


async def how_it_works_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Switch to detailed how-it-works view in the same message bubble."""
    query = update.callback_query
    await query.answer()

    lang = get_user_lang(context)
    await query.edit_message_text(
        strings.get('HOW_IT_WORKS_MSG', lang),
        parse_mode="Markdown",
        reply_markup=keyboards.get_help_back_inline_keyboard(lang),
        disable_web_page_preview=True,
    )


async def help_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Return to the main help view in the same message bubble."""
    query = update.callback_query
    await query.answer()

    lang = get_user_lang(context)
    await query.edit_message_text(
        strings.get('HELP_MSG', lang),
        parse_mode="Markdown",
        reply_markup=keyboards.get_help_inline_keyboard(lang),
    )

async def check_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    await update.message.reply_text(
        strings.get('PROMPT_MATRIC', lang),
        parse_mode="Markdown",
        reply_markup=keyboards.get_cancel_menu(lang)
    )
    return states.ASK_MATRIC

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    await update.message.reply_text(strings.get('ERR_CANCEL', lang), reply_markup=keyboards.get_main_menu(lang))
    return ConversationHandler.END

async def receive_matric(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    text = update.message.text.strip().upper()
    if len(text) > MAX_INPUT_LEN_MATRIC:
        log_security_event("INPUT_REJECT", f"field=matric len={len(text)} uid={update.effective_user.id}")
        await update.message.reply_text(
            strings.get('ERR_INVALID_MATRIC', lang),
            parse_mode="Markdown",
            reply_markup=keyboards.get_retry_menu(lang)
        )
        return states.ASK_MATRIC
    
    # Check Cancel
    if text in strings.get_all('BTN_CANCEL') or text == "CANCEL": 
        return await cancel(update, context)
    
    # Handle "Try Again"
    if text in strings.get_all('BTN_TRY_AGAIN'):
        await update.message.reply_text(strings.get('PROMPT_MATRIC', lang), parse_mode="Markdown", reply_markup=keyboards.get_cancel_menu(lang))
        return states.ASK_MATRIC

    # Global Navigation Check
    nav = await check_keywords(update, context)
    if nav is not None: return nav

    if not re.match(r'^[A-Z0-9]{6,15}$', text):
        await update.message.reply_text(
            strings.get('ERR_INVALID_MATRIC', lang), 
            parse_mode="Markdown",
            reply_markup=keyboards.get_retry_menu(lang)
        )
        return states.ASK_MATRIC
    
    context.user_data['matric'] = text
    await update.message.reply_text(
        strings.get('PROMPT_IC', lang).format(matric=text),
        parse_mode="Markdown",
        reply_markup=keyboards.get_cancel_menu(lang)
    )
    return states.ASK_IC

async def receive_ic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    text = update.message.text.strip()
    if len(text) > 16:
        log_security_event("INPUT_REJECT", f"field=ic len={len(text)} uid={update.effective_user.id}")
        await update.message.reply_text(
            strings.get('ERR_INVALID_IC', lang),
            parse_mode="Markdown",
            reply_markup=keyboards.get_retry_menu(lang)
        )
        return states.ASK_IC
    
    if text in strings.get_all('BTN_CANCEL') or text == "CANCEL": return await cancel(update, context)

    # Handle "Try Again"
    if text in strings.get_all('BTN_TRY_AGAIN'):
        user_matric = context.user_data.get('matric', 'Unknown')
        await update.message.reply_text(
            strings.get('PROMPT_IC', lang).format(matric=user_matric),
            parse_mode="Markdown",
            reply_markup=keyboards.get_cancel_menu(lang)
        )
        return states.ASK_IC

    # Global Navigation Check
    nav = await check_keywords(update, context)
    if nav is not None: return nav

    if not re.match(r'^\d{4}$', text):
        await update.message.reply_text(
            strings.get('ERR_INVALID_IC', lang), 
            parse_mode="Markdown",
            reply_markup=keyboards.get_retry_menu(lang)
        )
        return states.ASK_IC
    
    # Optimized: No "Verifying..." message. Cache is instant. 
    # Sending/Deleting message takes 2 extra API calls (SLOW).
    # loading_msg = await update.message.reply_text(strings.get('PROMPT_LOADING', lang), parse_mode="Markdown")
    
    user_matric = context.user_data['matric']
    user_ic_last4 = text
    ok, retry_after = _global_rate_guard(update.effective_user.id, "verify")
    if not ok:
        await update.message.reply_text(
            f"Too many requests. Try again in {retry_after}s.",
            reply_markup=keyboards.get_main_menu(lang),
        )
        return ConversationHandler.END
    limited, retry_after = _check_verif_limit(update.effective_user.id, user_matric)
    if limited:
        wait_for = _format_duration(retry_after)
        lock_msg = (
            "⛔ *Verification Temporarily Locked*\n"
            "\n"
            "Too many attempts were detected.\n"
            f"Please try again in *{wait_for}*."
        )
        if lang == "MS":
            lock_msg = (
                "⛔ *Pengesahan Dikunci Sementara*\n"
                "\n"
                "Terlalu banyak cubaan dikesan.\n"
                f"Sila cuba lagi dalam *{wait_for}*."
            )
        await update.message.reply_text(
            lock_msg,
            parse_mode="Markdown",
            reply_markup=keyboards.get_main_menu(lang),
        )
        return ConversationHandler.END

    msg = strings.get('ERR_DB_CONNECTION', lang)
    verification_ok = False
    show_renewal_prompt = False
    profile_card_url = None
    generic_fail_msg = "*Verification Failed*\nYour details could not be verified."
    if lang == "MS":
        generic_fail_msg = "*Pengesahan Gagal*\nMaklumat anda tidak dapat disahkan."
    
    try:
        row_values, row_index = await run_db_call(db.find_member, user_matric)
        
        if row_values:
            if len(row_values) > 9: # Need at least up to IC (Index 9)
                # Gspread List 0-index values: A=0(Timestamp), C=2(Name), D=3(Matric), E=4(Courses/Prog)
                # J=9(IC), Q=16(Receipt), R=17(Status)
                db_timestamp = row_values[0]
                membership_start_raw = row_values[13] if len(row_values) > 13 and str(row_values[13]).strip() else db_timestamp
                db_name = row_values[2] 
                db_ic = str(row_values[9]).strip().replace(" ", "") # J is 9
                db_prog = row_values[4] # E is 4
                db_prog_short = strings.format_program_short(db_prog)
                # Col Q (index 16) is Receipt, Col R (index 17) is Status
                db_resit = str(row_values[16]).strip() if len(row_values) > 16 else ""
                db_status_raw = str(row_values[17]).strip() if len(row_values) > 17 else ""
                db_status_norm = " ".join(db_status_raw.lower().split())
                membership_id = str(row_values[15]).strip() if len(row_values) > 15 else ""

                # Accept flow with legacy compatibility:
                # - old rows can use symbols (✓/✅) or custom words instead of "Approved"
                # - some rows are effectively approved if Membership ID already exists
                approved_tokens = (
                    "approved", "verified", "verify", "accept", "accepted",
                    "disahkan", "lulus", "aktif", "valid"
                )
                expired_tokens = (
                    "expired", "expire", "tamat", "luput"
                )
                rejected_tokens = (
                    "rejected", "reject", "tolak", "ditolak", "batal", "cancel"
                )
                pending_tokens = (
                    "pending", "proses", "review", "semakan"
                )

                final_status = "Pending"
                if any(tok in db_status_norm for tok in expired_tokens):
                    final_status = "Expired"
                elif any(tok in db_status_norm for tok in approved_tokens):
                    final_status = "Approved"
                elif (
                    any(tok in db_status_norm for tok in rejected_tokens)
                ):
                    final_status = "Rejected"
                elif any(tok in db_status_norm for tok in pending_tokens):
                    final_status = "Pending"
                elif membership_id and membership_id != "-":
                    # Fallback for historical rows with empty/non-standard status.
                    final_status = "Approved"
                elif not db_status_norm:
                    final_status = "Pending"

                if db_ic.endswith(user_ic_last4):
                    verification_ok = True
                    if final_status == "Approved": 
                        if not membership_id or membership_id == "-":
                            # Fallback if ID not generated yet but status is Approved
                            msg = strings.get('STATUS_PENDING', lang)
                        else:
                            register_date, expired_date, is_expired = _format_membership_dates(membership_start_raw)
                            if is_expired:
                                final_status = "Expired"
                                try:
                                    await run_db_call(db.update_status_by_row_or_matric, row_index, user_matric, "Expired")
                                except Exception as e:
                                    logger.error(f"Failed to auto-mark expired for {user_matric}: {e}")
                            else:
                                msg = strings.get('VERIFICATION_SUCCESS', lang).format(
                                    membership_id=membership_id,
                                    name=db_name,
                                    matric=user_matric,
                                    program=db_prog_short,
                                    register_date=register_date,
                                    expired_date=expired_date
                                )
                                base_url = _public_base_url()
                                if base_url:
                                    profile_payload = {
                                        "membership_id": membership_id,
                                        "name": db_name,
                                        "matric": user_matric,
                                        "program": db_prog_short,
                                        "register_date": register_date,
                                        "expired_date": expired_date,
                                        "status": "Verified",
                                        "generated_at": datetime.now(KL_TZ).strftime("%Y-%m-%d %H:%M:%S"),
                                        "lang": lang,
                                    }
                                    token = stats_web.create_member_profile_report(
                                        profile_payload,
                                        subject=user_matric,
                                        ttl_seconds=1200,
                                    )
                                    profile_card_url = f"{base_url}/profile/membership/{token}"

                    elif final_status == "Pending":
                        msg = strings.get('STATUS_PENDING', lang)
                    elif final_status == "Rejected":
                        msg = strings.get('STATUS_REJECT', lang)
                    elif final_status == "Expired":
                        _, expired_date, _ = _format_membership_dates(membership_start_raw)
                        if not membership_id or membership_id == "-":
                            membership_id = "-"
                        msg = strings.get('STATUS_EXPIRED', lang).format(
                            membership_id=membership_id,
                            expired_date=expired_date,
                        )
                        show_renewal_prompt = True
                    else:
                        msg = strings.get('STATUS_PENDING', lang)
                else:
                    msg = generic_fail_msg
            else:
                msg = generic_fail_msg
        else:
            msg = generic_fail_msg
                
    except Exception as e:
        logger.error("Verification flow error [%s]: %s", "INC-VERIFY", e)
        verification_ok = False

    # AUTO DELETE LOADING MESSAGE
    # AUTO DELETE LOADING MESSAGE (Removed for speed cleanup)
    # try:
    #     await loading_msg.delete()
    # except Exception:
    #     pass 

    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboards.get_main_menu(lang))
    if profile_card_url:
        profile_prompt = (
            "*Interactive Profile Card*\n"
            "_This secure link expires in 20 minutes._"
        )
        open_label = "Open Profile Card"
        if lang == "MS":
            profile_prompt = (
                "*Kad Profil Interaktif*\n"
                "_Pautan selamat ini tamat dalam 20 minit._"
            )
            open_label = "Buka Kad Profil"
        prev_meta = context.user_data.get("last_profile_card_message")
        if prev_meta:
            try:
                await context.bot.delete_message(
                    chat_id=prev_meta.get("chat_id"),
                    message_id=prev_meta.get("message_id"),
                )
            except BadRequest:
                pass
            except Exception as e:
                logger.warning("Could not delete previous profile card message: %s", e)

        sent_profile_message = await update.message.reply_text(
            profile_prompt,
            parse_mode="Markdown",
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton(open_label, url=profile_card_url)]]
            ),
        )
        context.user_data["last_profile_card_message"] = {
            "chat_id": sent_profile_message.chat_id,
            "message_id": sent_profile_message.message_id,
        }
        if context.job_queue:
            context.job_queue.run_once(
                _delete_message_job,
                when=1200,
                data={
                    "chat_id": sent_profile_message.chat_id,
                    "message_id": sent_profile_message.message_id,
                },
                name=f"profile_card_delete:{sent_profile_message.chat_id}:{sent_profile_message.message_id}",
            )
    if show_renewal_prompt:
        await update.message.reply_text(
            strings.get('REGISTRATION_MSG', lang),
            parse_mode="Markdown",
            reply_markup=keyboards.get_become_member_keyboard(lang)
        )
    _mark_verif_attempt(update.effective_user.id, user_matric, verification_ok)
    
    # Log the result
    log_status = "SUCCESS" if verification_ok else "FAILED_VERIFY"
    db.log_action(
        update.effective_user.first_name,
        "CHECK_MEMBERSHIP",
        f"Matric: {_mask_sensitive_in_text(user_matric)} | Result: {log_status}",
        role="USER"
    )
    
    return ConversationHandler.END

# --- LOGGING HANDLER (GROUP -1) ---
async def log_any_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Logs ALL user interactions for anomaly detection."""
    user = update.effective_user
    if not user: return
    
    # Handle non-text messages
    if not update.message or not update.message.text:
        msg_type = "MEDIA/OTHER"
        if update.message:
            if update.message.sticker: msg_type = "STICKER"
            elif update.message.photo: msg_type = "PHOTO"
            elif update.message.document: msg_type = "DOCUMENT"
            elif update.message.voice: msg_type = "VOICE"
        db.log_action(f"{user.first_name} ({user.id})", "MSG_NON_TEXT", msg_type, role="USER")
        return

    text = update.message.text.strip()
    
    # Identify Keyboard Clicks
    action = "MSG"
    details = f"Text({len(text)} chars)"
    
    # All Button Keys from strings.py
    btn_keys = [
        'BTN_CHECK', 'BTN_HELP', 'BTN_SETTINGS', 'BTN_LANGUAGES', 'BTN_BACK', 'BTN_CANCEL', 
        'BTN_TRY_AGAIN', 'BTN_BECOME_MEMBER', 'BTN_LANG_EN', 'BTN_LANG_MS',
        'BTN_ADMIN_MANAGE', 'BTN_ADMIN_BROADCAST', 'BTN_ADMIN_STATS', 'BTN_ADMIN_EXIT',
        'BTN_ADMIN_STATS_REGISTRATION', 'BTN_ADMIN_STATS_DEMOGRAPHIC',
        'BTN_ADMIN_DEL', 'BTN_ADMIN_LIST', 'BTN_ADMIN_SEARCH', 'BTN_ADMIN_CHECK_PENDING',
        'BTN_SA_MAINTENANCE', 'BTN_SA_ADMINS', 'BTN_SA_HEALTH', 'BTN_SA_REFRESH', 'BTN_SA_LOGS'
    ]
    
    for key in btn_keys:
        if text in strings.get_all(key):
            action = "KEYBOARD_CLICK"
            details = f"Button: {key} ({text})"
            break

    db.log_action(
        f"{user.first_name} ({user.id})",
        action,
        _mask_sensitive_in_text(details),
        role="USER",
    )

# --- JOB QUEUE & CALLBACKS ---
async def check_pending_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manual trigger to check pending registrations immediately."""
    user_id = update.effective_user.id
    if not db.is_admin(user_id): return
    
    await update.message.reply_text("🔎 Scanning for pending registrations...")
    await check_registrations(context)
    await update.message.reply_text("✅ Scan complete.")

async def check_registrations(context: ContextTypes.DEFAULT_TYPE):
    """Job to check for new unprocessed registrations."""
    try:
        new_regs = await run_db_call(db.get_unprocessed_registrations)
        if new_regs and len(new_regs) >= ALERT_QUEUE_BACKLOG_THRESHOLD:
            await send_superadmin_alert(
                context.bot,
                "queue_backlog",
                (
                    "⚠️ *Queue Backlog Alert*\n"
                    f"Pending registrations detected: *{len(new_regs)}*.\n"
                    "Processing may be delayed. Please review admin queue."
                ),
                cooldown_seconds=ALERT_QUEUE_COOLDOWN_SECONDS,
            )

        if not new_regs:
            return
        
        # Notify ALL Admins (Super + Env + Sheet)
        admins = await run_db_call(db.get_all_admin_ids)
        for reg in new_regs:
            row_idx = reg['row']
            data = reg['data']
            # data: [time, email, name, matric, courses, ..., ic, ..., receipt(16), status(17)]
            name = data[2]
            matric = data[3]
            resit_url = data[16] if len(data) > 16 else "No Receipt"

            safe_name = _escape_md(name)
            safe_matric = _escape_md(matric)
            cache_key = f"{row_idx}:{safe_matric}"
            now_ts = time.time()
            last_ts = _pending_alert_cache.get(cache_key, 0)
            if (now_ts - last_ts) < 6 * 60 * 60:
                continue
            
            # Handle Receipt URL (often contains underscores)
            receipt_display = _receipt_md_value(resit_url)
            
            msg = (
                f"*NEW REGISTRATION 🔔*\n\n"
                f"Name: *{safe_name}*\n"
                f"Matric: *{safe_matric}*\n"
                f"Receipt: {receipt_display}"
            )
            
            review_token = build_review_token(data)
            review_keyboard = keyboards.get_admin_review_keyboard(row_idx, matric, review_token, "EN")

            # Send to all admins
            for admin_id in admins:
                try:
                    sent = await context.bot.send_message(
                        chat_id=admin_id,
                        text=msg,
                        parse_mode="Markdown",
                        reply_markup=review_keyboard
                    )
                    await register_review_message(review_token, sent.chat_id, sent.message_id)
                except Exception as e:
                    logger.error(f"Failed to notify admin {admin_id}: {e}")
            _pending_alert_cache[cache_key] = now_ts
            
            # Mark pending so the bot does not notify repeatedly.
            await run_db_call(db.update_status, row_idx, "Pending")
            
    except Exception as e:
        logger.error(f"Check Regs Error: {e}")
        await send_superadmin_alert(
            context.bot,
            "sheets_check_registrations_error",
            (
                "🚨 *Sheets/API Error*\n"
                "Failed while scanning pending registrations.\n"
                "Error: `INC-REGSCAN`"
            ),
            cooldown_seconds=ALERT_COOLDOWN_SECONDS,
        )

def _build_review_summary(row_values):
    name = _escape_md(row_values[2] if len(row_values) > 2 else "-")
    matric = _escape_md(row_values[3] if len(row_values) > 3 else "-")
    receipt = row_values[16] if len(row_values) > 16 else "-"
    receipt_md = _receipt_md_value(receipt)
    return (
        f"*NEW REGISTRATION*\n\n"
        f"Name: *{name}*\n"
        f"Matric: *{matric}*\n"
        f"Receipt: {receipt_md}"
    )

async def review_accept_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_user_lang(context)

    if not db.is_admin(query.from_user.id):
        await query.answer("Admins only.", show_alert=True)
        return

    parsed = _parse_review_callback_data(query.data, "review_accept")
    if not parsed:
        await query.edit_message_text("Invalid action payload.")
        return
    row_idx, matric, review_token = parsed

    row_values, _, stale_reason = await _get_verified_review_row(row_idx, matric, review_token)
    if stale_reason:
        await _mark_stale_review_message(query)
        return

    await query.edit_message_text(
        f"Confirm accept for *{_escape_md(matric)}*?",
        parse_mode="Markdown",
        reply_markup=keyboards.get_admin_confirm_keyboard("accept", row_idx, matric, review_token, lang)
    )

async def review_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_user_lang(context)

    if not db.is_admin(query.from_user.id):
        await query.answer("Admins only.", show_alert=True)
        return

    parsed = _parse_review_callback_data(query.data, "review_reject")
    if not parsed:
        await query.edit_message_text("Invalid action payload.")
        return
    row_idx, matric, review_token = parsed

    row_values, _, stale_reason = await _get_verified_review_row(row_idx, matric, review_token)
    if stale_reason:
        await _mark_stale_review_message(query)
        return

    await query.edit_message_text(
        f"Confirm reject for *{_escape_md(matric)}*?\nThis will remove the record from database.",
        parse_mode="Markdown",
        reply_markup=keyboards.get_admin_confirm_keyboard("reject", row_idx, matric, review_token, lang)
    )


async def review_renew_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_user_lang(context)

    if not db.is_admin(query.from_user.id):
        await query.answer("Admins only.", show_alert=True)
        return

    parsed = _parse_review_callback_data(query.data, "review_renew")
    if not parsed:
        await query.edit_message_text("Invalid action payload.")
        return
    row_idx, matric, review_token = parsed

    row_values, _, stale_reason = await _get_verified_review_row(row_idx, matric, review_token)
    if stale_reason == "record_not_found":
        await query.edit_message_text("Record not found.")
        return
    if stale_reason:
        await _mark_stale_review_message(query)
        return

    if not _row_is_expired(row_values):
        await query.answer("This membership is still active.", show_alert=True)
        return

    await query.edit_message_text(
        f"Confirm renewal (+1 year) for *{_escape_md(matric)}*?",
        parse_mode="Markdown",
        reply_markup=keyboards.get_admin_confirm_keyboard("renew", row_idx, matric, review_token, lang)
    )

async def review_do_accept_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not db.is_admin(query.from_user.id):
        await query.answer("Admins only.", show_alert=True)
        return

    parsed = _parse_review_callback_data(query.data, "review_do_accept")
    if not parsed:
        await query.edit_message_text("Invalid action payload.")
        return
    row_idx, matric, review_token = parsed

    row_values, _, stale_reason = await _get_verified_review_row(row_idx, matric, review_token)
    if stale_reason:
        await _mark_stale_review_message(query)
        return

    await query.edit_message_text(
        f"Processing approval for *{_escape_md(matric)}*...",
        parse_mode="Markdown"
    )

    result = await run_db_call(_post_apps_script_action, "approve", row_idx)
    if result.get("ok"):
        db.log_action(
            f"{query.from_user.first_name} ({query.from_user.id})",
            "ACCEPT_MEMBER",
            f"Matric: {matric} | Row: {row_idx}",
            role="ADMIN"
        )
        actor_name = _escape_md(query.from_user.first_name or "Admin")
        await query.edit_message_text(
            (
                f"✅ *Approved*\n"
                f"Matric: `{_escape_md(matric)}`\n"
                f"By: *{actor_name}*"
            ),
            parse_mode="Markdown"
        )
        await _finalize_review_cards(
            context,
            review_token,
            "approve",
            matric,
            actor_name,
            query.message.chat_id,
            query.message.message_id,
        )
    else:
        err = _escape_md(result.get("error", "unknown"))
        await query.edit_message_text(
            f"Could not accept `{_escape_md(matric)}`\nError: `{err}`",
            parse_mode="Markdown"
        )

async def review_do_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not db.is_admin(query.from_user.id):
        await query.answer("Admins only.", show_alert=True)
        return

    parsed = _parse_review_callback_data(query.data, "review_do_reject")
    if not parsed:
        await query.edit_message_text("Invalid action payload.")
        return
    row_idx, matric, review_token = parsed

    row_values, _, stale_reason = await _get_verified_review_row(row_idx, matric, review_token)
    if stale_reason:
        await _mark_stale_review_message(query)
        return

    result = await run_db_call(_post_apps_script_action, "reject", row_idx)
    if result.get("ok"):
        db.log_action(
            f"{query.from_user.first_name} ({query.from_user.id})",
            "REJECT_MEMBER",
            f"Matric: {matric} | Row: {row_idx} | Action: Removed",
            role="ADMIN"
        )
        actor_name = _escape_md(query.from_user.first_name or "Admin")
        await query.edit_message_text(
            (
                f"🚫 *Rejected*\n"
                f"Matric: `{_escape_md(matric)}`\n"
                f"By: *{actor_name}*\n"
                f"Record removed from database."
            ),
            parse_mode="Markdown"
        )
        await _finalize_review_cards(
            context,
            review_token,
            "reject",
            matric,
            actor_name,
            query.message.chat_id,
            query.message.message_id,
        )
    else:
        err = _escape_md(result.get("error", "unknown"))
        await query.edit_message_text(
            f"Could not reject `{_escape_md(matric)}`\nError: `{err}`",
            parse_mode="Markdown"
        )


async def review_do_renew_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not db.is_admin(query.from_user.id):
        await query.answer("Admins only.", show_alert=True)
        return

    parsed = _parse_review_callback_data(query.data, "review_do_renew")
    if not parsed:
        await query.edit_message_text("Invalid action payload.")
        return
    row_idx, matric, review_token = parsed

    _, _, stale_reason = await _get_verified_review_row(row_idx, matric, review_token)
    if stale_reason:
        await _mark_stale_review_message(query)
        return

    result = await run_db_call(db.renew_membership_by_row_or_matric, row_idx, matric)
    if result.get("ok"):
        db.log_action(
            f"{query.from_user.first_name} ({query.from_user.id})",
            "RENEW_MEMBER",
            (
                f"Matric: {matric} | Row: {result.get('row')} | "
                f"OldExpiry: {result.get('old_expiry')} | NewExpiry: {result.get('new_expiry')}"
            ),
            role="ADMIN"
        )
        await query.edit_message_text(
            (
                f"Renewed: *{_escape_md(matric)}*\n"
                f"Old expiry: *{_escape_md(result.get('old_expiry', '-'))}*\n"
                f"New expiry: *{_escape_md(result.get('new_expiry', '-'))}*"
            ),
            parse_mode="Markdown"
        )
    else:
        await query.edit_message_text(
            f"Could not renew `{_escape_md(matric)}`\nReason: {_escape_md(result.get('error', 'unknown'))}",
            parse_mode="Markdown"
        )

async def review_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Action cancelled.")
    lang = get_user_lang(context)
    parsed = _parse_review_callback_data(query.data, "review_cancel")
    if not parsed:
        await query.edit_message_text("Action cancelled.")
        return
    row_idx, matric, review_token = parsed

    row_values, _, stale_reason = await _get_verified_review_row(row_idx, matric, review_token)
    if stale_reason == "record_not_found":
        await query.edit_message_text("Action cancelled. Record not found anymore.")
        return
    if stale_reason:
        await _mark_stale_review_message(query)
        return

    await query.edit_message_text(
        _build_review_summary(row_values),
        parse_mode="Markdown",
        reply_markup=keyboards.get_admin_review_keyboard(row_idx, matric, review_token, lang, show_renew=_row_is_expired(row_values))
    )

async def review_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_user_lang(context)

    if not db.is_admin(query.from_user.id):
        await query.answer("Admins only.", show_alert=True)
        return

    parsed = _parse_review_callback_data(query.data, "review_detail")
    if not parsed:
        await query.answer("Invalid detail payload.", show_alert=True)
        return
    row_idx, matric, review_token = parsed

    row_values, _, stale_reason = await _get_verified_review_row(row_idx, matric, review_token)
    if stale_reason == "record_not_found":
        await query.answer("Record not found.", show_alert=True)
        return
    if stale_reason:
        await _mark_stale_review_message(query)
        return

    # Enrich pending-detail output with latest cached row for the same matric,
    # so fields generated later (USAS email, entry date, ID, invoice, receipt)
    # still appear when available.
    cached_row, _ = await run_db_call(db.find_member, str(matric).strip().upper())
    if cached_row:
        max_len = max(len(row_values), len(cached_row))
        merged = []
        for i in range(max_len):
            primary = row_values[i] if i < len(row_values) else ""
            fallback = cached_row[i] if i < len(cached_row) else ""
            merged.append(primary if str(primary).strip() else fallback)
        row_values = merged

    def v(idx):
        return str(row_values[idx]).strip() if len(row_values) > idx and row_values[idx] is not None else "-"

    name = v(2)
    matric_v = v(3)
    prog = strings.format_program_short(v(4))
    sem = v(5)
    phone = v(6)
    personal_email = v(7)
    usas_email = v(8)
    ic = v(9)
    birthday = v(10)
    birthplace = v(11)
    address = v(12)
    entry_raw = v(13)
    minute_no = v(14)
    membership_id = v(15)
    proof_url = v(16)
    status = v(17)
    receipt_url = v(18)
    invoice_no = v(19)

    entry_display = entry_raw
    try:
        if entry_raw and entry_raw != "-":
            dt = None
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d %H:%M:%S"):
                try:
                    dt = datetime.strptime(entry_raw.split(" ")[0], fmt)
                    break
                except ValueError:
                    continue
            if dt:
                entry_display = dt.strftime("%d-%b-%y").lstrip("0")
    except Exception:
        entry_display = entry_raw

    proof_display = _safe_md_link(proof_url, "Proof PDF")
    receipt_display = _safe_md_link(receipt_url, "Download PDF")
    status_norm = status.lower()
    id_line = "" if "pending" in status_norm else f"🔑 ID: {_escape_md(membership_id)}\n"
    invoice_line = "" if "pending" in status_norm else f"🧾 Invoice: {_escape_md(invoice_no)}\n"
    receipt_line = "" if "pending" in status_norm else f"📎 Receipt: {receipt_display}\n"

    details_text = (
        f"👤 {_escape_md(name)}\n"
        f"🆔 {_escape_md(matric_v)}\n"
        f"🎓 Prog: {_escape_md(prog)} | Sem: {_escape_md(sem)}\n"
        f"📞 {_escape_md(phone)}\n"
        f"📧 {_escape_md(personal_email)}\n"
        f"🏫 {_escape_md(usas_email)}\n"
        f"🪪 IC: {_escape_md(ic)}\n"
        f"🎂 {_escape_md(birthday)} ({_escape_md(birthplace)})\n"
        f"🏠 {_escape_md(address)}\n"
        f"📅 Entry: {_escape_md(entry_display)}\n"
        f"⏱️ Min: {_escape_md(minute_no)}\n"
        f"{id_line}"
        f"📄 Proof: {proof_display}\n"
        f"{invoice_line}"
        f"{receipt_line}"
        f"✅ Status: {_escape_md(status)}"
    )

    await query.edit_message_text(
        details_text,
        parse_mode="Markdown",
        reply_markup=keyboards.get_admin_review_detail_keyboard(row_idx, matric, review_token, lang, show_renew=_row_is_expired(row_values))
    )

async def review_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_user_lang(context)

    if not db.is_admin(query.from_user.id):
        await query.answer("Admins only.", show_alert=True)
        return

    parsed = _parse_review_callback_data(query.data, "review_back")
    if not parsed:
        await query.edit_message_text("Invalid action payload.")
        return
    row_idx, matric, review_token = parsed

    row_values, _, stale_reason = await _get_verified_review_row(row_idx, matric, review_token)
    if stale_reason == "record_not_found":
        await query.edit_message_text("Record not found.")
        return
    if stale_reason:
        await _mark_stale_review_message(query)
        return

    await query.edit_message_text(
        _build_review_summary(row_values),
        parse_mode="Markdown",
        reply_markup=keyboards.get_admin_review_keyboard(row_idx, matric, review_token, lang, show_renew=_row_is_expired(row_values))
    )

async def send_daily_logs(context: ContextTypes.DEFAULT_TYPE):
    """Send pending daily logs up to yesterday (KL time)."""
    if _DAILY_LOG_LOCK.locked():
        return

    async with _DAILY_LOG_LOCK:
        target_date = (datetime.now(KL_TZ).date() - timedelta(days=1)).strftime("%Y-%m-%d")
        last_maintenance = await run_db_call(db.get_last_maintenance)
        if last_maintenance == target_date:
            return
        if not db.superadmin_ids:
            logger.warning("Daily log job skipped: SUPERADMIN_IDS is not configured.")
            return

        filename = ACTIVITY_LOG_PATH
        if not os.path.exists(filename):
            logger.info("Daily log skipped for %s: %s is missing.", target_date, filename)
            await run_db_call(db.update_last_maintenance, target_date)
            return

        try:
            with open(filename, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            logger.error(f"Failed to read activity.log: {e}")
            return

        if not lines:
            await run_db_call(db.update_last_maintenance, target_date)
            return

        lines_by_date = {}
        keep_lines = []
        for line in lines:
            match = LOG_DATE_RE.match(line)
            if not match:
                keep_lines.append(line)
                continue
            line_date = match.group(1)
            if line_date <= target_date:
                lines_by_date.setdefault(line_date, []).append(line)
            else:
                keep_lines.append(line)

        pending_dates = sorted(
            report_date
            for report_date in lines_by_date
            if last_maintenance < report_date <= target_date
        )

        # Nothing pending: mark up to yesterday so the scheduler can move on.
        if not pending_dates:
            await run_db_call(db.update_last_maintenance, target_date)
            return

        sent_dates = []
        for report_date in pending_dates:
            report_content = "".join(lines_by_date[report_date])
            report_name = f"Logs_{report_date}.txt"
            sent_count = 0
            for uid in db.superadmin_ids:
                try:
                    payload = BytesIO(report_content.encode("utf-8"))
                    payload.name = report_name
                    await context.bot.send_document(
                        chat_id=uid,
                        document=payload,
                        filename=report_name,
                        caption="Daily Admin Logs",
                    )
                    sent_count += 1
                except Exception as e:
                    logger.error(f"Failed to send logs to {uid}: {e}")

            # Keep logs if nobody received them so next run can retry.
            if sent_count == 0:
                logger.warning("Daily logs not delivered for %s. Will retry later.", report_date)
                break

            sent_dates.append(report_date)

        if not sent_dates:
            return

        try:
            sent_dates_set = set(sent_dates)
            with open(filename, "w", encoding="utf-8") as f:
                f.writelines(keep_lines)
                for report_date in pending_dates:
                    if report_date not in sent_dates_set:
                        f.writelines(lines_by_date[report_date])
            await run_db_call(db.update_last_maintenance, sent_dates[-1])
            logger.info("Daily logs sent for: %s", ", ".join(sent_dates))
        except Exception as e:
            logger.error(f"Failed to rotate activity.log: {e}")
