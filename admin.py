from telegram import Update
from telegram.ext import ConversationHandler, ContextTypes
import strings
import keyboards
import states
from database import db
import logging

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if not db.is_admin(user_id):
        await update.message.reply_text(strings.ERR_ACCESS_DENIED, parse_mode="Markdown")
        return ConversationHandler.END
    
    await update.message.reply_text(
        strings.ADMIN_DASHBOARD, 
        parse_mode="Markdown", 
        reply_markup=keyboards.get_admin_menu()
    )
    return states.ADMIN_MENU

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        total = db.get_stats()
        await update.message.reply_text(
            strings.ADMIN_STATS.format(total=total), 
            parse_mode="Markdown",
            reply_markup=keyboards.get_admin_menu()
        )
    except Exception as e:
        logger.error(e)
        await update.message.reply_text(strings.ERR_DB_CONNECTION)
    return states.ADMIN_MENU

# --- ADD MEMBER FLOW ---
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(strings.ADMIN_ADD_MATRIC, parse_mode="Markdown", reply_markup=keyboards.get_cancel_menu())
    return states.ADD_MATRIC

async def add_matric(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().upper()
    if text == strings.BTN_CANCEL or text == "CANCEL": return await back(update, context)
    
    context.user_data['new_matric'] = text
    await update.message.reply_text(strings.ADMIN_ADD_NAME, parse_mode="Markdown", reply_markup=keyboards.get_cancel_menu())
    return states.ADD_NAME

async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == strings.BTN_CANCEL: return await back(update, context)
    context.user_data['new_name'] = update.message.text.upper()
    await update.message.reply_text(strings.ADMIN_ADD_IC, parse_mode="Markdown", reply_markup=keyboards.get_cancel_menu())
    return states.ADD_IC

async def add_ic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == strings.BTN_CANCEL: return await back(update, context)
    context.user_data['new_ic'] = update.message.text
    await update.message.reply_text(strings.ADMIN_ADD_PROG, parse_mode="Markdown", reply_markup=keyboards.get_cancel_menu())
    return states.ADD_PROG

async def add_prog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == strings.BTN_CANCEL: return await back(update, context)
    prog = update.message.text.upper()
    
    matric = context.user_data['new_matric']
    name = context.user_data['new_name']
    ic = context.user_data['new_ic']
    
    loading = await update.message.reply_text(strings.ADMIN_SAVING, parse_mode="Markdown")
    
    try:
        if db.add_member(name, matric, ic, prog):
            await loading.edit_text(strings.ADMIN_ADD_SUCCESS.format(name=name, matric=matric), parse_mode="Markdown")
        else:
             await loading.edit_text(strings.ERR_DB_CONNECTION, parse_mode="Markdown")
    except Exception as e:
        logger.error(e)
        await loading.edit_text(strings.ERR_DB_CONNECTION, parse_mode="Markdown")
        
    await update.message.reply_text("Returning to dashboard...", reply_markup=keyboards.get_admin_menu())
    return states.ADMIN_MENU

# --- DELETE MEMBER FLOW ---
async def del_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(strings.ADMIN_DEL_START, parse_mode="Markdown", reply_markup=keyboards.get_cancel_menu())
    return states.DEL_MATRIC

async def del_matric(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().upper()
    if text == strings.BTN_CANCEL or text == "CANCEL": return await back(update, context)
    
    loading = await update.message.reply_text(strings.ADMIN_SEARCHING, parse_mode="Markdown")
    
    try:
        success, row = db.delete_member(text)
        if success:
            await loading.edit_text(strings.ADMIN_DEL_SUCCESS.format(row=row), parse_mode="Markdown")
        else:
            await loading.edit_text(strings.ADMIN_DEL_NOT_FOUND, parse_mode="Markdown")
    except Exception as e:
        logger.error(e)
        await loading.edit_text(strings.ERR_DB_CONNECTION, parse_mode="Markdown")
        
    await update.message.reply_text("Returning to dashboard...", reply_markup=keyboards.get_admin_menu())
    return states.ADMIN_MENU

async def back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("🔙 Cancelled.", reply_markup=keyboards.get_admin_menu())
    return states.ADMIN_MENU

async def exit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(strings.ADMIN_EXIT, reply_markup=keyboards.get_main_menu())
    return ConversationHandler.END
