import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Bot configuration
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# Option 1: Use captured initData from browser (Recommended)
TELEGRAM_INIT_DATA = os.getenv("TELEGRAM_INIT_DATA")

# Option 2: Manual account data (for reference/fallback)
TELEGRAM_USER_ID = os.getenv("TELEGRAM_USER_ID")
TELEGRAM_FIRST_NAME = os.getenv("TELEGRAM_FIRST_NAME")
TELEGRAM_LAST_NAME = os.getenv("TELEGRAM_LAST_NAME", "")
TELEGRAM_USERNAME = os.getenv("TELEGRAM_USERNAME")
TELEGRAM_LANGUAGE_CODE = os.getenv("TELEGRAM_LANGUAGE_CODE", "en")
TELEGRAM_IS_PREMIUM = os.getenv("TELEGRAM_IS_PREMIUM", "false").lower() == "true"
TELEGRAM_PHOTO_URL = os.getenv("TELEGRAM_PHOTO_URL", "")

# Option 3: Use telegram api key
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")

# API configuration
API_BASE_URL = "https://stickerscan.online/api"
AUTH_ENDPOINT = f"{API_BASE_URL}/auth/telegram"
PRICE_BUNDLES_ENDPOINT = f"{API_BASE_URL}/characters/min-price-bundles"

# Whitelisted users
WHITELISTED_USER_IDS = os.getenv("WHITELISTED_USER_IDS", "")
WHITELISTED_USER_IDS = [int(user) for user in WHITELISTED_USER_IDS.split(',')]

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
PRICE_CHECK_INTERVAL = int(os.getenv("PRICE_CHECK_INTERVAL", 180))  # 3 minutes in seconds
ERROR_RETRY_INTERVAL = int(os.getenv("ERROR_RETRY_INTERVAL", 60))   # 1 minute in seconds

# Default notification settings
DEFAULT_BUY_MULTIPLIER = 2.0
DEFAULT_SELL_MULTIPLIER = 3.0

# Google Sheets configuration
GOOGLE_SHEETS_KEY = os.getenv("GOOGLE_SHEETS_KEY")
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", ".credentials.json") 