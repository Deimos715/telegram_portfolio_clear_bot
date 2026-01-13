# ===== Settings =====
COMPOSE := docker compose
SERVICE_BOT := bot
SERVICE_DB  := db

# ===== Help =====
.PHONY: help
help:
	@echo 'Targets:'
	@echo '  make build        - собрать образы'
	@echo '  make up           - поднять всё в фоне'
	@echo '  make up-build     - пересобрать и поднять'
	@echo '  make down         - остановить и удалить контейнеры'
	@echo '  make restart      - перезапустить только бот'
	@echo '  make logs         - логи бота (follow)'
	@echo '  make logs-db      - логи базы (follow)'
	@echo '  make ps           - статус сервисов'
	@echo '  make shell        - войти в контейнер бота (sh)'
	@echo '  make db-shell     - войти в контейнер базы (sh)'
	@echo '  make psql         - открыть psql к базе внутри контейнера'
	@echo '  make pull         - подтянуть свежие образы'

# ===== Lifecycle =====
.PHONY: build up up-build down restart ps pull
build:
	$(COMPOSE) build

up:
	$(COMPOSE) up -d

up-build:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart $(SERVICE_BOT)

ps:
	$(COMPOSE) ps

pull:
	$(COMPOSE) pull

# ===== Logs =====
.PHONY: logs logs-db
logs:
	$(COMPOSE) logs -f $(SERVICE_BOT)

logs-db:
	$(COMPOSE) logs -f $(SERVICE_DB)

# ===== Shells =====
.PHONY: shell db-shell psql
shell:
	$(COMPOSE) exec $(SERVICE_BOT) sh

db-shell:
	$(COMPOSE) exec $(SERVICE_DB) sh

psql:
	$(COMPOSE) exec -e PGPASSWORD=botpass $(SERVICE_DB) psql -U botuser -d botdb
