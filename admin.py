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

# --- LIST MEMBERS ---
async def list_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    loading = await update.message.reply_text(strings.get('ADMIN_SEARCHING', lang))
    
    try:
        members = db.get_members(limit=30) # Safe limit for message size
        
        if not members:
            await loading.edit_text(strings.get('ADMIN_LIST_EMPTY', lang), parse_mode="Markdown")
        else:
            items = []
            for i, row in enumerate(members, 1):
                # row[2]=Name, row[3]=Matric
                name = row[2] if len(row) > 2 else "Unknown"
                matric = row[3] if len(row) > 3 else "Unknown"
                items.append(f"{i}. *{name}* (`{matric}`)")
            
            msg_text = strings.get('ADMIN_LIST_HEADER', lang).format(limit=len(members), items="\n\n".join(items))
            await loading.edit_text(msg_text, parse_mode="Markdown")

    except Exception as e:
        logger.error(e)
        await loading.edit_text(strings.get('ERR_DB_CONNECTION', lang))

    return states.ADMIN_MENU

# --- SEARCH MEMBERS ---
async def search_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    await update.message.reply_text(
        strings.get('ADMIN_SEARCH_PROMPT', lang), 
        parse_mode="Markdown", 
        reply_markup=keyboards.get_cancel_menu(lang)
    )
    return states.SEARCH_QUERY

async def search_perform(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    query = update.message.text.strip()
    
    if query in strings.get_all('BTN_CANCEL') or query == "CANCEL": 
        return await back(update, context)

    loading = await update.message.reply_text(strings.get('ADMIN_SEARCHING', lang))

    try:
        results = db.search_members(query)
        
        if not results:
            await loading.edit_text(strings.get('ADMIN_SEARCH_EMPTY', lang).format(query=query), parse_mode="Markdown")
        else:
            items = []
            # Limit results to avoid overflow if query is too broad
            for i, row in enumerate(results[:20], 1):
                name = row[2] if len(row) > 2 else "Unknown"
                matric = row[3] if len(row) > 3 else "Unknown"
                prog = row[5] if len(row) > 5 else ""
                items.append(f"{i}. *{name}* (`{matric}`) - {prog}")

            msg_text = strings.get('ADMIN_SEARCH_RESULT', lang).format(query=query, items="\n\n".join(items))
            await loading.edit_text(msg_text, parse_mode="Markdown")

    except Exception as e:
        logger.error(e)
        await loading.edit_text(strings.get('ERR_DB_CONNECTION', lang))
    
    await update.message.reply_text("Returning...", reply_markup=keyboards.get_admin_menu(lang))
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
