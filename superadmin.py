from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ConversationHandler, ContextTypes
import strings
import keyboards
import states
from database import db
import psutil
import time
import logging

logger = logging.getLogger(__name__)

# --- HELPERS ---
def get_user_lang(context: ContextTypes.DEFAULT_TYPE):
    return context.user_data.get('lang', strings.DEFAULT_LANG)

def get_super_menu(lang='EN'):
    return ReplyKeyboardMarkup([
        [strings.get('BTN_SA_MAINTENANCE', lang)],
        [strings.get('BTN_SA_ADMINS', lang), strings.get('BTN_SA_HEALTH', lang)],
        [strings.get('BTN_ADMIN_EXIT', lang)]
    ], resize_keyboard=True)

# --- START ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if not db.is_admin(user_id): return ConversationHandler.END # Silent fail for non-admins
    
    # Sync config fresh
    db.refresh_system_config()
    
    lang = get_user_lang(context)
    status = "🔴 ON" if db.maintenance_mode else "🟢 OFF"
    
    await update.message.reply_text(
        f"🔐 *Superadmin Dashboard*\n\nMaintenance Mode: {status}",
        parse_mode="Markdown",
        reply_markup=get_super_menu(lang)
    )
    return states.SUPER_MENU

# --- FEATURES ---
async def check_health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    uptime = time.time() - psutil.boot_time()
    
    # Format uptime roughly
    hours = int(uptime // 3600)
    mins = int((uptime % 3600) // 60)
    
    msg = (
        f"🩺 *System Health*\n\n"
        f"🧠 CPU: {cpu}%\n"
        f"💾 RAM: {ram}%\n"
        f"⏱️ Uptime: ~{hours}h {mins}m"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")
    return states.SUPER_MENU

async def toggle_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_state = not db.maintenance_mode
    if db.set_maintenance(new_state):
        status = "🔴 ENABLED" if new_state else "🟢 DISABLED"
        await update.message.reply_text(f"Maintenance Mode: *{status}*", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Failed to update config.")
    return states.SUPER_MENU

# --- ADMIN MANAGEMENT ---
async def manage_admins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Just show instructions for now to keep simple
    # Or implement full add/remove flow
    lang = get_user_lang(context)
    
    admins = db.cached_sheet_admins
    msg = f"👮 *Secondary Admins ({len(admins)}):*\n" + "\n".join([f"`{a}`" for a in admins])
    msg += "\n\nReply with a Telegram ID to ADD it. Or usage `/remove_admin <id>` to remove."
    
    await update.message.reply_text(msg, parse_mode="Markdown")
    return states.SUPER_MENU

async def exit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    await update.message.reply_text("Superadmin closed.", reply_markup=keyboards.get_main_menu(lang))
    return ConversationHandler.END
