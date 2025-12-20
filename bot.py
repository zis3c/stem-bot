import os
import logging
import asyncio
import re
from aiohttp import web, ClientSession
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
)

# Import Modules
import strings
import states
import handlers
import admin

# --- CONFIGURATION ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
PORT = int(os.getenv("PORT", 10000))
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL")

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

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

    # Filters
    filter_check = filters.Regex(f"^{re.escape(strings.BTN_CHECK)}$")
    filter_help = filters.Regex(f"^{re.escape(strings.BTN_HELP)}$")
    filter_cancel = filters.Regex(f"^{re.escape(strings.BTN_CANCEL)}$")
    
    # Admin Filters
    filter_admin_add = filters.Regex(f"^{re.escape(strings.BTN_ADMIN_ADD)}$")
    filter_admin_del = filters.Regex(f"^{re.escape(strings.BTN_ADMIN_DEL)}$")
    filter_admin_stats = filters.Regex(f"^{re.escape(strings.BTN_ADMIN_STATS)}$")
    filter_admin_exit = filters.Regex(f"^{re.escape(strings.BTN_ADMIN_EXIT)}$")

    # User Config
    user_conv = ConversationHandler(
        entry_points=[MessageHandler(filter_check, handlers.check_start)],
        states={
            states.ASK_MATRIC: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filter_cancel, handlers.receive_matric)],
            states.ASK_IC: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filter_cancel, handlers.receive_ic)],
        },
        fallbacks=[MessageHandler(filter_cancel | filters.COMMAND, handlers.cancel)],
    )

    # Admin Config
    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("admin", admin.start)],
        states={
            states.ADMIN_MENU: [
                MessageHandler(filter_admin_add, admin.add_start),
                MessageHandler(filter_admin_del, admin.del_start),
                MessageHandler(filter_admin_stats, admin.stats),
                MessageHandler(filter_admin_exit, admin.exit)
            ],
            states.ADD_MATRIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.add_matric)],
            states.ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.add_name)],
            states.ADD_IC: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.add_ic)],
            states.ADD_PROG: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.add_prog)],
            states.DEL_MATRIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.del_matric)],
        },
        fallbacks=[CommandHandler("cancel", admin.exit)],
    )

    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(MessageHandler(filter_help, handlers.help_command))
    application.add_handler(user_conv)
    application.add_handler(admin_conv)
    
    webhook_path = f"{WEBHOOK_URL}/telegram"
    await application.bot.set_webhook(webhook_path)
    
    # Set Bot Commands (Suggestions)
    from telegram import BotCommand
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Get help information"),
        BotCommand("admin", "Open Admin Dashboard (Admins Only)"),
        BotCommand("cancel", "Cancel current operation"),
    ]
    await application.bot.set_my_commands(commands)
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
    
    # Start Self Pinger
    asyncio.create_task(self_pinger())
    
    # Keep alive loop
    while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
