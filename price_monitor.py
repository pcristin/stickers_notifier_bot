import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List
from config import (
    PRICE_CACHE_FILE, PRICE_CHECK_INTERVAL, ERROR_RETRY_INTERVAL,
    DEFAULT_BUY_MULTIPLIER, DEFAULT_SELL_MULTIPLIER, WHITELISTED_USER_IDS
)

logger = logging.getLogger(__name__)

class PriceMonitor:
    def __init__(self, api_client, notification_manager, user_settings, save_user_settings_callback):
        self.api_client = api_client
        self.notification_manager = notification_manager
        self.user_settings = user_settings
        self.save_user_settings_callback = save_user_settings_callback
        self.price_cache = self.load_price_cache()
    
    def load_price_cache(self) -> Dict:
        """Load price cache from file"""
        try:
            with open(PRICE_CACHE_FILE, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
            
    def save_price_cache(self):
        """Save price cache to file"""
        with open(PRICE_CACHE_FILE, 'w') as f:
            json.dump(self.price_cache, f, indent=2)
    
    async def start_monitoring(self):
        """Start the price monitoring background task"""
        while True:
            try:
                await self.check_all_prices()
                await asyncio.sleep(PRICE_CHECK_INTERVAL)
            except Exception as e:
                logger.error(f"Error in price monitoring: {e}")
                await asyncio.sleep(ERROR_RETRY_INTERVAL)
    
    async def check_all_prices(self):
        """Check prices for all configured collections"""
        logger.info("Price check cycle started...")
        
        if not self.api_client:
            logger.error("API client not initialized")
            return
            
        # Fetch current price bundles
        bundles = await self.api_client.fetch_price_bundles()
        if not bundles:
            logger.warning("No price bundles received from API")
            return
            
        # Update price cache
        current_time = datetime.now().isoformat()
        self.price_cache = {
            "last_updated": current_time,
            "bundles": bundles
        }
        self.save_price_cache()
        
        # Check each user's collections (only for whitelisted users)
        whitelisted_users = {}
        for uid, data in self.user_settings.items():
            try:
                if int(uid) in WHITELISTED_USER_IDS:
                    whitelisted_users[uid] = data
            except (ValueError, TypeError):
                logger.warning(f"Invalid user ID in settings: {uid}")
                continue
        
        logger.info(f"Checking collections for {len(whitelisted_users)} whitelisted users (total users in settings: {len(self.user_settings)})")
        
        total_collections_checked = 0
        for user_id, user_data in whitelisted_users.items():
            collections = user_data.get("collections", {})
            notification_settings = user_data.get("notification_settings", {})
            
            logger.info(f"User {user_id}: {len(collections)} collections")
            
            for collection_id, collection in collections.items():
                total_collections_checked += 1
                await self.check_collection_price(
                    user_id, collection_id, collection, 
                    bundles, notification_settings
                )
                
        logger.info(f"Price check completed for {len(bundles)} bundles, checked {total_collections_checked} user collections")
    
    async def check_collection_price(self, user_id: str, collection_id: str, collection: Dict, 
                                   bundles: List[Dict], notification_settings: Dict):
        """Check price for a specific collection and send notifications if needed"""
        try:
            # Find the collection in bundles
            bundle = self.api_client.find_collection_by_names(
                bundles, 
                collection['collection_name'], 
                collection['stickerpack_name']
            )
            
            if not bundle:
                logger.warning(f"Collection not found: {collection['collection_name']} - {collection['stickerpack_name']}")
                return
                
            # Get current prices and marketplace data
            marketplace_data = self.api_client.get_marketplace_data(bundle)
            marketplace_prices = self.api_client.get_marketplace_prices(bundle)
            lowest_price = self.api_client.get_lowest_price(bundle)
            highest_price = self.api_client.get_highest_price(bundle)
            
            if not marketplace_prices:
                logger.warning(f"No prices found for collection: {collection['collection_name']}")
                return
                
            # Calculate thresholds
            launch_price = float(collection['launch_price'])
            buy_multiplier = notification_settings.get('buy_multiplier', DEFAULT_BUY_MULTIPLIER)
            sell_multiplier = notification_settings.get('sell_multiplier', DEFAULT_SELL_MULTIPLIER)
            
            buy_threshold = launch_price * buy_multiplier
            sell_threshold = launch_price * sell_multiplier
            
            # Check for notifications
            notifications = []
            
            # Check buy opportunities (price below threshold)
            if lowest_price and lowest_price <= buy_threshold:
                if self.notification_manager.should_send_notification(user_id, collection_id, "buy", lowest_price):
                    buy_markets = []
                    for market, price in marketplace_prices.items():
                        if price <= buy_threshold:
                            market_info = marketplace_data.get(market, {})
                            url = market_info.get('url')
                            buy_markets.append({
                                'name': market,
                                'price': price,
                                'url': url
                            })
                    
                    if buy_markets:
                        notifications.append({
                            'type': 'buy',
                            'collection': collection['collection_name'],
                            'stickerpack': collection['stickerpack_name'],
                            'threshold': buy_threshold,
                            'lowest_price': lowest_price,
                            'markets': buy_markets
                        })
            
            # Check sell opportunities (price above threshold)
            if highest_price and highest_price >= sell_threshold:
                if self.notification_manager.should_send_notification(user_id, collection_id, "sell", highest_price):
                    sell_markets = []
                    for market, price in marketplace_prices.items():
                        if price >= sell_threshold:
                            market_info = marketplace_data.get(market, {})
                            url = market_info.get('url')
                            sell_markets.append({
                                'name': market,
                                'price': price,
                                'url': url
                            })
                    
                    if sell_markets:
                        notifications.append({
                            'type': 'sell',
                            'collection': collection['collection_name'],
                            'stickerpack': collection['stickerpack_name'],
                            'threshold': sell_threshold,
                            'highest_price': highest_price,
                            'markets': sell_markets
                        })
            
            # Send notifications
            for notification in notifications:
                await self.notification_manager.send_price_notification(int(user_id), notification)
                
        except Exception as e:
            logger.error(f"Error checking collection price for user {user_id}: {e}")
    
    async def manual_price_check_for_user(self, user_id: str) -> List[str]:
        """Manually trigger price check for user's collections and return results"""
        collections = self.user_settings.get(user_id, {}).get("collections", {})
        
        if not collections:
            return []
            
        if not self.api_client:
            return ["❌ API client not initialized. Please try again later."]
        
        # Trigger immediate price check
        bundles = await self.api_client.fetch_price_bundles()
        
        if not bundles:
            return ["❌ Failed to fetch price data. Please try again later."]
        
        # Check user's collections
        results = []
        
        for collection_id, collection in collections.items():
            bundle = self.api_client.find_collection_by_names(
                bundles, 
                collection['collection_name'], 
                collection['stickerpack_name']
            )
            
            if bundle:
                marketplace_prices = self.api_client.get_marketplace_prices(bundle)
                lowest_price = self.api_client.get_lowest_price(bundle)
                
                if marketplace_prices:
                    price_text = f"Lowest: {lowest_price} TON"
                    results.append(f"📦 {collection['collection_name']}: {price_text}")
                else:
                    results.append(f"📦 {collection['collection_name']}: No prices available")
            else:
                results.append(f"📦 {collection['collection_name']}: Not found")
        
        return results if results else ["📊 No price data available for your collections."] 