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
from config import (
    USER_SETTINGS_FILE, DEFAULT_BUY_MULTIPLIER, DEFAULT_SELL_MULTIPLIER,
    WHITELISTED_USER_IDS
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
        
        # Log whitelist configuration
        logger.info(f"Whitelisted user IDs: {WHITELISTED_USER_IDS}")
        if not WHITELISTED_USER_IDS:
            logger.warning("⚠️  No whitelisted users configured! Bot will deny access to all users.")
    
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
                }
            }
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
            asyncio.create_task(self.price_monitor.start_monitoring())
            
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