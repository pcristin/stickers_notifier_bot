import logging
import uuid
import json
import os
from datetime import datetime
from aiogram import F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from auth import require_whitelisted_user
from user_states import UserState, WallData
from utils import escape_markdown, clean_marketplace_name
from config import WHITELISTED_USER_IDS

logger = logging.getLogger(__name__)

class BotHandlers:
    def __init__(self, bot_instance):
        self.bot = bot_instance
        
    def register_handlers(self):
        """Register all bot handlers"""
        self.bot.dp.message(Command("start"))(require_whitelisted_user(self.cmd_start))
        self.bot.dp.message(Command("settings"))(require_whitelisted_user(self.cmd_settings))
        self.bot.dp.message(Command("cancel"))(require_whitelisted_user(self.cmd_cancel))
        self.bot.dp.message(Command("cleanup_users"))(require_whitelisted_user(self.cmd_cleanup_users))
        self.bot.dp.message(Command("wall"))(require_whitelisted_user(self.cmd_wall))
        
        # Callback query handlers
        self.bot.dp.callback_query(F.data.startswith("main_"))(require_whitelisted_user(self.handle_main_menu))
        self.bot.dp.callback_query(F.data.startswith("collection_"))(require_whitelisted_user(self.handle_collection_settings))
        self.bot.dp.callback_query(F.data.startswith("notification_"))(require_whitelisted_user(self.handle_notification_settings))
        self.bot.dp.callback_query(F.data.startswith("confirm_"))(require_whitelisted_user(self.handle_confirmation))
        
        # Text message handlers for user input flows
        self.bot.dp.message(F.text & ~F.text.startswith("/"))(require_whitelisted_user(self.handle_text_input))
    
    async def cmd_start(self, message: types.Message):
        """Handle /start command"""
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
        user_id = message.from_user.id
        
        if self.bot.state_manager.is_user_in_flow(user_id):
            self.bot.state_manager.reset_user_session(user_id)
            await message.answer(
                "❌ Operation cancelled. Use /settings to access the menu.",
                reply_markup=types.ReplyKeyboardRemove()
            )
        else:
            await message.answer("No active operation to cancel. Use /settings to access the menu.")
            
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
            parse_mode="Markdown"
        )
        
    async def cmd_wall(self, message: types.Message):
        """Handle /wall command to check sell order walls"""
        user_id = message.from_user.id
        
        # Reset any existing flow and start wall query
        self.bot.state_manager.reset_user_session(user_id)
        self.bot.state_manager.set_user_state(user_id, UserState.WALL_COLLECTION_NAME)
        
        text = (
            "🧱 **Wall Analysis**\n\n"
            "Step 1/2: Enter the **collection name**\n\n"
            "Example: `Flappy Bird`, `Hamster Kombat`, `TON Society`\n\n"
            "💡 This will show how many sell orders are under your specified price.\n\n"
            "Type /cancel to abort this process."
        )
        
        await message.answer(text, parse_mode="Markdown")
        
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
            InlineKeyboardButton(text="📦 Collection Settings", callback_data="main_collections"),
            InlineKeyboardButton(text="🔔 Notification Settings", callback_data="main_notifications")
        )
        builder.row(
            InlineKeyboardButton(text="📊 My Collections", callback_data="main_view_collections"),
            InlineKeyboardButton(text="🔄 Check Prices Now", callback_data="main_check_prices")
        )
        
        return builder.as_markup()
        
    async def handle_main_menu(self, callback: types.CallbackQuery):
        """Handle main menu callbacks"""
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
                    callback_data=f"collection_edit_{collection_id}"
                )
            )
            
        builder.row(
            InlineKeyboardButton(text="➕ Add New Collection", callback_data="collection_add_new")
        )
        builder.row(
            InlineKeyboardButton(text="⬅️ Back to Main", callback_data="main_back")
        )
        
        text = (
            "📦 Collection Settings\n\n"
            f"You have {len(user_collections)} collection(s) configured.\n"
            "Select a collection to edit or add a new one:"
        )
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        
    async def show_notification_settings(self, callback: types.CallbackQuery):
        """Show notification configuration"""
        user_id = str(callback.from_user.id)
        settings = self.bot.user_settings[user_id]["notification_settings"]
        
        builder = InlineKeyboardBuilder()
        
        builder.row(
            InlineKeyboardButton(
                text=f"📈 Buy Alert: {settings['buy_multiplier']}x", 
                callback_data="notification_buy_multiplier"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=f"📉 Sell Alert: {settings['sell_multiplier']}x", 
                callback_data="notification_sell_multiplier"
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
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        
    async def show_user_collections(self, callback: types.CallbackQuery):
        """Display user's configured collections"""
        user_id = str(callback.from_user.id)
        collections = self.bot.user_settings[user_id]["collections"]
        
        if not collections:
            text = "📦 No collections configured yet.\n\nUse Collection Settings to add your first collection!"
        else:
            text = "📦 Your Collections:\n\n"
            for collection_id, collection in collections.items():
                # Escape Markdown characters
                escaped_collection_name = escape_markdown(collection['collection_name'])
                escaped_stickerpack_name = escape_markdown(collection['stickerpack_name'])
                
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
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
        
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
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        
    async def handle_collection_settings(self, callback: types.CallbackQuery):
        """Handle collection-specific settings"""
        user_id = callback.from_user.id
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
        
        await callback.message.edit_text(text, parse_mode="Markdown")
        await callback.answer()
    
    async def start_collection_editing(self, callback: types.CallbackQuery, collection_id: str):
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
                callback_data=f"edit_field_collection_name_{collection_id}"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=f"📑 Edit Sticker Pack: {collection['stickerpack_name']}", 
                callback_data=f"edit_field_stickerpack_name_{collection_id}"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=f"💰 Edit Launch Price: {collection['launch_price']} TON", 
                callback_data=f"edit_field_launch_price_{collection_id}"
            )
        )
        builder.row(
            InlineKeyboardButton(text="🗑️ Delete Collection", callback_data=f"collection_delete_{collection_id}"),
            InlineKeyboardButton(text="⬅️ Back", callback_data="main_collections")
        )
        
        # Escape Markdown characters in collection data
        escaped_collection_name = escape_markdown(collection['collection_name'])
        escaped_stickerpack_name = escape_markdown(collection['stickerpack_name'])
        
        text = (
            f"✏️ Editing Collection\n\n"
            f"🏷️ **Collection:** {escaped_collection_name}\n"
            f"📑 **Sticker Pack:** {escaped_stickerpack_name}\n"
            f"💰 **Launch Price:** {collection['launch_price']} TON\n\n"
            f"Select what you want to edit:"
        )
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
        await callback.answer()
    
    async def confirm_collection_deletion(self, callback: types.CallbackQuery, collection_id: str):
        """Confirm collection deletion"""
        user_id = str(callback.from_user.id)
        collections = self.bot.user_settings[user_id]["collections"]
        
        if collection_id not in collections:
            await callback.answer("Collection not found!", show_alert=True)
            return
            
        collection = collections[collection_id]
        
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="🗑️ Yes, Delete", callback_data=f"confirm_delete_{collection_id}"),
            InlineKeyboardButton(text="❌ Cancel", callback_data=f"collection_edit_{collection_id}")
        )
        
        # Escape Markdown characters
        escaped_collection_name = escape_markdown(collection['collection_name'])
        escaped_stickerpack_name = escape_markdown(collection['stickerpack_name'])
        
        text = (
            f"⚠️ **Delete Collection?**\n\n"
            f"🏷️ Collection: **{escaped_collection_name}**\n"
            f"📑 Sticker Pack: **{escaped_stickerpack_name}**\n\n"
            f"This action cannot be undone!"
        )
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
        await callback.answer()
         
    async def handle_notification_settings(self, callback: types.CallbackQuery):
        """Handle notification settings changes"""
        action_parts = callback.data.split("_")
        
        if len(action_parts) < 2:
            await callback.answer("Invalid notification action", show_alert=True)
            return
            
        action = action_parts[1]
        user_id = callback.from_user.id
        
        if action == "buy" and len(action_parts) > 2 and action_parts[2] == "multiplier":
            await self.start_buy_multiplier_editing(callback)
        elif action == "sell" and len(action_parts) > 2 and action_parts[2] == "multiplier":
            await self.start_sell_multiplier_editing(callback)
        else:
            await callback.answer("Unknown notification action", show_alert=True)
    
    async def start_buy_multiplier_editing(self, callback: types.CallbackQuery):
        """Start editing buy multiplier"""
        user_id = callback.from_user.id
        user_id_str = str(user_id)
        
        current_multiplier = self.bot.user_settings[user_id_str]["notification_settings"]["buy_multiplier"]
        
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
        
        await callback.message.edit_text(text, parse_mode="Markdown")
        await callback.answer()
    
    async def start_sell_multiplier_editing(self, callback: types.CallbackQuery):
        """Start editing sell multiplier"""
        user_id = callback.from_user.id
        user_id_str = str(user_id)
        
        current_multiplier = self.bot.user_settings[user_id_str]["notification_settings"]["sell_multiplier"]
        
        # Reset any existing flow and start new one
        self.bot.state_manager.reset_user_session(user_id)
        self.bot.state_manager.set_user_state(user_id, UserState.EDITING_SELL_MULTIPLIER)
        
        text = (
            f"📉 **Edit Sell Alert Multiplier**\n\n"
            f"Current value: **{current_multiplier}x**\n\n"
            f"Enter the new multiplier for sell alerts.\n"
            f"You'll get notified when prices rise to this multiple of the launch price or above.\n\n"
            f"Example: `3` (for 3x launch price), `2.5`, `5.0`\n\n"
            f"Valid range: 0.1 to 100\n\n"
            f"Type /cancel to abort this change."
        )
        
        await callback.message.edit_text(text, parse_mode="Markdown")
        await callback.answer()
    
    async def handle_text_input(self, message: types.Message):
        """Handle text input from users during flows"""
        user_id = message.from_user.id
        user_state = self.bot.state_manager.get_user_state(user_id)
        
        if user_state == UserState.IDLE:
            # User not in any flow, ignore
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
        elif user_state == UserState.WALL_COLLECTION_NAME:
            await self.process_wall_collection_name_input(message, text)
        elif user_state == UserState.WALL_TON_AMOUNT:
            await self.process_wall_ton_amount_input(message, text)
    
    async def process_collection_name_input(self, message: types.Message, text: str):
        """Process collection name input"""
        user_id = message.from_user.id
        
        if len(text) < 2 or len(text) > 50:
            await message.answer(
                "❌ Collection name must be between 2 and 50 characters.\n\n"
                "Please try again or type /cancel to abort."
            )
            return
            
        # Store collection name and move to next step
        self.bot.state_manager.update_collection_data(user_id, collection_name=text)
        self.bot.state_manager.set_user_state(user_id, UserState.ADDING_STICKERPACK_NAME)
        
        # Escape Markdown characters for display
        escaped_text = escape_markdown(text)
        
        await message.answer(
            f"✅ Collection name: **{escaped_text}**\n\n"
            f"Step 2/3: Enter the **sticker pack name**\n\n"
            f"Example: `Golden Hamster`, `Diamond Society`, `Premium Notcoin`\n\n"
            f"💡 This is the specific sticker pack within the collection.\n\n"
            f"Type /cancel to abort this process.",
            parse_mode="Markdown"
        )
    
    async def process_stickerpack_name_input(self, message: types.Message, text: str):
        """Process sticker pack name input"""
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
            parse_mode="Markdown"
        )
    
    async def process_launch_price_input(self, message: types.Message, text: str):
        """Process launch price input"""
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
            InlineKeyboardButton(text="✅ Confirm & Save", callback_data="confirm_add_collection"),
            InlineKeyboardButton(text="❌ Cancel", callback_data="confirm_cancel_collection")
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
        
        await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    
    async def process_buy_multiplier_input(self, message: types.Message, text: str):
        """Process buy multiplier input"""
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
        self.bot.user_settings[user_id_str]["notification_settings"]["buy_multiplier"] = multiplier
        self.bot.save_user_settings()
        self.bot.state_manager.reset_user_session(user_id)
        
        await message.answer(
            f"✅ Buy alert multiplier updated to **{multiplier}x**\n\n"
            f"You'll now receive notifications when prices drop to **{multiplier}x** the launch price or below.",
            parse_mode="Markdown"
        )
    
    async def process_sell_multiplier_input(self, message: types.Message, text: str):
        """Process sell multiplier input"""
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
        self.bot.user_settings[user_id_str]["notification_settings"]["sell_multiplier"] = multiplier
        self.bot.save_user_settings()
        self.bot.state_manager.reset_user_session(user_id)
        
        await message.answer(
            f"✅ Sell alert multiplier updated to **{multiplier}x**\n\n"
            f"You'll now receive notifications when prices rise to **{multiplier}x** the launch price or above.",
            parse_mode="Markdown"
        )
    
    async def handle_confirmation(self, callback: types.CallbackQuery):
        """Handle confirmation callbacks"""
        action_parts = callback.data.split("_")
        
        if len(action_parts) < 2:
            await callback.answer("Invalid confirmation action", show_alert=True)
            return
            
        action = action_parts[1]
        
        if action == "add" and len(action_parts) > 2 and action_parts[2] == "collection":
            await self.confirm_add_collection(callback)
        elif action == "cancel" and len(action_parts) > 2 and action_parts[2] == "collection":
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
            "added_date": datetime.now().isoformat()
        }
        
        # Ensure user settings exist
        self.bot.ensure_user_settings(user_id_str)
        
        # Save to user settings
        self.bot.user_settings[user_id_str]["collections"][collection_id] = new_collection
        self.bot.save_user_settings()
        
        # Reset user session
        self.bot.state_manager.reset_user_session(user_id)
        
        # Escape Markdown characters
        escaped_collection_name = escape_markdown(new_collection['collection_name'])
        escaped_stickerpack_name = escape_markdown(new_collection['stickerpack_name'])
        
        text = (
            f"🎉 **Collection Added Successfully!**\n\n"
            f"🏷️ Collection: **{escaped_collection_name}**\n"
            f"📑 Sticker Pack: **{escaped_stickerpack_name}**\n"
            f"💰 Launch Price: **{new_collection['launch_price']} TON**\n\n"
            f"🔔 You'll receive notifications when prices meet your thresholds.\n\n"
            f"Use /settings to manage your collections."
        )
        
        await callback.message.edit_text(text, parse_mode="Markdown")
        await callback.answer("Collection added!")
    
    async def cancel_collection_creation(self, callback: types.CallbackQuery):
        """Cancel collection creation"""
        user_id = callback.from_user.id
        self.bot.state_manager.reset_user_session(user_id)
        
        text = "❌ Collection creation cancelled.\n\nUse /settings to access the menu."
        
        await callback.message.edit_text(text)
        await callback.answer("Cancelled")
    
    async def confirm_delete_collection(self, callback: types.CallbackQuery, collection_id: str):
        """Confirm and delete collection"""
        user_id = str(callback.from_user.id)
        
        if collection_id not in self.bot.user_settings[user_id]["collections"]:
            await callback.answer("Collection not found!", show_alert=True)
            return
            
        collection = self.bot.user_settings[user_id]["collections"][collection_id]
        del self.bot.user_settings[user_id]["collections"][collection_id]
        self.bot.save_user_settings()
        
        # Clean up notification history for this collection
        self.bot.notification_manager.cleanup_notifications_for_collection(user_id, collection_id)
        
        # Escape Markdown characters
        escaped_collection_name = escape_markdown(collection['collection_name'])
        escaped_stickerpack_name = escape_markdown(collection['stickerpack_name'])
        
        text = (
            f"🗑️ **Collection Deleted**\n\n"
            f"**{escaped_collection_name}** - **{escaped_stickerpack_name}** "
            f"has been removed from your watchlist.\n\n"
            f"Use /settings to manage your remaining collections."
        )
        
        await callback.message.edit_text(text, parse_mode="Markdown")
        await callback.answer("Collection deleted!")

    async def process_wall_collection_name_input(self, message: types.Message, text: str):
        """Process wall collection name input"""
        user_id = message.from_user.id
        
        if len(text) < 2 or len(text) > 50:
            await message.answer(
                "❌ Collection name must be between 2 and 50 characters.\n\n"
                "Please try again or type /cancel to abort."
            )
            return
            
        # Store collection name and move to next step
        self.bot.state_manager.update_wall_data(user_id, collection_name=text)
        self.bot.state_manager.set_user_state(user_id, UserState.WALL_TON_AMOUNT)
        
        # Escape Markdown characters for display
        escaped_text = escape_markdown(text)
        
        await message.answer(
            f"✅ Collection: **{escaped_text}**\n\n"
            f"Step 2/2: Enter the **TON amount** for wall analysis\n\n"
            f"Example: `10`, `25.5`, `100`\n\n"
            f"💡 This will count sell orders under this price.\n\n"
            f"Type /cancel to abort this process.",
            parse_mode="Markdown"
        )

    async def process_wall_ton_amount_input(self, message: types.Message, text: str):
        """Process wall TON amount input"""
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
            
        # Store amount and calculate wall
        self.bot.state_manager.update_wall_data(user_id, ton_amount=amount)
        wall_data = self.bot.state_manager.get_wall_data(user_id)
        
        # Reset user session
        self.bot.state_manager.reset_user_session(user_id)
        
        # Calculate and display wall
        await self.calculate_and_display_wall(message, wall_data.collection_name, wall_data.ton_amount)

    async def calculate_and_display_wall(self, message: types.Message, collection_name: str, ton_amount: float):
        """Calculate and display wall analysis"""
        try:
            # Check if API client is available
            if not self.bot.api_client:
                await message.answer("❌ API client not available. Please try again later.")
                return
                
            # Fetch current price bundles from API
            bundle_data = await self.bot.api_client.fetch_price_bundles()
            if not bundle_data:
                await message.answer("❌ Failed to fetch price data. Please try again later.")
                return
            
            # Find matching collections (case-insensitive)
            matching_collections = []
            for item in bundle_data:
                if collection_name.lower() in item.get('collectionName', '').lower():
                    matching_collections.append(item)
            
            if not matching_collections:
                await message.answer(
                    f"❌ No collection found matching **{escape_markdown(collection_name)}**\n\n"
                    f"Please check the collection name and try again.",
                    parse_mode="Markdown"
                )
                return
            
            # Calculate wall for each marketplace
            marketplace_walls = {}
            total_wall = 0
            
            for collection_item in matching_collections:
                for marketplace_info in collection_item.get('marketplaces', []):
                    marketplace = marketplace_info.get('marketplace', 'Unknown')
                    prices = marketplace_info.get('prices', [])
                    
                    # Count prices under the specified amount
                    wall_count = sum(1 for price_item in prices if price_item.get('price', 0) <= ton_amount)
                    
                    if marketplace not in marketplace_walls:
                        marketplace_walls[marketplace] = 0
                    marketplace_walls[marketplace] += wall_count
            
            # Calculate total wall
            total_wall = sum(marketplace_walls.values())
            
            if total_wall == 0:
                await message.answer(
                    f"🧱 **Wall Analysis Results**\n\n"
                    f"🏷️ Collection: **{escape_markdown(collection_name)}**\n"
                    f"💰 Price Threshold: **{ton_amount} TON**\n\n"
                    f"❌ No sell orders found under **{ton_amount} TON**",
                    parse_mode="Markdown"
                )
                return
            
            # Format results
            result_text = (
                f"🧱 **Wall Analysis Results**\n\n"
                f"🏷️ Collection: **{escape_markdown(collection_name)}**\n"
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