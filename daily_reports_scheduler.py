import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Dict, Optional
import pytz
from config import TIME_PREFERENCE_HOURS, DEFAULT_TIMEZONE

logger = logging.getLogger(__name__)

class DailyReportsScheduler:
    def __init__(self, bot_instance, handlers_instance):
        self.bot = bot_instance
        self.handlers = handlers_instance
        self.scheduler_task = None
        self.timezone = pytz.timezone(DEFAULT_TIMEZONE)
        
    async def start_scheduler(self):
        """Start the daily reports scheduler"""
        if self.scheduler_task and not self.scheduler_task.done():
            logger.warning("Daily reports scheduler is already running")
            return
            
        logger.info("Starting daily reports scheduler...")
        self.scheduler_task = asyncio.create_task(self._scheduler_loop())
        
    async def stop_scheduler(self):
        """Stop the daily reports scheduler"""
        if self.scheduler_task and not self.scheduler_task.done():
            logger.info("Stopping daily reports scheduler...")
            self.scheduler_task.cancel()
            try:
                await self.scheduler_task
            except asyncio.CancelledError:
                pass
                
    async def _scheduler_loop(self):
        """Main scheduler loop that checks for reports to send"""
        logger.info("Daily reports scheduler loop started")
        
        while True:
            try:
                await self._check_and_send_reports()
                
                # Sleep until the next minute to check again
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"Error in daily reports scheduler loop: {e}")
                # Wait a bit before retrying on error
                await asyncio.sleep(60)
                
    async def _check_and_send_reports(self):
        """Check if any users need reports sent at current time"""
        current_utc = datetime.now(pytz.UTC)
        current_minute = current_utc.minute
        
        # Only check at the top of each hour (minute 0)
        if current_minute != 0:
            return
            
        # Get all users who have daily reports enabled
        users_to_notify = []
        
        for user_id, settings in self.bot.user_settings.items():
            daily_reports = settings.get("daily_reports", {})
            
            if not daily_reports.get("enabled", False):
                continue
                
            time_preference = daily_reports.get("time_preference", "morning")
            user_timezone_str = daily_reports.get("timezone", DEFAULT_TIMEZONE)
            target_hour = TIME_PREFERENCE_HOURS.get(time_preference, 9)
            
            try:
                # Convert current UTC time to user's timezone
                user_timezone = pytz.timezone(user_timezone_str)
                user_current_time = current_utc.astimezone(user_timezone)
                
                # Check if it's the right hour for this user
                if user_current_time.hour == target_hour:
                    users_to_notify.append({
                        "user_id": int(user_id),
                        "time_preference": time_preference,
                        "timezone": user_timezone_str
                    })
                    
            except Exception as e:
                logger.error(f"Error processing timezone for user {user_id}: {e}")
                continue
                
        if users_to_notify:
            logger.info(f"Sending daily reports to {len(users_to_notify)} users")
            
            # Send reports to all users who need them
            for user_info in users_to_notify:
                try:
                    await self._send_daily_report(user_info["user_id"], user_info["time_preference"])
                except Exception as e:
                    logger.error(f"Failed to send daily report to user {user_info['user_id']}: {e}")
                    
    async def _send_daily_report(self, user_id: int, time_preference: str):
        """Send daily report to a specific user"""
        try:
            # Create a mock message object for the report command
            class MockMessage:
                def __init__(self, user_id: int, bot_instance):
                    self.from_user = type('obj', (object,), {'id': user_id})
                    self.chat = type('obj', (object,), {'id': user_id})
                    self.bot_instance = bot_instance
                    
                async def answer(self, text, **kwargs):
                    await self.bot_instance.bot.send_message(user_id, text, **kwargs)
                    
            # Create mock message
            mock_message = MockMessage(user_id, self.bot)
            
            # Get time emoji for the greeting
            time_emojis = {
                "morning": "🌅",
                "afternoon": "☀️", 
                "evening": "🌆"
            }
            emoji = time_emojis.get(time_preference, "📊")
            
            # Send greeting message
            greeting = f"{emoji} **Daily Market Overview - {time_preference.title()}**\n\nGenerating your daily market overview..."
            await self.bot.bot.send_message(user_id, greeting, parse_mode="Markdown")
            
            # Generate and send the market overview using existing handler
            await self.handlers.cmd_market_overview(mock_message)
            
            logger.info(f"Daily report sent successfully to user {user_id} ({time_preference})")
            
        except Exception as e:
            logger.error(f"Error sending daily report to user {user_id}: {e}")
            # Send error message to user
            try:
                error_msg = "❌ **Daily Report Error**\n\nSorry, there was an error generating your daily market overview. Please try using the /market command manually."
                await self.bot.bot.send_message(user_id, error_msg, parse_mode="Markdown")
            except:
                pass  # Don't fail if we can't even send the error message
                
    def get_next_report_time(self, user_id: str) -> Optional[datetime]:
        """Get the next scheduled report time for a user"""
        if user_id not in self.bot.user_settings:
            return None
            
        daily_reports = self.bot.user_settings[user_id].get("daily_reports", {})
        
        if not daily_reports.get("enabled", False):
            return None
            
        time_preference = daily_reports.get("time_preference", "morning")
        user_timezone_str = daily_reports.get("timezone", DEFAULT_TIMEZONE)
        target_hour = TIME_PREFERENCE_HOURS.get(time_preference, 9)
        
        try:
            # Get current time in user's timezone
            user_timezone = pytz.timezone(user_timezone_str)
            current_time = datetime.now(user_timezone)
            
            # Calculate next report time
            next_report = current_time.replace(hour=target_hour, minute=0, second=0, microsecond=0)
            
            # If the time has already passed today, schedule for tomorrow
            if next_report <= current_time:
                next_report += timedelta(days=1)
                
            return next_report
        except Exception as e:
            logger.error(f"Error calculating next report time for user {user_id}: {e}")
            return None
        
    def get_scheduler_status(self) -> Dict:
        """Get current scheduler status"""
        is_running = self.scheduler_task and not self.scheduler_task.done()
        
        # Count enabled users
        enabled_users = 0
        for settings in self.bot.user_settings.values():
            if settings.get("daily_reports", {}).get("enabled", False):
                enabled_users += 1
                
        return {
            "running": is_running,
            "enabled_users": enabled_users,
            "timezone": str(self.timezone),
            "time_mappings": TIME_PREFERENCE_HOURS
        }