from telegram import Update
from telegram.ext import ConversationHandler, ContextTypes
import strings
import keyboards
import states
from database import db
import logging

logger = logging.getLogger(__name__)

# Helper to get lang (Admins might use local too)
def get_user_lang(context: ContextTypes.DEFAULT_TYPE):
    return context.user_data.get('lang', strings.DEFAULT_LANG)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    user_id = update.effective_user.id
    if not db.is_admin(user_id):
        await update.message.reply_text(strings.get('ERR_ACCESS_DENIED', lang), parse_mode="Markdown")
        return ConversationHandler.END
    
    await update.message.reply_text(
        strings.get('ADMIN_DASHBOARD', lang), 
        parse_mode="Markdown", 
        reply_markup=keyboards.get_admin_menu(lang)
    )
    return states.ADMIN_MENU

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    try:
        total = db.get_stats()
        await update.message.reply_text(
            strings.get('ADMIN_STATS', lang).format(total=total), 
            parse_mode="Markdown",
            reply_markup=keyboards.get_admin_menu(lang)
        )
    except Exception as e:
        logger.error(e)
        await update.message.reply_text(strings.get('ERR_DB_CONNECTION', lang))
    return states.ADMIN_MENU

# --- ADD MEMBER FLOW ---
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    await update.message.reply_text(strings.get('ADMIN_ADD_MATRIC', lang), parse_mode="Markdown", reply_markup=keyboards.get_cancel_menu(lang))
    return states.ADD_MATRIC

async def add_matric(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    text = update.message.text.strip().upper()
    if text in strings.get_all('BTN_CANCEL') or text == "CANCEL": return await back(update, context)
    
    context.user_data['new_matric'] = text
    await update.message.reply_text(strings.get('ADMIN_ADD_NAME', lang), parse_mode="Markdown", reply_markup=keyboards.get_cancel_menu(lang))
    return states.ADD_NAME

async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    text = update.message.text
    if text in strings.get_all('BTN_CANCEL'): return await back(update, context)
    context.user_data['new_name'] = text.upper()
    await update.message.reply_text(strings.get('ADMIN_ADD_IC', lang), parse_mode="Markdown", reply_markup=keyboards.get_cancel_menu(lang))
    return states.ADD_IC

async def add_ic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    text = update.message.text
    if text in strings.get_all('BTN_CANCEL'): return await back(update, context)
    context.user_data['new_ic'] = text
    await update.message.reply_text(strings.get('ADMIN_ADD_PROG', lang), parse_mode="Markdown", reply_markup=keyboards.get_program_menu(lang))
    return states.ADD_PROG

async def add_prog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    text = update.message.text
    if text in strings.get_all('BTN_CANCEL'): return await back(update, context)
    prog = text.upper()
    
    matric = context.user_data['new_matric']
    name = context.user_data['new_name']
    ic = context.user_data['new_ic']
    
    loading = await update.message.reply_text(strings.get('ADMIN_SAVING', lang), parse_mode="Markdown")
    
    try:
        if db.add_member(name, matric, ic, prog):
            await loading.edit_text(strings.get('ADMIN_ADD_SUCCESS', lang).format(name=name, matric=matric), parse_mode="Markdown")
        else:
             await loading.edit_text(strings.get('ERR_DB_CONNECTION', lang), parse_mode="Markdown")
    except Exception as e:
        logger.error(e)
        await loading.edit_text(strings.get('ERR_DB_CONNECTION', lang), parse_mode="Markdown")
        
    await update.message.reply_text("Returning...", reply_markup=keyboards.get_admin_menu(lang))
    return states.ADMIN_MENU

# --- DELETE MEMBER FLOW ---
async def del_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    await update.message.reply_text(strings.get('ADMIN_DEL_START', lang), parse_mode="Markdown", reply_markup=keyboards.get_cancel_menu(lang))
    return states.DEL_MATRIC

async def del_matric(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    text = update.message.text.strip().upper()
    if text in strings.get_all('BTN_CANCEL') or text == "CANCEL": return await back(update, context)
    
    loading = await update.message.reply_text(strings.get('ADMIN_SEARCHING', lang), parse_mode="Markdown")
    
    try:
        success, row = db.delete_member(text)
        if success:
            await loading.edit_text(strings.get('ADMIN_DEL_SUCCESS', lang).format(row=row), parse_mode="Markdown")
        else:
            await loading.edit_text(strings.get('ADMIN_DEL_NOT_FOUND', lang), parse_mode="Markdown")
    except Exception as e:
        logger.error(e)
        await loading.edit_text(strings.get('ERR_DB_CONNECTION', lang), parse_mode="Markdown")
        
    await update.message.reply_text("Returning...", reply_markup=keyboards.get_admin_menu(lang))
    return states.ADMIN_MENU

async def back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    await update.message.reply_text(strings.get('ERR_CANCEL', lang), reply_markup=keyboards.get_admin_menu(lang))
    return states.ADMIN_MENU

async def exit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    await update.message.reply_text(strings.get('ADMIN_EXIT', lang), reply_markup=keyboards.get_main_menu(lang))
    return ConversationHandler.END
