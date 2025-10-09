# Telegram Sticker Price Notifier Bot

A Telegram bot that monitors sticker pack prices on multiple marketplaces and sends notifications when prices reach configured thresholds.

## Features

- Track multiple sticker collections with configurable price alerts
- Monitor prices across 3 different marketplaces
- Inline keyboard interface for easy configuration
- File-based storage for user settings
- Background price monitoring every 3 minutes
- Customizable buy/sell price multipliers
- **Complete collection management system**
- **Multi-step guided collection creation**
- **Real-time price verification during setup**
- **Smart notification system with threshold alerts**

## Setup

> 💡 **Quick Start**: This project uses a comprehensive Makefile for all operations. Run `make help` to see all available commands!

### 🐳 Docker Deployment (Recommended for Production)

**For server deployment, use Docker:**

1. **Quick deployment:**
   ```bash
   # Copy your .env file to the server
   # Deploy with one command
   make deploy
   ```

2. **Manage the bot:**
   ```bash
   make status           # Check status
   make logs             # View logs
   make restart          # Restart bot
   make backup           # Create backup
   make help             # Show all commands
   ```

📋 **See [DEPLOYMENT.md](DEPLOYMENT.md) for complete server setup guide.**

### 🐍 Local Development Setup

**For local development and testing:**

1. **Install dependencies:**
   ```bash
   # Using Makefile (recommended)
   make dev-setup
   
   # Or manually
   pip install -r requirements.txt
   ```

2. **Configure bot token and authentication:**
   Create a `.env` file in the project root:
   ```bash
   # Telegram Bot Configuration
   BOT_TOKEN=your_telegram_bot_token_here

   # Stickers.Tools integration does not require Telegram WebApp auth tokens
   # Additional environment variables are optional.

   ```

3. **Test authentication (optional but recommended):**
   ```bash
   # Using Makefile (recommended)
   make test-auth
   
   # Or manually
   python test_auth.py
   ```

4. **Run the bot:**
   ```bash
   # Using Makefile (recommended)
   make dev-run
   
   # Or manually
   python main.py
   ```

## Project Structure

```
stickers_notifier_bot/
├── main.py                  # Main bot logic with aiogram
├── api_client.py            # API client for stickers.tools stats endpoint
├── user_states.py           # User state management system
├── config.py                # Configuration settings
├── requirements.txt         # Python dependencies
├── DEPLOYMENT.md            # Complete deployment guide
├── Makefile                 # Comprehensive automation for all operations
├── Dockerfile               # Docker container definition
├── docker-compose.yml       # Docker Compose configuration
├── .dockerignore           # Docker build exclusions
├── data/                   # Persistent bot data (auto-created)
│   ├── user_settings.json
│   ├── price_cache.json
│   └── notification_history.json
├── logs/                   # Application logs (auto-created)
│   └── bot.log
└── bundle_price.json       # Legacy stickerscan response sample
```

## Bot Commands

- `/start` - Initialize the bot and show welcome message
- `/settings` - Open the main settings menu
- `/cancel` - Cancel any active operation (collection creation, editing, etc.)

## Settings Menu

### Collection Settings
✅ **Fully Implemented:**
- **Add new collections** with guided 3-step process:
  1. Collection name (e.g., "Hamster Kombat")
  2. Sticker pack name (e.g., "Golden Hamster")  
  3. Launch price in TON (e.g., "10")
- **Edit existing collections** - modify any field
- **Delete collections** with confirmation
- **Real-time verification** - checks if collection exists during setup
- **Smart validation** - prevents invalid data entry

### Notification Settings
✅ **Fully Implemented:**
- **Buy alert multiplier** - get notified when prices drop below threshold
- **Sell alert multiplier** - get notified when prices rise above threshold
- **Interactive editing** - guided input with validation

### Collection Management
✅ **Fully Implemented:**
- **View all collections** - see your watchlist with details
- **Manual price checks** - instant price lookup for your collections
- **Automatic monitoring** - background price checking every 3 minutes

## How It Works

### Collection Creation Flow
1. User clicks "➕ Add New Collection"
2. **Step 1:** Enter collection name (validated 2-50 characters)
3. **Step 2:** Enter sticker pack name (validated 2-50 characters)
4. **Step 3:** Enter launch price (validated 0.01-10,000 TON)
5. **Verification:** Bot checks if collection exists in API
6. **Confirmation:** Review and confirm collection details
7. **Success:** Collection added to user's watchlist

### Price Monitoring
- **Automatic checks** every 3 minutes for all user collections
- **Threshold calculations** using launch price × multipliers
- **Smart notifications** sent when conditions are met
- **Multi-marketplace tracking** across all available markets

### Notification Examples

**Buy Alert:**
```
📈🔔 BUY OPPORTUNITY

🏷️ Collection: Hamster Kombat
📑 Sticker Pack: Golden Hamster  
💰 Lowest: 15.5 TON (≤ 20.0 TON)

🏪 Available on:
• MRKT: 15.5 TON
• Fragment: 16.2 TON

⏰ 14:32:15
```

**Sell Alert:**
```
📉🔔 SELL OPPORTUNITY

🏷️ Collection: Hamster Kombat
📑 Sticker Pack: Golden Hamster
💰 Highest: 45.2 TON (≥ 30.0 TON)

🏪 Available on:
• GetGems: 45.2 TON

⏰ 14:35:42
```

## API Integration

The bot now integrates with `https://stickers.tools/api/stats-new` to:
1. Fetch floor prices and market statistics for all sticker collections
2. Monitor price changes using public metrics (no webapp auth required)
3. Keep image previews in sync with stickers.tools metadata

## API Client Features

✅ **Implemented:**
- Public stats retrieval from stickers.tools
- Legacy bundle compatibility layer for existing bot features
- Collection price comparison and threshold checking
- Formatted notification system

## User Experience

### State Management
- **Flow-based interactions** - guided multi-step processes
- **Cancellation support** - `/cancel` command works anywhere
- **Input validation** - prevents errors with helpful feedback
- **Session persistence** - maintains user context during flows

### Error Handling
- **Graceful failures** - informative error messages
- **Retry mechanisms** - automatic API reconnection
- **Data validation** - prevents invalid configurations
- **User guidance** - clear instructions throughout

## Development Status

✅ **Completed Features:**
- Complete bot framework with aiogram
- API client with authentication
- User state management system  
- Collection creation/editing/deletion
- Notification settings management
- Price monitoring and alerts
- Real-time collection verification
- Input validation and error handling

## TODO

- [ ] Add price history tracking and trends
- [ ] Implement rate limiting and API error handling
- [ ] Add collection search/browse functionality
- [ ] Implement user analytics and statistics
- [ ] Add export/import settings functionality 
