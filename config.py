import os
from typing import Optional
from dotenv import load_dotenv


def _to_float(value: Optional[str], default: float) -> float:
    """Safely convert environment values to float with fallback."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

# Load environment variables from .env file
load_dotenv()

# Bot configuration
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# Option 3: Use telegram api key
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", 0))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")

# API configuration
API_BASE_URL = "https://stickers.tools/api"
STICKER_STATS_ENDPOINT = f"{API_BASE_URL}/stats-new"

# Whitelisted users
WHITELISTED_USER_IDS = os.getenv("WHITELISTED_USER_IDS", "")
WHITELISTED_USER_IDS = [int(user) for user in WHITELISTED_USER_IDS.split(",")]

# Data directory for persistent storage
DATA_DIR = os.getenv("DATA_DIR", "data")
LOGS_DIR = os.getenv("LOGS_DIR", "logs")

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# File paths for data storage
USER_SETTINGS_FILE = os.path.join(DATA_DIR, "user_settings.json")
PRICE_CACHE_FILE = os.path.join(DATA_DIR, "price_cache.json")
NOTIFICATION_HISTORY_FILE = os.path.join(DATA_DIR, "notification_history.json")

# Monitoring settings
PRICE_CHECK_INTERVAL = int(
    os.getenv("PRICE_CHECK_INTERVAL", 180)
)  # 3 minutes in seconds
ERROR_RETRY_INTERVAL = int(os.getenv("ERROR_RETRY_INTERVAL", 60))  # 1 minute in seconds

# Default notification settings
DEFAULT_BUY_MULTIPLIER = 2.0
DEFAULT_SELL_MULTIPLIER = 3.0

# Default daily report settings
DEFAULT_DAILY_REPORTS_ENABLED = True
DEFAULT_REPORT_TIME_PREFERENCE = "morning"  # morning, afternoon, evening

# Time preference to hour mapping (24-hour format)
TIME_PREFERENCE_HOURS = {
    "morning": 9,    # 9:00 AM
    "afternoon": 14, # 2:00 PM  
    "evening": 19    # 7:00 PM
}

# Timezone configuration
DEFAULT_TIMEZONE = os.getenv("TIMEZONE", "UTC")  # Default to UTC if not specified

# Periodic floor price update settings
FLOOR_UPDATE_ENABLED = os.getenv("FLOOR_UPDATE_ENABLED", "false").lower() == "true"
FLOOR_UPDATE_INTERVAL = int(os.getenv("FLOOR_UPDATE_INTERVAL", 7200))  # 2 hours in seconds

# Google Sheets configuration
GOOGLE_SHEETS_KEY = os.getenv("GOOGLE_SHEETS_KEY")
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", ".credentials.json")
GOOGLE_SHEETS_READ_DELAY = _to_float(os.getenv("GOOGLE_SHEETS_READ_DELAY"), 1.0)
GOOGLE_SHEETS_WORKSHEET_DELAY = _to_float(
    os.getenv("GOOGLE_SHEETS_WORKSHEET_DELAY"), 1.0
)
