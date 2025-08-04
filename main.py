import asyncio
import signal
import sys

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
    
    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Start the bot
        await bot.start_polling()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down...")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        logger.info("Bot shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())
