from telegram import Update
from telegram.ext import ConversationHandler, ContextTypes
import strings
import keyboards
import states
import handlers
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
        # Security: Silent fail for unauthorized users
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
        data = db.get_stats()
        await update.message.reply_text(
            strings.get('ADMIN_STATS', lang).format(
                total=data['total']
            ), 
            parse_mode="Markdown",
            reply_markup=keyboards.get_admin_menu(lang)
        )
    except Exception as e:
        logger.error(e)
        await update.message.reply_text(strings.get('ERR_DB_CONNECTION', lang))
        await update.message.reply_text(strings.get('ERR_DB_CONNECTION', lang))
    return states.ADMIN_MENU

async def check_pending_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Manual check triggered from Admin Menu button."""
    lang = get_user_lang(context)
    await update.message.reply_text("🔎 " + strings.get('ADMIN_SEARCHING', lang)) # Reuse searching text or just 'Checking...'
    
    # Call the logic from handlers
    await handlers.check_registrations(context)
    
    await update.message.reply_text("✅ " + strings.get('BTN_ADMIN_CHECK_PENDING', lang) + " Done.", reply_markup=keyboards.get_admin_menu(lang))
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
            def esc(t): return str(t).replace('_', '\\_').replace('*', '\\*').replace('`', '\\`').replace('[', '\\[')
            for i, row in enumerate(members, 1):
                # row[2]=Name, row[3]=Matric
                name = row[2] if len(row) > 2 else "Unknown"
                matric = row[3] if len(row) > 3 else "Unknown"
                items.append(f"{i}. *{esc(name)}* (`{esc(matric)}`)")
            
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
        strings.get('ADMIN_SEARCH_MODE_PROMPT', lang), 
        parse_mode="Markdown", 
        reply_markup=keyboards.get_search_mode_menu(lang)
    )
    return states.SEARCH_MODE

async def receive_search_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    text = update.message.text.strip()
    
    if text in strings.get_all('BTN_CANCEL') or text == "CANCEL": 
        return await back(update, context)

    # Determine mode
    mode = "simple"
    if text in strings.get_all('BTN_SEARCH_DETAIL'):
        mode = "detail"
    elif text in strings.get_all('BTN_SEARCH_SIMPLE'):
        mode = "simple"
    else:
        # Invalid selection? Just default to simple or ask again.
        # Let's ask again for robustness
        await update.message.reply_text(
            strings.get('ADMIN_SEARCH_MODE_PROMPT', lang), 
            reply_markup=keyboards.get_search_mode_menu(lang)
        )
        return states.SEARCH_MODE
        
    context.user_data['search_mode'] = mode
    
    await update.message.reply_text(
        strings.get('ADMIN_SEARCH_PROMPT', lang),
        parse_mode="Markdown",
        reply_markup=keyboards.get_cancel_menu(lang)
    )
    return states.SEARCH_QUERY

async def search_perform(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    query = update.message.text.strip()
    mode = context.user_data.get('search_mode', 'simple')
    
    if query in strings.get_all('BTN_CANCEL') or query == "CANCEL": 
        return await back(update, context)

    loading = await update.message.reply_text(strings.get('ADMIN_SEARCHING', lang))

    try:
        results = db.search_members(query)
        
        if not results:
            await loading.edit_text(strings.get('ADMIN_SEARCH_EMPTY', lang).format(query=query), parse_mode="Markdown")
        else:
            items = []
            limit = 20 if mode == 'simple' else 5
            
            for i, row in enumerate(results[:limit], 1):
                # row indexes: A=0, B=1, ...
                # C=2 (Name), D=3 (Matric), E=4 (Prog), I=8 (USAS Email), J=9 (IC), N=13 (Date), P=15 (ID), Q=16 (Receipt), R=17 (Status)
                
                name = row[2] if len(row) > 2 else "-"
                matric = row[3] if len(row) > 3 else "-"
                
                if mode == 'simple':
                    prog = row[4] if len(row) > 4 else "-"
                    mem_id = row[15] if len(row) > 15 else "-" # P=15 is Membership ID
                    
                    # Local escape helper (duplicated for scope safety or move it up - moving it up is better but hard with replace tool constraints)
                    # Use simple replace here since function is defined lower down
                    def esc(t): return str(t).replace('_', '\\_').replace('*', '\\*').replace('`', '\\`').replace('[', '\\[')

                    simple_card = (
                        f"{i}.\n"
                        f"🔑 ID: `{esc(mem_id)}`\n"
                        f"👤 *{esc(name)}*\n"
                        f"🆔 `{esc(matric)}`\n"
                        f"🎓 {esc(prog)}"
                    )
                    items.append(simple_card)
                else:

                    def escape_md(text):
                        """Escape special characters for Telegram Markdown (Legacy)"""
                        return str(text).replace('_', '\\_').replace('*', '\\*').replace('`', '\\`').replace('[', '\\[')

                    def safe_get(idx): return escape_md(row[idx] if len(row) > idx else "-")
                    
                    # Special handler for URL to avoid breaking it with escapes
                    raw_receipt = row[18] if len(row) > 18 else "-"
                    receipt_display = f"[Download PDF]({raw_receipt})" if raw_receipt.startswith("http") else escape_md(raw_receipt)

                    detail_card = (
                        f"👤 *{safe_get(2)}*\n" # C Name
                        f"🆔 `{safe_get(3)}`\n" # D Matric
                        f"🎓 Prog: {safe_get(4)} | Sem: {safe_get(5)}\n" # E, F
                        f"📞 {safe_get(6)}\n" # G Phone
                        f"📧 {safe_get(7)}\n" # H Personal Email
                        f"🏫 {safe_get(8)}\n" # I USAS Email
                        f"🪪 IC: {safe_get(9)}\n" # J IC
                        f"🎂 {safe_get(10)} ({safe_get(11)})\n" # K Birthday, L Place
                        f"🏠 {safe_get(12)}\n" # M Address
                        f"📅 Entry: {safe_get(13)}\n" # N Date Entry
                        f"⏱️ Min: {safe_get(14)}\n" # O Minute
                        f"🔑 ID: `{safe_get(15)}`\n" # P Membership ID
                        f"📄 Proof: {safe_get(16)}\n" # Q Receipt Proof (Index 16)
                        f"🧾 Invoice: `{safe_get(19)}`\n" # T Invoice No (Index 19)
                        f"📎 Receipt: {receipt_display}\n" # S Receipt URL (Index 18)
                        f"✅ Status: {safe_get(17)}\n" # R Status
                    )
                    items.append(detail_card)

            msg_text = strings.get('ADMIN_SEARCH_RESULT', lang).format(mode=mode.upper(), query=query, items="\n\n".join(items))
            await loading.edit_text(msg_text, parse_mode="Markdown")

    except Exception as e:
        logger.error(e)
        await loading.edit_text(strings.get('ERR_DB_CONNECTION', lang))
    
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
            db.log_action(update.effective_user.first_name, "DELETE_MEMBER", f"Matric: {text} (Row {row})")
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
    
    final_msg = strings.get('BROADCAST_TITLE', lang).format(msg=msg)
    
    for uid in users:
        try:
            await context.bot.send_message(chat_id=uid, text=final_msg, parse_mode="Markdown")
            success += 1
        except Exception:
            failed += 1
            
    await status_msg.edit_text(
        strings.get('ADMIN_BROADCAST_DONE', lang).format(success=success, failed=failed), 
        parse_mode="Markdown"
    )
    
    db.log_action(update.effective_user.first_name, "BROADCAST", f"Msg: {msg[:30]}... | Success: {success}/{len(users)}")
    
    await update.message.reply_text(strings.get('ADMIN_DASHBOARD', lang), reply_markup=keyboards.get_admin_menu(lang), parse_mode="Markdown")
    return states.ADMIN_MENU

async def exit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    await update.message.reply_text(strings.get('ADMIN_EXIT', lang), reply_markup=keyboards.get_main_menu(lang))
    return ConversationHandler.END
