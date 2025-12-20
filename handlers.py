from telegram import Update
from telegram.ext import ConversationHandler, ContextTypes
import strings
import keyboards
import states
from database import db
import logging
import re

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_text(
        strings.WELCOME_MSG.format(name=user.first_name), 
        reply_markup=keyboards.get_main_menu(), 
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        strings.HELP_MSG,
        parse_mode="Markdown",
        reply_markup=keyboards.get_main_menu()
    )

async def check_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        strings.PROMPT_MATRIC,
        parse_mode="Markdown",
        reply_markup=keyboards.get_cancel_menu()
    )
    return states.ASK_MATRIC

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(strings.ERR_CANCEL, reply_markup=keyboards.get_main_menu())
    return ConversationHandler.END

async def receive_matric(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().upper()
    if text == strings.BTN_CANCEL.upper() or text == "CANCEL": return await cancel(update, context)
    
    # Handle "Try Again" - just re-prompt
    if text == strings.BTN_TRY_AGAIN.upper():
        await update.message.reply_text(strings.PROMPT_MATRIC, parse_mode="Markdown", reply_markup=keyboards.get_cancel_menu())
        return states.ASK_MATRIC

    # Handle Main Menu Buttons if they are clicked
    if text == strings.BTN_CHECK.upper(): return await check_start(update, context)
    if text == strings.BTN_HELP.upper(): 
        await help_command(update, context)
        return ConversationHandler.END

    if not re.match(r'^[A-Z0-9]{6,15}$', text):
        await update.message.reply_text(
            strings.ERR_INVALID_MATRIC, 
            parse_mode="Markdown",
            reply_markup=keyboards.get_retry_menu() # Show Retry Menu on error
        )
        return states.ASK_MATRIC
    
    context.user_data['matric'] = text
    await update.message.reply_text(
        strings.PROMPT_IC.format(matric=text),
        parse_mode="Markdown",
        reply_markup=keyboards.get_cancel_menu()
    )
    return states.ASK_IC

async def receive_ic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == strings.BTN_CANCEL or text == "CANCEL": return await cancel(update, context)

    # Handle "Try Again"
    if text == strings.BTN_TRY_AGAIN:
        user_matric = context.user_data.get('matric', 'Unknown')
        await update.message.reply_text(
            strings.PROMPT_IC.format(matric=user_matric),
            parse_mode="Markdown",
            reply_markup=keyboards.get_cancel_menu()
        )
        return states.ASK_IC

    # Handle Main Menu Buttons
    if text == strings.BTN_CHECK: return await check_start(update, context)
    if text == strings.BTN_HELP: 
        await help_command(update, context)
        return ConversationHandler.END

    if not re.match(r'^\d{4}$', text):
        await update.message.reply_text(
            strings.ERR_INVALID_IC, 
            parse_mode="Markdown",
            reply_markup=keyboards.get_retry_menu() # Show Retry Menu on error
        )
        return states.ASK_IC
    
    await update.message.reply_text(strings.PROMPT_LOADING, parse_mode="Markdown")
    
    user_matric = context.user_data['matric']
    user_ic_last4 = text
    
    msg = strings.ERR_DB_CONNECTION
    
    try:
        row_values, _ = db.find_member(user_matric)
        
        if row_values:
            if len(row_values) > 5:
                # Gspread List 0-index values: C=2, E=4, F=5
                db_name = row_values[2] 
                db_ic = str(row_values[4]).strip().replace(" ", "")
                db_prog = row_values[5]
                
                if db_ic.endswith(user_ic_last4):
                    msg = strings.VERIFICATION_SUCCESS.format(
                        name=db_name,
                        matric=user_matric,
                        program=db_prog
                    )
                else:
                    msg = "**Verification Failed**\nMatric found, but IC digits do not match."
            else:
                    msg = "Record found but data is incomplete."
        else:
            msg = strings.ERR_NOT_FOUND
                
    except Exception as e:
        logger.error(e)

    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboards.get_main_menu())
    return ConversationHandler.END
