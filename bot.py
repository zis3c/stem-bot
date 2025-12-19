import os
import logging
import re
import json
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from aiohttp import web
import traceback

# --- CONFIGURATION ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
SHEET_ID = os.getenv("SHEET_ID")
GOOGLE_JSON = os.getenv("GOOGLE_CREDENTIALS")
PORT = int(os.getenv("PORT", 10000))
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL")

# States
ASK_MATRIC, ASK_IC = range(2)

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- GSPREAD SETUP ---
def get_sheet_db():
    try:
        if not GOOGLE_JSON:
            logger.error("❌ CRITICAL: GOOGLE_CREDENTIALS Env Var is missing or empty!")
            return None
            
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        try:
            creds_dict = json.loads(GOOGLE_JSON)
        except json.JSONDecodeError as je:
             logger.error(f"❌ JSON Decode Error: {je}")
             return None
             
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_ID).sheet1
        return sheet
    except Exception as e:
        logger.error(f"DB Connection Error: {e}")
        logger.error(traceback.format_exc())
        return None

# --- UI HELPERS ---
def get_cancel_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel")]])

async def safe_delete(update: Update):
    """safely delete the user's message to keep chat clean"""
    try:
        if update.message:
            await update.message.delete()
    except Exception:
        pass

# --- FLOW HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("🔍 Check Membership", callback_data="check_start")],
        [InlineKeyboardButton("ℹ️ Help / Info", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        f"👋 *Hi {user.first_name}!*\n\n"
        "I am the **Eligible STEM Bot**.\n"
        "I can verify your membership status instantly.\n\n"
        "👇 Tap below to begin."
    )
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    if query.data == "check_start" or query.data == "retry":
        await query.edit_message_text(
            text="Step 1/2\n\n📌 Please type your **Matric Number**:\n(Example: `I24107504`)",
            parse_mode="Markdown",
            reply_markup=get_cancel_keyboard()
        )
        return ASK_MATRIC
    
    if query.data == "help":
        await query.edit_message_text(
            "ℹ️ **About This Bot**\n\n"
            "This service checks the STEM USAS membership database.\n"
            "It is connected to the official Google Sheet records.\n\n"
            "Developed securely on Render.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="start")]])
        )
        return ConversationHandler.END

    if query.data == "start":
        await start(update, context)
        return ConversationHandler.END

    if query.data == "cancel":
        await query.edit_message_text("❌ Operation Cancelled.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="start")]]))
        return ConversationHandler.END

async def receive_matric(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().upper()
    await safe_delete(update) # Delete user's message to keep chat clean
    
    # Validation
    if not re.match(r'^[A-Z0-9]{6,15}$', text):
        # We need to find the bot's last message to edit it. 
        # Since we can't easily track the message ID without DB, we'll send a new temp message or just reply.
        # Simple approach: Reply then delete.
        msg = await update.message.reply_text("⚠️ **Invalid Matric Format!**\nPlease try again (e.g. `I24107504`).", parse_mode="Markdown")
        # Ensure we don't get stuck, just ask again.
        return ASK_MATRIC
    
    context.user_data['matric'] = text
    
    # Move to next step (Send new message because we deleted the user's input, flow looks cleaner)
    await update.message.reply_text(
        f"✅ Matric: `{text}`\n\nStep 2/2\n🔑 Now enter the **Last 4 Digits** of your IC:",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    return ASK_IC

async def receive_ic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    await safe_delete(update)
    
    if not re.match(r'^\d{4}$', text):
        await update.message.reply_text("⚠️ **Invalid IC!**\nPlease enter exactly 4 digits.", parse_mode="Markdown")
        return ASK_IC
    
    # Loading State
    loading_msg = await update.message.reply_text("🔄 **Verifying with Database...**", parse_mode="Markdown")
    
    user_matric = context.user_data['matric']
    user_ic_last4 = text
    
    # --- DB CALL ---
    msg = "⚠️ System Error: Database unavailable."
    success = False
    
    try:
        sheet = get_sheet_db()
        if sheet:
            cell = sheet.find(user_matric, in_column=4) # Col D
            
            if cell:
                row_values = sheet.row_values(cell.row)
                # 0=A, 1=B, 2=C(Name), 3=D(Matric), 4=E(IC), 5=F(Program)
                
                # Safety check for row length
                if len(row_values) > 5:
                    db_name = row_values[2] # Col C
                    db_ic = str(row_values[4]).strip().replace(" ", "") # Col E
                    db_prog = row_values[5] # Col F
                    
                    if db_ic.endswith(user_ic_last4):
                        msg = (
                            "🎉 **MEMBERSHIP VERIFIED** 🎉\n\n"
                            f"👤 **Name:** {db_name}\n"
                            f"🆔 **Matric:** `{user_matric}`\n"
                            f"🎓 **Program:** {db_prog}\n\n"
                            "✅ **Status: ACTIVE**"
                        )
                        success = True
                    else:
                        msg = "❌ **Verification Failed**\nMatric found, but IC digits do not match."
                else:
                     msg = "⚠️ Record found but data is incomplete."
            else:
                msg = "❌ **Not Found**\nWe could not find that Matric Number in our records."
                
    except Exception as e:
        logger.error(e)
        msg = f"⚠️ Server Error. Please contact admin."

    # Final Result
    keyboard = []
    if not success:
        keyboard.append([InlineKeyboardButton("🔄 Try Again", callback_data="retry")])
    keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data="start")])
    
    await loading_msg.edit_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Cancelled.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Menu", callback_data="start")]]))
    return ConversationHandler.END

# --- WEBHOOK ---
async def main():
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern='^check_start$|^retry$')],
        states={
            ASK_MATRIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_matric)],
            ASK_IC: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ic)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(button_handler, pattern='^cancel$')
        ],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", button_handler)) # redirects to button logic
    application.add_handler(CallbackQueryHandler(button_handler, pattern='^start$|^help$'))
    application.add_handler(conv_handler)
    
    webhook_path = f"{WEBHOOK_URL}/telegram"
    await application.bot.set_webhook(webhook_path)

    async def telegram_webhook(request):
        update_data = await request.json()
        await application.process_update(Update.de_json(update_data, application.bot))
        return web.Response(text="OK")

    async def health(request): return web.Response(text="Alive")

    app = web.Application()
    app.router.add_post("/telegram", telegram_webhook)
    app.router.add_get("/", health)
    
    await application.initialize()
    await application.start()
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    
    import asyncio
    while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    import asyncio
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
