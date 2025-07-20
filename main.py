import asyncio
import json
import logging
import logging.handlers
import os
from datetime import datetime
from typing import Dict, List, Optional

import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram import F
import re

from functools import wraps

# Import configuration
from api.harbor.harbor_client import HarborClient
from config import (
    BOT_TOKEN, API_BASE_URL, USER_SETTINGS_FILE, PRICE_CACHE_FILE,
    PRICE_CHECK_INTERVAL, ERROR_RETRY_INTERVAL,
    DEFAULT_BUY_MULTIPLIER, DEFAULT_SELL_MULTIPLIER,
    NOTIFICATION_HISTORY_FILE, LOGS_DIR, WHITELISTED_USER_IDS
)
from api_client import Scanner
from user_states import UserStateManager, UserState
import uuid

def require_whitelisted_user(func):
    """Decorator to check if user is whitelisted"""
    @wraps(func)
    async def wrapper(update, *args, **kwargs):
        user_id = None
        
        # Handle different update types
        if hasattr(update, 'from_user') and update.from_user:
            user_id = update.from_user.id
        elif hasattr(update, 'message') and update.message and update.message.from_user:
            user_id = update.message.from_user.id
        
        if user_id not in WHITELISTED_USER_IDS:
            await send_unauthorized_message(update)
            return
            
        return await func(update, *args, **kwargs)
    return wrapper

async def send_unauthorized_message(update):
    """Send unauthorized access message"""
    message = (
        "🚫 **Access Denied**\n\n"
        "Sorry, this bot is restricted to authorized users only.\n"
        "If you believe you should have access, please contact the administrator."
    )
    
    try:
        if hasattr(update, 'message') and update.message:
            await update.message.answer(message, parse_mode="Markdown")
        elif hasattr(update, 'answer'):
            await update.answer(message, show_alert=True)
    except Exception as e:
        logger.error(f"Failed to send unauthorized message: {e}")

# Configure logging
def setup_logging():
    """Setup logging configuration for both console and file output"""
    # Create logs directory if it doesn't exist
    os.makedirs(LOGS_DIR, exist_ok=True)
    
    # Create formatters
    console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')
    
    # Create and configure root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    
    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(LOGS_DIR, 'bot.log'),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(file_formatter)
    
    # Add handlers to logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger

# Setup logging
logger = setup_logging()

def escape_markdown(text: str) -> str:
    """Escape special Markdown characters in text, but preserve dots in numbers"""
    if not text:
        return ""
    
    # Escape Markdown special characters, but be smarter about dots
    escape_chars = ['*', '_', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '!']
    escaped_text = text
    
    # Escape most special characters
    for char in escape_chars:
        escaped_text = escaped_text.replace(char, f'\\{char}')
    
    # Handle dots more carefully - only escape if not part of a number
    # Use regex to find dots that are NOT between digits
    # This regex finds dots that are not preceded and followed by digits
    escaped_text = re.sub(r'(?<!\d)\.(?!\d)', r'\\.', escaped_text)
    
    return escaped_text

class StickerNotifierBot:
    def __init__(self, token: str):
        self.bot = Bot(token=token)
        self.dp = Dispatcher()
        self.session = None
        self.api_client = None
        self.user_settings = self.load_user_settings()
        self.price_cache = self.load_price_cache()
        self.state_manager = UserStateManager()
        
        # Notification tracking to prevent spam
        self.last_notifications = self.load_notification_history()
        
        # Register handlers
        self._register_handlers()
        
    def _register_handlers(self):
        """Register all bot handlers"""
        self.dp.message(Command("start"))(require_whitelisted_user(self.cmd_start))
        self.dp.message(Command("settings"))(require_whitelisted_user(self.cmd_settings))
        self.dp.message(Command("cancel"))(require_whitelisted_user(self.cmd_cancel))
        
        # Callback query handlers
        self.dp.callback_query(F.data.startswith("main_"))(require_whitelisted_user(self.handle_main_menu))
        self.dp.callback_query(F.data.startswith("collection_"))(require_whitelisted_user(self.handle_collection_settings))
        self.dp.callback_query(F.data.startswith("notification_"))(require_whitelisted_user(self.handle_notification_settings))
        self.dp.callback_query(F.data.startswith("confirm_"))(require_whitelisted_user(self.handle_confirmation))
        
        # Text message handlers for user input flows
        self.dp.message(F.text & ~F.text.startswith("/"))(require_whitelisted_user(self.handle_text_input))
        
    async def cmd_start(self, message: types.Message):
        """Handle /start command"""
        user_id = message.from_user.id
        
        # Initialize user settings if not exists
        if str(user_id) not in self.user_settings:
            self.user_settings[str(user_id)] = {
                "collections": {},
                "notification_settings": {
                    "buy_multiplier": DEFAULT_BUY_MULTIPLIER,
                    "sell_multiplier": DEFAULT_SELL_MULTIPLIER
                }
            }
            self.save_user_settings()
            
        welcome_text = (
            "🔔 Welcome to Sticker Price Notifier Bot!\n\n"
            "I'll help you track Telegram sticker pack prices and notify you when they reach your target levels.\n\n"
            "Use /settings to configure your collections and notification preferences."
        )
        
        await message.answer(welcome_text)
    
    async def cmd_cancel(self, message: types.Message):
        """Handle /cancel command to exit any active flow"""
        user_id = message.from_user.id
        
        if self.state_manager.is_user_in_flow(user_id):
            self.state_manager.reset_user_session(user_id)
            await message.answer(
                "❌ Operation cancelled. Use /settings to access the menu.",
                reply_markup=types.ReplyKeyboardRemove()
            )
        else:
            await message.answer("No active operation to cancel. Use /settings to access the menu.")
        
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
        user_collections = self.user_settings[user_id]["collections"]
        
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
        settings = self.user_settings[user_id]["notification_settings"]
        
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
        collections = self.user_settings[user_id]["collections"]
        
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
        collections = self.user_settings[user_id]["collections"]
        
        if not collections:
            await callback.answer("No collections configured!", show_alert=True)
            return
            
        await callback.answer("Checking prices...")
        
        if not self.api_client:
            text = "❌ API client not initialized. Please try again later."
        else:
            # Trigger immediate price check
            bundles = await self.api_client.fetch_price_bundles()
            
            if bundles:
                # Check user's collections
                notification_settings = self.user_settings[user_id].get("notification_settings", {})
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
                
                if results:
                    text = f"🔄 Price Check Results:\n\n" + "\n".join(results)
                else:
                    text = "📊 No price data available for your collections."
            else:
                text = "❌ Failed to fetch price data. Please try again later."
        
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
        self.state_manager.reset_user_session(user_id)
        self.state_manager.set_user_state(user_id, UserState.ADDING_COLLECTION_NAME)
        
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
        collections = self.user_settings[user_id]["collections"]
        
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
        collections = self.user_settings[user_id]["collections"]
        
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
        
        current_multiplier = self.user_settings[user_id_str]["notification_settings"]["buy_multiplier"]
        
        # Reset any existing flow and start new one
        self.state_manager.reset_user_session(user_id)
        self.state_manager.set_user_state(user_id, UserState.EDITING_BUY_MULTIPLIER)
        
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
        
        current_multiplier = self.user_settings[user_id_str]["notification_settings"]["sell_multiplier"]
        
        # Reset any existing flow and start new one
        self.state_manager.reset_user_session(user_id)
        self.state_manager.set_user_state(user_id, UserState.EDITING_SELL_MULTIPLIER)
        
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
        user_state = self.state_manager.get_user_state(user_id)
        
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
        self.state_manager.update_collection_data(user_id, collection_name=text)
        self.state_manager.set_user_state(user_id, UserState.ADDING_STICKERPACK_NAME)
        
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
        self.state_manager.update_collection_data(user_id, stickerpack_name=text)
        self.state_manager.set_user_state(user_id, UserState.ADDING_LAUNCH_PRICE)
        
        collection_data = self.state_manager.get_collection_data(user_id)
        
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
        self.state_manager.update_collection_data(user_id, launch_price=price)
        self.state_manager.set_user_state(user_id, UserState.CONFIRMING_COLLECTION)
        
        collection_data = self.state_manager.get_collection_data(user_id)
        
        # Check if collection already exists in API
        status_text = await self.check_collection_availability(collection_data)
        
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
        self.user_settings[user_id_str]["notification_settings"]["buy_multiplier"] = multiplier
        self.save_user_settings()
        self.state_manager.reset_user_session(user_id)
        
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
        self.user_settings[user_id_str]["notification_settings"]["sell_multiplier"] = multiplier
        self.save_user_settings()
        self.state_manager.reset_user_session(user_id)
        
        await message.answer(
            f"✅ Sell alert multiplier updated to **{multiplier}x**\n\n"
            f"You'll now receive notifications when prices rise to **{multiplier}x** the launch price or above.",
            parse_mode="Markdown"
        )
    
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
        collection_data = self.state_manager.get_collection_data(user_id)
        
        # Generate unique collection ID
        collection_id = str(uuid.uuid4())[:8]
        
        # Create collection entry
        new_collection = {
            "collection_name": collection_data.collection_name,
            "stickerpack_name": collection_data.stickerpack_name,
            "launch_price": collection_data.launch_price,
            "added_date": datetime.now().isoformat()
        }
        
        # Save to user settings
        if user_id_str not in self.user_settings:
            self.user_settings[user_id_str] = {
                "collections": {},
                "notification_settings": {
                    "buy_multiplier": DEFAULT_BUY_MULTIPLIER,
                    "sell_multiplier": DEFAULT_SELL_MULTIPLIER
                }
            }
            
        self.user_settings[user_id_str]["collections"][collection_id] = new_collection
        self.save_user_settings()
        
        # Reset user session
        self.state_manager.reset_user_session(user_id)
        
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
        self.state_manager.reset_user_session(user_id)
        
        text = "❌ Collection creation cancelled.\n\nUse /settings to access the menu."
        
        await callback.message.edit_text(text)
        await callback.answer("Cancelled")
    
    async def confirm_delete_collection(self, callback: types.CallbackQuery, collection_id: str):
        """Confirm and delete collection"""
        user_id = str(callback.from_user.id)
        
        if collection_id not in self.user_settings[user_id]["collections"]:
            await callback.answer("Collection not found!", show_alert=True)
            return
            
        collection = self.user_settings[user_id]["collections"][collection_id]
        del self.user_settings[user_id]["collections"][collection_id]
        self.save_user_settings()
        
        # Clean up notification history for this collection
        keys_to_remove = [key for key in self.last_notifications.keys() if key.startswith(f"{user_id}:{collection_id}:")]
        for key in keys_to_remove:
            del self.last_notifications[key]
        self.save_notification_history()
        
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
            
    async def start_polling(self):
        """Start the bot polling"""
        try:
            # Initialize aiohttp session
            self.session = aiohttp.ClientSession()
            
            # Initialize API clients
            self.api_client = Scanner(self.session)
            self.harbor_client = HarborClient()
            
            # Start background tasks
            asyncio.create_task(self.price_monitoring_loop())
            
            # Start polling
            await self.dp.start_polling(self.bot)
        finally:
            if self.session:
                await self.session.close()
                
    async def price_monitoring_loop(self):
        """Background task to monitor prices every 3 minutes"""
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

        if not self.harbor_client:
            logger.error("Harbor client not initialized")
            return
            
        # Fetch current price bundles
        bundles = await self.api_client.fetch_price_bundles()
        harbor_floor_prices = await self.harbor_client.fetch_floor_price_harbor()
        if not bundles:
            logger.warning("No price bundles received from API")
            return
            
        # Update price cache
        current_time = datetime.now().isoformat()
        self.price_cache = {
            "last_updated": current_time,
            "bundles": bundles,
            "harbor_floor_prices": harbor_floor_prices
        }
        self.save_price_cache()
        
        # Check each user's collections
        logger.info(f"Checking collections for {len(self.user_settings)} users")
        
        total_collections_checked = 0
        for user_id, user_data in self.user_settings.items():
            collections = user_data.get("collections", {})
            notification_settings = user_data.get("notification_settings", {})
            
            logger.info(f"User {user_id}: {len(collections)} collections")
            
            for collection_id, collection in collections.items():
                total_collections_checked += 1
                await self.check_collection_price(
                    user_id, collection_id, collection, 
                    bundles, notification_settings,
                    harbor_floor_prices
                )
                
        logger.info(f"Price check completed for {len(bundles)} bundles, checked {total_collections_checked} user collections")
    
    async def check_collection_price(self, user_id: str, collection_id: str, collection: Dict, 
                                   bundles: List[Dict], notification_settings: Dict, harbor_floor_prices: Dict = None):
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
                
            # Get current prices
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
                if self.should_send_notification(user_id, collection_id, "buy", lowest_price):
                    buy_markets = [
                        f"{market}: {price} TON" 
                        for market, price in marketplace_prices.items() 
                        if price <= buy_threshold
                    ]
                    
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
                if self.should_send_notification(user_id, collection_id, "sell", highest_price):
                    sell_markets = [
                        f"{market}: {price} TON" 
                        for market, price in marketplace_prices.items() 
                        if price >= sell_threshold
                    ]
                    
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
                await self.send_price_notification(int(user_id), notification)
                
        except Exception as e:
            logger.error(f"Error checking collection price for user {user_id}: {e}")
    
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
            
            # Escape market names in the markets list
            escaped_markets = []
            for market in notification['markets']:
                escaped_market = escape_markdown(market)
                escaped_markets.append(f"• {escaped_market}")
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
                fallback_message = (
                    f"{emoji} {title}\n\n"
                    f"Collection: {notification['collection']}\n"
                    f"Sticker Pack: {notification['stickerpack']}\n"
                    f"Price: {price_info}\n\n"
                    f"Available on:\n" + "\n".join(f"• {market}" for market in notification['markets']) + "\n\n"
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

# Main execution
async def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or not BOT_TOKEN:
        logger.error("Please set your bot token in .env file or BOT_TOKEN environment variable")
        return
        
    bot = StickerNotifierBot(BOT_TOKEN)
    await bot.start_polling()

if __name__ == "__main__":
    asyncio.run(main())