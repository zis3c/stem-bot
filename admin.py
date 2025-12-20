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

# --- MANAGE MEMBERS MENU ---
async def manage_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    await update.message.reply_text(
        strings.get('BTN_ADMIN_MANAGE', lang), 
        parse_mode="Markdown", 
        reply_markup=keyboards.get_admin_manage_menu(lang)
    )
    return states.ADMIN_MANAGE

async def back_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Used for "Back" button inside Manage Menu
    return await start(update, context)

async def back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Used for "Cancel" inside Add/Del flows -> returns to Manage Menu now
    lang = get_user_lang(context)
    await update.message.reply_text(strings.get('ERR_CANCEL', lang), reply_markup=keyboards.get_admin_manage_menu(lang))
    return states.ADMIN_MANAGE

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

    except Exception as e:
        logger.error(e)
        await loading.edit_text(strings.get('ERR_DB_CONNECTION', lang))

    return states.ADMIN_MANAGE

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
    
    await update.message.reply_text(strings.get('BTN_ADMIN_MANAGE', lang), reply_markup=keyboards.get_admin_manage_menu(lang))
    return states.ADMIN_MANAGE


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
        
    await update.message.reply_text(strings.get('BTN_ADMIN_MANAGE', lang), reply_markup=keyboards.get_admin_manage_menu(lang))
    return states.ADMIN_MANAGE

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
        
    await update.message.reply_text(strings.get('BTN_ADMIN_MANAGE', lang), reply_markup=keyboards.get_admin_manage_menu(lang))
    return states.ADMIN_MANAGE

async def back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    await update.message.reply_text(strings.get('ERR_CANCEL', lang), reply_markup=keyboards.get_admin_menu(lang))
    return states.ADMIN_MENU

# --- BROADCAST FLOW ---
async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    await update.message.reply_text(
        strings.get('ADMIN_BROADCAST_PROMPT', lang), 
        parse_mode="Markdown", 
        reply_markup=keyboards.get_cancel_menu(lang)
    )
    return states.BROADCAST_MSG

async def broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    text = update.message.text
    
    if text in strings.get_all('BTN_CANCEL') or text == "CANCEL": 
        return await back(update, context)

    context.user_data['broadcast_msg'] = text
    
    # Get user count preview
    users = db.get_all_users()
    count = len(users)
    
    await update.message.reply_text(
        strings.get('ADMIN_BROADCAST_CONFIRM', lang).format(msg=text, count=count),
        parse_mode="Markdown",
        reply_markup=keyboards.get_confirm_menu(lang)
    )
    return states.BROADCAST_CONFIRM

async def broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    text = update.message.text
    
    if text in strings.get_all('BTN_CONFIRM_NO'):
        return await back(update, context)
        
    if text not in strings.get_all('BTN_CONFIRM_YES'):
        # Invalid input, ask again or cancel? Let's assume cancel or re-ask.
        # Simplest: cancel
        return await back(update, context)

    msg = context.user_data.get('broadcast_msg')
    if not msg: return await back(update, context)

    status_msg = await update.message.reply_text(strings.get('ADMIN_BROADCAST_START', lang))
    
    users = db.get_all_users()
    success = 0
    failed = 0
    
    for uid in users:
        try:
            await context.bot.send_message(chat_id=uid, text=msg)
            success += 1
        except Exception:
            failed += 1
            
    await status_msg.edit_text(
        strings.get('ADMIN_BROADCAST_DONE', lang).format(success=success, failed=failed), 
        parse_mode="Markdown"
    )
    
    await update.message.reply_text(strings.get('ADMIN_DASHBOARD', lang), reply_markup=keyboards.get_admin_menu(lang), parse_mode="Markdown")
    return states.ADMIN_MENU

async def exit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    await update.message.reply_text(strings.get('ADMIN_EXIT', lang), reply_markup=keyboards.get_main_menu(lang))
    return ConversationHandler.END
