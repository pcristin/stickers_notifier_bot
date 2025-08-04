import asyncio
import json
import logging
from typing import Dict
import aiohttp
from aiogram import Bot, Dispatcher

from api_client import Scanner
from user_states import UserStateManager
from notifications import NotificationManager
from price_monitor import PriceMonitor
from daily_reports_scheduler import DailyReportsScheduler
from config import (
    USER_SETTINGS_FILE, DEFAULT_BUY_MULTIPLIER, DEFAULT_SELL_MULTIPLIER,
    WHITELISTED_USER_IDS, DEFAULT_DAILY_REPORTS_ENABLED, DEFAULT_REPORT_TIME_PREFERENCE,
    FLOOR_UPDATE_ENABLED, FLOOR_UPDATE_INTERVAL, DEFAULT_TIMEZONE
)

logger = logging.getLogger(__name__)

class StickerNotifierBot:
    def __init__(self, token: str):
        self.bot = Bot(token=token)
        self.dp = Dispatcher()
        self.session = None
        self.api_client = None
        
        # Load user settings
        self.user_settings = self.load_user_settings()
        
        # Initialize managers
        self.state_manager = UserStateManager()
        self.notification_manager = None  # Will be initialized after bot is created
        self.price_monitor = None  # Will be initialized after other components
        self.daily_reports_scheduler = None  # Will be initialized after handlers are set
        self.handlers = None  # Will be set from main.py
        
        # Log whitelist configuration
        logger.info(f"Whitelisted user IDs: {WHITELISTED_USER_IDS}")
        if not WHITELISTED_USER_IDS:
            logger.warning("⚠️  No whitelisted users configured! Bot will deny access to all users.")
    
    def set_handlers(self, handlers):
        """Set the handlers instance for use in background tasks"""
        self.handlers = handlers
        # Initialize daily reports scheduler now that we have handlers
        self.daily_reports_scheduler = DailyReportsScheduler(self, handlers)
    
    def initialize_managers(self):
        """Initialize managers that depend on the bot instance"""
        self.notification_manager = NotificationManager(self.bot)
        self.price_monitor = PriceMonitor(
            self.api_client,
            self.notification_manager, 
            self.user_settings, 
            self.save_user_settings
        )
    
    def load_user_settings(self) -> Dict:
        """Load user settings from file"""
        try:
            with open(USER_SETTINGS_FILE, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
            
    def save_user_settings(self):
        """Save user settings to file"""
        with open(USER_SETTINGS_FILE, 'w') as f:
            json.dump(self.user_settings, f, indent=2)
    
    def ensure_user_settings(self, user_id: str):
        """Ensure user settings exist for given user ID"""
        if user_id not in self.user_settings:
            self.user_settings[user_id] = {
                "collections": {},
                "notification_settings": {
                    "buy_multiplier": DEFAULT_BUY_MULTIPLIER,
                    "sell_multiplier": DEFAULT_SELL_MULTIPLIER
                },
                "daily_reports": {
                    "enabled": DEFAULT_DAILY_REPORTS_ENABLED,
                    "time_preference": DEFAULT_REPORT_TIME_PREFERENCE,
                    "timezone": DEFAULT_TIMEZONE
                }
            }
            self.save_user_settings()
        
        # Ensure daily_reports exists for existing users (backward compatibility)
        if "daily_reports" not in self.user_settings[user_id]:
            self.user_settings[user_id]["daily_reports"] = {
                "enabled": DEFAULT_DAILY_REPORTS_ENABLED,
                "time_preference": DEFAULT_REPORT_TIME_PREFERENCE,
                "timezone": DEFAULT_TIMEZONE
            }
            self.save_user_settings()
        
        # Ensure timezone exists in daily_reports (backward compatibility)
        if "timezone" not in self.user_settings[user_id]["daily_reports"]:
            self.user_settings[user_id]["daily_reports"]["timezone"] = DEFAULT_TIMEZONE
            self.save_user_settings()
    
    def cleanup_non_whitelisted_users(self) -> tuple[int, int]:
        """Remove non-whitelisted users from settings and return counts"""
        # Count and remove non-whitelisted users
        non_whitelisted = {uid: data for uid, data in self.user_settings.items() 
                          if int(uid) not in WHITELISTED_USER_IDS}
        
        removed_count = 0
        for uid in list(non_whitelisted.keys()):
            del self.user_settings[uid]
            removed_count += 1
        
        # Clean notification history
        notifications_removed = 0
        if self.notification_manager:
            for uid in non_whitelisted.keys():
                notifications_removed += self.notification_manager.cleanup_notifications_for_user(uid)
            self.notification_manager.save_notification_history()
        
        # Save cleaned data
        self.save_user_settings()
        
        return removed_count, notifications_removed
    
    async def start_polling(self):
        """Start the bot polling"""
        try:
            # Initialize aiohttp session
            self.session = aiohttp.ClientSession()
            
            # Initialize API clients
            self.api_client = Scanner(self.session)
            
            # Initialize managers that depend on other components
            self.initialize_managers()
            
            # Start background tasks
            if self.price_monitor == None:
                logger.error("PriceMonitor was not initialized yet! Try again runing /start command.")
                return 
            asyncio.create_task(self.price_monitor.start_monitoring())
            
            # Start periodic floor price updates if enabled
            if FLOOR_UPDATE_ENABLED:
                asyncio.create_task(self.start_floor_update_monitoring())
                logger.info(f"Floor price updates enabled: every {FLOOR_UPDATE_INTERVAL} seconds")
            
            # Start daily reports scheduler
            if self.daily_reports_scheduler:
                await self.daily_reports_scheduler.start_scheduler()
                logger.info("Daily reports scheduler started")
            
            # Start polling
            await self.dp.start_polling(self.bot)
        finally:
            if self.session:
                await self.session.close()
    
    async def check_collection_availability(self, collection_data) -> str:
        """Check if collection exists in API and return status text"""
        if not self.api_client:
            return "⚠️ Cannot verify collection existence (API not available)"
            
        try:
            bundles = await self.api_client.fetch_price_bundles()
            if bundles:
                bundle = self.api_client.find_collection_by_names(
                    bundles, collection_data.collection_name, collection_data.stickerpack_name
                )
                if bundle:
                    prices = self.api_client.get_marketplace_prices(bundle)
                    if prices:
                        lowest_price = min(prices.values())
                        return f"✅ Collection found! Current lowest price: {lowest_price} TON"
                    else:
                        return "⚠️ Collection found but no current prices available"
                else:
                    return "❌ Collection not found in current marketplace data"
            else:
                return "⚠️ Cannot verify collection existence (API error)"
        except Exception as e:
            logger.error(f"Error checking collection availability: {e}")
            return "⚠️ Cannot verify collection existence (API error)"
    
    async def start_floor_update_monitoring(self):
        """Start the periodic floor price update background task"""
        logger.info("Starting periodic floor price update monitoring...")
        
        while True:
            try:
                logger.info("Running periodic floor price update...")
                
                # Call the internal update method from handlers
                if hasattr(self, 'handlers') and self.handlers:
                    result = await self.handlers.update_floor_prices_internal()
                    
                    if result["success"]:
                        logger.info(f"Floor price update completed: {result['updated']} updated, "
                                  f"{result['skipped']} skipped, {result['errors']} errors")
                    else:
                        logger.warning(f"Floor price update failed: {result['message']}")
                else:
                    logger.warning("Handlers not available for floor price update")
                
                # Wait for the next update cycle
                await asyncio.sleep(FLOOR_UPDATE_INTERVAL)
                
            except Exception as e:
                logger.error(f"Error in periodic floor price update: {e}")
                # Wait a shorter time before retrying on error
                await asyncio.sleep(300)  # 5 minutes retry delay 
