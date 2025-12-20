import os
import logging
import re
import json
import asyncio
import gspread
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from aiohttp import web, ClientSession
import traceback

# --- CONFIGURATION ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
SHEET_ID = os.getenv("SHEET_ID")
GOOGLE_JSON = os.getenv("GOOGLE_CREDENTIALS")
PORT = int(os.getenv("PORT", 10000))
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL")
ADMIN_IDS = set()

# Parse Admin IDs
raw_admins = os.getenv("ADMIN_IDS", "")
if raw_admins:
    try:
        ADMIN_IDS = {int(x.strip()) for x in raw_admins.split(",") if x.strip()}
    except ValueError:
        print("⚠️ Error parsing ADMIN_IDS")

# States - User
ASK_MATRIC, ASK_IC = range(2)

# States - Admin
ADMIN_MENU = 10
ADD_MATRIC, ADD_NAME, ADD_IC, ADD_PROG = range(11, 15)
DEL_MATRIC = 16

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

# --- UI CONSTANTS ---
BTN_CHECK = "🔍 Check Membership"
BTN_HELP = "ℹ️ Help / Info"
BTN_CANCEL = "❌ Cancel"
BTN_MENU = "🔙 Main Menu"

# Admin Buttons
BTN_ADMIN_ADD = "➕ Add Member"
BTN_ADMIN_DEL = "🗑️ Delete Member"
BTN_ADMIN_STATS = "📊 Stats"
BTN_ADMIN_EXIT = "🔙 Exit Admin"

# --- UI HELPERS ---
def get_main_menu():
    return ReplyKeyboardMarkup(
        [[BTN_CHECK, BTN_HELP]], 
        resize_keyboard=True
    )

def get_cancel_menu():
    return ReplyKeyboardMarkup(
        [[BTN_CANCEL]], 
        resize_keyboard=True, 
        one_time_keyboard=True
    )

def get_admin_menu():
    return ReplyKeyboardMarkup(
        [
            [BTN_ADMIN_ADD, BTN_ADMIN_DEL],
            [BTN_ADMIN_STATS, BTN_ADMIN_EXIT]
        ],
        resize_keyboard=True
    )

# --- USER FLOW ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    text = (
        f"👋 *Hi {user.first_name}!*\n\n"
        "I am the **Eligible STEM Bot**.\n"
        "I can verify your membership status instantly.\n\n"
        "👇 *Use the menu below to begin.*"
    )
    await update.message.reply_text(text, reply_markup=get_main_menu(), parse_mode="Markdown")

async def check_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Step 1/2\n\n📌 Please type your **Matric Number**:\n(Example: `I24107504`)",
        parse_mode="Markdown",
        reply_markup=get_cancel_menu()
    )
    return ASK_MATRIC

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "ℹ️ **About This Bot**\n\n"
        "This service checks the STEM USAS membership database.\n"
        "It connects securely to the official records.\n\n"
        "👨‍💻 Dev: @zis3c",
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Operation Cancelled.", reply_markup=get_main_menu())
    return ConversationHandler.END

async def receive_matric(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().upper()
    if text == BTN_CANCEL.upper() or text == "CANCEL": return await cancel(update, context)

    if not re.match(r'^[A-Z0-9]{6,15}$', text):
        await update.message.reply_text(
            "⚠️ **Invalid Matric Format!**\nPlease try again (e.g. `I24107504`)", 
            parse_mode="Markdown",
            reply_markup=get_cancel_menu()
        )
        return ASK_MATRIC
    
    context.user_data['matric'] = text
    await update.message.reply_text(
        f"✅ Matric: `{text}`\n\nStep 2/2\n🔑 Now enter the **Last 4 Digits** of your IC:",
        parse_mode="Markdown",
        reply_markup=get_cancel_menu()
    )
    return ASK_IC

async def receive_ic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == BTN_CANCEL or text == "CANCEL": return await cancel(update, context)

    if not re.match(r'^\d{4}$', text):
        await update.message.reply_text("⚠️ **Invalid IC!**\nPlease enter exactly 4 digits.", parse_mode="Markdown")
        return ASK_IC
    
    loading_msg = await update.message.reply_text("🔄 **Verifying...**", parse_mode="Markdown")
    
    user_matric = context.user_data['matric']
    user_ic_last4 = text
    
    msg = "⚠️ System Error: Database unavailable."
    
    try:
        sheet = get_sheet_db()
        if sheet:
            # Search Col D (Matric)
            cell = sheet.find(user_matric, in_column=4)
            
            if cell:
                row_values = sheet.row_values(cell.row)
                # Ensure row has enough columns
                if len(row_values) > 5:
                    # Gspread 1-index: C=3, E=5, F=6
                    # List 0-index:    C=2, E=4, F=5
                    db_name = row_values[2] 
                    db_ic = str(row_values[4]).strip().replace(" ", "")
                    db_prog = row_values[5]
                    
                    if db_ic.endswith(user_ic_last4):
                        msg = (
                            "🎉 **MEMBERSHIP VERIFIED** 🎉\n\n"
                            f"👤 **Name:** {db_name}\n"
                            f"🆔 **Matric:** `{user_matric}`\n"
                            f"🎓 **Program:** {db_prog}\n\n"
                            "✅ **Status: ACTIVE**"
                        )
                    else:
                        msg = "❌ **Verification Failed**\nMatric found, but IC digits do not match."
                else:
                     msg = "⚠️ Record found but data is incomplete."
            else:
                msg = "❌ **Not Found**\nMatric Number not in records."
                
    except Exception as e:
        logger.error(e)
        msg = f"⚠️ Database Error."

    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_main_menu())
    return ConversationHandler.END

# --- ADMIN FLOW ---

async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ **Access Denied**\nYou are not an admin.", parse_mode="Markdown")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "🛡️ **Admin Dashboard**\nSelect an action:", 
        parse_mode="Markdown", 
        reply_markup=get_admin_menu()
    )
    return ADMIN_MENU

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        sheet = get_sheet_db()
        if sheet:
            # Assuming row 1 is header
            all_records = sheet.get_all_values()
            total = len(all_records) - 1 # Subtract header
            await update.message.reply_text(
                f"📊 **Database Stats**\n\n👥 Total Members: **{total}**", 
                parse_mode="Markdown",
                reply_markup=get_admin_menu()
            )
        else:
            await update.message.reply_text("⚠️ Database Error.")
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("⚠️ Error fetching stats.")
    return ADMIN_MENU

async def admin_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("➕ **Add Member**\nEnter Matric Number:", reply_markup=get_cancel_menu())
    return ADD_MATRIC

async def admin_add_matric(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().upper()
    if text == BTN_CANCEL or text == "CANCEL": return await admin_back(update, context)
    
    context.user_data['new_matric'] = text
    await update.message.reply_text("👤 Enter **Full Name**:", reply_markup=get_cancel_menu())
    return ADD_NAME

async def admin_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == BTN_CANCEL: return await admin_back(update, context)
    context.user_data['new_name'] = update.message.text.upper()
    await update.message.reply_text("🆔 Enter **Full IC Number** (e.g. 020512081234):", reply_markup=get_cancel_menu())
    return ADD_IC

async def admin_add_ic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == BTN_CANCEL: return await admin_back(update, context)
    context.user_data['new_ic'] = update.message.text
    await update.message.reply_text("🎓 Enter **Program Code** (e.g. CS230):", reply_markup=get_cancel_menu())
    return ADD_PROG

async def admin_add_prog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == BTN_CANCEL: return await admin_back(update, context)
    prog = update.message.text.upper()
    
    # Save to DB
    matric = context.user_data['new_matric']
    name = context.user_data['new_name']
    ic = context.user_data['new_ic']
    
    loading = await update.message.reply_text("💾 Saving...")
    
    try:
        sheet = get_sheet_db()
        if sheet:
            # Columns: Timestamp(A), Email(B), Name(C), Matric(D), IC(E), Program(F)
            # We can leave A and B empty or fill dummy data
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            row = [timestamp, "added_by_bot", name, matric, ic, prog]
            sheet.append_row(row)
            await loading.edit_text(f"✅ **Success!**\nAdded {name} ({matric})", parse_mode="Markdown")
    except Exception as e:
        logger.error(e)
        await loading.edit_text("⚠️ Failed to save to database.")
        
    await update.message.reply_text("Returning to dashboard...", reply_markup=get_admin_menu())
    return ADMIN_MENU

async def admin_del_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("🗑️ **Delete Member**\nEnter Matric Number to delete:", reply_markup=get_cancel_menu())
    return DEL_MATRIC

async def admin_del_matric(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().upper()
    if text == BTN_CANCEL or text == "CANCEL": return await admin_back(update, context)
    
    loading = await update.message.reply_text("🔍 Searching...")
    
    try:
        sheet = get_sheet_db()
        if sheet:
            cell = sheet.find(text, in_column=4)
            if cell:
                sheet.delete_rows(cell.row)
                await loading.edit_text(f"✅ **Deleted**\nRow {cell.row} removed.", parse_mode="Markdown")
            else:
                await loading.edit_text("❌ Matric not found.")
    except Exception as e:
        logger.error(e)
        await loading.edit_text("⚠️ Database Error.")
        
    await update.message.reply_text("Returning to dashboard...", reply_markup=get_admin_menu())
    return ADMIN_MENU

async def admin_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Return to Admin Menu from sub-states"""
    await update.message.reply_text("🔙 Cancelled.", reply_markup=get_admin_menu())
    return ADMIN_MENU

async def admin_exit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("👋 Exiting Admin Mode.", reply_markup=get_main_menu())
    return ConversationHandler.END

# --- SELF PINGER (KEEP ALIVE) ---

async def self_pinger():
    """Pings the bot's own URL every 14 minutes to prevent sleep."""
    while True:
        await asyncio.sleep(14 * 60) # 14 minutes
        if WEBHOOK_URL:
             try:
                 url = f"{WEBHOOK_URL}/health"
                 async with ClientSession() as session:
                     async with session.get(url) as resp:
                         status = resp.status
                         logger.info(f"💓 Self-Ping: {status}")
             except Exception as e:
                 logger.error(f"⚠️ Self-Ping Failed: {e}")

# --- WEBHOOK & MAIN ---
async def main():
    application = Application.builder().token(TOKEN).build()

    # Regex filters
    filter_check = filters.Regex(f"^{re.escape(BTN_CHECK)}$")
    filter_help = filters.Regex(f"^{re.escape(BTN_HELP)}$")
    filter_cancel = filters.Regex(f"^{re.escape(BTN_CANCEL)}$")
    
    # Admin Filters
    filter_admin_add = filters.Regex(f"^{re.escape(BTN_ADMIN_ADD)}$")
    filter_admin_del = filters.Regex(f"^{re.escape(BTN_ADMIN_DEL)}$")
    filter_admin_stats = filters.Regex(f"^{re.escape(BTN_ADMIN_STATS)}$")
    filter_admin_exit = filters.Regex(f"^{re.escape(BTN_ADMIN_EXIT)}$")

    # User Config
    user_conv = ConversationHandler(
        entry_points=[MessageHandler(filter_check, check_start)],
        states={
            ASK_MATRIC: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filter_cancel, receive_matric)],
            ASK_IC: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filter_cancel, receive_ic)],
        },
        fallbacks=[MessageHandler(filter_cancel | filters.COMMAND, cancel)],
    )

    # Admin Config
    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_start)],
        states={
            ADMIN_MENU: [
                MessageHandler(filter_admin_add, admin_add_start),
                MessageHandler(filter_admin_del, admin_del_start),
                MessageHandler(filter_admin_stats, admin_stats),
                MessageHandler(filter_admin_exit, admin_exit)
            ],
            ADD_MATRIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_matric)],
            ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_name)],
            ADD_IC: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_ic)],
            ADD_PROG: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_prog)],
            DEL_MATRIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_del_matric)],
        },
        fallbacks=[CommandHandler("cancel", admin_exit)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filter_help, help_command))
    application.add_handler(user_conv)
    application.add_handler(admin_conv)
    
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
    app.router.add_get("/health", health) # Dedicated endpoint for self-pinger
    
    await application.initialize()
    await application.start()
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    
    # Start Self Pinger Task
    asyncio.create_task(self_pinger())
    
    # Keep alive loop
    while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
