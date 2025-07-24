import logging
from functools import wraps
from aiogram import types
from config import WHITELISTED_USER_IDS

logger = logging.getLogger(__name__)

def require_whitelisted_user(func):
    """Decorator to check if user is whitelisted"""
    @wraps(func)
    async def wrapper(event, *args, **kwargs):
        user_id = None
        
        # Handle different event types - aiogram passes specific types
        if isinstance(event, types.Message) and event.from_user != None:
            user_id = event.from_user.id
        elif isinstance(event, types.CallbackQuery):
            user_id = event.from_user.id
        else:
            # Fallback for other types
            if hasattr(event, 'from_user') and event.from_user:
                user_id = event.from_user.id
        
        if not user_id:
            logger.error("Could not extract user_id from event")
            return
            
        if user_id not in WHITELISTED_USER_IDS:
            logger.info(f"Unauthorized access attempt by user_id: {user_id}")
            await send_unauthorized_message(event)
            return
            
        return await func(event, *args, **kwargs)
    return wrapper

async def send_unauthorized_message(event):
    """Send unauthorized access message"""
    message = (
        "🚫 **Access Denied**\n\n"
        "Sorry, this bot is restricted to authorized users only.\n"
        "If you believe you should have access, please contact the administrator."
    )
    
    try:
        if isinstance(event, types.Message):
            await event.answer(message, parse_mode="Markdown")
        elif isinstance(event, types.CallbackQuery):
            await event.answer(message, show_alert=True)
    except Exception as e:
        logger.error(f"Failed to send unauthorized message: {e}") 
