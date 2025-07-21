import logging
import logging.handlers
import os
import re
from config import LOGS_DIR

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
    # This regex finds dots that are not preceded and followed by digits
    escaped_text = re.sub(r'(?<!\d)\.(?!\d)', r'\\.', escaped_text)
    
    return escaped_text

def escape_markdown_link_text(text: str) -> str:
    """Escape Markdown characters for text that will be used inside [link text](url).
    Underscores don't need escaping inside link text."""
    if not text:
        return ""
    
    # For link text, we don't need to escape underscores as they're safe inside [text](url)
    escape_chars = ['*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '!']
    escaped_text = text
    
    # Escape special characters except underscores
    for char in escape_chars:
        escaped_text = escaped_text.replace(char, f'\\{char}')
    
    # Handle dots more carefully - only escape if not part of a number
    escaped_text = re.sub(r'(?<!\d)\.(?!\d)', r'\\.', escaped_text)
    
    return escaped_text

def clean_marketplace_name(name: str) -> str:
    """Clean marketplace name for display - remove underscores, make it readable"""
    if not name:
        return ""
    
    # Remove underscores and replace with spaces
    cleaned = name.replace('_', ' ')
    
    # Convert to title case for better readability
    cleaned = cleaned.title()
    
    # Handle common abbreviations/acronyms that should stay uppercase
    abbreviations = ['NFT', 'TON', 'API', 'ID', 'URL', 'UI', 'UX']
    for abbr in abbreviations:
        # Replace title-cased version with uppercase
        cleaned = cleaned.replace(abbr.title(), abbr)
    
    return cleaned 