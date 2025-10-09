# 🚀 Deployment Guide - Telegram Sticker Notifier Bot

This guide will walk you through deploying your Telegram Sticker Notifier Bot on a server using Docker.

> 💡 **Quick Start**: This project uses a comprehensive Makefile for all operations. Run `make help` to see all available commands!

## 📋 Prerequisites

### Server Requirements
- **OS**: Linux (Ubuntu 20.04+ recommended)
- **RAM**: Minimum 512MB, Recommended 1GB
- **Storage**: 2GB free space minimum
- **Network**: Internet connection for API access

### Software Requirements
- **Docker**: Latest stable version
- **Docker Compose**: v2.0+
- **Git**: For cloning/updating the repository

## 🛠️ Server Setup

### 1. Install Docker (Ubuntu/Debian)

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add user to docker group
sudo usermod -aG docker $USER

# Install Docker Compose (if not included)
sudo apt install docker-compose-plugin -y

# Verify installation
docker --version
docker compose version
```

### 2. Clone Repository

```bash
# Clone your bot repository
git clone <your-repository-url>
cd stickers_notifier_bot

# Or upload files manually if not using git
```

## ⚙️ Configuration

### 1. Create Environment File

Copy your working `.env` file to the server, or create it:

```bash
# Create .env file
nano .env
```

Add your configuration:

```bash
# Telegram Bot Configuration
BOT_TOKEN=your_telegram_bot_token_here

# OPTION 1: Use captured initData (Recommended)
TELEGRAM_INIT_DATA=user=%7B%22id%22%3A...your_captured_initdata_here

# OPTION 2: Manual account data (fallback)
TELEGRAM_USER_ID=your_telegram_user_id
TELEGRAM_FIRST_NAME=your_first_name
TELEGRAM_LAST_NAME=your_last_name
TELEGRAM_USERNAME=your_username
TELEGRAM_LANGUAGE_CODE=en
TELEGRAM_IS_PREMIUM=false
TELEGRAM_PHOTO_URL=
```

### 2. Secure the Configuration

```bash
# Set proper permissions
chmod 600 .env
```

## 🚀 Deployment

### Option 1: Automated Deployment (Recommended)

Use the provided Makefile:

```bash
# Deploy the bot (all-in-one command)
make deploy
```

This will:
- ✅ Check Docker installation
- ✅ Validate environment configuration
- ✅ Create necessary directories
- ✅ Build Docker image
- ✅ Start the bot in background

### Option 2: Step-by-Step Deployment

```bash
# Check prerequisites
make check-docker
make check-env

# Setup and build
make setup
make build

# Start the bot
make start
```

### Option 3: Manual Deployment

```bash
# Create directories
mkdir -p data logs

# Build Docker image
docker build -t stickers-notifier-bot .

# Start with Docker Compose
docker compose up -d

# Check status
docker compose ps
```

## 📊 Management

Use the Makefile for easy bot control:

```bash
# Get help with all available commands
make help

# Essential commands:
make status          # Check bot status and health
make logs            # View recent logs
make logs-follow     # Follow logs in real-time
make restart         # Restart the bot
make stop            # Stop the bot
make start           # Start the bot
make update          # Update and restart the bot
make backup          # Create backup of bot data
make clean           # Clean up old containers and images
```

### Examples

```bash
# Check if bot is running
make status

# Watch logs in real-time
make logs-follow

# Restart after configuration changes
make restart

# Create backup before updates
make backup

# Show all available commands
make help
```

## 📁 Data Persistence

The bot stores data in the following structure:

```
stickers_notifier_bot/
├── data/                 # Persistent bot data
│   ├── user_settings.json
│   ├── price_cache.json
│   └── notification_history.json
├── logs/                 # Application logs
│   ├── bot.log
│   ├── bot.log.1
│   └── ...
└── .env                  # Configuration (keep secure!)
```

### Backup Strategy

```bash
# Manual backup
make backup

# Scheduled backup (add to crontab)
0 2 * * * cd /path/to/bot && make backup

# Restore from backup
make restore BACKUP=backup_YYYYMMDD_HHMMSS.tar.gz
```

## 🔧 Monitoring

### Health Checks

The bot includes automatic health monitoring:

```bash
# Check health status
docker ps

# View health check logs
docker logs stickers-notifier-bot
```

### Log Monitoring

```bash
# Recent logs
make logs

# Follow logs in real-time
make logs-follow

# Check specific errors
make logs-errors
```

### Resource Monitoring

```bash
# Container resource usage
make stats

# Disk usage and bot status
make status

# System information
make system-info
```

## 🔄 Updates

### Manual Update

```bash
# Update and restart (includes git pull if repository)
make update

# Or step by step
git pull
make build
make restart
```

### Automated Updates

Add to crontab for weekly updates:

```bash
# Edit crontab
crontab -e

# Add weekly update (Sundays at 3 AM)
0 3 * * 0 cd /path/to/bot && make update
```

## 🛡️ Security Best Practices

### 1. File Permissions

```bash
# Secure environment file
chmod 600 .env

# Secure scripts
chmod 755 deploy.sh manage.sh

# Secure data directory
chmod 755 data logs
```

### 2. Firewall Configuration

```bash
# UFW (Ubuntu)
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### 3. Regular Updates

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Update Docker images
docker system prune -f
```

## 🔍 Troubleshooting

### Common Issues

#### Bot Not Starting

```bash
# Check logs
make logs

# Check configuration
make env-check

# Verify Docker
make ps
```

#### Permission Errors

```bash
# Fix data directory permissions
sudo chown -R $USER:$USER data logs

# Check environment configuration
make env-check
```

#### Network Issues

```bash
# Test API connectivity
curl -s "https://api.telegram.org/bot$BOT_TOKEN/getMe"

# Test stickers.tools stats endpoint
curl -s "https://stickers.tools/api/stats-new" | head
```

#### High Memory Usage

```bash
# Check resource usage
make stats

# Restart bot
make restart

# Clean up old data
make clean
```

### Log Analysis

```bash
# Find error logs
make logs-errors

# Check recent logs for patterns
make logs

# Follow logs in real-time
make logs-follow
```

## 🔧 Development

For local development and testing:

### Local Development Environment

```bash
# Setup Python virtual environment
make dev-setup

# Run bot locally (without Docker)
make dev-run

# Test authentication
make test-auth
```

### Development Commands

```bash
# Get help with all commands
make help

# Build and restart (for development)
make rebuild

# Open shell in running container
make shell

# Check environment configuration
make env-check

# Show container information
make ps
make images
make system-info
```

### Container Development

```bash
# Build only
make build

# Start/stop individual services
make start
make stop
make restart

# View logs during development
make logs-follow
```

## 📱 Production Checklist

Before going live, ensure:

- [ ] ✅ Bot token is correctly configured
- [ ] ✅ Telegram account data is properly set
- [ ] ✅ Health check is passing
- [ ] ✅ Logs show successful API authentication
- [ ] ✅ Test notifications are working
- [ ] ✅ Data persistence is working
- [ ] ✅ Backup system is configured
- [ ] ✅ Monitoring is in place
- [ ] ✅ Firewall is properly configured

## 🆘 Support

If you encounter issues:

1. **Check logs**: `make logs`
2. **Verify configuration**: `make env-check`
3. **Test connectivity**: Ensure API access works
4. **Restart services**: `make restart`
5. **Clean up**: `make clean`

### All Available Commands

Run `make help` to see all available commands with descriptions.

## 📈 Performance Optimization

### Resource Limits

Edit `docker-compose.yml` to adjust resource limits:

```yaml
deploy:
  resources:
    limits:
      memory: 256M      # Adjust based on usage
      cpus: '0.5'       # Adjust based on server capacity
```

### Log Rotation

Logs are automatically rotated, but you can adjust in `main.py`:

```python
file_handler = logging.handlers.RotatingFileHandler(
    os.path.join(LOGS_DIR, 'bot.log'),
    maxBytes=10*1024*1024,  # 10MB (adjust as needed)
    backupCount=5           # Keep 5 old files
)
```

Your bot is now ready for production deployment! 🎉 
