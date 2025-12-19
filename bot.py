import os
import logging
import re
import json
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

# --- CONFIGURATION ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
SHEET_ID = os.getenv("SHEET_ID") # The ID from your Google Sheet URL (d/...)
GOOGLE_JSON = os.getenv("GOOGLE_CREDENTIALS") # The entire JSON content
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
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        # Load credentials from the Environment Variable String
        creds_dict = json.loads(GOOGLE_JSON)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        
        # Open the sheet
        sheet = client.open_by_key(SHEET_ID).sheet1
        return sheet
    except Exception as e:
        logger.error(f"DB Connection Error: {e}")
        return None

# --- FLOW HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("🔍 Check Status", callback_data="check_start")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👋 *Welcome to Eligible STEM, {user.first_name}!*\n\n"
        "I can verify your membership status directly from our database.\n\n"
        "Tap the button to start.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("This bot checks your STEM USAS membership.\nIt runs securely on Render and connects to Google Sheets.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    if query.data == "check_start" or query.data == "retry":
        await query.edit_message_text(
            text="Please enter your **Matric Number**\n(Example: I24107504)",
            parse_mode="Markdown"
        )
        return ASK_MATRIC
    
    if query.data == "help":
        await query.edit_message_text("This bot checks your STEM USAS membership.\nIt runs securely on Render and connects to Google Sheets.")
        return ConversationHandler.END

async def receive_matric(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().upper()
    if not re.match(r'^[A-Z0-9]{6,15}$', text):
        await update.message.reply_text("❌ Invalid format. Please try again (e.g. I24107504).")
        return ASK_MATRIC
    
    context.user_data['matric'] = text
    await update.message.reply_text("✅ OK. Now enter the **Last 4 Digits** of your IC.", parse_mode="Markdown")
    return ASK_IC

async def receive_ic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not re.match(r'^\d{4}$', text):
        await update.message.reply_text("❌ Invalid format. Please enter exactly 4 digits.")
        return ASK_IC
    
    context.user_data['ic'] = text
    await update.message.reply_text("🔄 Checking database...")
    
    user_matric = context.user_data['matric']
    user_ic_last4 = text
    
    # --- QUERY GOOGLE SHEETS via gspread ---
    msg = "⚠️ System Error: Database unavailable."
    
    try:
        sheet = get_sheet_db()
        if sheet:
            # Get only required columns to save quota/time. 
            # Assuming C=Name(3), D=Matric(4), E=IC(5), F=Program(6)
            # Fetch all records (List of Dicts if headers exist, or List of Lists)
            # For simplicity, we get all values. For High Performance with 10k+ rows, we cache this.
            
            # Using find() is efficient for Matric search
            cell = sheet.find(user_matric, in_column=4) # Column D=4
            
            if cell:
                # Found Matric! Now check IC.
                row_num = cell.row
                # Get Name(Col 2 in 0-index? No, gspread uses 1-index)
                # We need C(3), E(5), F(6)
                # Batch get the row
                row_values = sheet.row_values(row_num)
                # row_values index: 0=A, 1=B, 2=C(Name), 3=D(Matric), 4=E(IC), 5=F(Program)
                
                db_name = row_values[2] # Col C
                db_ic = str(row_values[4]).strip().replace(" ", "") # Col E
                db_prog = row_values[5] # Col F
                
                if db_ic.endswith(user_ic_last4):
                    msg = (
                        "✅ **VERIFIED MEMBER**\n\n"
                        f"👤 Name: `{db_name}`\n"
                        f"🎓 Program: `{db_prog}`\n"
                        "✨ Status: **Active**"
                    )
                else:
                    msg = "❌ **Verification Failed**\nMatric found, but IC does not match."
            else:
                msg = "❌ **Not Found**\nDetails do not match our records."
                
    except Exception as e:
        logger.error(e)
        msg = "⚠️ Connection Error to Google Sheets."

    keyboard = [[InlineKeyboardButton("🔄 Check Another", callback_data="retry")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=reply_markup)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END

# --- WEBHOOK ---
async def main():
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern='^check_start$')],
        states={
            ASK_MATRIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_matric)],
            ASK_IC: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ic)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(button_handler, pattern='^retry$'))
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
