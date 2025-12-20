from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ConversationHandler, ContextTypes
import strings
import keyboards
import states
from database import db
import logging
import re

logger = logging.getLogger(__name__)

# --- HELPERS ---
def get_user_lang(context: ContextTypes.DEFAULT_TYPE):
    """Retrieve user language, default to EN."""
    return context.user_data.get('lang', strings.DEFAULT_LANG)

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
    # Log user for broadcast
    try:
        db.log_user(user.id, user.first_name)
    except Exception as e:
        logger.error(f"Log user fail: {e}")

    await update.message.reply_text(
        strings.get('WELCOME_MSG', lang).format(name=user.first_name), 
        reply_markup=keyboards.get_main_menu(lang), 
        parse_mode="Markdown"
    )
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

async def set_lang_en(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['lang'] = 'EN'
    # Return to Settings Menu to show context
    await update.message.reply_text(
        strings.get('MSG_LANG_CHANGED', 'EN'),
        reply_markup=keyboards.get_settings_menu('EN')
    )
    return ConversationHandler.END

async def set_lang_ms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['lang'] = 'MS'
    # Return to Settings Menu to show context
    await update.message.reply_text(
        strings.get('MSG_LANG_CHANGED', 'MS'),
        reply_markup=keyboards.get_settings_menu('MS')
    )
    return ConversationHandler.END

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    # Clear everything EXCEPT the language setting
    current_lang = context.user_data.get('lang', 'EN')
    context.user_data.clear()
    context.user_data['lang'] = current_lang
    
    await update.message.reply_text(strings.get('MSG_HISTORY_CLEARED', lang))
    return await start(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    await update.message.reply_text(
        strings.get('HELP_MSG', lang),
        parse_mode="Markdown",
        reply_markup=keyboards.get_main_menu(lang)
    )
    return ConversationHandler.END

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
    
    loading_msg = await update.message.reply_text(strings.get('PROMPT_LOADING', lang), parse_mode="Markdown")
    
    user_matric = context.user_data['matric']
    user_ic_last4 = text
    msg = strings.get('ERR_DB_CONNECTION', lang)
    
    try:
        row_values, _ = db.find_member(user_matric)
        
        if row_values:
            if len(row_values) > 5:
                # Gspread List 0-index values: A=0(Timestamp), C=2(Name), E=4(IC), F=5(Program)
                db_timestamp = row_values[0]
                db_name = row_values[2] 
                db_ic = str(row_values[4]).strip().replace(" ", "")
                db_prog = row_values[5]
                # Col I (index 8) is Status
                db_status = str(row_values[8]).strip().title() if len(row_values) > 8 else "Approved" # Default to Approved if missing (legacy data)
                
                if db_ic.endswith(user_ic_last4):
                    if db_status == "Approved" or db_status not in ["Pending", "Rejected", "Approve", "Reject"]: 
                         # Treating anything NOT explicitly Pending/Rejected as Approved for backward compat
                        msg = strings.get('VERIFICATION_SUCCESS', lang).format(
                            name=db_name,
                            matric=user_matric,
                            program=db_prog,
                            timestamp=db_timestamp
                        )
                    elif db_status == "Pending":
                        msg = strings.get('STATUS_PENDING', lang)
                    elif db_status == "Rejected":
                         msg = strings.get('STATUS_REJECT', lang)
                    else:
                         msg = strings.get('STATUS_PENDING', lang) # Fallback
                else:
                     # Specific localized error construction if needed, or simple string
                     msg = "*Verification Failed*\nMatric found, but IC digits do not match." 
                     if lang == 'MS': msg = "*Pengesahan Gagal*\nMatrik dijumpai, tetapi digit IC tidak sepadan."
            else:
                    msg = "Record found but data is incomplete."
                    if lang == 'MS': msg = "Rekod dijumpai tetapi data tidak lengkap."
        else:
            msg = strings.get('ERR_NOT_FOUND', lang)
                
    except Exception as e:
        logger.error(e)

    # AUTO DELETE LOADING MESSAGE
    try:
        await loading_msg.delete()
    except Exception:
        pass 

    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboards.get_main_menu(lang))
    return ConversationHandler.END

# --- JOB QUEUE & CALLBACKS ---
async def check_registrations(context: ContextTypes.DEFAULT_TYPE):
    """Job to check for new unprocessed registrations."""
    try:
        new_regs = db.get_unprocessed_registrations()
        if not new_regs: return
        
        # Notify Admins
        for reg in new_regs:
            row_idx = reg['row']
            data = reg['data']
            # Data: 0=Timestamp, 2=Name, 3=Matric, 7=Resit
            name = data[2]
            matric = data[3]
            resit = data[7]
            
            # Immediately mark Pending to avoid double notification on next poll
            db.update_status(row_idx, "Pending")
            
            # Send to all admins
            admin_ids = db.admin_ids
            buttons = [
                [
                    InlineKeyboardButton(strings.get('BTN_APPROVE', 'EN'), callback_data=f"approve_{row_idx}"),
                    InlineKeyboardButton(strings.get('BTN_REJECT', 'EN'), callback_data=f"reject_{row_idx}")
                ]
            ]
            markup = InlineKeyboardMarkup(buttons)
            text = strings.get('NOTIFY_NEW_REG', 'EN').format(name=name, matric=matric, resit=resit)
            
            for admin_id in admin_ids:
                try:
                    await context.bot.send_message(chat_id=admin_id, text=text, reply_markup=markup, parse_mode="Markdown")
                except Exception as e:
                    logger.error(f"Failed to notify admin {admin_id}: {e}")
                    
    except Exception as e:
        logger.error(f"Check Job Error: {e}")

async def handle_approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Approve/Reject inline buttons."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if not db.is_admin(user_id):
        await query.message.reply_text("Access Denied.")
        return

    data = query.data
    action, row_idx = data.split("_")
    row_idx = int(row_idx)
    
    status = "Approved" if action == "approve" else "Rejected"
    
    # Update DB
    if db.update_status(row_idx, status):
        # Update Message
        text_lines = query.message.text.split('\n')
        name_line = next((line for line in text_lines if "Name:" in line or "Nama:" in line), "User")
        name = name_line.split(":", 1)[1].strip() if ":" in name_line else "User"
        
        result_msg = strings.get('MSG_APPROVED' if status == "Approved" else 'MSG_REJECTED', 'EN').format(name=name)
        await query.edit_message_text(f"{query.message.text}\n\n{result_msg}")
    else:
        await query.edit_message_text(f"{query.message.text}\n\n❌ Database Error.")
