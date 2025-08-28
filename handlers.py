import logging
import uuid
from datetime import datetime
from aiogram import F, types
from aiogram.filters import Command
from aiogram.types import (
    InaccessibleMessage,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode

from auth import require_whitelisted_user
from user_states import UserState
from utils import escape_markdown, clean_marketplace_name
from modules.sticker_tools import StickerToolsClient

from datetime import datetime

logger = logging.getLogger(__name__)


class BotHandlers:
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.sticker_client = None
        self.collections_cache = None  # Cache for all available collections
        self.cache_timestamp = None    # When cache was last updated
        self.images_cache = None       # Cache for sticker images
        self.images_cache_timestamp = None  # When images cache was last updated

    def register_handlers(self):
        """Register all bot handlers"""
        self.bot.dp.message(Command("start"))(require_whitelisted_user(self.cmd_start))
        self.bot.dp.message(Command("settings"))(
            require_whitelisted_user(self.cmd_settings)
        )
        self.bot.dp.message(Command("cancel"))(
            require_whitelisted_user(self.cmd_cancel)
        )
        self.bot.dp.message(Command("cleanup_users"))(
            require_whitelisted_user(self.cmd_cleanup_users)
        )
        self.bot.dp.message(Command("wall"))(require_whitelisted_user(self.cmd_wall))
        self.bot.dp.message(Command("update_floor"))(
            require_whitelisted_user(self.cmd_update_floor)
        )
        self.bot.dp.message(Command("report"))(
            require_whitelisted_user(self.cmd_report)
        )
        self.bot.dp.message(Command("market"))(
            require_whitelisted_user(self.cmd_market_overview)
        )
        self.bot.dp.message(Command("collection"))(
            require_whitelisted_user(self.cmd_collection_analysis)
        )
        self.bot.dp.message(Command("sticker"))(
            require_whitelisted_user(self.cmd_sticker_details)
        )
        self.bot.dp.message(Command("scheduler_status"))(require_whitelisted_user(self.cmd_scheduler_status))
        self.bot.dp.message(Command("test_daily_report"))(require_whitelisted_user(self.cmd_test_daily_report))
        self.bot.dp.message(Command("help"))(require_whitelisted_user(self.cmd_help))
        self.bot.dp.message(Command("info"))(require_whitelisted_user(self.cmd_help))

        # Callback query handlers
        self.bot.dp.callback_query(F.data.startswith("main_"))(
            require_whitelisted_user(self.handle_main_menu)
        )
        self.bot.dp.callback_query(F.data.startswith("collection_"))(
            require_whitelisted_user(self.handle_collection_settings)
        )
        self.bot.dp.callback_query(F.data.startswith("notification_"))(
            require_whitelisted_user(self.handle_notification_settings)
        )
        self.bot.dp.callback_query(F.data.startswith("daily_reports_"))(
            require_whitelisted_user(self.handle_daily_reports_callbacks)
        )
        self.bot.dp.callback_query(F.data.startswith("set_timezone_"))(
            require_whitelisted_user(self.handle_timezone_setting)
        )
        self.bot.dp.callback_query(F.data.startswith("confirm_"))(
            require_whitelisted_user(self.handle_confirmation)
        )
        self.bot.dp.callback_query(F.data.startswith("wall_"))(
            require_whitelisted_user(self.handle_wall_callbacks)
        )
        self.bot.dp.callback_query(F.data.startswith("sticker_"))(
            require_whitelisted_user(self.handle_sticker_callbacks)
        )
        self.bot.dp.callback_query(F.data.startswith("edit_"))(
            require_whitelisted_user(self.handle_edit_callbacks)
        )
        self.bot.dp.callback_query(F.data.startswith("toggle_"))(
            require_whitelisted_user(self.handle_toggle_callbacks)
        )

        # Text message handlers for user input flows
        self.bot.dp.message(F.text & ~F.text.startswith("/"))(
            require_whitelisted_user(self.handle_text_input)
        )
        
        # Inline query handler
        self.bot.dp.inline_query()(
            require_whitelisted_user(self.handle_inline_query)
        )
    
    def initialize_sticker_client(self):
        """Initialize the sticker tools client with the bot's session"""
        if self.bot.session:
            self.sticker_client = StickerToolsClient(self.bot.session)
            logger.info("Sticker tools client initialized")
        else:
            logger.error("Bot session not available for sticker client")
    
    def ensure_sticker_client(self):
        """Ensure sticker client is initialized (lazy initialization)"""
        if not self.sticker_client and self.bot.session:
            self.initialize_sticker_client()
        return self.sticker_client is not None
    
    async def get_collections_cache(self, force_refresh: bool = False):
        """Get cached collections data, refresh if needed"""
        from datetime import timedelta
        
        # Check if cache needs refresh (older than 1 hour or forced)
        now = datetime.now()
        if (force_refresh or 
            self.collections_cache is None or 
            self.cache_timestamp is None or 
            now - self.cache_timestamp > timedelta(hours=1)):
            
            if not self.ensure_sticker_client():
                return None
                
            logger.info("Refreshing collections cache...")
            try:
                self.collections_cache = await self.sticker_client.get_all_collections()
                self.cache_timestamp = now
                logger.info(f"Cache refreshed with {len(self.collections_cache or [])} collections")
            except Exception as e:
                logger.error(f"Failed to refresh collections cache: {e}")
                return None
        
        return self.collections_cache

    async def get_images_cache(self, force_refresh: bool = False):
        """Get cached sticker images data, refresh if needed"""
        now = datetime.now()
        cache_age_hours = 2  # Cache images for 2 hours
        
        # Check if we need to refresh the cache
        if (force_refresh or 
            not self.images_cache or 
            not self.images_cache_timestamp or
            (now - self.images_cache_timestamp).total_seconds() > cache_age_hours * 3600):
            
            logger.info("Refreshing images cache...")
            try:
                if self.bot.api_client:
                    price_bundles = await self.bot.api_client.fetch_price_bundles() or []
                    
                    # Create a mapping of collection+sticker name to image URL
                    images_map = {}
                    for bundle in price_bundles:
                        collection_name = bundle.get("collectionName", "").lower()
                        character_name = bundle.get("characterName", "").lower()
                        image_url = bundle.get("imageUrl")
                        
                        if collection_name and character_name and image_url:
                            key = f"{collection_name}:{character_name}"
                            images_map[key] = image_url
                    
                    self.images_cache = images_map
                    self.images_cache_timestamp = now
                    logger.info(f"Images cache refreshed with {len(images_map)} entries")
                else:
                    logger.warning("API client not available for images cache")
                    self.images_cache = {}
            except Exception as e:
                logger.error(f"Failed to refresh images cache: {e}")
                self.images_cache = {}
        
        return self.images_cache or {}

    async def get_all_stickers(self):
        """Get all individual stickers from all collections for inline queries with images"""
        try:
            collections = await self.get_collections_cache()
            if not collections:
                return []
            
            # Get cached images data
            images_map = await self.get_images_cache()
            
            all_stickers = []
            images_found = 0
            for collection in collections:
                for sticker in collection.stickers:
                    # Look up image URL from cache
                    image_key = f"{collection.name.lower()}:{sticker.name.lower()}"
                    image_url = images_map.get(image_key)
                    
                    # If exact match fails, try partial matching
                    if not image_url:
                        # Try to find partial matches in case naming differs slightly
                        collection_lower = collection.name.lower()
                        sticker_lower = sticker.name.lower()
                        
                        for key, url in images_map.items():
                            key_parts = key.split(":")
                            if len(key_parts) == 2:
                                key_collection, key_sticker = key_parts
                                # Check if names are similar (contains each other)
                                if (collection_lower in key_collection or key_collection in collection_lower) and \
                                   (sticker_lower in key_sticker or key_sticker in sticker_lower):
                                    image_url = url
                                    break
                    
                    if image_url:
                        images_found += 1
                    
                    # Add collection info to sticker for context
                    sticker_info = {
                        'sticker': sticker,
                        'collection_name': collection.name,
                        'collection_id': collection.id,
                        'image_url': image_url
                    }
                    all_stickers.append(sticker_info)
            
            logger.info(f"Found images for {images_found}/{len(all_stickers)} stickers")
            
            return all_stickers
        except Exception as e:
            logger.error(f"Error getting all stickers: {e}")
            return []

    async def handle_inline_query(self, inline_query: InlineQuery):
        """Handle inline queries for sticker search"""
        if not self.ensure_sticker_client():
            await inline_query.answer([], cache_time=1)
            return
        
        query = inline_query.query.strip().lower()
        
        # Check if query starts with "stickerpack:" or just "sticker:"
        if query.startswith("stickerpack:"):
            search_term = query.replace("stickerpack:", "").strip()
        elif query.startswith("sticker:"):
            search_term = query.replace("sticker:", "").strip()
        else:
            # Show help message if no proper prefix
            help_result = InlineQueryResultArticle(
                id="help",
                title="🎯 Sticker Analysis",
                description="Type 'stickerpack: name' to search stickers",
                input_message_content=InputTextMessageContent(
                    message_text="💡 To search stickers, type:\n`@your_bot_name stickerpack: sticker_name`",
                    parse_mode=ParseMode.MARKDOWN
                )
            )
            await inline_query.answer([help_result], cache_time=60)
            return
        
        # Get all stickers
        all_stickers = await self.get_all_stickers()
        if not all_stickers:
            no_data_result = InlineQueryResultArticle(
                id="no_data",
                title="❌ No Data Available",
                description="Sticker data is not available right now",
                input_message_content=InputTextMessageContent(
                    message_text="❌ Sticker data is currently unavailable. Please try again later.\n\n"
                               "💡 Make sure:\n"
                               "• Bot has inline mode enabled in @BotFather\n"
                               "• APIs are responding properly\n"
                               "• You have the latest bot version",
                    parse_mode=ParseMode.MARKDOWN
                )
            )
            await inline_query.answer([no_data_result], cache_time=10)
            return
        
        # Filter stickers based on search term
        filtered_stickers = []
        if search_term:
            # Split search term into words for better matching
            search_words = search_term.split()
            
            for sticker_info in all_stickers:
                sticker = sticker_info['sticker']
                collection_name = sticker_info['collection_name']
                
                # Search in sticker name and collection name
                sticker_text = f"{sticker.name} {collection_name}".lower()
                
                # Check if all search words are present (more flexible matching)
                if all(word in sticker_text for word in search_words):
                    filtered_stickers.append(sticker_info)
                elif any(word in sticker.name.lower() for word in search_words):
                    # Prioritize matches in sticker name
                    filtered_stickers.insert(0, sticker_info)
        else:
            # Show top stickers by volume if no search term
            sorted_stickers = sorted(all_stickers, 
                                   key=lambda x: x['sticker'].vol_24h_ton, 
                                   reverse=True)
            filtered_stickers = sorted_stickers[:50]
        
        # Convert to inline results (limit to 50 for performance)
        results = []
        for i, sticker_info in enumerate(filtered_stickers[:50]):
            sticker = sticker_info['sticker']
            collection_name = sticker_info['collection_name']
            image_url = sticker_info.get('image_url')
            
            # Format sticker details for display
            trend_emoji = sticker.price_trend.value
            floor_price = f"{sticker.floor_price_ton:.1f}"
            volume_24h = f"{sticker.vol_24h_ton:.1f}"
            
            # Create the message content
            sticker_details = self.sticker_client.generate_sticker_details(sticker)
            
            # Create inline result with thumbnail if image URL is available
            result_kwargs = {
                "id": f"sticker_{sticker_info['collection_id']}_{sticker.id}",
                "title": f"{trend_emoji} {sticker.name}",
                "description": f"{collection_name} | Floor: {floor_price} TON | Vol: {volume_24h} TON",
                "input_message_content": InputTextMessageContent(
                    message_text=sticker_details,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            }
            
            # Add thumbnail if image URL is available and valid
            if image_url and image_url.startswith(("http://", "https://")):
                result_kwargs["thumbnail_url"] = image_url
                # Also set thumbnail dimensions for better display
                result_kwargs["thumbnail_width"] = 100
                result_kwargs["thumbnail_height"] = 100
            
            result = InlineQueryResultArticle(**result_kwargs)
            results.append(result)
        
        # Answer the inline query
        await inline_query.answer(
            results, 
            cache_time=60,  # Cache for 1 minute
            is_personal=True  # Results are personalized
        )

    async def cmd_start(self, message: types.Message):
        """Handle /start command"""
        if message.from_user == None:
            await message.answer("❌ Unexpected error occured! ")
            return
        user_id = message.from_user.id
        user_id_str = str(user_id)

        # Initialize user settings if not exists
        self.bot.ensure_user_settings(user_id_str)
        
        # Get current time for welcome
        from datetime import datetime
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        welcome_text = (
            f"🕐 *{escape_markdown(current_time)}*\n\n"
            "🚀 *Welcome to Advanced Sticker Market Bot\\!*\n\n"
            "📊 **Your Complete Telegram Stickers Trading Assistant**\n\n"
            
            "🔥 **Core Features:**\n"
            "• 💰 *Price Monitoring* \\- Track your collections 24/7\n"
            "• 🔔 *Smart Alerts* \\- Custom buy/sell notifications per collection\n"
            "• 📈 *Market Analysis* \\- Real\\-time trends, volume, floor prices\n"
            "• 🖼️ *Inline Search* \\- Type `@bot_name stickerpack: name` anywhere\n"
            "• 📰 *Daily Reports* \\- Automated market summaries\n"
            "• 📊 *Google Sheets* \\- Import floor prices from your sheets\n\n"
            
            "⚡ **Quick Start:**\n"
            "• `/settings` \\- Configure collections & notifications\n"
            "• `/market` \\- View your collections market status\n"
            "• `/collection` \\- Analyze any collection with trends\n"
            "• `/sticker` \\- Deep dive into individual stickers\n"
            "• `/help` \\- Full command reference\n\n"
            
            "🎯 **Pro Features:**\n"
            "• Per\\-collection notification controls\n"
            "• Smart trend analysis \\(📈📉➡️\\)\n"
            "• Volume change tracking vs 7d average\n"
            "• High\\-activity detection algorithms\n"
            "• Real\\-time floor price monitoring\n\n"
            
            "💡 *Start by adding your first collection in /settings\\!*"
        )

        await message.answer(welcome_text, parse_mode=ParseMode.MARKDOWN_V2)

    async def cmd_help(self, message: types.Message):
        """Handle /help and /info commands"""
        if message.from_user == None:
            await message.answer("❌ Unexpected error occurred!")
            return
            
        # Get current time for help
        from datetime import datetime
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        help_text = (
            f"🕐 *{escape_markdown(current_time)}*\n\n"
            "📚 *Complete Command Reference*\n\n"
            
            "🔧 **Setup & Configuration:**\n"
            "• `/start` \\- Welcome message & feature overview\n"
            "• `/settings` \\- Main configuration menu\n"
            "• `/cancel` \\- Cancel any active operation\n\n"
            
            "📊 **Market Analysis:**\n"
            "• `/market` \\- Your collections market overview\n"
            "• `/collection` \\- Analyze any collection \\(interactive\\)\n"
            "• `/sticker` \\- Deep sticker analysis \\(interactive\\)\n\n"
            
            "🔍 **Inline Search \\(Use Anywhere\\):**\n"
            "• `@bot_name stickerpack: wilson` \\- Search specific sticker\n"
            "• `@bot_name stickerpack: azuki` \\- Find collection stickers\n"
            "• `@bot_name stickerpack: ` \\- Browse top stickers\n\n"
            
            "📈 **Data Management:**\n"
            "• `/update_floor` \\- Import floor prices from Google Sheets\n"
            "• `/report` \\- Generate detailed trading report\n"
            "• `/wall` \\- Check account wall/balance\n\n"
            
            "🤖 **Daily Market Overview System:**\n"
            "• `/scheduler_status` \\- Check scheduler status & next report time\n"
            "• `/test_daily_report` \\- Test daily market overview generation\n\n"
            
            "⚙️ **Settings Categories:**\n"
            "• 📦 *Collection Settings* \\- Add/edit your collections\n"
            "• 🔔 *Notification Settings* \\- Default alert multipliers\n"
            "• 📰 *Daily Reports* \\- Auto report preferences\n"
            "• 📊 *My Collections* \\- View configured collections\n\n"
            
            "🎯 **Per\\-Collection Features:**\n"
            "• Individual buy/sell multipliers\n"
            "• Enable/disable notifications per collection\n"
            "• Launch price tracking\n"
            "• Performance vs launch price\n\n"
            
            "📊 **Market Insights:**\n"
            "• Real\\-time floor price tracking\n"
            "• 24h volume change analysis\n"
            "• Median price trends \\(vs 7d\\)\n"
            "• Activity level detection\n"
            "• Smart trend indicators \\(📈📉➡️\\)\n\n"
            
            "💡 **Pro Tips:**\n"
            "• Set different multipliers per collection\n"
            "• Use inline search for quick analysis\n"
            "• Configure daily reports for your timezone\n"
            "• Monitor high\\-volume stickers for opportunities\n\n"
            
            "🆘 **Need Help?** All commands have interactive menus\\!"
        )

        await message.answer(help_text, parse_mode=ParseMode.MARKDOWN_V2)

    async def cmd_cancel(self, message: types.Message):
        """Handle /cancel command to exit any active flow"""
        if message.from_user == None:
            await message.answer("❌ Unexpected error occured! ")
            return
        user_id = message.from_user.id

        if self.bot.state_manager.is_user_in_flow(user_id):
            self.bot.state_manager.reset_user_session(user_id)
            await message.answer(
                "❌ Operation cancelled. Use /settings to access the menu.",
                reply_markup=types.ReplyKeyboardRemove(),
            )
        else:
            await message.answer(
                "No active operation to cancel. Use /settings to access the menu."
            )

    async def cmd_cleanup_users(self, message: types.Message):
        """Remove non-whitelisted users from settings (admin command)"""
        removed_count, notifications_removed = self.bot.cleanup_non_whitelisted_users()

        if removed_count == 0:
            await message.answer("✅ No non-whitelisted users found in settings.")
            return

        await message.answer(
            f"🧹 **Cleanup Complete**\n\n"
            f"• Removed {removed_count} non-whitelisted users\n"
            f"• Cleaned {notifications_removed} old notifications\n\n"
            f"Only whitelisted users will now be monitored.",
            parse_mode="Markdown",
        )

    async def cmd_wall(self, message: types.Message):
        """Handle /wall command to check sell order walls"""
        if message.from_user == None:
            await message.answer("❌ Unexpected error occured! ")
            return
        user_id = message.from_user.id

        # Check if API client is available
        if not self.bot.api_client:
            await message.answer("❌ API client not available. Please try again later.")
            return

        # Reset any existing flow and start wall query
        self.bot.state_manager.reset_user_session(user_id)
        self.bot.state_manager.set_user_state(
            user_id, UserState.WALL_SELECTING_COLLECTION
        )

        # Show loading message
        loading_msg = await message.answer("🔄 Loading collections...")

        try:
            # Get user's configured collections
            user_id_str = str(user_id)
            user_collections = self.bot.user_settings.get(user_id_str, {}).get(
                "collections", {}
            )

            if not user_collections:
                await loading_msg.edit_text(
                    "❌ No collections configured for wall analysis.\n\n"
                    "Use /settings → Collection Settings to add collections first."
                )
                self.bot.state_manager.reset_user_session(user_id)
                return

            # Organize by collection name -> sticker packs
            collections = {}
            for collection_data in user_collections.values():
                collection_name = collection_data["collection_name"]
                stickerpack_name = collection_data["stickerpack_name"]

                if collection_name not in collections:
                    collections[collection_name] = []
                if stickerpack_name not in collections[collection_name]:
                    collections[collection_name].append(stickerpack_name)

            # Store collections data
            self.bot.state_manager.update_wall_data(
                user_id, available_collections=collections
            )

            # Create inline keyboard with collections (max 100 per page for now)
            builder = InlineKeyboardBuilder()
            sorted_collections = sorted(collections.keys())

            for i, collection_name in enumerate(
                sorted_collections[:20]
            ):  # Limit to 20 for now
                builder.row(
                    InlineKeyboardButton(
                        text=f"📦 {collection_name}",
                        callback_data=f"wall_collection_{i}",
                    )
                )

            builder.row(
                InlineKeyboardButton(text="❌ Cancel", callback_data="wall_cancel")
            )

            text = (
                "🧱 **Wall Analysis**\n\n"
                f"Found **{len(collections)}** collections with sticker packs.\n\n"
                "📦 **Select a collection:**"
            )

            await loading_msg.edit_text(
                text, reply_markup=builder.as_markup(), parse_mode="Markdown"
            )

        except Exception as e:
            logger.error(f"Error loading collections for wall: {e}")
            await loading_msg.edit_text(
                "❌ Error loading collections. Please try again later."
            )
            self.bot.state_manager.reset_user_session(user_id)

    async def cmd_update_floor(self, message: types.Message):
        """Update floor prices in Google Sheets from scanner API"""
        # Send processing message for command
        from utils import escape_markdown
        initial_title = f"*{escape_markdown('Updating floor prices...')}*"
        initial_body = escape_markdown("Initializing...")
        status_msg = await message.answer(
            f"🔄 {initial_title}\n\n{initial_body}",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        
        # Call the main update method
        result = await self.update_floor_prices_internal()
        
        # Update the status message with result
        await status_msg.edit_text(result["message"], parse_mode=ParseMode.MARKDOWN_V2)

    async def update_floor_prices_internal(self) -> dict:
        """Internal method to update floor prices, returns result dict"""
        from modules.google_sheets.sheets_client import SheetsClient
        from config import GOOGLE_SHEETS_KEY, GOOGLE_CREDENTIALS_PATH

        # Validate prerequisites
        if not GOOGLE_SHEETS_KEY:
            return {
                "success": False,
                "message": "❌ Google Sheets key not configured in environment",
                "updated": 0,
                "skipped": 0,
                "errors": 0
            }

        if not self.bot.api_client:
            return {
                "success": False,
                "message": "❌ API client not available",
                "updated": 0,
                "skipped": 0,
                "errors": 0
            }

        try:
            # Initialize sheets client
            sheets_client = SheetsClient(GOOGLE_CREDENTIALS_PATH)
            if not sheets_client.authenticate():
                return {
                    "success": False,
                    "message": "❌ Failed to authenticate with Google Sheets",
                    "updated": 0,
                    "skipped": 0,
                    "errors": 0
                }

            # Get cached price bundles (uses existing cache mechanism)
            bundle_data = await self.bot.api_client.fetch_price_bundles()
            if not bundle_data:
                return {
                    "success": False,
                    "message": "❌ Failed to fetch price data from scanner API",
                    "updated": 0,
                    "skipped": 0,
                    "errors": 0
                }

            # Get all worksheets
            worksheets = sheets_client.get_all_worksheets(GOOGLE_SHEETS_KEY)
            if not worksheets:
                return {
                    "success": False,
                    "message": "❌ No worksheets found in Google Sheets",
                    "updated": 0,
                    "skipped": 0,
                    "errors": 0
                }

            # Track results
            results = {"updated": 0, "skipped": 0, "errors": 0, "details": []}

            # Process each worksheet
            for i, worksheet in enumerate(worksheets):

                # Get collection info
                collection_name, stickerpack_name = sheets_client.get_collection_info(
                    worksheet
                )

                if not collection_name or not stickerpack_name:
                    results["skipped"] += 1
                    from utils import escape_markdown
                    results["details"].append(
                        f"⚠️ {escape_markdown(worksheet.title)}: Missing collection/stickerpack info"
                    )
                    continue

                # Find matching collection in API data
                matching_bundle = self.bot.api_client.find_collection_by_names(
                    bundle_data, collection_name, stickerpack_name
                )

                if not matching_bundle:
                    results["skipped"] += 1
                    from utils import escape_markdown
                    results["details"].append(
                        f"⚠️ {escape_markdown(worksheet.title)}: No API data for {escape_markdown(collection_name)} \\- {escape_markdown(stickerpack_name)}"
                    )
                    continue

                # Get lowest price
                floor_price = self.bot.api_client.get_lowest_price(matching_bundle)
                if floor_price is None:
                    results["errors"] += 1
                    from utils import escape_markdown
                    results["details"].append(
                        f"❌ {escape_markdown(worksheet.title)}: No price data available"
                    )
                    continue

                # Update floor price
                if sheets_client.update_floor_price(worksheet, floor_price):
                    results["updated"] += 1
                    from utils import escape_markdown
                    results["details"].append(
                        f"✅ {escape_markdown(worksheet.title)}: Updated to {escape_markdown(f'{floor_price}')} TON"
                    )
                else:
                    results["errors"] += 1
                    from utils import escape_markdown
                    results["details"].append(f"❌ {escape_markdown(worksheet.title)}: Failed to update")

            # Format final summary
            from datetime import datetime
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            from utils import escape_markdown
            summary_text = (
                f"🕐 *{escape_markdown(current_time)}*\n\n"
                f"📊 *Floor Price Update Complete*\n\n"
                f"✅ *Updated:* {escape_markdown(str(results['updated']))} worksheets\n"
                f"⚠️ *Skipped:* {escape_markdown(str(results['skipped']))} worksheets\n"
                f"❌ *Errors:* {escape_markdown(str(results['errors']))} worksheets\n\n"
            )

            # Add details (limit to avoid message length issues)
            if results["details"]:
                summary_text += "*Details:*\n"
                for detail in results["details"][:10]:  # Show max 10 details
                    summary_text += f"{detail}\n"

                if len(results["details"]) > 10:
                    # Use ellipsis character to avoid MDV2 dot escaping
                    summary_text += f"\n… and {len(results['details']) - 10} more"

            return {
                "success": True,
                "message": summary_text,
                "updated": results["updated"],
                "skipped": results["skipped"],
                "errors": results["errors"],
                "details": results["details"]
            }

        except Exception as e:
            logger.error(f"Error in update_floor_prices_internal: {e}")
            return {
                "success": False,
                "message": f"❌ Unexpected error: {str(e)}",
                "updated": 0,
                "skipped": 0,
                "errors": 0
            }

    async def cmd_report(self, message: types.Message):
        """Generate text report based on Google Sheets data"""
        from modules.google_sheets.sheets_client import SheetsClient
        from config import GOOGLE_SHEETS_KEY, GOOGLE_CREDENTIALS_PATH

        # Validate prerequisites
        if not GOOGLE_SHEETS_KEY:
            await message.answer("❌ Google Sheets key not configured in environment")
            return

        # First, update floor price
        try:
            await self.cmd_update_floor(message)
        except Exception as e:
            logger.error(f"Error in updating floor: {e}")
            await message.answer(f"Floor updating error occured, using old values")

        # Send processing message
        status_msg = await message.answer(
            "📊 **Generating report...**\n\nLoading data from Google Sheets...",
            parse_mode="Markdown",
        )

        try:
            # Initialize sheets client
            sheets_client = SheetsClient(GOOGLE_CREDENTIALS_PATH)
            if not sheets_client.authenticate():
                await status_msg.edit_text(
                    "❌ Failed to authenticate with Google Sheets"
                )
                return

            # Get all report data
            report_data = sheets_client.get_all_report_data(GOOGLE_SHEETS_KEY)
            if not report_data:
                await status_msg.edit_text("❌ No valid data found in Google Sheets")
                return

            await status_msg.edit_text(
                "📊 **Generating report...**\n\nFormatting report...",
                parse_mode="Markdown",
            )

            # Generate report
            report_text = self.format_report(report_data)

            # Split message if too long (Telegram limit is 4096 characters)
            if len(report_text) <= 4096:
                await status_msg.edit_text(
                    report_text, parse_mode=ParseMode.MARKDOWN_V2
                )
            else:
                # Send in parts
                await status_msg.edit_text(
                    "📊 **Report Generated**\n\nSending report in parts...",
                    parse_mode=ParseMode.MARKDOWN,
                )

                # Split into chunks
                chunks = self.split_report(report_text, 4000)  # Leave some margin
                for i, chunk in enumerate(chunks):
                    if i == 0:
                        await status_msg.edit_text(
                            chunk, parse_mode=ParseMode.MARKDOWN_V2
                        )
                    else:
                        await message.answer(chunk, parse_mode=ParseMode.MARKDOWN_V2)

        except Exception as e:
            logger.error(f"Error in report command: {e}")
            await status_msg.edit_text(f"❌ Unexpected error: {str(e)}")

    async def cmd_market_overview(self, message: types.Message):
        """Show market overview for user's configured collections"""
        if not self.ensure_sticker_client():
            await message.reply("❌ Sticker analysis not available - session not ready")
            return
        
        if message.from_user is None:
            await message.reply("❌ User information not available")
            return
            
        user_id = str(message.from_user.id)
        user_collections = self.bot.user_settings.get(user_id, {}).get("collections", {})
        
        if not user_collections:
            from datetime import datetime
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            await message.reply(
                f"🕐 **{current_time}**\n\n"
                "📊 **Market Overview**\n\n"
                "❌ No collections configured for monitoring.\n\n"
                "Use /settings → Collection Settings to add collections first.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
            
        try:
            loading_msg = await message.reply("📊 Fetching market data for your collections...")
            
            # Get collections cache
            all_collections = await self.get_collections_cache()
            if not all_collections:
                await loading_msg.edit_text("❌ Failed to fetch market data")
                return
            
            # Find user's collections in the market data
            user_market_data = []
            for collection_config in user_collections.values():
                collection_name = collection_config["collection_name"]
                stickerpack_name = collection_config["stickerpack_name"]
                
                # Find matching collection
                for market_collection in all_collections:
                    if market_collection.name.lower() == collection_name.lower():
                        # Find specific sticker pack within collection
                        matching_sticker = None
                        for sticker in market_collection.stickers:
                            if sticker.name.lower() == stickerpack_name.lower():
                                matching_sticker = sticker
                                break
                        
                        if matching_sticker:
                            user_market_data.append({
                                'collection': market_collection,
                                'sticker': matching_sticker,
                                'config': collection_config
                            })
                        break
            
            if not user_market_data:
                await loading_msg.edit_text(
                    "📊 **Market Overview**\n\n"
                    "❌ None of your configured collections found in current market data.\n\n"
                    "Your collections might not be actively traded or names might not match exactly.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            # Get current time for the report
            from datetime import datetime
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Generate analytical overview for user's collections
            overview_text = f"🕐 *{escape_markdown(current_time)}*\n\n📊 *Your Collections Market Analysis*\n\n"
            
            for i, data in enumerate(user_market_data, 1):
                sticker = data['sticker']
                config = data['config']
                
                # Calculate performance vs launch price
                launch_price = config['launch_price']
                current_price = sticker.floor_price_ton
                price_change_vs_launch = ((current_price / launch_price) - 1) * 100 if launch_price > 0 else 0
                
                # Get analytical data
                vol_change = sticker.vol_change_pct
                floor_change_24h = sticker.floor_change_pct
                median_change = sticker.median_change_pct
                trend = sticker.price_trend
                is_high_volume = sticker.is_high_volume
                
                # Escape and format name with bold
                escaped_name = escape_markdown(sticker.name)
                
                # Format numbers with bold and proper escaping
                floor_price_bold = f"*{escape_markdown(f'{current_price:.1f}')}*"
                launch_vs_bold = f"*{escape_markdown(f'{price_change_vs_launch:+.1f}')}" + "%*"
                vol_24h_bold = f"*{escape_markdown(f'{sticker.vol_24h_ton:.1f}')}*"
                median_price_bold = f"*{escape_markdown(f'{sticker.median_price_24h_ton:.1f}')}*"
                
                overview_text += f"{escape_markdown(str(i))}\\. *{escaped_name}* {trend.value}\n"
                overview_text += f"   💰 Floor: {floor_price_bold} TON \\({launch_vs_bold} vs launch\\)\n"
                
                # Add median price and its change
                if median_change is not None:
                    median_change_formatted = f"*{escape_markdown(f'{median_change:+.1f}')}*%"
                    overview_text += f"   📊 Median: {median_price_bold} TON \\({median_change_formatted} vs 7d\\)\n"
                else:
                    overview_text += f"   📊 Median: {median_price_bold} TON\n"
                
                # Add volume analysis
                if vol_change is not None:
                    vol_change_formatted = f"*{escape_markdown(f'{vol_change:+.1f}')}*%"
                    vol_trend_emoji = "🚀" if vol_change > 50 else "📈" if vol_change > 0 else "📉"
                    overview_text += f"   {vol_trend_emoji} Volume: {vol_24h_bold} TON \\({vol_change_formatted} vs avg\\)\n"
                else:
                    overview_text += f"   📈 Volume: {vol_24h_bold} TON\n"
                
                # Add 24h floor change if significant
                if abs(floor_change_24h) > 1:  # Only show if > 1% change
                    floor_change_formatted = f"*{escape_markdown(f'{floor_change_24h:+.1f}')}*%"
                    floor_emoji = "📈" if floor_change_24h > 0 else "📉"
                    overview_text += f"   {floor_emoji} Floor 24h: {floor_change_formatted}\n"
                
                # Add activity indicator
                activity_emoji = "🔥" if is_high_volume else "😴"
                activity_text = "High activity" if is_high_volume else "Low activity"
                overview_text += f"   {activity_emoji} {escape_markdown(activity_text)}\n\n"
            
            await loading_msg.edit_text(overview_text, parse_mode=ParseMode.MARKDOWN_V2)
            
        except Exception as e:
            logger.error(f"Error in market overview: {e}")
            await message.reply("❌ Failed to fetch market data")
    
    async def cmd_collection_analysis(self, message: types.Message):
        """Show collection selection menu"""
        if not self.ensure_sticker_client():
            await message.reply("❌ Sticker analysis not available - session not ready")
            return
        
        try:
            loading_msg = await message.reply("📊 Loading collections...")
            
            # Get collections cache
            collections = await self.get_collections_cache()
            if not collections:
                await loading_msg.edit_text("❌ Failed to fetch collections data")
                return
            
            # Sort collections by name
            sorted_collections = sorted(collections, key=lambda c: c.name.lower())
            
            if not sorted_collections:
                await loading_msg.edit_text("❌ No collections available")
                return
            
            # Create inline keyboard with collections (20 per page)
            builder = InlineKeyboardBuilder()
            
            for i, collection in enumerate(sorted_collections[:20]):  # Limit to 20
                builder.row(
                    InlineKeyboardButton(
                        text=f"📦 {collection.name}",
                        callback_data=f"sticker_select_collection_{i}"
                    )
                )
            
            # Add pagination if needed
            if len(sorted_collections) > 20:
                builder.row(
                    InlineKeyboardButton(
                        text="➡️ Next Page", 
                        callback_data="sticker_collection_page_1"
                    )
                )
            
            builder.row(
                InlineKeyboardButton(
                    text="❌ Cancel", 
                    callback_data="sticker_cancel"
                )
            )
            
            text = (
                "📊 *Collection Analysis*\n\n"
                f"Found *{escape_markdown(str(len(sorted_collections)))}* collections\\.\n\n"
                "📦 *Select a collection to analyze:*"
            )
            
            await loading_msg.edit_text(
                text, 
                reply_markup=builder.as_markup(), 
                parse_mode=ParseMode.MARKDOWN_V2
            )
            
        except Exception as e:
            logger.error(f"Error in collection analysis: {e}")
            await message.reply("❌ Failed to load collections")
    
    async def cmd_sticker_details(self, message: types.Message):
        """Show collection selection menu for sticker analysis"""
        if not self.ensure_sticker_client():
            await message.reply("❌ Sticker analysis not available - session not ready")
            return
        
        try:
            loading_msg = await message.reply("🎯 Loading collections...")
            
            # Get collections cache
            collections = await self.get_collections_cache()
            if not collections:
                await loading_msg.edit_text("❌ Failed to fetch collections data")
                return
            
            # Sort collections by name
            sorted_collections = sorted(collections, key=lambda c: c.name.lower())
            
            if not sorted_collections:
                await loading_msg.edit_text("❌ No collections available")
                return
            
            # Create inline keyboard with collections (20 per page)
            builder = InlineKeyboardBuilder()
            
            for i, collection in enumerate(sorted_collections[:20]):  # Limit to 20
                builder.row(
                    InlineKeyboardButton(
                        text=f"📦 {collection.name}",
                        callback_data=f"sticker_select_for_details_{i}"
                    )
                )
            
            # Add pagination if needed
            if len(sorted_collections) > 20:
                builder.row(
                    InlineKeyboardButton(
                        text="➡️ Next Page", 
                        callback_data="sticker_details_page_1"
                    )
                )
            
            builder.row(
                InlineKeyboardButton(
                    text="❌ Cancel", 
                    callback_data="sticker_cancel"
                )
            )
            
            text = (
                "🎯 *Sticker Analysis*\n\n"
                f"Found *{escape_markdown(str(len(sorted_collections)))}* collections\\.\n\n"
                "📦 *Select a collection to see its stickers:*"
            )
            
            await loading_msg.edit_text(
                text, 
                reply_markup=builder.as_markup(), 
                parse_mode=ParseMode.MARKDOWN_V2
            )
            
        except Exception as e:
            logger.error(f"Error in sticker analysis: {e}")
            await message.reply("❌ Failed to load collections")

    def format_report(self, report_data: list) -> str:
        """Format report data into the required text format"""

        # First dateline
        dateline = [
            f"*__{escape_markdown(datetime.now().strftime('%d.%m.%y %H:%M'))}__*"
        ]

        dateline.append("")  # Empty line after line with report date and time

        # Individual collection details
        total_unrealized_pnl = 0.0
        total_spent = 0.0
        total_realized_pnl = 0.0
        total_left_on_cold = 0.0

        for data in report_data:
            collection_name = data["collection_name"]
            stickerpack_name = data["stickerpack_name"]
            floor_price = data["floor_price"]
            total_left = data["total_left"]
            percent_supply = data["percent_supply"]
            avg_buy_price = data["avg_buy_price"]
            unrealized_pnl = data["unrealized_pnl"]
            total_sells = data["total_sells"]
            realized_pnl = data["realized_pnl"]
            collection_spent = data["collection_spent_on_markets"]
            left_on_cold = data["left_on_cold"]

            # Calculate total spent for this collection
            total_spent += collection_spent
            total_unrealized_pnl += unrealized_pnl
            total_realized_pnl += realized_pnl
            total_left_on_cold += left_on_cold

            # Format the collection section
            dateline.append(
                f"{escape_markdown(collection_name)} {escape_markdown(stickerpack_name)}:"
            )
            dateline.append(f"FP: *{escape_markdown(f'{floor_price:.3f}')} TON*")
            dateline.append(
                f"Own: *{total_left} \\({escape_markdown(f'{percent_supply:.3f}')}% supply\\)*"
            )
            dateline.append(f"Avg price: *{escape_markdown(f'{avg_buy_price:.2f}')}*")
            dateline.append(
                f"Unrealized PnL: *{escape_markdown(f'{unrealized_pnl:.3f}')}*"
            )
            dateline.append(f"Total sold: *{total_sells}*")
            dateline.append(f"Realized PnL: *{escape_markdown(f'{realized_pnl:.3f}')}*")
            dateline.append(f"Left on cold: *{escape_markdown(f'{left_on_cold:.3f}')}*")

            dateline.append("")  # Empty line after each collection

        # Summary section
        dateline.extend(
            [
                "Summary:",
                f"Total spent on markets: *{escape_markdown(f'{total_spent:.2f}')}*",
                f"Unrealized PnL: *{escape_markdown(f'{total_unrealized_pnl:.3f}')}*",
                f"Realized PnL: *{escape_markdown(f'{total_realized_pnl:.3f}')}*",
                f"Total left on cold wallets: *{escape_markdown(f'{total_left_on_cold:.3f}')}*",
            ]
        )

        return "\n".join(dateline)

    def split_report(self, text: str, max_length: int) -> list:
        """Split report into chunks if it's too long"""
        if len(text) <= max_length:
            return [text]

        chunks = []
        lines = text.split("\n")
        current_chunk = []
        current_length = 0

        for line in lines:
            line_length = len(line) + 1  # +1 for newline

            if current_length + line_length > max_length and current_chunk:
                # Save current chunk and start a new one
                chunks.append("\n".join(current_chunk))
                current_chunk = [line]
                current_length = line_length
            else:
                current_chunk.append(line)
                current_length += line_length

        # Add the last chunk
        if current_chunk:
            chunks.append("\n".join(current_chunk))

        return chunks

    async def cmd_settings(self, message: types.Message):
        """Show main settings menu"""
        keyboard = self.get_main_settings_keyboard()

        text = (
            "⚙️ **Advanced Settings Menu**\n\n"
            "🚀 **Configure Your Trading Dashboard:**\n\n"
            "📦 **Collection Settings** \\- Add, edit, and manage monitored collections\n"
            "🔔 **Notification Settings** \\- Set default buy/sell alert multipliers\n"
            "📰 **Daily Reports** \\- Configure automated market summaries\n"
            "📊 **My Collections** \\- View all configured collections & status\n"
            "🔄 **Check Prices Now** \\- Manual price check for your collections\n\n"
            "💡 *Each collection has individual notification controls\\!*"
        )

        await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN_V2)

    def get_main_settings_keyboard(self) -> InlineKeyboardMarkup:
        """Create main settings keyboard"""
        builder = InlineKeyboardBuilder()

        builder.row(
            InlineKeyboardButton(
                text="📦 Collection Settings", callback_data="main_collections"
            ),
            InlineKeyboardButton(
                text="🔔 Notification Settings", callback_data="main_notifications"
            ),
        )
        builder.row(
            InlineKeyboardButton(
                text="📰 Daily Reports", callback_data="main_daily_reports"
            ),
            InlineKeyboardButton(
                text="📊 My Collections", callback_data="main_view_collections"
            ),
        )
        builder.row(
            InlineKeyboardButton(
                text="🔄 Check Prices Now", callback_data="main_check_prices"
            ),
        )

        return builder.as_markup()

    async def handle_main_menu(self, callback: types.CallbackQuery):
        """Handle main menu callbacks"""
        if callback.data == None:
            return "Unexpected error occur"
        action = callback.data.split("_", 1)[1]

        if action == "collections":
            await self.show_collection_settings(callback)
        elif action == "notifications":
            await self.show_notification_settings(callback)
        elif action == "daily_reports":
            await self.show_daily_reports_settings(callback)
        elif action == "view_collections":
            await self.show_user_collections(callback)
        elif action == "check_prices":
            await self.manual_price_check(callback)
        elif action == "back":
            # Show main menu again
            keyboard = self.get_main_settings_keyboard()
            text = (
                "⚙️ **Advanced Settings Menu**\n\n"
                "🚀 **Configure Your Trading Dashboard:**\n\n"
                "📦 **Collection Settings** \\- Add, edit, and manage monitored collections\n"
                "🔔 **Notification Settings** \\- Set default buy/sell alert multipliers\n"
                "📰 **Daily Reports** \\- Configure automated market summaries\n"
                "📊 **My Collections** \\- View all configured collections & status\n"
                "🔄 **Check Prices Now** \\- Manual price check for your collections\n\n"
                "💡 *Each collection has individual notification controls\\!*"
            )

            # Check if callback.message does not exist or is inaccessible
            if (
                isinstance(callback.message, InaccessibleMessage)
                or callback.message == None
            ):
                return "The message is no longer accessible"
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN_V2)

    async def show_collection_settings(self, callback: types.CallbackQuery):
        """Show collection configuration options"""
        user_id = str(callback.from_user.id)
        user_collections = self.bot.user_settings[user_id]["collections"]

        builder = InlineKeyboardBuilder()

        # Add existing collections
        for collection_id, collection in user_collections.items():
            builder.row(
                InlineKeyboardButton(
                    text=f"📦 {collection['collection_name']} - {collection['stickerpack_name']}",
                    callback_data=f"collection_edit_{collection_id}",
                )
            )

        builder.row(
            InlineKeyboardButton(
                text="➕ Add New Collection", callback_data="collection_add_new"
            )
        )
        builder.row(
            InlineKeyboardButton(text="⬅️ Back to Main", callback_data="main_back")
        )

        text = (
            "📦 Collection Settings\n\n"
            f"You have {len(user_collections)} collection(s) configured.\n"
            "Select a collection to edit or add a new one:"
        )

        # Check if callback.message does not exist or is inaccessible
        if (
            isinstance(callback.message, InaccessibleMessage)
            or callback.message == None
        ):
            return "The message is no longer accessible"
        await callback.message.edit_text(text, reply_markup=builder.as_markup())

    async def show_notification_settings(self, callback: types.CallbackQuery):
        """Show notification configuration"""
        user_id = str(callback.from_user.id)
        settings = self.bot.user_settings[user_id]["notification_settings"]

        builder = InlineKeyboardBuilder()

        builder.row(
            InlineKeyboardButton(
                text=f"📈 Buy Alert: {settings['buy_multiplier']}x",
                callback_data="notification_buy_multiplier",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=f"📉 Sell Alert: {settings['sell_multiplier']}x",
                callback_data="notification_sell_multiplier",
            )
        )
        builder.row(
            InlineKeyboardButton(text="⬅️ Back to Main", callback_data="main_back")
        )

        text = (
            "🔔 **Default Notification Settings**\n\n"
            f"📈 **Default Buy Alert:** {settings['buy_multiplier']}x launch price\n"
            f"📉 **Default Sell Alert:** {settings['sell_multiplier']}x launch price\n\n"
            f"ℹ️ **Note:** These are default settings for new collections.\n"
            f"Each collection now has individual notification settings.\n\n"
            f"💡 **To configure notifications for existing collections:**\n"
            f"Go to Collection Settings → Select Collection → Notification Settings\n\n"
            f"**Modify default settings for new collections:**"
        )

        if (
            isinstance(callback.message, InaccessibleMessage)
            or callback.message == None
        ):
            return "The message is no longer accessible"
        await callback.message.edit_text(text, reply_markup=builder.as_markup())

    async def show_daily_reports_settings(self, callback: types.CallbackQuery):
        """Show daily reports configuration"""
        user_id = str(callback.from_user.id)
        
        # Ensure user settings exist and have daily reports
        self.bot.ensure_user_settings(user_id)
        daily_reports = self.bot.user_settings[user_id]["daily_reports"]
        
        enabled = daily_reports.get("enabled", True)
        time_preference = daily_reports.get("time_preference", "morning")
        user_timezone = daily_reports.get("timezone", "UTC")
        
        builder = InlineKeyboardBuilder()
        
        # Enable/disable toggle
        status_text = "✅ Enabled" if enabled else "❌ Disabled"
        builder.row(
            InlineKeyboardButton(
                text=f"🔔 Status: {status_text}",
                callback_data="daily_reports_toggle_enabled"
            )
        )
        
        # Time preference
        time_emojis = {
            "morning": "🌅",
            "afternoon": "☀️", 
            "evening": "🌆"
        }
        current_emoji = time_emojis.get(time_preference, "🌅")
        builder.row(
            InlineKeyboardButton(
                text=f"{current_emoji} Time: {time_preference.title()}",
                callback_data="daily_reports_time_preference"
            )
        )
        
        # Timezone setting
        builder.row(
            InlineKeyboardButton(
                text=f"🌍 Timezone: {user_timezone}",
                callback_data="daily_reports_timezone"
            )
        )
        
        builder.row(
            InlineKeyboardButton(text="⬅️ Back to Main", callback_data="main_back")
        )
        
        # Calculate next report time
        next_report_info = ""
        if enabled and hasattr(self.bot, 'daily_reports_scheduler') and self.bot.daily_reports_scheduler:
            try:
                next_time = self.bot.daily_reports_scheduler.get_next_report_time(user_id)
                if next_time:
                    next_report_info = f"\n⏰ **Next Report:** {next_time.strftime('%Y-%m-%d %H:%M %Z')}"
            except Exception as e:
                logger.error(f"Error calculating next report time: {e}")
        
        text = (
            "📰 **Daily Reports Settings**\n\n"
            f"📊 **Auto Market Reports:** {status_text}\n"
            f"{current_emoji} **Preferred Time:** {time_preference.title()}\n\n"
            f"ℹ️ **About Daily Reports:**\n"
            f"• Automatically send market overview at chosen time\n"
            f"• Choose your preferred time of day for reports\n"
            f"• Reports include all your configured collections\n"
            f"• Reports show current time and market analysis\n\n"
            f"💡 **Manual Reports:** You can always use /market anytime\n\n"
            f"**Configure your daily report preferences:**"
        )
        
        if (
            isinstance(callback.message, InaccessibleMessage)
            or callback.message == None
        ):
            return "The message is no longer accessible"
        await callback.message.edit_text(text, reply_markup=builder.as_markup())

    async def show_user_collections(self, callback: types.CallbackQuery):
        """Display user's configured collections"""
        user_id = str(callback.from_user.id)
        collections = self.bot.user_settings[user_id]["collections"]

        if not collections:
            text = "📦 No collections configured yet.\n\nUse Collection Settings to add your first collection!"
        else:
            text = "📦 Your Collections:\n\n"
            for _, collection in collections.items():
                # Escape Markdown characters
                escaped_collection_name = escape_markdown(collection["collection_name"])
                escaped_stickerpack_name = escape_markdown(
                    collection["stickerpack_name"]
                )
                
                # Get notification settings with backward compatibility
                notification_settings = collection.get("notification_settings", {})
                if not notification_settings:
                    from config import DEFAULT_BUY_MULTIPLIER, DEFAULT_SELL_MULTIPLIER
                    notification_settings = {
                        "buy_multiplier": DEFAULT_BUY_MULTIPLIER,
                        "sell_multiplier": DEFAULT_SELL_MULTIPLIER,
                        "enabled": True
                    }
                
                enabled_status = "✅" if notification_settings.get("enabled", True) else "❌"
                buy_multiplier = notification_settings.get("buy_multiplier", 2.0)
                sell_multiplier = notification_settings.get("sell_multiplier", 3.0)

                text += (
                    f"🏷️ **{escaped_collection_name}**\n"
                    f"📑 Sticker Pack: {escaped_stickerpack_name}\n"
                    f"💰 Launch Price: {collection['launch_price']} TON\n"
                    f"🔔 Notifications: {enabled_status} (📈{buy_multiplier}x | 📉{sell_multiplier}x)\n"
                    f"🕒 Added: {collection.get('added_date', 'Unknown')}\n\n"
                )

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="⬅️ Back to Main", callback_data="main_back")
        )
        if (
            isinstance(callback.message, InaccessibleMessage)
            or callback.message == None
        ):
            return "The message is no longer accessible"
        await callback.message.edit_text(
            text, reply_markup=builder.as_markup(), parse_mode="Markdown"
        )

    async def manual_price_check(self, callback: types.CallbackQuery):
        """Manually trigger price check for user's collections"""
        user_id = str(callback.from_user.id)
        collections = self.bot.user_settings[user_id]["collections"]

        if not collections:
            await callback.answer("No collections configured!", show_alert=True)
            return

        await callback.answer("Checking prices...")

        # Use price monitor for manual check
        results = await self.bot.price_monitor.manual_price_check_for_user(user_id)

        if results:
            text = f"🔄 Price Check Results:\n\n" + "\n".join(results)
        else:
            text = "📊 No price data available for your collections."

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="⬅️ Back to Main", callback_data="main_back")
        )

        # Check is callback.message does not exist or is inaccessible
        if (
            isinstance(callback.message, InaccessibleMessage)
            or callback.message == None
        ):
            return "The message is no longer accessible"

        await callback.message.edit_text(text, reply_markup=builder.as_markup())

    async def handle_collection_settings(self, callback: types.CallbackQuery):
        """Handle collection-specific settings"""
        if callback.data == None:
            logger.error("Callback data is None, canceling context")
            return
        action_parts = callback.data.split("_")

        if len(action_parts) < 2:
            await callback.answer("Invalid action", show_alert=True)
            return

        action = action_parts[1]

        if action == "add" and len(action_parts) > 2 and action_parts[2] == "new":
            await self.start_collection_creation(callback)
        elif action == "edit" and len(action_parts) > 2:
            collection_id = action_parts[2]
            await self.start_collection_editing(callback, collection_id)
        elif action == "delete" and len(action_parts) > 2:
            collection_id = action_parts[2]
            await self.confirm_collection_deletion(callback, collection_id)
        else:
            await callback.answer("Unknown collection action", show_alert=True)

    async def start_collection_creation(self, callback: types.CallbackQuery):
        """Start the collection creation flow"""
        user_id = callback.from_user.id

        # Reset any existing flow and start new one
        self.bot.state_manager.reset_user_session(user_id)
        self.bot.state_manager.set_user_state(user_id, UserState.ADDING_COLLECTION_NAME)

        text = (
            "📦 Adding New Collection\n\n"
            "Step 1/3: Enter the **collection name**\n\n"
            "Example: `Hamster Kombat`, `TON Society`, `Notcoin`\n\n"
            "💡 This is the main collection name as shown on marketplaces.\n\n"
            "Type /cancel to abort this process."
        )

        # Check is callback.message does not exist or is inaccessible
        if (
            isinstance(callback.message, InaccessibleMessage)
            or callback.message == None
        ):
            return "The message is no longer accessible"

        await callback.message.edit_text(text, parse_mode="Markdown")
        await callback.answer()

    async def start_collection_editing(
        self, callback: types.CallbackQuery, collection_id: str
    ):
        """Start editing an existing collection"""
        user_id = str(callback.from_user.id)
        collections = self.bot.user_settings[user_id]["collections"]

        if collection_id not in collections:
            await callback.answer("Collection not found!", show_alert=True)
            return

        collection = collections[collection_id]
        
        # Ensure backward compatibility - add notification settings if missing
        if "notification_settings" not in collection:
            from config import DEFAULT_BUY_MULTIPLIER, DEFAULT_SELL_MULTIPLIER
            collection["notification_settings"] = {
                "buy_multiplier": DEFAULT_BUY_MULTIPLIER,
                "sell_multiplier": DEFAULT_SELL_MULTIPLIER,
                "enabled": True
            }
            self.bot.save_user_settings()

        notification_settings = collection["notification_settings"]
        enabled_status = "✅ Enabled" if notification_settings.get("enabled", True) else "❌ Disabled"

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text=f"📝 Edit Name: {collection['collection_name']}",
                callback_data=f"edit_field_collection_name_{collection_id}",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=f"📑 Edit Sticker Pack: {collection['stickerpack_name']}",
                callback_data=f"edit_field_stickerpack_name_{collection_id}",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=f"💰 Edit Launch Price: {collection['launch_price']} TON",
                callback_data=f"edit_field_launch_price_{collection_id}",
            )
        )
        
        # Notification settings section
        builder.row(
            InlineKeyboardButton(
                text="🔔 Notification Settings",
                callback_data=f"edit_notifications_{collection_id}",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=f"📈 Buy Alert: {notification_settings['buy_multiplier']}x",
                callback_data=f"edit_buy_multiplier_{collection_id}",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=f"📉 Sell Alert: {notification_settings['sell_multiplier']}x",
                callback_data=f"edit_sell_multiplier_{collection_id}",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=f"🔔 Status: {enabled_status}",
                callback_data=f"toggle_notifications_{collection_id}",
            )
        )
        
        builder.row(
            InlineKeyboardButton(
                text="🗑️ Delete Collection",
                callback_data=f"collection_delete_{collection_id}",
            ),
            InlineKeyboardButton(text="⬅️ Back", callback_data="main_collections"),
        )

        # Escape Markdown characters in collection data
        escaped_collection_name = escape_markdown(collection["collection_name"])
        escaped_stickerpack_name = escape_markdown(collection["stickerpack_name"])

        text = (
            f"✏️ Editing Collection\n\n"
            f"🏷️ **Collection:** {escaped_collection_name}\n"
            f"📑 **Sticker Pack:** {escaped_stickerpack_name}\n"
            f"💰 **Launch Price:** {collection['launch_price']} TON\n\n"
            f"🔔 **Notifications:** {enabled_status}\n"
            f"📈 **Buy Alert:** {notification_settings['buy_multiplier']}x launch price\n"
            f"📉 **Sell Alert:** {notification_settings['sell_multiplier']}x launch price\n\n"
            f"Select what you want to edit:"
        )

        # Check is callback.message does not exist or is inaccessible
        if (
            isinstance(callback.message, InaccessibleMessage)
            or callback.message == None
        ):
            return "The message is no longer accessible"

        await callback.message.edit_text(
            text, reply_markup=builder.as_markup(), parse_mode="Markdown"
        )
        await callback.answer()

    async def confirm_collection_deletion(
        self, callback: types.CallbackQuery, collection_id: str
    ):
        """Confirm collection deletion"""
        user_id = str(callback.from_user.id)
        collections = self.bot.user_settings[user_id]["collections"]

        if collection_id not in collections:
            await callback.answer("Collection not found!", show_alert=True)
            return

        collection = collections[collection_id]

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="🗑️ Yes, Delete", callback_data=f"confirm_delete_{collection_id}"
            ),
            InlineKeyboardButton(
                text="❌ Cancel", callback_data=f"collection_edit_{collection_id}"
            ),
        )

        # Escape Markdown characters
        escaped_collection_name = escape_markdown(collection["collection_name"])
        escaped_stickerpack_name = escape_markdown(collection["stickerpack_name"])

        text = (
            f"⚠️ **Delete Collection?**\n\n"
            f"🏷️ Collection: **{escaped_collection_name}**\n"
            f"📑 Sticker Pack: **{escaped_stickerpack_name}**\n\n"
            f"This action cannot be undone!"
        )

        # Check is callback.message does not exist or is inaccessible
        if (
            isinstance(callback.message, InaccessibleMessage)
            or callback.message == None
        ):
            return "The message is no longer accessible"

        await callback.message.edit_text(
            text, reply_markup=builder.as_markup(), parse_mode="Markdown"
        )
        await callback.answer()

    async def handle_notification_settings(self, callback: types.CallbackQuery):
        """Handle notification settings changes"""
        if callback.data == None:
            logger.error("Callback data is None!")
            return
        action_parts = callback.data.split("_")

        if len(action_parts) < 2:
            await callback.answer("Invalid notification action", show_alert=True)
            return

        action = action_parts[1]

        if (
            action == "buy"
            and len(action_parts) > 2
            and action_parts[2] == "multiplier"
        ):
            await self.start_buy_multiplier_editing(callback)
        elif (
            action == "sell"
            and len(action_parts) > 2
            and action_parts[2] == "multiplier"
        ):
            await self.start_sell_multiplier_editing(callback)
        else:
            await callback.answer("Unknown notification action", show_alert=True)

    async def start_buy_multiplier_editing(self, callback: types.CallbackQuery):
        """Start editing buy multiplier"""
        user_id = callback.from_user.id
        user_id_str = str(user_id)

        current_multiplier = self.bot.user_settings[user_id_str][
            "notification_settings"
        ]["buy_multiplier"]

        # Reset any existing flow and start new one
        self.bot.state_manager.reset_user_session(user_id)
        self.bot.state_manager.set_user_state(user_id, UserState.EDITING_BUY_MULTIPLIER)

        text = (
            f"📈 **Edit Buy Alert Multiplier**\n\n"
            f"Current value: **{current_multiplier}x**\n\n"
            f"Enter the new multiplier for buy alerts.\n"
            f"You'll get notified when prices drop to this multiple of the launch price or below.\n\n"
            f"Example: `2` (for 2x launch price), `1.5`, `3.0`\n\n"
            f"Valid range: 0.1 to 100\n\n"
            f"Type /cancel to abort this change."
        )

        # Check is callback.message does not exist or is inaccessible
        if (
            isinstance(callback.message, InaccessibleMessage)
            or callback.message == None
        ):
            return "The message is no longer accessible"

        await callback.message.edit_text(text, parse_mode="Markdown")
        await callback.answer()

    async def start_sell_multiplier_editing(self, callback: types.CallbackQuery):
        """Start editing sell multiplier"""
        user_id = callback.from_user.id
        user_id_str = str(user_id)

        current_multiplier = self.bot.user_settings[user_id_str][
            "notification_settings"
        ]["sell_multiplier"]

        # Reset any existing flow and start new one
        self.bot.state_manager.reset_user_session(user_id)
        self.bot.state_manager.set_user_state(
            user_id, UserState.EDITING_SELL_MULTIPLIER
        )

        text = (
            f"📉 **Edit Sell Alert Multiplier**\n\n"
            f"Current value: **{current_multiplier}x**\n\n"
            f"Enter the new multiplier for sell alerts.\n"
            f"You'll get notified when prices rise to this multiple of the launch price or above.\n\n"
            f"Example: `3` (for 3x launch price), `2.5`, `5.0`\n\n"
            f"Valid range: 0.1 to 100\n\n"
            f"Type /cancel to abort this change."
        )

        # Check is callback.message does not exist or is inaccessible
        if (
            isinstance(callback.message, InaccessibleMessage)
            or callback.message == None
        ):
            return "The message is no longer accessible"

        await callback.message.edit_text(text, parse_mode="Markdown")
        await callback.answer()

    async def handle_daily_reports_callbacks(self, callback: types.CallbackQuery):
        """Handle daily reports settings callbacks"""
        if callback.data is None:
            logger.error("Callback data is None!")
            return
        
        action_parts = callback.data.split("_")
        if len(action_parts) < 3:
            await callback.answer("Invalid daily reports action", show_alert=True)
            return
        
        action = "_".join(action_parts[2:])  # daily_reports_toggle_enabled -> toggle_enabled
        user_id = str(callback.from_user.id)
        
        # Ensure user settings exist
        self.bot.ensure_user_settings(user_id)
        daily_reports = self.bot.user_settings[user_id]["daily_reports"]
        
        if action == "toggle_enabled":
            # Toggle enabled status
            current_status = daily_reports.get("enabled", True)
            daily_reports["enabled"] = not current_status
            self.bot.save_user_settings()
            
            new_status = "enabled" if not current_status else "disabled"
            await callback.answer(f"✅ Daily reports {new_status}!")
            
            # Refresh the settings view
            await self.show_daily_reports_settings(callback)
            
        elif action == "time_preference":
            # Cycle through time preferences
            current_time = daily_reports.get("time_preference", "morning")
            time_options = ["morning", "afternoon", "evening"]
            current_index = time_options.index(current_time) if current_time in time_options else 0
            next_index = (current_index + 1) % len(time_options)
            new_time = time_options[next_index]
            
            daily_reports["time_preference"] = new_time
            self.bot.save_user_settings()
            
            time_emojis = {"morning": "🌅", "afternoon": "☀️", "evening": "🌆"}
            emoji = time_emojis.get(new_time, "🌅")
            await callback.answer(f"{emoji} Time preference: {new_time.title()}")
            
            # Refresh the settings view
            await self.show_daily_reports_settings(callback)
            
        elif action == "timezone":
            # Show timezone selection
            await self.show_timezone_selection(callback)
            
        else:
            await callback.answer("Unknown daily reports action", show_alert=True)

    async def show_timezone_selection(self, callback: types.CallbackQuery):
        """Show timezone selection menu"""
        builder = InlineKeyboardBuilder()
        
        # Common timezones
        common_timezones = [
            ("UTC", "UTC"),
            ("US/Eastern", "US Eastern"),
            ("US/Central", "US Central"),
            ("US/Mountain", "US Mountain"),
            ("US/Pacific", "US Pacific"),
            ("Europe/London", "London"),
            ("Europe/Paris", "Paris"),
            ("Europe/Berlin", "Berlin"),
            ("Europe/Moscow", "Moscow"),
            ("Asia/Tokyo", "Tokyo"),
            ("Asia/Shanghai", "Shanghai"),
            ("Asia/Kolkata", "India"),
            ("Australia/Sydney", "Sydney")
        ]
        
        for tz_id, display_name in common_timezones:
            builder.row(
                InlineKeyboardButton(
                    text=display_name,
                    callback_data=f"set_timezone_{tz_id.replace('/', '_')}"
                )
            )
        
        builder.row(
            InlineKeyboardButton(text="⬅️ Back to Daily Reports", callback_data="daily_reports")
        )
        
        text = (
            "🌍 **Select Your Timezone**\n\n"
            "Choose your timezone for daily report scheduling:\n\n"
            "⏰ Reports will be sent at your local time based on this setting."
        )
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())

    async def handle_timezone_setting(self, callback: types.CallbackQuery):
        """Handle timezone setting"""
        if not callback.data or not callback.data.startswith("set_timezone_"):
            return
            
        timezone_id = callback.data.replace("set_timezone_", "").replace("_", "/")
        user_id = str(callback.from_user.id)
        
        # Validate timezone
        try:
            import pytz
            pytz.timezone(timezone_id)
        except:
            await callback.answer("❌ Invalid timezone", show_alert=True)
            return
        
        # Update user settings
        self.bot.ensure_user_settings(user_id)
        self.bot.user_settings[user_id]["daily_reports"]["timezone"] = timezone_id
        self.bot.save_user_settings()
        
        await callback.answer(f"🌍 Timezone set to {timezone_id}")
        
        # Go back to daily reports settings
        await self.show_daily_reports_settings(callback)

    async def handle_text_input(self, message: types.Message):
        """Handle text input from users during flows"""
        if message.from_user == None:
            await message.answer("❌ Unexpected error occur")
            return
        user_id = message.from_user.id
        user_state = self.bot.state_manager.get_user_state(user_id)

        if user_state == UserState.IDLE:
            # User not in any flow, ignore
            return

        if message.text == None:
            await message.answer("❌ Unexpected error occured")
            return
        text = message.text.strip()

        if user_state == UserState.ADDING_COLLECTION_NAME:
            await self.process_collection_name_input(message, text)
        elif user_state == UserState.ADDING_STICKERPACK_NAME:
            await self.process_stickerpack_name_input(message, text)
        elif user_state == UserState.ADDING_LAUNCH_PRICE:
            await self.process_launch_price_input(message, text)
        elif user_state == UserState.EDITING_BUY_MULTIPLIER:
            await self.process_buy_multiplier_input(message, text)
        elif user_state == UserState.EDITING_SELL_MULTIPLIER:
            await self.process_sell_multiplier_input(message, text)
        elif user_state == UserState.WALL_TON_AMOUNT:
            await self.process_wall_ton_amount_input(message, text)

    async def process_collection_name_input(self, message: types.Message, text: str):
        """Process collection name input"""
        if message.from_user == None:
            await message.answer("❌ Unexpected error occured! ")
            return
        user_id = message.from_user.id

        if len(text) < 2 or len(text) > 50:
            await message.answer(
                "❌ Collection name must be between 2 and 50 characters.\n\n"
                "Please try again or type /cancel to abort."
            )
            return

        # Store collection name and move to next step
        self.bot.state_manager.update_collection_data(user_id, collection_name=text)
        self.bot.state_manager.set_user_state(
            user_id, UserState.ADDING_STICKERPACK_NAME
        )

        # Escape Markdown characters for display
        escaped_text = escape_markdown(text)

        await message.answer(
            f"✅ Collection name: **{escaped_text}**\n\n"
            f"Step 2/3: Enter the **sticker pack name**\n\n"
            f"Example: `Golden Hamster`, `Diamond Society`, `Premium Notcoin`\n\n"
            f"💡 This is the specific sticker pack within the collection.\n\n"
            f"Type /cancel to abort this process.",
            parse_mode="Markdown",
        )

    async def process_stickerpack_name_input(self, message: types.Message, text: str):
        """Process sticker pack name input"""
        if message.from_user == None:
            await message.answer("❌ Unexpected error occured! ")
            return
        user_id = message.from_user.id

        if len(text) < 2 or len(text) > 50:
            await message.answer(
                "❌ Sticker pack name must be between 2 and 50 characters.\n\n"
                "Please try again or type /cancel to abort."
            )
            return

        # Store sticker pack name and move to next step
        self.bot.state_manager.update_collection_data(user_id, stickerpack_name=text)
        self.bot.state_manager.set_user_state(user_id, UserState.ADDING_LAUNCH_PRICE)

        collection_data = self.bot.state_manager.get_collection_data(user_id)

        # Escape Markdown characters for display
        escaped_collection_name = escape_markdown(collection_data.collection_name)
        escaped_stickerpack_name = escape_markdown(text)

        await message.answer(
            f"✅ Collection: **{escaped_collection_name}**\n"
            f"✅ Sticker Pack: **{escaped_stickerpack_name}**\n\n"
            f"Step 3/3: Enter the **launch price in TON**\n\n"
            f"Example: `10`, `25.5`, `100`\n\n"
            f"💡 This is the original mint/launch price used to calculate notification thresholds.\n\n"
            f"Type /cancel to abort this process.",
            parse_mode="Markdown",
        )

    async def process_launch_price_input(self, message: types.Message, text: str):
        """Process launch price input"""
        if message.from_user == None:
            await message.answer("❌ Unexpected error occured! ")
            return
        user_id = message.from_user.id

        try:
            price = float(text)
            if price <= 0 or price > 10000:
                raise ValueError("Price out of range")
        except ValueError:
            await message.answer(
                "❌ Invalid price. Please enter a valid number between 0.01 and 10000 TON.\n\n"
                "Example: `10`, `25.5`, `100`\n\n"
                "Type /cancel to abort."
            )
            return

        # Store launch price and show confirmation
        self.bot.state_manager.update_collection_data(user_id, launch_price=price)
        self.bot.state_manager.set_user_state(user_id, UserState.CONFIRMING_COLLECTION)

        collection_data = self.bot.state_manager.get_collection_data(user_id)

        # Check if collection already exists in API
        status_text = await self.bot.check_collection_availability(collection_data)

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="✅ Confirm & Save", callback_data="confirm_add_collection"
            ),
            InlineKeyboardButton(
                text="❌ Cancel", callback_data="confirm_cancel_collection"
            ),
        )

        # Escape Markdown characters in collection data
        escaped_collection_name = escape_markdown(collection_data.collection_name)
        escaped_stickerpack_name = escape_markdown(collection_data.stickerpack_name)

        text = (
            f"📋 **Confirm New Collection**\n\n"
            f"🏷️ **Collection:** {escaped_collection_name}\n"
            f"📑 **Sticker Pack:** {escaped_stickerpack_name}\n"
            f"💰 **Launch Price:** {collection_data.launch_price} TON\n\n"
            f"{status_text}\n\n"
            f"Confirm to add this collection to your watchlist?"
        )

        await message.answer(
            text, reply_markup=builder.as_markup(), parse_mode="Markdown"
        )

    async def process_buy_multiplier_input(self, message: types.Message, text: str):
        """Process buy multiplier input for specific collection"""
        if message.from_user == None:
            await message.answer("❌ Unexpected error occured! ")
            return
        user_id = message.from_user.id
        user_id_str = str(user_id)

        try:
            multiplier = float(text)
            if multiplier <= 0 or multiplier > 100:
                raise ValueError("Multiplier out of range")
        except ValueError:
            await message.answer(
                "❌ Invalid multiplier. Please enter a number between 0.1 and 100.\n\n"
                "Example: `2`, `1.5`, `3.0`\n\n"
                "Type /cancel to abort."
            )
            return

        # Get collection ID from session
        collection_data = self.bot.state_manager.get_collection_data(user_id)
        collection_id = getattr(collection_data, 'editing_collection_id', None)
        
        if not collection_id:
            await message.answer("❌ Collection ID not found. Please try again.")
            self.bot.state_manager.reset_user_session(user_id)
            return
        
        # Update collection-specific notification settings
        collections = self.bot.user_settings.get(user_id_str, {}).get("collections", {})
        if collection_id not in collections:
            await message.answer("❌ Collection not found. Please try again.")
            self.bot.state_manager.reset_user_session(user_id)
            return
        
        collection = collections[collection_id]
        if "notification_settings" not in collection:
            from config import DEFAULT_BUY_MULTIPLIER, DEFAULT_SELL_MULTIPLIER
            collection["notification_settings"] = {
                "buy_multiplier": DEFAULT_BUY_MULTIPLIER,
                "sell_multiplier": DEFAULT_SELL_MULTIPLIER,
                "enabled": True
            }
        
        collection["notification_settings"]["buy_multiplier"] = multiplier
        self.bot.save_user_settings()
        self.bot.state_manager.reset_user_session(user_id)

        # Escape Markdown characters
        escaped_collection_name = escape_markdown(collection["collection_name"])
        escaped_stickerpack_name = escape_markdown(collection["stickerpack_name"])

        await message.answer(
            f"✅ **Buy Alert Updated**\n\n"
            f"📦 **Collection:** {escaped_collection_name}\n"
            f"📑 **Sticker Pack:** {escaped_stickerpack_name}\n\n"
            f"📈 **New Buy Alert:** {multiplier}x launch price\n\n"
            f"You'll receive notifications when prices drop to **{multiplier}x** the launch price ({collection['launch_price']} TON) or below.",
            parse_mode="Markdown",
        )

    async def process_sell_multiplier_input(self, message: types.Message, text: str):
        """Process sell multiplier input for specific collection"""
        if message.from_user == None:
            await message.answer("❌ Unexpected error occured! ")
            return
        user_id = message.from_user.id
        user_id_str = str(user_id)

        try:
            multiplier = float(text)
            if multiplier <= 0 or multiplier > 100:
                raise ValueError("Multiplier out of range")
        except ValueError:
            await message.answer(
                "❌ Invalid multiplier. Please enter a number between 0.1 and 100.\n\n"
                "Example: `3`, `2.5`, `5.0`\n\n"
                "Type /cancel to abort."
            )
            return

        # Get collection ID from session
        collection_data = self.bot.state_manager.get_collection_data(user_id)
        collection_id = getattr(collection_data, 'editing_collection_id', None)
        
        if not collection_id:
            await message.answer("❌ Collection ID not found. Please try again.")
            self.bot.state_manager.reset_user_session(user_id)
            return
        
        # Update collection-specific notification settings
        collections = self.bot.user_settings.get(user_id_str, {}).get("collections", {})
        if collection_id not in collections:
            await message.answer("❌ Collection not found. Please try again.")
            self.bot.state_manager.reset_user_session(user_id)
            return
        
        collection = collections[collection_id]
        if "notification_settings" not in collection:
            from config import DEFAULT_BUY_MULTIPLIER, DEFAULT_SELL_MULTIPLIER
            collection["notification_settings"] = {
                "buy_multiplier": DEFAULT_BUY_MULTIPLIER,
                "sell_multiplier": DEFAULT_SELL_MULTIPLIER,
                "enabled": True
            }
        
        collection["notification_settings"]["sell_multiplier"] = multiplier
        self.bot.save_user_settings()
        self.bot.state_manager.reset_user_session(user_id)

        # Escape Markdown characters
        escaped_collection_name = escape_markdown(collection["collection_name"])
        escaped_stickerpack_name = escape_markdown(collection["stickerpack_name"])

        await message.answer(
            f"✅ **Sell Alert Updated**\n\n"
            f"📦 **Collection:** {escaped_collection_name}\n"
            f"📑 **Sticker Pack:** {escaped_stickerpack_name}\n\n"
            f"📉 **New Sell Alert:** {multiplier}x launch price\n\n"
            f"You'll receive notifications when prices rise to **{multiplier}x** the launch price ({collection['launch_price']} TON) or above.",
            parse_mode="Markdown",
        )

    async def handle_confirmation(self, callback: types.CallbackQuery):
        """Handle confirmation callbacks"""
        if callback.data == None:
            logger.error("Callback.data is None")
            return
        action_parts = callback.data.split("_")

        if len(action_parts) < 2:
            await callback.answer("Invalid confirmation action", show_alert=True)
            return

        action = action_parts[1]

        if (
            action == "add"
            and len(action_parts) > 2
            and action_parts[2] == "collection"
        ):
            await self.confirm_add_collection(callback)
        elif (
            action == "cancel"
            and len(action_parts) > 2
            and action_parts[2] == "collection"
        ):
            await self.cancel_collection_creation(callback)
        elif action == "delete" and len(action_parts) > 2:
            collection_id = action_parts[2]
            await self.confirm_delete_collection(callback, collection_id)
        else:
            await callback.answer("Unknown confirmation action", show_alert=True)

    async def confirm_add_collection(self, callback: types.CallbackQuery):
        """Confirm and save new collection"""
        user_id = callback.from_user.id
        user_id_str = str(user_id)
        collection_data = self.bot.state_manager.get_collection_data(user_id)

        # Generate unique collection ID
        collection_id = str(uuid.uuid4())[:8]

        # Create collection entry with default notification settings
        from config import DEFAULT_BUY_MULTIPLIER, DEFAULT_SELL_MULTIPLIER
        new_collection = {
            "collection_name": collection_data.collection_name,
            "stickerpack_name": collection_data.stickerpack_name,
            "launch_price": collection_data.launch_price,
            "added_date": datetime.now().isoformat(),
            "notification_settings": {
                "buy_multiplier": DEFAULT_BUY_MULTIPLIER,
                "sell_multiplier": DEFAULT_SELL_MULTIPLIER,
                "enabled": True
            }
        }

        # Ensure user settings exist
        self.bot.ensure_user_settings(user_id_str)

        # Save to user settings
        self.bot.user_settings[user_id_str]["collections"][
            collection_id
        ] = new_collection
        self.bot.save_user_settings()

        # Reset user session
        self.bot.state_manager.reset_user_session(user_id)

        # Escape Markdown characters
        escaped_collection_name = escape_markdown(new_collection["collection_name"])
        escaped_stickerpack_name = escape_markdown(new_collection["stickerpack_name"])

        text = (
            f"🎉 **Collection Added Successfully!**\n\n"
            f"🏷️ Collection: **{escaped_collection_name}**\n"
            f"📑 Sticker Pack: **{escaped_stickerpack_name}**\n"
            f"💰 Launch Price: **{new_collection['launch_price']} TON**\n\n"
            f"🔔 You'll receive notifications when prices meet your thresholds.\n\n"
            f"Use /settings to manage your collections."
        )

        # Check is callback.message does not exist or is inaccessible
        if (
            isinstance(callback.message, InaccessibleMessage)
            or callback.message == None
        ):
            return "The message is no longer accessible"

        await callback.message.edit_text(text, parse_mode="Markdown")
        await callback.answer("Collection added!")

    async def cancel_collection_creation(self, callback: types.CallbackQuery):
        """Cancel collection creation"""
        user_id = callback.from_user.id
        self.bot.state_manager.reset_user_session(user_id)

        text = "❌ Collection creation cancelled.\n\nUse /settings to access the menu."

        # Check is callback.message does not exist or is inaccessible
        if (
            isinstance(callback.message, InaccessibleMessage)
            or callback.message == None
        ):
            return "The message is no longer accessible"

        await callback.message.edit_text(text)
        await callback.answer("Cancelled")

    async def confirm_delete_collection(
        self, callback: types.CallbackQuery, collection_id: str
    ):
        """Confirm and delete collection"""
        user_id = str(callback.from_user.id)

        if collection_id not in self.bot.user_settings[user_id]["collections"]:
            await callback.answer("Collection not found!", show_alert=True)
            return

        collection = self.bot.user_settings[user_id]["collections"][collection_id]
        del self.bot.user_settings[user_id]["collections"][collection_id]
        self.bot.save_user_settings()

        # Clean up notification history for this collection
        self.bot.notification_manager.cleanup_notifications_for_collection(
            user_id, collection_id
        )

        # Escape Markdown characters
        escaped_collection_name = escape_markdown(collection["collection_name"])
        escaped_stickerpack_name = escape_markdown(collection["stickerpack_name"])

        text = (
            f"🗑️ **Collection Deleted**\n\n"
            f"**{escaped_collection_name}** - **{escaped_stickerpack_name}** "
            f"has been removed from your watchlist.\n\n"
            f"Use /settings to manage your remaining collections."
        )

        # Check is callback.message does not exist or is inaccessible
        if (
            isinstance(callback.message, InaccessibleMessage)
            or callback.message == None
        ):
            return "The message is no longer accessible"

        await callback.message.edit_text(text, parse_mode="Markdown")
        await callback.answer("Collection deleted!")

    async def process_wall_ton_amount_input(self, message: types.Message, text: str):
        """Process wall TON amount input"""
        if message.from_user == None:
            await message.answer("❌ Unexpected error occured! ")
            return
        user_id = message.from_user.id

        try:
            amount = float(text)
            if amount <= 0 or amount > 100000:
                raise ValueError("Amount out of range")
        except ValueError:
            await message.answer(
                "❌ Invalid amount. Please enter a valid number between 0.01 and 100000 TON.\n\n"
                "Example: `10`, `25.5`, `100`\n\n"
                "Type /cancel to abort."
            )
            return

        # Store amount and get wall data
        self.bot.state_manager.update_wall_data(user_id, ton_amount=amount)
        wall_data = self.bot.state_manager.get_wall_data(user_id)

        # Validate we have required data
        if not wall_data.collection_name or not wall_data.stickerpack_name:
            await message.answer(
                "❌ Missing collection data. Please start over with /wall"
            )
            self.bot.state_manager.reset_user_session(user_id)
            return

        # Reset user session
        self.bot.state_manager.reset_user_session(user_id)

        # Calculate and display wall
        await self.calculate_and_display_wall(
            message,
            wall_data.collection_name,
            wall_data.stickerpack_name,
            wall_data.ton_amount,
        )

    async def calculate_and_display_wall(
        self,
        message: types.Message,
        collection_name: str,
        stickerpack_name: str,
        ton_amount: float,
    ):
        """Calculate and display wall analysis"""
        try:
            # Check if API client is available
            if not self.bot.api_client:
                await message.answer(
                    "❌ API client not available. Please try again later."
                )
                return

            # Fetch current price bundles from API
            bundle_data = await self.bot.api_client.fetch_price_bundles()
            if not bundle_data:
                await message.answer(
                    "❌ Failed to fetch price data. Please try again later."
                )
                return

            # Find matching collection+stickerpack (exact match)
            target_collection = None
            for item in bundle_data:
                if (
                    item.get("collectionName", "").lower() == collection_name.lower()
                    and item.get("characterName", "").lower()
                    == stickerpack_name.lower()
                ):
                    target_collection = item
                    break

            if not target_collection:
                await message.answer(
                    f"❌ No sticker pack found: **{escape_markdown(collection_name)}** - **{escape_markdown(stickerpack_name)}**\n\n"
                    f"Please check the collection and sticker pack names.",
                    parse_mode="Markdown",
                )
                return

            # Calculate wall for each marketplace
            marketplace_walls = {}

            for marketplace_info in target_collection.get("marketplaces", []):
                marketplace = marketplace_info.get("marketplace", "Unknown")
                prices = marketplace_info.get("prices", [])

                # Count prices under the specified amount
                wall_count = sum(
                    1
                    for price_item in prices
                    if price_item.get("price", 0) <= ton_amount
                )

                if wall_count > 0:
                    marketplace_walls[marketplace] = wall_count

            # Calculate total wall
            total_wall = sum(marketplace_walls.values())

            if total_wall == 0:
                await message.answer(
                    f"🧱 **Wall Analysis Results**\n\n"
                    f"🏷️ Collection: **{escape_markdown(collection_name)}**\n"
                    f"📑 Sticker Pack: **{escape_markdown(stickerpack_name)}**\n"
                    f"💰 Price Threshold: **{ton_amount} TON**\n\n"
                    f"❌ No sell orders found under **{ton_amount} TON**",
                    parse_mode="Markdown",
                )
                return

            # Format results
            result_text = (
                f"🧱 **Wall Analysis Results**\n\n"
                f"🏷️ Collection: **{escape_markdown(collection_name)}**\n"
                f"📑 Sticker Pack: **{escape_markdown(stickerpack_name)}**\n"
                f"💰 Price Threshold: **{ton_amount} TON**\n\n"
                f"📊 **Sell Orders Under {ton_amount} TON:**\n\n"
            )

            # Add marketplace breakdown
            for marketplace, count in sorted(marketplace_walls.items()):
                if count > 0:
                    count_display = f"{count}+" if count >= 20 else str(count)
                    marketplace_clean = clean_marketplace_name(marketplace)
                    result_text += f"🏪 **{escape_markdown(marketplace_clean)}:** {count_display}\n"

            # Add total
            total_display = f"{total_wall}+" if total_wall >= 20 else str(total_wall)
            result_text += f"\n🔢 **Total Wall:** {total_display} sell orders\n\n"

            if total_wall >= 20:
                result_text += "💡 *Note: Wall shows 20+ because each marketplace shows max 20 lowest offers*"

            await message.answer(result_text, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error calculating wall: {e}")
            await message.answer(
                "❌ Error calculating wall analysis. Please try again later."
            )

    async def handle_wall_callbacks(self, callback: types.CallbackQuery):
        """Handle wall-related callbacks"""
        if callback.data == None:
            logger.error("Callback.data is empty!")
            return
        action_parts = callback.data.split("_")

        if len(action_parts) < 2:
            await callback.answer("Invalid wall action", show_alert=True)
            return

        action = action_parts[1]

        if action == "collection" and len(action_parts) > 2:
            collection_index = int(action_parts[2])
            await self.handle_wall_collection_selection(callback, collection_index)
        elif action == "stickerpack" and len(action_parts) > 2:
            stickerpack_index = int(action_parts[2])
            await self.handle_wall_stickerpack_selection(callback, stickerpack_index)
        elif (
            action == "back"
            and len(action_parts) > 2
            and action_parts[2] == "to"
            and action_parts[3] == "collections"
        ):
            await self.handle_wall_back_to_collections(callback)
        elif action == "cancel":
            await self.handle_wall_cancel(callback)
        else:
            await callback.answer("Unknown wall action", show_alert=True)

    async def handle_wall_collection_selection(
        self, callback: types.CallbackQuery, collection_index: int
    ):
        """Handle collection selection for wall analysis"""
        user_id = callback.from_user.id
        wall_data = self.bot.state_manager.get_wall_data(user_id)

        if not wall_data.available_collections:
            await callback.answer("Collection data not available", show_alert=True)
            return

        sorted_collections = sorted(wall_data.available_collections.keys())

        if collection_index >= len(sorted_collections):
            await callback.answer("Invalid collection selection", show_alert=True)
            return

        selected_collection = sorted_collections[collection_index]
        stickerpacks = wall_data.available_collections[selected_collection]

        # Store selected collection
        self.bot.state_manager.update_wall_data(
            user_id, collection_name=selected_collection
        )

        if len(stickerpacks) == 1:
            # Only one stickerpack, skip selection and go to TON amount
            self.bot.state_manager.update_wall_data(
                user_id, stickerpack_name=stickerpacks[0]
            )
            await self.show_wall_ton_amount_input(
                callback, selected_collection, stickerpacks[0]
            )
        else:
            # Multiple stickerpacks, show selection
            self.bot.state_manager.set_user_state(
                user_id, UserState.WALL_SELECTING_STICKERPACK
            )
            await self.show_wall_stickerpack_selection(
                callback, selected_collection, stickerpacks
            )

    async def show_wall_stickerpack_selection(
        self, callback: types.CallbackQuery, collection_name: str, stickerpacks: list
    ):
        """Show stickerpack selection for wall analysis"""
        builder = InlineKeyboardBuilder()

        for i, stickerpack_name in enumerate(stickerpacks[:20]):  # Limit to 20
            builder.row(
                InlineKeyboardButton(
                    text=f"📑 {stickerpack_name}", callback_data=f"wall_stickerpack_{i}"
                )
            )

        builder.row(
            InlineKeyboardButton(
                text="⬅️ Back", callback_data="wall_back_to_collections"
            ),
            InlineKeyboardButton(text="❌ Cancel", callback_data="wall_cancel"),
        )

        # Escape Markdown characters
        escaped_collection_name = escape_markdown(collection_name)

        text = (
            f"🧱 **Wall Analysis**\n\n"
            f"📦 Collection: **{escaped_collection_name}**\n\n"
            f"Found **{len(stickerpacks)}** sticker packs in this collection.\n\n"
            f"📑 **Select a sticker pack:**"
        )

        # Check is callback.message does not exist or is inaccessible
        if (
            isinstance(callback.message, InaccessibleMessage)
            or callback.message == None
        ):
            return "The message is no longer accessible"

        await callback.message.edit_text(
            text, reply_markup=builder.as_markup(), parse_mode="Markdown"
        )

    async def handle_wall_stickerpack_selection(
        self, callback: types.CallbackQuery, stickerpack_index: int
    ):
        """Handle stickerpack selection for wall analysis"""
        user_id = callback.from_user.id
        wall_data = self.bot.state_manager.get_wall_data(user_id)

        if not wall_data.collection_name or not wall_data.available_collections:
            await callback.answer("Collection data not available", show_alert=True)
            return

        stickerpacks = wall_data.available_collections[wall_data.collection_name]

        if stickerpack_index >= len(stickerpacks):
            await callback.answer("Invalid stickerpack selection", show_alert=True)
            return

        selected_stickerpack = stickerpacks[stickerpack_index]

        # Store selected stickerpack
        self.bot.state_manager.update_wall_data(
            user_id, stickerpack_name=selected_stickerpack
        )

        await self.show_wall_ton_amount_input(
            callback, wall_data.collection_name, selected_stickerpack
        )

    async def show_wall_ton_amount_input(
        self, callback: types.CallbackQuery, collection_name: str, stickerpack_name: str
    ):
        """Show TON amount input for wall analysis"""
        user_id = callback.from_user.id

        # Set state to wait for TON amount input
        self.bot.state_manager.set_user_state(user_id, UserState.WALL_TON_AMOUNT)

        # Escape Markdown characters
        escaped_collection_name = escape_markdown(collection_name)
        escaped_stickerpack_name = escape_markdown(stickerpack_name)

        text = (
            f"🧱 **Wall Analysis**\n\n"
            f"📦 Collection: **{escaped_collection_name}**\n"
            f"📑 Sticker Pack: **{escaped_stickerpack_name}**\n\n"
            f"💰 **Enter TON amount** for wall analysis:\n\n"
            f"Example: `10`, `25.5`, `100`\n\n"
            f"💡 This will count sell orders under this price.\n\n"
            f"Type /cancel to abort this process."
        )

        # Check is callback.message does not exist or is inaccessible
        if (
            isinstance(callback.message, InaccessibleMessage)
            or callback.message == None
        ):
            return "The message is no longer accessible"

        await callback.message.edit_text(text, parse_mode="Markdown")

    async def handle_wall_cancel(self, callback: types.CallbackQuery):
        """Handle wall analysis cancellation"""
        user_id = callback.from_user.id
        self.bot.state_manager.reset_user_session(user_id)

        # Check is callback.message does not exist or is inaccessible
        if (
            isinstance(callback.message, InaccessibleMessage)
            or callback.message == None
        ):
            return "The message is no longer accessible"

        await callback.message.edit_text(
            "❌ Wall analysis cancelled.\n\nUse /wall to start again."
        )
        await callback.answer("Cancelled")

    async def handle_wall_back_to_collections(self, callback: types.CallbackQuery):
        """Handle back to collections from stickerpack selection"""
        user_id = callback.from_user.id
        wall_data = self.bot.state_manager.get_wall_data(user_id)

        if not wall_data.available_collections:
            await callback.answer("Collection data not available", show_alert=True)
            return

        # Reset to collection selection state
        self.bot.state_manager.set_user_state(
            user_id, UserState.WALL_SELECTING_COLLECTION
        )
        self.bot.state_manager.update_wall_data(
            user_id, collection_name=None, stickerpack_name=None
        )

        # Show collection selection again
        builder = InlineKeyboardBuilder()
        sorted_collections = sorted(wall_data.available_collections.keys())

        for i, collection_name in enumerate(sorted_collections[:20]):  # Limit to 20
            builder.row(
                InlineKeyboardButton(
                    text=f"📦 {collection_name}", callback_data=f"wall_collection_{i}"
                )
            )

        builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="wall_cancel"))

        text = (
            "🧱 **Wall Analysis**\n\n"
            f"Found **{len(wall_data.available_collections)}** collections with sticker packs.\n\n"
            "📦 **Select a collection:**"
        )

        # Check is callback.message does not exist or is inaccessible
        if (
            isinstance(callback.message, InaccessibleMessage)
            or callback.message == None
        ):
            return "The message is no longer accessible"

        await callback.message.edit_text(
            text, reply_markup=builder.as_markup(), parse_mode="Markdown"
        )
        await callback.answer("Back to collections")

    async def handle_sticker_callbacks(self, callback: types.CallbackQuery):
        """Handle sticker-related callbacks"""
        if callback.data is None:
            logger.error("Callback data is None")
            return
        
        action_parts = callback.data.split("_")
        if len(action_parts) < 2:
            await callback.answer("Invalid sticker action", show_alert=True)
            return
        
        action = action_parts[1]
        
        try:
            if action == "select" and len(action_parts) > 3:
                if action_parts[2] == "collection":
                    # Collection selected for analysis
                    collection_index = int(action_parts[3])
                    await self.handle_collection_selected(callback, collection_index)
                elif action_parts[2] == "for" and action_parts[3] == "details":
                    # Collection selected for sticker details
                    collection_index = int(action_parts[4])
                    await self.handle_collection_selected_for_details(callback, collection_index)
            elif action == "sticker" and len(action_parts) > 3:
                # Specific sticker selected - format: sticker_sticker_{collection_index}_{sticker_index}
                await self.handle_sticker_selected(callback)
            elif action == "back":
                if len(action_parts) > 2 and action_parts[2] == "to":
                    if action_parts[3] == "collections":
                        if len(action_parts) > 4 and action_parts[4] == "details":
                            # Back to collections from sticker details flow
                            await self.cmd_sticker_details_callback(callback)
                        else:
                            # Back to collections from collection analysis
                            await self.cmd_collection_analysis_callback(callback)
            elif action == "cancel":
                await self.handle_sticker_cancel(callback)
            else:
                await callback.answer("Unknown sticker action", show_alert=True)
                
        except Exception as e:
            logger.error(f"Error in sticker callback: {e}")
            await callback.answer("❌ Error processing request", show_alert=True)
    
    async def handle_collection_selected(self, callback: types.CallbackQuery, collection_index: int):
        """Handle collection selection for analysis"""
        try:
            collections = await self.get_collections_cache()
            if not collections or collection_index >= len(collections):
                await callback.answer("Collection not found", show_alert=True)
                return
            
            sorted_collections = sorted(collections, key=lambda c: c.name.lower())
            selected_collection = sorted_collections[collection_index]
            
            # Generate collection summary
            summary = self.sticker_client.generate_collection_summary(selected_collection)
            
            # Add back button
            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(
                    text="⬅️ Back to Collections", 
                    callback_data="sticker_back_to_collections"
                )
            )
            
            if isinstance(callback.message, InaccessibleMessage) or callback.message is None:
                return "The message is no longer accessible"
            
            await callback.message.edit_text(
                summary, 
                reply_markup=builder.as_markup(), 
                parse_mode=ParseMode.MARKDOWN_V2
            )
            await callback.answer()
            
        except Exception as e:
            logger.error(f"Error handling collection selection: {e}")
            await callback.answer("❌ Error analyzing collection", show_alert=True)
    
    async def handle_collection_selected_for_details(self, callback: types.CallbackQuery, collection_index: int):
        """Handle collection selection for sticker details"""
        try:
            collections = await self.get_collections_cache()
            if not collections or collection_index >= len(collections):
                await callback.answer("Collection not found", show_alert=True)
                return
            
            sorted_collections = sorted(collections, key=lambda c: c.name.lower())
            selected_collection = sorted_collections[collection_index]
            
            if not selected_collection.stickers:
                await callback.answer("No stickers found in this collection", show_alert=True)
                return
            
            # Show stickers in this collection
            builder = InlineKeyboardBuilder()
            
            # Sort stickers by name
            sorted_stickers = sorted(selected_collection.stickers, key=lambda s: s.name.lower())
            
            for i, sticker in enumerate(sorted_stickers[:20]):  # Limit to 20
                builder.row(
                    InlineKeyboardButton(
                        text=f"🎯 {sticker.name}",
                        callback_data=f"sticker_sticker_{collection_index}_{i}"
                    )
                )
            
            builder.row(
                InlineKeyboardButton(
                    text="⬅️ Back to Collections", 
                    callback_data="sticker_back_to_collections_details"
                )
            )
            
            text = (
                f"🎯 *{escape_markdown(selected_collection.name)}*\n\n"
                f"Found *{escape_markdown(str(len(selected_collection.stickers)))}* stickers\\.\n\n"
                "🎯 *Select a sticker for detailed analysis:*"
            )
            
            if isinstance(callback.message, InaccessibleMessage) or callback.message is None:
                return "The message is no longer accessible"
            
            await callback.message.edit_text(
                text, 
                reply_markup=builder.as_markup(), 
                parse_mode=ParseMode.MARKDOWN_V2
            )
            await callback.answer()
            
        except Exception as e:
            logger.error(f"Error handling collection selection for details: {e}")
            await callback.answer("❌ Error loading stickers", show_alert=True)
    
    async def handle_sticker_selected(self, callback: types.CallbackQuery):
        """Handle specific sticker selection"""
        try:
            # Parse collection and sticker indices from callback data
            # Format: sticker_sticker_{collection_index}_{sticker_index}
            action_parts = callback.data.split("_")
            if len(action_parts) < 4:
                await callback.answer("Invalid sticker selection", show_alert=True)
                return
            
            collection_index = int(action_parts[2])
            sticker_index = int(action_parts[3])
            
            collections = await self.get_collections_cache()
            if not collections or collection_index >= len(collections):
                await callback.answer("Collection not found", show_alert=True)
                return
            
            sorted_collections = sorted(collections, key=lambda c: c.name.lower())
            selected_collection = sorted_collections[collection_index]
            
            sorted_stickers = sorted(selected_collection.stickers, key=lambda s: s.name.lower())
            if sticker_index >= len(sorted_stickers):
                await callback.answer("Sticker not found", show_alert=True)
                return
            
            selected_sticker = sorted_stickers[sticker_index]
            
            # Generate sticker details
            details = self.sticker_client.generate_sticker_details(selected_sticker)
            
            # Add back button
            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(
                    text="⬅️ Back to Stickers", 
                    callback_data=f"sticker_select_for_details_{collection_index}"
                ),
                InlineKeyboardButton(
                    text="📦 Collection Info", 
                    callback_data=f"sticker_select_collection_{collection_index}"
                )
            )
            
            if isinstance(callback.message, InaccessibleMessage) or callback.message is None:
                return "The message is no longer accessible"
            
            await callback.message.edit_text(
                details, 
                reply_markup=builder.as_markup(), 
                parse_mode=ParseMode.MARKDOWN_V2
            )
            await callback.answer()
            
        except Exception as e:
            logger.error(f"Error handling sticker selection: {e}")
            await callback.answer("❌ Error analyzing sticker", show_alert=True)
    
    async def handle_sticker_cancel(self, callback: types.CallbackQuery):
        """Handle sticker analysis cancellation"""
        if isinstance(callback.message, InaccessibleMessage) or callback.message is None:
            return "The message is no longer accessible"
        
        await callback.message.edit_text("❌ Sticker analysis cancelled.")
        await callback.answer("Cancelled")
    
    async def cmd_collection_analysis_callback(self, callback: types.CallbackQuery):
        """Show collection selection menu from callback"""
        try:
            # Get collections cache
            collections = await self.get_collections_cache()
            if not collections:
                await callback.answer("❌ Failed to fetch collections data", show_alert=True)
                return
            
            # Sort collections by name
            sorted_collections = sorted(collections, key=lambda c: c.name.lower())
            
            # Create inline keyboard with collections (20 per page)
            builder = InlineKeyboardBuilder()
            
            for i, collection in enumerate(sorted_collections[:20]):  # Limit to 20
                builder.row(
                    InlineKeyboardButton(
                        text=f"📦 {collection.name}",
                        callback_data=f"sticker_select_collection_{i}"
                    )
                )
            
            builder.row(
                InlineKeyboardButton(
                    text="❌ Cancel", 
                    callback_data="sticker_cancel"
                )
            )
            
            text = (
                "📊 **Collection Analysis**\n\n"
                f"Found **{len(sorted_collections)}** collections.\n\n"
                "📦 **Select a collection to analyze:**"
            )
            
            if isinstance(callback.message, InaccessibleMessage) or callback.message is None:
                return "The message is no longer accessible"
            
            await callback.message.edit_text(
                text, 
                reply_markup=builder.as_markup(), 
                parse_mode=ParseMode.MARKDOWN
            )
            await callback.answer()
            
        except Exception as e:
            logger.error(f"Error in collection analysis callback: {e}")
            await callback.answer("❌ Error loading collections", show_alert=True)
    
    async def cmd_sticker_details_callback(self, callback: types.CallbackQuery):
        """Show collection selection menu for sticker details from callback"""
        try:
            # Get collections cache
            collections = await self.get_collections_cache()
            if not collections:
                await callback.answer("❌ Failed to fetch collections data", show_alert=True)
                return
            
            # Sort collections by name
            sorted_collections = sorted(collections, key=lambda c: c.name.lower())
            
            # Create inline keyboard with collections (20 per page)
            builder = InlineKeyboardBuilder()
            
            for i, collection in enumerate(sorted_collections[:20]):  # Limit to 20
                builder.row(
                    InlineKeyboardButton(
                        text=f"📦 {collection.name}",
                        callback_data=f"sticker_select_for_details_{i}"
                    )
                )
            
            builder.row(
                InlineKeyboardButton(
                    text="❌ Cancel", 
                    callback_data="sticker_cancel"
                )
            )
            
            text = (
                "🎯 **Sticker Analysis**\n\n"
                f"Found **{len(sorted_collections)}** collections.\n\n"
                "📦 **Select a collection to see its stickers:**"
            )
            
            if isinstance(callback.message, InaccessibleMessage) or callback.message is None:
                return "The message is no longer accessible"
            
            await callback.message.edit_text(
                text, 
                reply_markup=builder.as_markup(), 
                parse_mode=ParseMode.MARKDOWN
            )
            await callback.answer()
            
        except Exception as e:
            logger.error(f"Error in sticker details callback: {e}")
            await callback.answer("❌ Error loading collections", show_alert=True)
    
    async def handle_edit_callbacks(self, callback: types.CallbackQuery):
        """Handle edit-related callbacks"""
        if callback.data is None:
            logger.error("Callback data is None")
            return
        
        action_parts = callback.data.split("_")
        if len(action_parts) < 3:
            await callback.answer("Invalid edit action", show_alert=True)
            return
        
        action = action_parts[1]
        
        try:
            if action == "notifications" and len(action_parts) > 2:
                collection_id = action_parts[2]
                await self.show_notification_settings_details(callback, collection_id)
            elif action == "buy" and len(action_parts) > 3 and action_parts[2] == "multiplier":
                collection_id = action_parts[3]
                await self.start_edit_buy_multiplier(callback, collection_id)
            elif action == "sell" and len(action_parts) > 3 and action_parts[2] == "multiplier":
                collection_id = action_parts[3]
                await self.start_edit_sell_multiplier(callback, collection_id)
            else:
                await callback.answer("Unknown edit action", show_alert=True)
                
        except Exception as e:
            logger.error(f"Error in edit callback: {e}")
            await callback.answer("❌ Error processing request", show_alert=True)
    
    async def handle_toggle_callbacks(self, callback: types.CallbackQuery):
        """Handle toggle-related callbacks"""
        if callback.data is None:
            logger.error("Callback data is None")
            return
        
        action_parts = callback.data.split("_")
        if len(action_parts) < 3:
            await callback.answer("Invalid toggle action", show_alert=True)
            return
        
        action = action_parts[1]
        
        try:
            if action == "notifications" and len(action_parts) > 2:
                collection_id = action_parts[2]
                await self.toggle_collection_notifications(callback, collection_id)
            else:
                await callback.answer("Unknown toggle action", show_alert=True)
                
        except Exception as e:
            logger.error(f"Error in toggle callback: {e}")
            await callback.answer("❌ Error processing request", show_alert=True)
    
    async def show_notification_settings_details(self, callback: types.CallbackQuery, collection_id: str):
        """Show detailed notification settings for a collection"""
        user_id = str(callback.from_user.id)
        collections = self.bot.user_settings.get(user_id, {}).get("collections", {})
        
        if collection_id not in collections:
            await callback.answer("Collection not found!", show_alert=True)
            return
        
        collection = collections[collection_id]
        
        # Ensure notification settings exist
        if "notification_settings" not in collection:
            from config import DEFAULT_BUY_MULTIPLIER, DEFAULT_SELL_MULTIPLIER
            collection["notification_settings"] = {
                "buy_multiplier": DEFAULT_BUY_MULTIPLIER,
                "sell_multiplier": DEFAULT_SELL_MULTIPLIER,
                "enabled": True
            }
            self.bot.save_user_settings()
        
        notification_settings = collection["notification_settings"]
        enabled_status = "✅ Enabled" if notification_settings.get("enabled", True) else "❌ Disabled"
        
        # Escape Markdown characters
        escaped_collection_name = escape_markdown(collection["collection_name"])
        escaped_stickerpack_name = escape_markdown(collection["stickerpack_name"])
        
        text = (
            f"🔔 **Notification Settings**\n\n"
            f"📦 **Collection:** {escaped_collection_name}\n"
            f"📑 **Sticker Pack:** {escaped_stickerpack_name}\n"
            f"💰 **Launch Price:** {collection['launch_price']} TON\n\n"
            f"🔔 **Status:** {enabled_status}\n"
            f"📈 **Buy Alert:** {notification_settings['buy_multiplier']}x launch price\n"
            f"📉 **Sell Alert:** {notification_settings['sell_multiplier']}x launch price\n\n"
            f"💡 **How it works:**\n"
            f"• Buy alerts trigger when price drops to {notification_settings['buy_multiplier']}x launch price or below\n"
            f"• Sell alerts trigger when price rises to {notification_settings['sell_multiplier']}x launch price or above\n\n"
            f"Use the buttons below to customize these settings:"
        )
        
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text=f"📈 Edit Buy Alert ({notification_settings['buy_multiplier']}x)",
                callback_data=f"edit_buy_multiplier_{collection_id}",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=f"📉 Edit Sell Alert ({notification_settings['sell_multiplier']}x)",
                callback_data=f"edit_sell_multiplier_{collection_id}",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=f"🔔 {enabled_status}",
                callback_data=f"toggle_notifications_{collection_id}",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="⬅️ Back to Collection",
                callback_data=f"collection_edit_{collection_id}",
            )
        )
        
        if isinstance(callback.message, InaccessibleMessage) or callback.message is None:
            return "The message is no longer accessible"
        
        await callback.message.edit_text(
            text, 
            reply_markup=builder.as_markup(), 
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()
    
    async def toggle_collection_notifications(self, callback: types.CallbackQuery, collection_id: str):
        """Toggle notifications on/off for a collection"""
        user_id = str(callback.from_user.id)
        collections = self.bot.user_settings.get(user_id, {}).get("collections", {})
        
        if collection_id not in collections:
            await callback.answer("Collection not found!", show_alert=True)
            return
        
        collection = collections[collection_id]
        
        # Ensure notification settings exist
        if "notification_settings" not in collection:
            from config import DEFAULT_BUY_MULTIPLIER, DEFAULT_SELL_MULTIPLIER
            collection["notification_settings"] = {
                "buy_multiplier": DEFAULT_BUY_MULTIPLIER,
                "sell_multiplier": DEFAULT_SELL_MULTIPLIER,
                "enabled": True
            }
        
        # Toggle enabled status
        current_status = collection["notification_settings"].get("enabled", True)
        collection["notification_settings"]["enabled"] = not current_status
        self.bot.save_user_settings()
        
        new_status = "enabled" if not current_status else "disabled"
        await callback.answer(f"✅ Notifications {new_status}!")
        
        # Refresh the notification settings view
        await self.show_notification_settings_details(callback, collection_id)
    
    async def start_edit_buy_multiplier(self, callback: types.CallbackQuery, collection_id: str):
        """Start editing buy multiplier for a collection"""
        user_id = callback.from_user.id
        user_id_str = str(user_id)
        collections = self.bot.user_settings.get(user_id_str, {}).get("collections", {})
        
        if collection_id not in collections:
            await callback.answer("Collection not found!", show_alert=True)
            return
        
        collection = collections[collection_id]
        current_multiplier = collection.get("notification_settings", {}).get("buy_multiplier", 2.0)
        
        # Reset any existing flow and start new one
        self.bot.state_manager.reset_user_session(user_id)
        self.bot.state_manager.set_user_state(user_id, UserState.EDITING_BUY_MULTIPLIER)
        
        # Store collection ID for later use
        self.bot.state_manager.update_collection_data(user_id, editing_collection_id=collection_id)
        
        # Escape Markdown characters
        escaped_collection_name = escape_markdown(collection["collection_name"])
        escaped_stickerpack_name = escape_markdown(collection["stickerpack_name"])
        
        text = (
            f"📈 **Edit Buy Alert Multiplier**\n\n"
            f"📦 **Collection:** {escaped_collection_name}\n"
            f"📑 **Sticker Pack:** {escaped_stickerpack_name}\n"
            f"💰 **Launch Price:** {collection['launch_price']} TON\n\n"
            f"Current buy alert: **{current_multiplier}x**\n\n"
            f"Enter the new multiplier for buy alerts.\n"
            f"You'll get notified when prices drop to this multiple of the launch price or below.\n\n"
            f"Example: `2` (for 2x launch price), `1.5`, `3.0`\n\n"
            f"Valid range: 0.1 to 100\n\n"
            f"Type /cancel to abort this change."
        )
        
        if isinstance(callback.message, InaccessibleMessage) or callback.message is None:
            return "The message is no longer accessible"
        
        await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN)
        await callback.answer()

    async def cmd_scheduler_status(self, message: types.Message):
        """Show daily reports scheduler status"""
        try:
            if not hasattr(self.bot, 'daily_reports_scheduler') or not self.bot.daily_reports_scheduler:
                await message.answer("❌ Daily reports scheduler is not initialized")
                return
                
            status = self.bot.daily_reports_scheduler.get_scheduler_status()
            
            status_emoji = "✅" if status["running"] else "❌"
            status_text = "Running" if status["running"] else "Stopped"
            
            # Get time mapping info
            time_info = []
            for time_pref, hour in status["time_mappings"].items():
                time_info.append(f"• {time_pref.title()}: {hour:02d}:00")
            
            # Get next report times for this user
            user_id = str(message.from_user.id)
            next_report_info = ""
            if user_id in self.bot.user_settings:
                try:
                    next_time = self.bot.daily_reports_scheduler.get_next_report_time(user_id)
                    if next_time:
                        next_report_info = f"\n🕐 **Your Next Report:** {next_time.strftime('%Y-%m-%d %H:%M %Z')}"
                    else:
                        next_report_info = "\n⏸️ **Your Daily Reports:** Disabled"
                except Exception as e:
                    logger.error(f"Error getting next report time: {e}")
                    next_report_info = "\n❌ **Error calculating next report time**"
            
            text = (
                f"📊 **Daily Reports Scheduler Status**\n\n"
                f"{status_emoji} **Status:** {status_text}\n"
                f"👥 **Enabled Users:** {status['enabled_users']}\n"
                f"🌍 **Server Timezone:** {status['timezone']}\n\n"
                f"⏰ **Time Mappings:**\n" + "\n".join(time_info) + 
                next_report_info
            )
            
            await message.answer(text, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"Error in scheduler_status command: {e}")
            await message.answer("❌ Error retrieving scheduler status")

    async def cmd_test_daily_report(self, message: types.Message):
        """Test daily report generation for the current user"""
        try:
            user_id = str(message.from_user.id)
            
            # Check if user has daily reports enabled
            self.bot.ensure_user_settings(user_id)
            daily_reports = self.bot.user_settings[user_id]["daily_reports"]
            
            if not daily_reports.get("enabled", False):
                await message.answer(
                    "❌ **Daily Reports Disabled**\n\n"
                    "Please enable daily reports in /settings first.",
                    parse_mode="Markdown"
                )
                return
            
            time_preference = daily_reports.get("time_preference", "morning")
            
            # Send test report
            if hasattr(self.bot, 'daily_reports_scheduler') and self.bot.daily_reports_scheduler:
                await message.answer(
                    f"🧪 **Testing Daily Market Overview**\n\n"
                    f"Generating test market overview for {time_preference} preference...",
                    parse_mode="Markdown"
                )
                
                try:
                    await self.bot.daily_reports_scheduler._send_daily_report(
                        int(user_id), time_preference
                    )
                    await message.answer("✅ Test daily report sent successfully!")
                except Exception as e:
                    logger.error(f"Error sending test daily report: {e}")
                    await message.answer(f"❌ Error sending test report: {str(e)}")
            else:
                await message.answer("❌ Daily reports scheduler is not available")
                
        except Exception as e:
            logger.error(f"Error in test_daily_report command: {e}")
            await message.answer("❌ Error testing daily market overview")
    
    async def start_edit_sell_multiplier(self, callback: types.CallbackQuery, collection_id: str):
        """Start editing sell multiplier for a collection"""
        user_id = callback.from_user.id
        user_id_str = str(user_id)
        collections = self.bot.user_settings.get(user_id_str, {}).get("collections", {})
        
        if collection_id not in collections:
            await callback.answer("Collection not found!", show_alert=True)
            return
        
        collection = collections[collection_id]
        current_multiplier = collection.get("notification_settings", {}).get("sell_multiplier", 3.0)
        
        # Reset any existing flow and start new one
        self.bot.state_manager.reset_user_session(user_id)
        self.bot.state_manager.set_user_state(user_id, UserState.EDITING_SELL_MULTIPLIER)
        
        # Store collection ID for later use
        self.bot.state_manager.update_collection_data(user_id, editing_collection_id=collection_id)
        
        # Escape Markdown characters
        escaped_collection_name = escape_markdown(collection["collection_name"])
        escaped_stickerpack_name = escape_markdown(collection["stickerpack_name"])
        
        text = (
            f"📉 **Edit Sell Alert Multiplier**\n\n"
            f"📦 **Collection:** {escaped_collection_name}\n"
            f"📑 **Sticker Pack:** {escaped_stickerpack_name}\n"
            f"💰 **Launch Price:** {collection['launch_price']} TON\n\n"
            f"Current sell alert: **{current_multiplier}x**\n\n"
            f"Enter the new multiplier for sell alerts.\n"
            f"You'll get notified when prices rise to this multiple of the launch price or above.\n\n"
            f"Example: `3` (for 3x launch price), `2.5`, `5.0`\n\n"
            f"Valid range: 0.1 to 100\n\n"
            f"Type /cancel to abort this change."
        )
        
        if isinstance(callback.message, InaccessibleMessage) or callback.message is None:
            return "The message is no longer accessible"
        
        await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN)
        await callback.answer()

    async def cmd_scheduler_status(self, message: types.Message):
        """Show daily reports scheduler status"""
        try:
            if not hasattr(self.bot, 'daily_reports_scheduler') or not self.bot.daily_reports_scheduler:
                await message.answer("❌ Daily reports scheduler is not initialized")
                return
                
            status = self.bot.daily_reports_scheduler.get_scheduler_status()
            
            status_emoji = "✅" if status["running"] else "❌"
            status_text = "Running" if status["running"] else "Stopped"
            
            # Get time mapping info
            time_info = []
            for time_pref, hour in status["time_mappings"].items():
                time_info.append(f"• {time_pref.title()}: {hour:02d}:00")
            
            # Get next report times for this user
            user_id = str(message.from_user.id)
            next_report_info = ""
            if user_id in self.bot.user_settings:
                try:
                    next_time = self.bot.daily_reports_scheduler.get_next_report_time(user_id)
                    if next_time:
                        next_report_info = f"\n🕐 **Your Next Report:** {next_time.strftime('%Y-%m-%d %H:%M %Z')}"
                    else:
                        next_report_info = "\n⏸️ **Your Daily Reports:** Disabled"
                except Exception as e:
                    logger.error(f"Error getting next report time: {e}")
                    next_report_info = "\n❌ **Error calculating next report time**"
            
            text = (
                f"📊 **Daily Reports Scheduler Status**\n\n"
                f"{status_emoji} **Status:** {status_text}\n"
                f"👥 **Enabled Users:** {status['enabled_users']}\n"
                f"🌍 **Server Timezone:** {status['timezone']}\n\n"
                f"⏰ **Time Mappings:**\n" + "\n".join(time_info) + 
                next_report_info
            )
            
            await message.answer(text, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"Error in scheduler_status command: {e}")
            await message.answer("❌ Error retrieving scheduler status")

    async def cmd_test_daily_report(self, message: types.Message):
        """Test daily report generation for the current user"""
        try:
            user_id = str(message.from_user.id)
            
            # Check if user has daily reports enabled
            self.bot.ensure_user_settings(user_id)
            daily_reports = self.bot.user_settings[user_id]["daily_reports"]
            
            if not daily_reports.get("enabled", False):
                await message.answer(
                    "❌ **Daily Reports Disabled**\n\n"
                    "Please enable daily reports in /settings first.",
                    parse_mode="Markdown"
                )
                return
            
            time_preference = daily_reports.get("time_preference", "morning")
            
            # Send test report
            if hasattr(self.bot, 'daily_reports_scheduler') and self.bot.daily_reports_scheduler:
                await message.answer(
                    f"🧪 **Testing Daily Market Overview**\n\n"
                    f"Generating test market overview for {time_preference} preference...",
                    parse_mode="Markdown"
                )
                
                try:
                    await self.bot.daily_reports_scheduler._send_daily_report(
                        int(user_id), time_preference
                    )
                    await message.answer("✅ Test daily report sent successfully!")
                except Exception as e:
                    logger.error(f"Error sending test daily report: {e}")
                    await message.answer(f"❌ Error sending test report: {str(e)}")
            else:
                await message.answer("❌ Daily reports scheduler is not available")
                
        except Exception as e:
            logger.error(f"Error in test_daily_report command: {e}")
            await message.answer("❌ Error testing daily market overview")
