import logging
import uuid
from datetime import datetime
from aiogram import F, types
from aiogram.filters import Command
from aiogram.types import (
    InaccessibleMessage,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from auth import require_whitelisted_user
from user_states import UserState
from utils import escape_markdown, clean_marketplace_name

from datetime import datetime

logger = logging.getLogger(__name__)


class BotHandlers:
    def __init__(self, bot_instance):
        self.bot = bot_instance

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
        self.bot.dp.callback_query(F.data.startswith("confirm_"))(
            require_whitelisted_user(self.handle_confirmation)
        )
        self.bot.dp.callback_query(F.data.startswith("wall_"))(
            require_whitelisted_user(self.handle_wall_callbacks)
        )

        # Text message handlers for user input flows
        self.bot.dp.message(F.text & ~F.text.startswith("/"))(
            require_whitelisted_user(self.handle_text_input)
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

        welcome_text = (
            "🔔 Welcome to Sticker Price Notifier Bot!\n\n"
            "I'll help you track Telegram sticker pack prices and notify you when they reach your target levels.\n\n"
            "Use /settings to configure your collections and notification preferences."
        )

        await message.answer(welcome_text)

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
        from modules.google_sheets.sheets_client import SheetsClient
        from config import GOOGLE_SHEETS_KEY, GOOGLE_CREDENTIALS_PATH

        # Validate prerequisites
        if not GOOGLE_SHEETS_KEY:
            await message.answer("❌ Google Sheets key not configured in environment")
            return

        if not self.bot.api_client:
            await message.answer("❌ API client not available")
            return

        # Send processing message
        status_msg = await message.answer(
            "🔄 **Updating floor prices...**\n\nInitializing...",
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

            await status_msg.edit_text(
                "🔄 **Updating floor prices...**\n\n📊 Fetching current price data...",
                parse_mode="Markdown",
            )

            # Get cached price bundles (uses existing cache mechanism)
            bundle_data = await self.bot.api_client.fetch_price_bundles()
            if not bundle_data:
                await status_msg.edit_text(
                    "❌ Failed to fetch price data from scanner API"
                )
                return

            await status_msg.edit_text(
                "🔄 **Updating floor prices...**\n\n📋 Loading worksheets...",
                parse_mode="Markdown",
            )

            # Get all worksheets
            worksheets = sheets_client.get_all_worksheets(GOOGLE_SHEETS_KEY)
            if not worksheets:
                await status_msg.edit_text("❌ No worksheets found in Google Sheets")
                return

            # Track results
            results = {"updated": 0, "skipped": 0, "errors": 0, "details": []}

            # Process each worksheet
            for i, worksheet in enumerate(worksheets):
                await status_msg.edit_text(
                    f"🔄 **Updating floor prices...**\n\n"
                    f"📝 Processing worksheet {i+1}/{len(worksheets)}: {worksheet.title}",
                    parse_mode="Markdown",
                )

                # Get collection info
                collection_name, stickerpack_name = sheets_client.get_collection_info(
                    worksheet
                )

                if not collection_name or not stickerpack_name:
                    results["skipped"] += 1
                    results["details"].append(
                        f"⚠️ {worksheet.title}: Missing collection/stickerpack info"
                    )
                    continue

                # Find matching collection in API data
                matching_bundle = self.bot.api_client.find_collection_by_names(
                    bundle_data, collection_name, stickerpack_name
                )

                if not matching_bundle:
                    results["skipped"] += 1
                    results["details"].append(
                        f"⚠️ {worksheet.title}: No API data for {collection_name} - {stickerpack_name}"
                    )
                    continue

                # Get lowest price
                floor_price = self.bot.api_client.get_lowest_price(matching_bundle)
                if floor_price is None:
                    results["errors"] += 1
                    results["details"].append(
                        f"❌ {worksheet.title}: No price data available"
                    )
                    continue

                # Update floor price
                if sheets_client.update_floor_price(worksheet, floor_price):
                    results["updated"] += 1
                    results["details"].append(
                        f"✅ {worksheet.title}: Updated to {floor_price} TON"
                    )
                else:
                    results["errors"] += 1
                    results["details"].append(f"❌ {worksheet.title}: Failed to update")

            # Format final summary
            summary_text = (
                f"📊 **Floor Price Update Complete**\n\n"
                f"✅ **Updated:** {results['updated']} worksheets\n"
                f"⚠️ **Skipped:** {results['skipped']} worksheets\n"
                f"❌ **Errors:** {results['errors']} worksheets\n\n"
            )

            # Add details (limit to avoid message length issues)
            if results["details"]:
                summary_text += "**Details:**\n"
                for detail in results["details"][:10]:  # Show max 10 details
                    summary_text += f"{detail}\n"

                if len(results["details"]) > 10:
                    summary_text += f"\n... and {len(results['details']) - 10} more"

            await status_msg.edit_text(summary_text, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error in update_floor command: {e}")
            await status_msg.edit_text(f"❌ Unexpected error: {str(e)}")

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
                parse_mode="MarkdownV2",
            )

            # Generate report
            report_text = self.format_report(report_data)

            # Split message if too long (Telegram limit is 4096 characters)
            if len(report_text) <= 4096:
                await status_msg.edit_text(report_text, parse_mode="Markdown")
            else:
                # Send in parts
                await status_msg.edit_text(
                    "📊 **Report Generated**\n\nSending report in parts...",
                    parse_mode="Markdown",
                )

                # Split into chunks
                chunks = self.split_report(report_text, 4000)  # Leave some margin
                for i, chunk in enumerate(chunks):
                    if i == 0:
                        await status_msg.edit_text(chunk)
                    else:
                        await message.answer(chunk)

        except Exception as e:
            logger.error(f"Error in report command: {e}")
            await status_msg.edit_text(f"❌ Unexpected error: {str(e)}")

    def format_report(self, report_data: list) -> str:
        """Format report data into the required text format"""

        # First dateline
        dateline = [f"*{datetime.now()}*"]

        dateline.append("")  # Empty line after line with report date and time

        # Individual collection details
        total_unrealized_pnl = 0.0
        total_spent = 0.0
        total_realized_pnl = 0.0

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

            # Calculate total spent for this collection
            total_spent += collection_spent
            total_unrealized_pnl += unrealized_pnl
            total_realized_pnl += realized_pnl

            # Format the collection section
            dateline.append(f"{collection_name} {stickerpack_name}:")
            dateline.append(f"FP: *{floor_price} TON*")
            dateline.append(f"Own: *{total_left} ({percent_supply:.3f}% supply)*")
            dateline.append(f"Avg price: *{avg_buy_price:.2f}*")
            dateline.append(f"Unrealized PnL: *{unrealized_pnl:.3f}*")
            dateline.append(f"Total sold: *{total_sells}*")
            dateline.append(f"Relized PnL: *{realized_pnl}*")

            dateline.append("")  # Empty line after each collection
            logger.debug(f"Report for {stickerpack_name}: {dateline}")

        # Summary section
        dateline.extend(
            [
                "Summary:",
                f"Total spent on markets: *{total_spent:,.2f}*",
                f"Unrealized PnL: *{total_unrealized_pnl:,.3f}*",
                f"Realized PnL: *{total_realized_pnl}*",
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
            "⚙️ Settings Menu\n\n"
            "Configure your collections and notification preferences:"
        )

        await message.answer(text, reply_markup=keyboard)

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
                text="📊 My Collections", callback_data="main_view_collections"
            ),
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
        elif action == "view_collections":
            await self.show_user_collections(callback)
        elif action == "check_prices":
            await self.manual_price_check(callback)
        elif action == "back":
            # Show main menu again
            keyboard = self.get_main_settings_keyboard()
            text = (
                "⚙️ Settings Menu\n\n"
                "Configure your collections and notification preferences:"
            )

            # Check if callback.message does not exist or is inaccessible
            if (
                isinstance(callback.message, InaccessibleMessage)
                or callback.message == None
            ):
                return "The message is no longer accessible"
            await callback.message.edit_text(text, reply_markup=keyboard)

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
            "🔔 Notification Settings\n\n"
            f"📈 Buy Alert: {settings['buy_multiplier']}x launch price\n"
            f"📉 Sell Alert: {settings['sell_multiplier']}x launch price\n\n"
            "Tap to modify these multipliers:"
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

                text += (
                    f"🏷️ **{escaped_collection_name}**\n"
                    f"📑 Sticker Pack: {escaped_stickerpack_name}\n"
                    f"💰 Launch Price: {collection['launch_price']} TON\n"
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
        """Process buy multiplier input"""
        if message.from_user == None:
            await message.answer("❌ Unexpected error occured! ")
            return
        user_id = message.from_user.id

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

        # Update user settings
        user_id_str = str(user_id)
        self.bot.user_settings[user_id_str]["notification_settings"][
            "buy_multiplier"
        ] = multiplier
        self.bot.save_user_settings()
        self.bot.state_manager.reset_user_session(user_id)

        await message.answer(
            f"✅ Buy alert multiplier updated to **{multiplier}x**\n\n"
            f"You'll now receive notifications when prices drop to **{multiplier}x** the launch price or below.",
            parse_mode="Markdown",
        )

    async def process_sell_multiplier_input(self, message: types.Message, text: str):
        """Process sell multiplier input"""
        if message.from_user == None:
            await message.answer("❌ Unexpected error occured! ")
            return
        user_id = message.from_user.id

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

        # Update user settings
        user_id_str = str(user_id)
        self.bot.user_settings[user_id_str]["notification_settings"][
            "sell_multiplier"
        ] = multiplier
        self.bot.save_user_settings()
        self.bot.state_manager.reset_user_session(user_id)

        await message.answer(
            f"✅ Sell alert multiplier updated to **{multiplier}x**\n\n"
            f"You'll now receive notifications when prices rise to **{multiplier}x** the launch price or above.",
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

        # Create collection entry
        new_collection = {
            "collection_name": collection_data.collection_name,
            "stickerpack_name": collection_data.stickerpack_name,
            "launch_price": collection_data.launch_price,
            "added_date": datetime.now().isoformat(),
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
