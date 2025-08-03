import asyncio

from bot_core import StickerNotifierBot
from handlers import BotHandlers
from utils import setup_logging
from config import BOT_TOKEN

# Setup logging
logger = setup_logging()

async def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or not BOT_TOKEN:
        logger.error("Please set your bot token in .env file or BOT_TOKEN environment variable")
        return
        
    # Initialize bot
    bot = StickerNotifierBot(BOT_TOKEN)
    
    # Initialize and register handlers
    handlers = BotHandlers(bot)
    handlers.register_handlers()
    
    # Set handlers reference for background tasks
    bot.set_handlers(handlers)
    
    # Start the bot
    await bot.start_polling()

if __name__ == "__main__":
    asyncio.run(main())
