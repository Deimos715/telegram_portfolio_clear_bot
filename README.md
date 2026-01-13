# Aiogram 3.x — структура как в статье (без реферальной системы)

Файлы и папки названы строго как в статье, но рефералка удалена.  
Используется `asyncpg-lite` с `ROOT_PASS` для опасных операций.

## Быстрый старт

1. Установить зависимости:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

2. Создать `.env` на основе примера и заполнить:

```env
TOKEN=your_bot_token
ADMINS=your_admins_ids
ROOT_PASS=change_me_strong_password
PG_LINK=postgresql://user:pass@localhost:5432/namedb
```

3. Запустить:

```bash
python aiogram_run.py
```

## Запуск с Docker

```bash
docker-compose -f docker-compose.yml up --build   # сборка и запуск проекта
docker compose -f docker-compose.yml down   # остановка и удаления контейнеров

docker-compose up # запуск контейнеров
docker compose up -d # запуск контейнеров в фоне
docker compose stop   # остановка контейнеров
```

## Команды

-   /start — регистрация/приветствие
-   /profile — мой профиль
-   /help — помощь
-   «⚙️ Админ панель» — кнопка для админов

## Структура

-   `create_bot.py` — инициализация бота/диспетчера, `db_manager` (asyncpg-lite), загрузка .env.
-   `aiogram_run.py` — точка входа, подключение роутеров, команды, уведомления админам.
-   `db_handler/db_funk.py` — функции БД: `init_db`, `insert_user`, `get_user_data`, `get_all_users`.
-   `handlers/user_router.py` — `/start`, `/profile`, «Назад».
-   `handlers/admin_panel.py` — вывод информации о пользователях (без рефералки).
-   `keyboards/kbs.py` — клавиатуры: главная, «Назад» (+ админ‑кнопка).
-   `utils/utils.py` — утилиты (заглушка).
