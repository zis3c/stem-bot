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
        [strings.get('BTN_SA_MAINTENANCE', lang), strings.get('BTN_SA_REFRESH', lang)],
        [strings.get('BTN_SA_ADMINS', lang), strings.get('BTN_SA_HEALTH', lang)],
        [strings.get('BTN_SA_EXIT', lang)]
    ], resize_keyboard=True)

# --- START ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    is_sa = db.is_superadmin(user_id)
    logger.info(f"DEBUG: /superadmin attempt by {user_id}. Is SA? {is_sa}. SA List: {db.superadmin_ids}")
    
    if not is_sa: return ConversationHandler.END # Silent fail for non-superadmins
    
    # Sync config fresh (now cached)
    db.refresh_system_config()
    
    lang = get_user_lang(context)
    status = "ON" if db.maintenance_mode else "OFF"
    
    await update.message.reply_text(
        f"*Superadmin Dashboard*\n\nMaintenance Mode: {status}",
        parse_mode="Markdown",
        reply_markup=get_super_menu(lang)
    )
    return states.SUPER_MENU

# --- FEATURES ---
async def refresh_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db.refresh_system_config(force=True)
    lang = get_user_lang(context)
    await update.message.reply_text(strings.get('MSG_CONFIG_REFRESHED', lang), parse_mode="Markdown")
    return states.SUPER_MENU

async def check_health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    uptime = time.time() - psutil.boot_time()
    
    # Format uptime roughly
    hours = int(uptime // 3600)
    mins = int((uptime % 3600) // 60)
    
    msg = (
        f"*System Health*\n\n"
        f"CPU: {cpu}%\n"
        f"RAM: {ram}%\n"
        f"Uptime: ~{hours}h {mins}m"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")
    return states.SUPER_MENU

async def toggle_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_state = not db.maintenance_mode
    if db.set_maintenance(new_state):
        status = "ENABLED" if new_state else "DISABLED"
        await update.message.reply_text(f"Maintenance Mode: *{status}*", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Failed to update config.")
    return states.SUPER_MENU

# --- ADMIN MANAGEMENT ---
# --- MENUS ---
def get_manage_admins_menu(lang='EN'):
    return ReplyKeyboardMarkup([
        [strings.get('BTN_SA_ADD_ADMIN', lang), strings.get('BTN_SA_DEL_ADMIN', lang)],
        [strings.get('BTN_SA_LIST_ADMIN', lang)],
        [strings.get('BTN_BACK', lang)]
    ], resize_keyboard=True)

# --- ADMIN MANAGEMENT ---
async def manage_admins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    await update.message.reply_text(
        strings.get('BTN_SA_ADMINS', lang), # Use button label as title
        reply_markup=get_manage_admins_menu(lang)
    )
    return states.SUPER_ADMIN_MANAGE

# --- SUBMENU ACTIONS ---
async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    admins = db.cached_sheet_admins
    
    if not admins:
        msg = "No secondary admins found."
    else:
        msg = f"*Secondary Admins ({len(admins)}):*\n" + "\n".join([f"`{a}`" for a in admins])
        
    await update.message.reply_text(msg, parse_mode="Markdown")
    return states.SUPER_ADMIN_MANAGE

async def add_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    await update.message.reply_text(
        strings.get('PROMPT_SA_ADD', lang),
        parse_mode="Markdown",
        reply_markup=keyboards.get_cancel_menu(lang)
    )
    return states.SUPER_ADD_ID

async def add_admin_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    text = update.message.text.strip()
    
    if not text.isdigit():
        await update.message.reply_text(strings.get('ERR_SA_INVALID_ID', lang))
        return states.SUPER_ADD_ID
        
    user_id = int(text)
    # Add to sheet
    if db.add_admin(user_id, "Unknown", f"SA:{update.effective_user.id}"):
        await update.message.reply_text(strings.get('MSG_SA_ADDED', lang), reply_markup=get_manage_admins_menu(lang))
        return states.SUPER_ADMIN_MANAGE
    else:
        await update.message.reply_text("❌ DB Error", reply_markup=get_manage_admins_menu(lang))
        return states.SUPER_ADMIN_MANAGE

async def del_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    await update.message.reply_text(
        strings.get('PROMPT_SA_DEL', lang),
        parse_mode="Markdown",
        reply_markup=keyboards.get_cancel_menu(lang)
    )
    return states.SUPER_DEL_ID

async def del_admin_perform(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    text = update.message.text.strip()
    
    if not text.isdigit():
        await update.message.reply_text(strings.get('ERR_SA_INVALID_ID', lang))
        return states.SUPER_DEL_ID
        
    user_id = int(text)
    if db.remove_admin(user_id):
        await update.message.reply_text(strings.get('MSG_SA_DELETED', lang), reply_markup=get_manage_admins_menu(lang))
    else:
        await update.message.reply_text("❌ Not found or Error", reply_markup=get_manage_admins_menu(lang))
        
    return states.SUPER_ADMIN_MANAGE

async def back_to_manage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    await update.message.reply_text(
        strings.get('ERR_CANCEL', lang),
        reply_markup=get_manage_admins_menu(lang)
    )
    return states.SUPER_ADMIN_MANAGE

async def back_to_super(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    await update.message.reply_text(
        "🔙 Superadmin Dashboard",
        reply_markup=get_super_menu(lang)
    )
    return states.SUPER_MENU

async def exit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    await update.message.reply_text("Superadmin closed.", reply_markup=keyboards.get_main_menu(lang))
    return ConversationHandler.END
