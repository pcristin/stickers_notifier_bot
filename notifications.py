import json
import logging
from datetime import datetime
from typing import Dict
from utils import escape_markdown, escape_markdown_link_text, clean_marketplace_name
from config import NOTIFICATION_HISTORY_FILE

logger = logging.getLogger(__name__)

class NotificationManager:
    def __init__(self, bot):
        self.bot = bot
        self.last_notifications = self.load_notification_history()
    
    def load_notification_history(self) -> Dict:
        """Load notification history from file"""
        try:
            with open(NOTIFICATION_HISTORY_FILE, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
    
    def save_notification_history(self):
        """Save notification history to file"""
        with open(NOTIFICATION_HISTORY_FILE, 'w') as f:
            json.dump(self.last_notifications, f, indent=2)
    
    def should_send_notification(self, user_id: str, collection_id: str, notification_type: str, current_price: float) -> bool:
        """Check if notification should be sent to avoid spam"""
        notification_key = f"{user_id}:{collection_id}:{notification_type}"
        
        if notification_key not in self.last_notifications:
            # First time notification for this condition
            self.last_notifications[notification_key] = {
                "last_price": current_price,
                "last_sent": datetime.now().isoformat(),
                "count": 1
            }
            self.save_notification_history()
            return True
        
        last_notification = self.last_notifications[notification_key]
        last_price = last_notification.get("last_price", 0)
        last_sent = datetime.fromisoformat(last_notification["last_sent"])
        
        # Check if price has changed significantly (more than 0.01 TON difference)
        price_changed = abs(current_price - last_price) >= 0.01
        
        # Check if enough time has passed (minimum 30 minutes between same notifications)
        time_passed = (datetime.now() - last_sent).total_seconds() >= 1800  # 30 minutes
        
        if price_changed or time_passed:
            # Update notification record
            self.last_notifications[notification_key] = {
                "last_price": current_price,
                "last_sent": datetime.now().isoformat(),
                "count": last_notification.get("count", 0) + 1
            }
            self.save_notification_history()
            return True
        
        return False
    
    async def send_price_notification(self, user_id: int, notification: Dict):
        """Send formatted price notification to user"""
        try:
            if notification['type'] == 'buy':
                emoji = "📈🔔"
                title = "BUY OPPORTUNITY"
                price_info = f"Lowest: {notification['lowest_price']} TON (≤ {notification['threshold']} TON)"
            else:
                emoji = "📉🔔"
                title = "SELL OPPORTUNITY"
                price_info = f"Highest: {notification['highest_price']} TON (≥ {notification['threshold']} TON)"
            
            # Escape Markdown characters in dynamic content
            collection_name = escape_markdown(notification['collection'])
            stickerpack_name = escape_markdown(notification['stickerpack'])
            
            # Format marketplace data with clickable links
            escaped_markets = []
            for market_data in notification['markets']:
                if isinstance(market_data, dict):
                    # New format with name, price, and URL
                    raw_market_name = market_data.get('name', 'Unknown')
                    price = market_data.get('price', 0)
                    url = market_data.get('url')
                    
                    # Clean the marketplace name for better display
                    display_name = clean_marketplace_name(raw_market_name)
                    
                    if url:
                        # Create clickable link: [Market Name](URL): Price TON
                        escaped_name = escape_markdown_link_text(display_name)
                        market_text = f"• [{escaped_name}]({url}): {price} TON"
                    else:
                        # Fallback without link - use same escaping as link text
                        escaped_name = escape_markdown_link_text(display_name)
                        market_text = f"• {escaped_name}: {price} TON"
                else:
                    # Legacy format (string) - for backward compatibility
                    escaped_market = escape_markdown(str(market_data))
                    market_text = f"• {escaped_market}"
                
                escaped_markets.append(market_text)
            markets_text = "\n".join(escaped_markets)
            
            message = (
                f"{emoji} {title}\n\n"
                f"🏷️ Collection: **{collection_name}**\n"
                f"📑 Sticker Pack: **{stickerpack_name}**\n"
                f"💰 {price_info}\n\n"
                f"🏪 Available on:\n{markets_text}\n\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}"
            )
            
            await self.bot.send_message(user_id, message, parse_mode="Markdown")
            logger.info(f"Sent {notification['type']} notification to user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to send price notification to user {user_id}: {e}")
            # Try sending without Markdown as fallback
            try:
                # Format markets for fallback (plain text)
                fallback_markets = []
                for market_data in notification['markets']:
                    if isinstance(market_data, dict):
                        raw_market_name = market_data.get('name', 'Unknown')
                        price = market_data.get('price', 0)
                        # Clean the marketplace name for better display
                        display_name = clean_marketplace_name(raw_market_name)
                        fallback_markets.append(f"• {display_name}: {price} TON")
                    else:
                        fallback_markets.append(f"• {market_data}")
                
                fallback_message = (
                    f"{emoji} {title}\n\n"
                    f"Collection: {notification['collection']}\n"
                    f"Sticker Pack: {notification['stickerpack']}\n"
                    f"Price: {price_info}\n\n"
                    f"Available on:\n" + "\n".join(fallback_markets) + "\n\n"
                    f"Time: {datetime.now().strftime('%H:%M:%S')}"
                )
                await self.bot.send_message(user_id, fallback_message)
                logger.info(f"Sent fallback {notification['type']} notification to user {user_id}")
            except Exception as fallback_error:
                logger.error(f"Failed to send fallback notification to user {user_id}: {fallback_error}")
         
    async def send_notification(self, user_id: int, message: str):
        """Send notification to user"""
        try:
            await self.bot.send_message(user_id, message)
        except Exception as e:
            logger.error(f"Failed to send notification to user {user_id}: {e}")
    
    def cleanup_notifications_for_user(self, user_id: str):
        """Clean up notification history for non-whitelisted users"""
        keys_to_remove = [key for key in self.last_notifications.keys() if key.startswith(f"{user_id}:")]
        for key in keys_to_remove:
            del self.last_notifications[key]
        return len(keys_to_remove)
    
    def cleanup_notifications_for_collection(self, user_id: str, collection_id: str):
        """Clean up notification history for a specific collection"""
        keys_to_remove = [key for key in self.last_notifications.keys() if key.startswith(f"{user_id}:{collection_id}:")]
        for key in keys_to_remove:
            del self.last_notifications[key]
        self.save_notification_history() 