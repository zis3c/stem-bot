from telegram import Update
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
    if text in strings.get_all('BTN_BACK'): return await start(update, context)
    return None

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.setdefault('lang', strings.DEFAULT_LANG) # Init lang if missing
    lang = get_user_lang(context)
    
    user = update.effective_user
    await update.message.reply_text(
        strings.get('WELCOME_MSG', lang).format(name=user.first_name), 
        reply_markup=keyboards.get_main_menu(lang), 
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_lang(context)
    await update.message.reply_text(
        strings.get('MSG_SELECT_LANG', lang), # Refactored header
        parse_mode="Markdown",
        reply_markup=keyboards.get_settings_menu(lang)
    )
    return ConversationHandler.END

async def set_lang_en(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['lang'] = 'EN'
    await update.message.reply_text(strings.get('MSG_LANG_CHANGED', 'EN'))
    return await start(update, context)

async def set_lang_ms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['lang'] = 'MS'
    await update.message.reply_text(strings.get('MSG_LANG_CHANGED', 'MS'))
    return await start(update, context)

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
                # Gspread List 0-index values: C=2, E=4, F=5
                db_name = row_values[2] 
                db_ic = str(row_values[4]).strip().replace(" ", "")
                db_prog = row_values[5]
                
                if db_ic.endswith(user_ic_last4):
                    msg = strings.get('VERIFICATION_SUCCESS', lang).format(
                        name=db_name,
                        matric=user_matric,
                        program=db_prog
                    )
                else:
                    # Specific localized error construction if needed, or simple string
                    msg = "*Verification Failed*\nMatric found, but IC digits do not match." 
                    # Ideally this should be in strings.py too, but for speed keeping logic here
                    # FIX: Making it properly localized manually or just English logic for now
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
