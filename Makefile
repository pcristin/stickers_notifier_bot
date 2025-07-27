# Telegram Sticker Notifier Bot - Makefile
# Comprehensive build, deployment, and management automation

# Configuration
COMPOSE_CMD := $(shell docker compose version >/dev/null 2>&1 && echo "docker compose" || echo "docker-compose")
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
	@echo "  $(WHITE)make logs$(RESET)       # View recent logs"
	@echo "  $(WHITE)make restart$(RESET)    # Restart the bot"
	@echo "  $(WHITE)make backup$(RESET)     # Create data backup"


# =============================================================================
# CONTAINER MANAGEMENT
# =============================================================================
.PHONY: build
build: ### Build containter with docker-compose
	@echo "$(BLUE)[INFO]$(RESET) Building the bot"
	@$(COMPOSE_CMD) build
	@echo "$(GREEN)[SUCCESS]$(RESET) Container build"

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
	@$(COMPOSE_CMD) build
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

.PHONY: clean
clean: ## Clean up old containers and images
	@echo "$(BLUE)[INFO]$(RESET) Cleaning up old containers and images..."
	@docker container prune -f
	@docker image prune -f
	@if [ -d "$(LOGS_DIR)" ]; then \
		find $(LOGS_DIR)/ -name "*.log.*" -mtime +30 -delete 2>/dev/null || true; \
	fi
	@echo "$(GREEN)[SUCCESS]$(RESET) Cleanup completed"

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
# ALIASES AND SHORTCUTS
# =============================================================================

.PHONY: follow
follow: logs-follow ## Alias for logs-follow
