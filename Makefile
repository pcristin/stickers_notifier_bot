# Telegram Sticker Notifier Bot - Makefile
# Comprehensive build, deployment, and management automation

# Configuration
COMPOSE_CMD := $(shell command -v docker-compose 2> /dev/null || echo "docker compose")
CONTAINER_NAME := stickers-notifier-bot
IMAGE_NAME := stickers-notifier-bot
DATA_DIR := data
LOGS_DIR := logs

# Colors for output
RED := \033[31m
GREEN := \033[32m
YELLOW := \033[33m
BLUE := \033[34m
MAGENTA := \033[35m
CYAN := \033[36m
WHITE := \033[37m
RESET := \033[0m

# Default target
.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help message
	@echo "$(CYAN)🤖 Telegram Sticker Notifier Bot$(RESET)"
	@echo "$(CYAN)================================$(RESET)"
	@echo ""
	@echo "$(YELLOW)Available targets:$(RESET)"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  $(GREEN)%-15s$(RESET) %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "$(YELLOW)Examples:$(RESET)"
	@echo "  $(WHITE)make deploy$(RESET)     # Deploy the bot"
	@echo "  $(WHITE)make logs$(RESET)       # View recent logs"
	@echo "  $(WHITE)make restart$(RESET)    # Restart the bot"
	@echo "  $(WHITE)make backup$(RESET)     # Create data backup"

# =============================================================================
# SETUP AND DEPLOYMENT
# =============================================================================

.PHONY: check-docker
check-docker: ## Check if Docker and Docker Compose are installed
	@echo "$(BLUE)[INFO]$(RESET) Checking Docker installation..."
	@command -v docker >/dev/null 2>&1 || { echo "$(RED)[ERROR]$(RESET) Docker is not installed"; exit 1; }
	@docker compose version >/dev/null 2>&1 || command -v docker-compose >/dev/null 2>&1 || { echo "$(RED)[ERROR]$(RESET) Docker Compose is not installed"; exit 1; }
	@echo "$(GREEN)[SUCCESS]$(RESET) Docker and Docker Compose are installed"

.PHONY: check-env
check-env: ## Check if .env file is properly configured
	@echo "$(BLUE)[INFO]$(RESET) Checking environment configuration..."
	@test -f .env || { echo "$(RED)[ERROR]$(RESET) .env file not found. Run 'make init-env' first"; exit 1; }
	@grep -q "your_telegram_bot_token_here" .env && { echo "$(RED)[ERROR]$(RESET) Please set your BOT_TOKEN in .env file"; exit 1; } || true
	@echo "$(GREEN)[SUCCESS]$(RESET) Environment configuration is valid"

.PHONY: init-env
init-env: ## Create .env template file
	@echo "$(BLUE)[INFO]$(RESET) Creating .env template..."
	@test -f .env && { echo "$(YELLOW)[WARNING]$(RESET) .env file already exists"; exit 1; } || true
	@echo "# Telegram Bot Configuration" > .env
	@echo "BOT_TOKEN=your_telegram_bot_token_here" >> .env
	@echo "" >> .env
	@echo "# OPTION 1: Use captured initData (Recommended)" >> .env
	@echo "TELEGRAM_INIT_DATA=user=%7B%22id%22%3A...your_captured_initdata_here" >> .env
	@echo "" >> .env
	@echo "# OPTION 2: Manual account data (fallback)" >> .env
	@echo "TELEGRAM_USER_ID=your_telegram_user_id" >> .env
	@echo "TELEGRAM_FIRST_NAME=your_first_name" >> .env
	@echo "TELEGRAM_LAST_NAME=your_last_name" >> .env
	@echo "TELEGRAM_USERNAME=your_username" >> .env
	@echo "TELEGRAM_LANGUAGE_CODE=en" >> .env
	@echo "TELEGRAM_IS_PREMIUM=false" >> .env
	@echo "TELEGRAM_PHOTO_URL=" >> .env
	@chmod 600 .env
	@echo "$(GREEN)[SUCCESS]$(RESET) .env template created"
	@echo "$(YELLOW)[WARNING]$(RESET) Please edit .env file with your configuration"

.PHONY: setup
setup: check-docker ## Create necessary directories and set permissions
	@echo "$(BLUE)[INFO]$(RESET) Setting up directories..."
	@mkdir -p $(DATA_DIR) $(LOGS_DIR)
	@chmod 755 $(DATA_DIR) $(LOGS_DIR)
	@echo "$(GREEN)[SUCCESS]$(RESET) Directories created and configured"

.PHONY: build
build: ## Build Docker image
	@echo "$(BLUE)[INFO]$(RESET) Building Docker image..."
	@docker build -t $(IMAGE_NAME) .
	@echo "$(GREEN)[SUCCESS]$(RESET) Docker image built successfully"

.PHONY: deploy
deploy: check-docker check-env setup build ## Complete deployment (setup + build + start)
	@echo "$(BLUE)[INFO]$(RESET) Starting deployment..."
	@$(COMPOSE_CMD) up -d
	@echo ""
	@echo "$(GREEN)[SUCCESS]$(RESET) 🎉 Bot deployed successfully!"
	@echo ""
	@echo "$(YELLOW)Management commands:$(RESET)"
	@echo "  $(WHITE)make status$(RESET)   # Check bot status"
	@echo "  $(WHITE)make logs$(RESET)     # View logs"
	@echo "  $(WHITE)make restart$(RESET)  # Restart bot"
	@echo "  $(WHITE)make stop$(RESET)     # Stop bot"
	@echo ""
	@$(MAKE) status

# =============================================================================
# CONTAINER MANAGEMENT
# =============================================================================

.PHONY: start
start: ## Start the bot container
	@echo "$(BLUE)[INFO]$(RESET) Starting bot..."
	@$(COMPOSE_CMD) up -d $(CONTAINER_NAME)
	@echo "$(GREEN)[SUCCESS]$(RESET) Bot started"
	@$(MAKE) status

.PHONY: stop
stop: ## Stop the bot container
	@echo "$(BLUE)[INFO]$(RESET) Stopping bot..."
	@$(COMPOSE_CMD) stop $(CONTAINER_NAME)
	@echo "$(GREEN)[SUCCESS]$(RESET) Bot stopped"

.PHONY: restart
restart: ## Restart the bot container
	@echo "$(BLUE)[INFO]$(RESET) Restarting bot..."
	@$(COMPOSE_CMD) restart $(CONTAINER_NAME)
	@echo "$(GREEN)[SUCCESS]$(RESET) Bot restarted"
	@$(MAKE) status

.PHONY: down
down: ## Stop and remove containers
	@echo "$(BLUE)[INFO]$(RESET) Stopping and removing containers..."
	@$(COMPOSE_CMD) down
	@echo "$(GREEN)[SUCCESS]$(RESET) Containers stopped and removed"

# =============================================================================
# MONITORING AND LOGS
# =============================================================================

.PHONY: status
status: ## Show bot status and health information
	@echo "$(BLUE)[INFO]$(RESET) Bot status:"
	@$(COMPOSE_CMD) ps
	@echo ""
	@container_id=$$(docker ps -q -f name=$(CONTAINER_NAME)); \
	if [ -n "$$container_id" ]; then \
		health=$$(docker inspect --format='{{.State.Health.Status}}' $$container_id 2>/dev/null || echo "unknown"); \
		if [ "$$health" = "healthy" ]; then \
			echo "$(GREEN)[SUCCESS]$(RESET) Bot is healthy ✅"; \
		elif [ "$$health" = "unhealthy" ]; then \
			echo "$(RED)[ERROR]$(RESET) Bot is unhealthy ❌"; \
		else \
			echo "$(YELLOW)[WARNING]$(RESET) Health status: $$health"; \
		fi \
	else \
		echo "$(RED)[ERROR]$(RESET) Bot container is not running"; \
	fi
	@echo ""
	@if [ -d "$(DATA_DIR)" ]; then \
		data_size=$$(du -sh $(DATA_DIR)/ | cut -f1); \
		echo "$(BLUE)[INFO]$(RESET) Data directory size: $$data_size"; \
	fi
	@if [ -d "$(LOGS_DIR)" ]; then \
		logs_size=$$(du -sh $(LOGS_DIR)/ | cut -f1); \
		echo "$(BLUE)[INFO]$(RESET) Logs directory size: $$logs_size"; \
	fi

.PHONY: logs
logs: ## Show recent bot logs
	@echo "$(BLUE)[INFO]$(RESET) Recent bot logs:"
	@$(COMPOSE_CMD) logs --tail=50 $(CONTAINER_NAME)

.PHONY: logs-follow
logs-follow: ## Follow bot logs in real-time
	@echo "$(BLUE)[INFO]$(RESET) Following bot logs (Ctrl+C to stop):"
	@$(COMPOSE_CMD) logs -f $(CONTAINER_NAME)

.PHONY: logs-errors
logs-errors: ## Show only error logs
	@echo "$(BLUE)[INFO]$(RESET) Error logs:"
	@$(COMPOSE_CMD) logs $(CONTAINER_NAME) | grep -i error || echo "No errors found"

.PHONY: health
health: ## Check container health
	@container_id=$$(docker ps -q -f name=$(CONTAINER_NAME)); \
	if [ -n "$$container_id" ]; then \
		echo "$(BLUE)[INFO]$(RESET) Container health details:"; \
		docker inspect --format='{{json .State.Health}}' $$container_id | jq .; \
	else \
		echo "$(RED)[ERROR]$(RESET) Container not running"; \
	fi

.PHONY: stats
stats: ## Show resource usage statistics
	@echo "$(BLUE)[INFO]$(RESET) Resource usage:"
	@docker stats $(CONTAINER_NAME) --no-stream

# =============================================================================
# MAINTENANCE
# =============================================================================

.PHONY: update
update: ## Update bot (rebuild image and restart)
	@echo "$(BLUE)[INFO]$(RESET) Updating bot..."
	@if [ -d ".git" ]; then \
		echo "$(BLUE)[INFO]$(RESET) Pulling latest changes..."; \
		git pull; \
	fi
	@echo "$(BLUE)[INFO]$(RESET) Rebuilding Docker image..."
	@docker build -t $(IMAGE_NAME) .
	@echo "$(BLUE)[INFO]$(RESET) Restarting with new image..."
	@$(COMPOSE_CMD) up -d --force-recreate $(CONTAINER_NAME)
	@echo "$(GREEN)[SUCCESS]$(RESET) Bot updated successfully"
	@$(MAKE) status

.PHONY: backup
backup: ## Create backup of bot data
	@timestamp=$$(date +"%Y%m%d_%H%M%S"); \
	backup_file="backup_$$timestamp.tar.gz"; \
	echo "$(BLUE)[INFO]$(RESET) Creating backup: $$backup_file"; \
	if [ -d "$(DATA_DIR)" ]; then \
		tar -czf "$$backup_file" $(DATA_DIR)/ $(LOGS_DIR)/ .env 2>/dev/null || tar -czf "$$backup_file" $(DATA_DIR)/; \
		echo "$(GREEN)[SUCCESS]$(RESET) Backup created: $$backup_file"; \
	else \
		echo "$(RED)[ERROR]$(RESET) No data directory found to backup"; \
		exit 1; \
	fi

.PHONY: restore
restore: ## Restore data from backup (Usage: make restore BACKUP=backup_file.tar.gz)
	@if [ -z "$(BACKUP)" ]; then \
		echo "$(RED)[ERROR]$(RESET) Please specify backup file: make restore BACKUP=backup_file.tar.gz"; \
		exit 1; \
	fi
	@if [ ! -f "$(BACKUP)" ]; then \
		echo "$(RED)[ERROR]$(RESET) Backup file not found: $(BACKUP)"; \
		exit 1; \
	fi
	@echo "$(YELLOW)[WARNING]$(RESET) This will overwrite existing data. Continue? [y/N]"; \
	read -r response; \
	if [ "$$response" = "y" ] || [ "$$response" = "Y" ]; then \
		echo "$(BLUE)[INFO]$(RESET) Stopping bot..."; \
		$(COMPOSE_CMD) stop $(CONTAINER_NAME); \
		echo "$(BLUE)[INFO]$(RESET) Restoring data from: $(BACKUP)"; \
		tar -xzf "$(BACKUP)"; \
		echo "$(BLUE)[INFO]$(RESET) Starting bot..."; \
		$(COMPOSE_CMD) up -d $(CONTAINER_NAME); \
		echo "$(GREEN)[SUCCESS]$(RESET) Data restored successfully"; \
	else \
		echo "$(BLUE)[INFO]$(RESET) Restore cancelled"; \
	fi

.PHONY: clean
clean: ## Clean up old containers and images
	@echo "$(BLUE)[INFO]$(RESET) Cleaning up old containers and images..."
	@docker container prune -f
	@docker image prune -f
	@if [ -d "$(LOGS_DIR)" ]; then \
		find $(LOGS_DIR)/ -name "*.log.*" -mtime +30 -delete 2>/dev/null || true; \
	fi
	@echo "$(GREEN)[SUCCESS]$(RESET) Cleanup completed"

.PHONY: clean-all
clean-all: down ## Remove everything (containers, images, volumes)
	@echo "$(YELLOW)[WARNING]$(RESET) This will remove all containers, images, and volumes. Continue? [y/N]"
	@read -r response; \
	if [ "$$response" = "y" ] || [ "$$response" = "Y" ]; then \
		echo "$(BLUE)[INFO]$(RESET) Removing everything..."; \
		$(COMPOSE_CMD) down -v --rmi all --remove-orphans; \
		docker system prune -af --volumes; \
		echo "$(GREEN)[SUCCESS]$(RESET) Everything cleaned"; \
	else \
		echo "$(BLUE)[INFO]$(RESET) Clean cancelled"; \
	fi

# =============================================================================
# DEVELOPMENT
# =============================================================================

.PHONY: dev-setup
dev-setup: ## Setup development environment
	@echo "$(BLUE)[INFO]$(RESET) Setting up development environment..."
	@python -m venv venv
	@. venv/bin/activate && pip install --upgrade pip
	@. venv/bin/activate && pip install -r requirements.txt
	@echo "$(GREEN)[SUCCESS]$(RESET) Development environment ready"
	@echo "$(YELLOW)[INFO]$(RESET) Activate with: source venv/bin/activate"

.PHONY: dev-run
dev-run: ## Run bot locally for development
	@echo "$(BLUE)[INFO]$(RESET) Running bot in development mode..."
	@. venv/bin/activate && python main.py

.PHONY: test-auth
test-auth: ## Test API authentication
	@echo "$(BLUE)[INFO]$(RESET) Testing authentication..."
	@. venv/bin/activate && python test_auth.py

.PHONY: shell
shell: ## Open shell in running container
	@docker exec -it $(CONTAINER_NAME) /bin/bash

.PHONY: rebuild
rebuild: stop build start ## Stop, rebuild, and start (for development)

# =============================================================================
# UTILITIES
# =============================================================================

.PHONY: env-check
env-check: ## Validate environment variables
	@echo "$(BLUE)[INFO]$(RESET) Environment validation:"
	@if [ -f ".env" ]; then \
		echo "$(GREEN)✓$(RESET) .env file exists"; \
		if grep -q "your_telegram_bot_token_here" .env; then \
			echo "$(RED)✗$(RESET) BOT_TOKEN not configured"; \
		else \
			echo "$(GREEN)✓$(RESET) BOT_TOKEN configured"; \
		fi; \
		if grep -q "TELEGRAM_INIT_DATA" .env && ! grep -q "your_captured_initdata_here" .env; then \
			echo "$(GREEN)✓$(RESET) TELEGRAM_INIT_DATA configured"; \
		else \
			echo "$(YELLOW)!$(RESET) TELEGRAM_INIT_DATA not configured (using fallback)"; \
		fi; \
	else \
		echo "$(RED)✗$(RESET) .env file missing"; \
	fi

.PHONY: ps
ps: ## Show all containers
	@docker ps -a

.PHONY: images
images: ## Show Docker images
	@docker images | grep -E "($(IMAGE_NAME)|TAG)"

.PHONY: system-info
system-info: ## Show system information
	@echo "$(BLUE)[INFO]$(RESET) System Information:"
	@echo "Docker version: $$(docker --version)"
	@echo "Compose command: $(COMPOSE_CMD)"
	@echo "Available disk space: $$(df -h . | tail -1 | awk '{print $$4}')"
	@echo "Memory usage: $$(free -h | grep Mem | awk '{print $$3 "/" $$2}')"

# =============================================================================
# ALIASES AND SHORTCUTS
# =============================================================================

.PHONY: up
up: start ## Alias for start

.PHONY: down-all
down-all: down ## Alias for down

.PHONY: log
log: logs ## Alias for logs

.PHONY: follow
follow: logs-follow ## Alias for logs-follow

.PHONY: build-deploy
build-deploy: build deploy ## Build and deploy in one command 