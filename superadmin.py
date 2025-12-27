from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ConversationHandler, ContextTypes
import strings
import keyboards
import states
from database import db
import psutil
import time
import logging
import asyncio

logger = logging.getLogger(__name__)

# --- HELPERS ---
def get_user_lang(context: ContextTypes.DEFAULT_TYPE):
    return context.user_data.get('lang', strings.DEFAULT_LANG)

def get_super_menu(lang='EN'):
    return ReplyKeyboardMarkup([
        [strings.get('BTN_SA_MAINTENANCE', lang), strings.get('BTN_SA_REFRESH', lang)],
        [strings.get('BTN_SA_ADMINS', lang), strings.get('BTN_SA_HEALTH', lang)],
        [strings.get('BTN_SA_LOGS', lang)],
        [strings.get('BTN_SA_EXIT', lang)]
    ], resize_keyboard=True)

# --- START ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    is_sa = db.is_superadmin(user_id)
    logger.info(f"DEBUG: /superadmin attempt by {user_id}. Is SA? {is_sa}. SA List: {db.superadmin_ids}")
    
    if not is_sa: 
        # Security: Silent fail for non-superadmins
        return ConversationHandler.END
    
    # Sync config in background so UI pops immediately
    # We rely on cache for immediate display. The refresh happens for NEXT time.
    # Or we can await loop.run_in_executor(None, db.refresh_system_config) 
    # But even that awaits. 
    # FASTEST: Just trigger it and don't wait. Or trust the background job.
    # Let's trust cache. If it's stale, it updates in background.
    # For now, let's just make it non-blocking fire-and-forget style or short timeout?
    # Actually, asyncio.to_thread is good for Py3.9+.
    # Since we want speed, let's skip the forced refresh here and rely on the background job?
    # But we don't have a background job for config refresh yet (only check_registrations).
    # Let's add loop.run_in_executor.
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, db.refresh_system_config)
    
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
        f"CPU: *{cpu}%*\n"
        f"RAM: *{ram}%*\n"
        f"Uptime: ~*{hours}h* *{mins}m*"
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

async def view_logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        await update.message.reply_document(
            document=open("admin_actions.log", "rb"),
            filename="admin_actions.log"
        )
    except FileNotFoundError:
        await update.message.reply_text("📂 Log file is empty or missing.")
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("❌ Error reading logs.")
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
        await update.message.reply_text(strings.get('ERR_SA_INVALID_ID', lang), parse_mode="Markdown")
        return states.SUPER_ADD_ID
        
    user_id = int(text)
    
    # Check if already admin
    if db.is_admin(user_id):
        await update.message.reply_text(
            strings.get('ERR_SA_ALREADY_ADMIN', lang),
            parse_mode="Markdown",
            reply_markup=get_manage_admins_menu(lang)
        )
        return states.SUPER_ADMIN_MANAGE

    # Add to sheet
    if db.add_admin(user_id, "Unknown", f"SA:{update.effective_user.id}"):
        await update.message.reply_text(strings.get('MSG_SA_ADDED', lang), parse_mode="Markdown", reply_markup=get_manage_admins_menu(lang))
        
        # Notify the new admin
        try:
            await context.bot.send_message(
                chat_id=user_id, 
                text=strings.get('MSG_SA_PROMOTED', lang),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Failed to notify new admin {user_id}: {e}")
            
        db.log_action(update.effective_user.first_name, "ADD_ADMIN", f"Promoted User {user_id}")
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
        await update.message.reply_text(strings.get('ERR_SA_INVALID_ID', lang), parse_mode="Markdown")
        return states.SUPER_DEL_ID
        
    user_id = int(text)
    if db.remove_admin(user_id):
        db.log_action(update.effective_user.first_name, "REMOVE_ADMIN", f"Demoted User {user_id}")
        await update.message.reply_text(strings.get('MSG_SA_DELETED', lang), parse_mode="Markdown", reply_markup=get_manage_admins_menu(lang))
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
