from typing import Any, Dict, List, Optional
import json
from create_bot import db_manager
from sqlalchemy import BigInteger, String, TIMESTAMP, text

USERS_TABLE = 'users_reg'
CASES_TABLE = 'cases'
IMAGES_TABLE = 'case_images'
EVENTS_TABLE = 'user_events'


# Создаём таблицу users_reg, если её ещё нет
async def init_db() -> None:
    users_sql = f"""
    CREATE TABLE IF NOT EXISTS {USERS_TABLE} (
        user_id   BIGINT PRIMARY KEY,
        full_name VARCHAR(255),
        user_login VARCHAR(255),
        date_reg  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """

    cases_sql = f"""
    CREATE TABLE IF NOT EXISTS {CASES_TABLE} (
        case_id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        title          VARCHAR(255)  NOT NULL,
        description    VARCHAR(2000) NOT NULL,

        status         VARCHAR(20) NOT NULL DEFAULT 'draft',
        sort_order     INT NOT NULL DEFAULT 0,

        created     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

        CHECK (status IN ('draft', 'published', 'archived'))
    );
    """

    images_sql = f"""
    CREATE TABLE IF NOT EXISTS {IMAGES_TABLE} (
        image_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        case_id        BIGINT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,

        tg_file_id     VARCHAR(300) NOT NULL,
        media_type    VARCHAR(10) NOT NULL DEFAULT 'photo',

        position       INT NOT NULL DEFAULT 0,
        is_cover       BOOLEAN NOT NULL DEFAULT FALSE,

        created     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """

    images_idx1_sql = f"""
    CREATE INDEX IF NOT EXISTS idx_case_images_case_id
    ON {IMAGES_TABLE}(case_id);
    """

    images_idx2_sql = f"""
    CREATE INDEX IF NOT EXISTS idx_case_images_position
    ON {IMAGES_TABLE}(case_id, position);
    """

    events_sql = f"""
    CREATE TABLE IF NOT EXISTS {EVENTS_TABLE} (
        event_id        BIGSERIAL PRIMARY KEY,
        user_id         BIGINT NOT NULL,
        event_type      VARCHAR(64) NOT NULL,
        event_context   VARCHAR(64),
        event_value     VARCHAR(128),
        payload         JSONB,
        created_at      TIMESTAMP NOT NULL DEFAULT NOW()
    );
    """

    events_idx_user_sql = f"""
    CREATE INDEX IF NOT EXISTS idx_user_events_user_id
    ON {EVENTS_TABLE}(user_id);
    """

    events_idx_type_sql = f"""
    CREATE INDEX IF NOT EXISTS idx_user_events_event_type
    ON {EVENTS_TABLE}(event_type);
    """

    events_idx_created_sql = f"""
    CREATE INDEX IF NOT EXISTS idx_user_events_created_at
    ON {EVENTS_TABLE}(created_at);
    """

    reviews_sql = """
    CREATE TABLE IF NOT EXISTS case_reviews (
        review_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        case_id BIGINT NOT NULL UNIQUE REFERENCES cases(case_id) ON DELETE CASCADE,
        created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """

    review_items_sql = """
    CREATE TABLE IF NOT EXISTS case_review_items (
        item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        review_id BIGINT NOT NULL REFERENCES case_reviews(review_id) ON DELETE CASCADE,
        tg_file_id VARCHAR(300),
        media_type VARCHAR(20) NOT NULL,
        text_content VARCHAR(4000),
        position INT NOT NULL DEFAULT 0,
        created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """

    review_idx_sql = """
    CREATE INDEX IF NOT EXISTS idx_case_reviews_case_id
    ON case_reviews(case_id);
    """

    review_items_idx_sql = """
    CREATE INDEX IF NOT EXISTS idx_case_review_items_review_id_position
    ON case_review_items(review_id, position);
    """

    cta_sql = """
    CREATE TABLE IF NOT EXISTS case_cta (
        case_id BIGINT PRIMARY KEY REFERENCES cases(case_id) ON DELETE CASCADE,
        button_text VARCHAR(64) NOT NULL DEFAULT 'Связаться со мной',
        action_type VARCHAR(16) NOT NULL DEFAULT 'contact',
        action_value VARCHAR(255),
        updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """

    settings_sql = """
    CREATE TABLE IF NOT EXISTS bot_settings (
        key TEXT PRIMARY KEY,
        value TEXT,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """
    async with db_manager as client:
        # Открываем ассинхронную сессию
        async with client.session() as session:
            await session.execute(text(users_sql))
            await session.execute(text(cases_sql))
            await session.execute(text(images_sql))
            await session.execute(text(events_sql))
            await session.execute(text(reviews_sql))
            await session.execute(text(review_items_sql))
            await session.execute(text(review_idx_sql))
            await session.execute(text(review_items_idx_sql))
            await session.execute(text(cta_sql))
            await session.execute(text(settings_sql))
            await session.execute(text(
                f"ALTER TABLE {IMAGES_TABLE} "
                "ADD COLUMN IF NOT EXISTS media_type VARCHAR(10) NOT NULL DEFAULT 'photo';"
            ))
            await session.execute(text(images_idx1_sql))
            await session.execute(text(images_idx2_sql))
            await session.execute(text(events_idx_user_sql))
            await session.execute(text(events_idx_type_sql))
            await session.execute(text(events_idx_created_sql))
            await session.commit()


# Обёртка для вызова init_db — создаём таблицы
async def create_tables() -> None:
    await init_db()


# Получаем данные конкретного пользователя по user_id
async def get_user_data(user_id: int, table_name: str = USERS_TABLE) -> Optional[Dict[str, Any]]:
    async with db_manager as client:
        return await client.select_data(
            table_name=table_name,
            where_dict={'user_id': user_id},
            one_dict=True
        )


async def get_setting(key: str, default: str | None = None) -> str | None:
    sql = text("SELECT value FROM bot_settings WHERE key = :key;")
    async with db_manager as client:
        async with client.session() as session:
            res = await session.execute(sql, {"key": key})
            value = res.scalar_one_or_none()
            return value if value is not None else default


async def set_setting(key: str, value: str) -> None:
    sql = text("""
        INSERT INTO bot_settings (key, value, updated_at)
        VALUES (:key, :value, CURRENT_TIMESTAMP)
        ON CONFLICT (key)
        DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP;
    """)
    async with db_manager as client:
        async with client.session() as session:
            await session.execute(sql, {"key": key, "value": value})
            await session.commit()


async def db_ping() -> bool:
    sql = text("SELECT 1;")
    try:
        async with db_manager as client:
            async with client.session() as session:
                await session.execute(sql)
        return True
    except Exception:
        return False


# Возвращаем список всех пользователей или только их количество
async def get_all_users(table_name: str = USERS_TABLE, count: bool = False):
    async with db_manager as client:
        all_users: List[Dict[str, Any]] = await client.select_data(table_name=table_name)
        if count:
            return len(all_users)
        return all_users
    
    
async def get_user_count(table_name: str = USERS_TABLE) -> int:
    sql = text(f"SELECT COUNT(*) FROM {table_name};")

    async with db_manager as client:
        async with client.session() as session:
            result = await session.execute(sql)
            return int(result.scalar_one())


async def get_cases_count(status: Optional[str] = None, table_name: str = CASES_TABLE) -> int:
    where_sql = ""
    params: Dict[str, Any] = {}
    if status:
        where_sql = "WHERE status = :status"
        params["status"] = status

    sql = text(f"SELECT COUNT(*) FROM {table_name} {where_sql};")

    async with db_manager as client:
        async with client.session() as session:
            result = await session.execute(sql, params)
            return int(result.scalar_one())


async def get_case_media_count(table_name: str = IMAGES_TABLE) -> int:
    sql = text(f"SELECT COUNT(*) FROM {table_name};")

    async with db_manager as client:
        async with client.session() as session:
            result = await session.execute(sql)
            return int(result.scalar_one())

# Добавляем пользователя в таблицу или обновляем данные, если такой user_id уже есть
async def insert_user(user_data: Dict[str, Any], table_name: str = USERS_TABLE) -> None:
    async with db_manager as client:
        await client.insert_data_with_update(
            table_name=table_name,
            records_data=user_data,
            conflict_column='user_id',
            update_on_conflict=True
        )


ALLOWED_CASE_FIELDS = {"title", "description", "status", "sort_order"}


async def get_cases_page(
    page: int = 0,
    limit: int = 6,
    table_name: str = CASES_TABLE,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    
     # защита от мусора
    page = max(int(page), 0)
    limit = max(int(limit), 1)

    page_size = (limit - 1) if limit > 1 else limit
    offset = page * page_size

    where_sql = ""
    params = {"limit": limit, "offset": offset}

    if status:
        where_sql = "WHERE status = :status"
        params["status"] = status

    sql = text(f"""
        SELECT
            case_id,
            title,
            description,
            status,
            sort_order,
            created,
            updated
        FROM {table_name}
        {where_sql}
        ORDER BY sort_order ASC, created DESC, case_id DESC
        LIMIT :limit OFFSET :offset;
    """)

    async with db_manager as client:
        async with client.session() as session:
            result = await session.execute(sql, params)
            rows = result.fetchall()
            return [dict(row._mapping) for row in rows]
        

async def create_case_draft(
    title: str = "Новый кейс",
    description: str = "Описание не задано",
    sort_order: int = 0,
    table_name: str = CASES_TABLE
) -> int:
    sql = text(f"""
        INSERT INTO {table_name} (title, description, status, sort_order)
        VALUES (:title, :description, 'draft', :sort_order)
        RETURNING case_id;
    """)
    async with db_manager as client:
        async with client.session() as session:
            res = await session.execute(sql, {
                "title": title,
                "description": description,
                "sort_order": sort_order
            })
            case_id = int(res.scalar_one())
            await session.commit()
            return case_id
        

async def get_case_by_id(case_id: int, table_name: str = CASES_TABLE) -> Optional[Dict[str, Any]]:
    sql = text(f"""
        SELECT case_id, title, description, status, sort_order, created, updated
        FROM {table_name}
        WHERE case_id = :case_id;
    """)
    async with db_manager as client:
        async with client.session() as session:
            res = await session.execute(sql, {"case_id": case_id})
            row = res.fetchone()
            return dict(row._mapping) if row else None
        

async def update_case_field(case_id: int, field: str, value: Any, table_name: str = CASES_TABLE) -> None:
    if field not in ALLOWED_CASE_FIELDS:
        raise ValueError("Field not allowed")

    sql = text(f"""
        UPDATE {table_name}
        SET {field} = :value,
            updated = CURRENT_TIMESTAMP
        WHERE case_id = :case_id;
    """)
    async with db_manager as client:
        async with client.session() as session:
            await session.execute(sql, {"case_id": case_id, "value": value})
            await session.commit()


async def set_case_cover(case_id: int, tg_file_id: str, table_name: str = IMAGES_TABLE) -> None:
    """
    Делает указанное изображение обложкой кейса:
    - сбрасывает is_cover у всех картинок кейса
    - вставляет новую запись как cover
    """
    sql_reset = text(f"""
        UPDATE {table_name}
        SET is_cover = FALSE
        WHERE case_id = :case_id;
    """)

    sql_insert = text(f"""
        INSERT INTO {table_name} (case_id, tg_file_id, position, is_cover)
        VALUES (:case_id, :tg_file_id, 0, TRUE);
    """)

    async with db_manager as client:
        async with client.session() as session:
            await session.execute(sql_reset, {"case_id": case_id})
            await session.execute(sql_insert, {"case_id": case_id, "tg_file_id": tg_file_id})
            await session.commit()


async def add_case_images(
    case_id: int,
    tg_file_ids: List[str],
    make_first_cover: bool = True,
    table_name: str = IMAGES_TABLE
) -> None:
    if not tg_file_ids:
        return

    sql_reset_cover = text(f"""
        UPDATE {table_name}
        SET is_cover = FALSE
        WHERE case_id = :case_id;
    """)

    sql_insert = text(f"""
        INSERT INTO {table_name} (case_id, tg_file_id, position, is_cover)
        VALUES (:case_id, :tg_file_id, :position, :is_cover);
    """)

    async with db_manager as client:
        async with client.session() as session:
            # если хотим перезаписывать альбом — очищаем cover (не удаляем старые, только меняем признак)
            await session.execute(sql_reset_cover, {"case_id": case_id})

            for i, fid in enumerate(tg_file_ids):
                is_cover = (i == 0) if make_first_cover else False
                await session.execute(sql_insert, {
                    "case_id": case_id,
                    "tg_file_id": fid,
                    "position": i,
                    "is_cover": is_cover
                })

            await session.commit()


async def add_case_media(
    case_id: int,
    items: List[Dict[str, str]],
    make_first_cover: bool = True,
    table_name: str = IMAGES_TABLE
) -> None:
    if not items:
        return

    sql_reset_cover = text(f"""
        UPDATE {table_name}
        SET is_cover = FALSE
        WHERE case_id = :case_id;
    """)

    sql_insert = text(f"""
        INSERT INTO {table_name} (case_id, tg_file_id, position, is_cover, media_type)
        VALUES (:case_id, :tg_file_id, :position, :is_cover, :media_type);
    """)

    async with db_manager as client:
        async with client.session() as session:
            await session.execute(sql_reset_cover, {"case_id": case_id})

            for i, item in enumerate(items):
                tg_file_id = item.get("tg_file_id")
                media_type = item.get("media_type") or "photo"
                if not tg_file_id:
                    continue
                is_cover = (i == 0) if make_first_cover else False
                await session.execute(sql_insert, {
                    "case_id": case_id,
                    "tg_file_id": tg_file_id,
                    "position": i,
                    "is_cover": is_cover,
                    "media_type": media_type
                })

            await session.commit()


async def get_case_images(case_id: int, table_name: str = IMAGES_TABLE) -> List[Dict[str, Any]]:
    sql = text(f"""
        SELECT image_id, tg_file_id, media_type, position, is_cover, created
        FROM {table_name}
        WHERE case_id = :case_id
        ORDER BY is_cover DESC, position ASC, created ASC, image_id ASC;
    """)
    async with db_manager as client:
        async with client.session() as session:
            res = await session.execute(sql, {"case_id": case_id})
            rows = res.fetchall()
            return [dict(r._mapping) for r in rows]
        

async def delete_case_images(case_id: int, table_name: str = IMAGES_TABLE) -> None:
    sql = text(f"""
        DELETE FROM {table_name}
        WHERE case_id = :case_id;
    """)
    async with db_manager as client:
        async with client.session() as session:
            await session.execute(sql, {"case_id": case_id})
            await session.commit()


async def get_case_review(case_id: int) -> Optional[Dict[str, Any]]:
    review_sql = text("""
        SELECT review_id, case_id, created, updated
        FROM case_reviews
        WHERE case_id = :case_id;
    """)
    items_sql = text("""
        SELECT item_id, tg_file_id, media_type, text_content, position, created
        FROM case_review_items
        WHERE review_id = :review_id
        ORDER BY position ASC, item_id ASC;
    """)
    async with db_manager as client:
        async with client.session() as session:
            review_res = await session.execute(review_sql, {"case_id": case_id})
            review_row = review_res.fetchone()
            if not review_row:
                return None
            review = dict(review_row._mapping)
            items_res = await session.execute(items_sql, {"review_id": review["review_id"]})
            items = [dict(r._mapping) for r in items_res.fetchall()]
            return {"review": review, "items": items}


async def upsert_case_review(case_id: int, items: List[Dict[str, Any]]) -> None:
    review_sql = text("""
        INSERT INTO case_reviews (case_id, updated)
        VALUES (:case_id, CURRENT_TIMESTAMP)
        ON CONFLICT (case_id)
        DO UPDATE SET updated = CURRENT_TIMESTAMP
        RETURNING review_id;
    """)
    delete_items_sql = text("""
        DELETE FROM case_review_items
        WHERE review_id = :review_id;
    """)
    insert_item_sql = text("""
        INSERT INTO case_review_items (review_id, tg_file_id, media_type, text_content, position)
        VALUES (:review_id, :tg_file_id, :media_type, :text_content, :position);
    """)
    async with db_manager as client:
        async with client.session() as session:
            res = await session.execute(review_sql, {"case_id": case_id})
            review_id = int(res.scalar_one())
            await session.execute(delete_items_sql, {"review_id": review_id})
            for i, item in enumerate(items):
                await session.execute(insert_item_sql, {
                    "review_id": review_id,
                    "tg_file_id": item.get("tg_file_id"),
                    "media_type": item.get("media_type"),
                    "text_content": item.get("text_content"),
                    "position": i
                })
            await session.commit()


async def delete_case_review(case_id: int) -> None:
    sql = text("""
        DELETE FROM case_reviews
        WHERE case_id = :case_id;
    """)
    async with db_manager as client:
        async with client.session() as session:
            await session.execute(sql, {"case_id": case_id})
            await session.commit()


async def get_case_cta(case_id: int) -> Optional[Dict[str, Any]]:
    sql = text("""
        SELECT case_id, button_text, action_type, action_value, updated
        FROM case_cta
        WHERE case_id = :case_id;
    """)
    async with db_manager as client:
        async with client.session() as session:
            res = await session.execute(sql, {"case_id": case_id})
            row = res.fetchone()
            return dict(row._mapping) if row else None


async def upsert_case_cta(case_id: int, button_text: str, action_type: str, action_value: str | None) -> None:
    sql = text("""
        INSERT INTO case_cta (case_id, button_text, action_type, action_value, updated)
        VALUES (:case_id, :button_text, :action_type, :action_value, CURRENT_TIMESTAMP)
        ON CONFLICT (case_id)
        DO UPDATE SET
            button_text = EXCLUDED.button_text,
            action_type = EXCLUDED.action_type,
            action_value = EXCLUDED.action_value,
            updated = CURRENT_TIMESTAMP;
    """)
    async with db_manager as client:
        async with client.session() as session:
            await session.execute(sql, {
                "case_id": case_id,
                "button_text": button_text,
                "action_type": action_type,
                "action_value": action_value
            })
            await session.commit()


async def log_event(
    user_id: int,
    event_type: str,
    event_context: str | None = None,
    event_value: str | None = None,
    payload: dict | None = None,
    table_name: str = EVENTS_TABLE
) -> None:
    try:
        sql = text(f"""
            INSERT INTO {table_name} (user_id, event_type, event_context, event_value, payload)
            VALUES (:user_id, :event_type, :event_context, :event_value, :payload);
        """)
        async with db_manager as client:
            async with client.session() as session:
                params = {
                    "user_id": user_id,
                    "event_type": event_type,
                    "event_context": event_context,
                    "event_value": event_value,
                    "payload": payload
                }
                try:
                    await session.execute(sql, params)
                except Exception:
                    try:
                        await session.rollback()
                        await session.execute(sql, {
                            **params,
                            "payload": json.dumps(payload) if payload is not None else None
                        })
                    except Exception:
                        return
                await session.commit()
    except Exception:
        pass


async def get_events_total(days: int = 30, table_name: str = EVENTS_TABLE) -> int:
    sql = text(f"""
        SELECT COUNT(*)
        FROM {table_name}
        WHERE created_at >= NOW() - (INTERVAL '1 day' * :days);
    """)
    async with db_manager as client:
        async with client.session() as session:
            res = await session.execute(sql, {"days": days})
            return int(res.scalar_one())


async def get_top_menu_clicks(
    days: int = 30,
    limit: int = 15,
    table_name: str = EVENTS_TABLE
) -> List[Dict[str, Any]]:
    sql = text(f"""
        SELECT
            event_context,
            event_value,
            COUNT(*) AS cnt
        FROM {table_name}
        WHERE event_type = 'menu_click'
          AND created_at >= NOW() - (INTERVAL '1 day' * :days)
        GROUP BY event_context, event_value
        ORDER BY cnt DESC
        LIMIT :limit;
    """)
    async with db_manager as client:
        async with client.session() as session:
            res = await session.execute(sql, {"days": days, "limit": limit})
            rows = res.fetchall()
            return [dict(r._mapping) for r in rows]


async def get_top_cases(
    days: int = 30,
    limit: int = 10,
    table_name: str = EVENTS_TABLE,
    cases_table: str = CASES_TABLE
) -> List[Dict[str, Any]]:
    sql = text(f"""
        SELECT
            c.case_id,
            c.title,
            COUNT(*) AS cnt
        FROM {table_name} e
        JOIN {cases_table} c
          ON c.case_id = e.event_value::BIGINT
        WHERE e.event_type = 'case_view'
          AND e.event_value ~ '^[0-9]+$'
          AND e.created_at >= NOW() - (INTERVAL '1 day' * :days)
        GROUP BY c.case_id, c.title
        ORDER BY cnt DESC
        LIMIT :limit;
    """)
    async with db_manager as client:
        async with client.session() as session:
            res = await session.execute(sql, {"days": days, "limit": limit})
            rows = res.fetchall()
            return [dict(r._mapping) for r in rows]


async def get_funnel(
    days: int = 30,
    table_name: str = EVENTS_TABLE
) -> List[Dict[str, Any]]:
    sql = text(f"""
        SELECT
            event_type,
            COUNT(DISTINCT user_id) AS users
        FROM {table_name}
        WHERE event_type IN ('start', 'cases_open', 'case_view', 'contact_open')
          AND created_at >= NOW() - (INTERVAL '1 day' * :days)
        GROUP BY event_type;
    """)
    async with db_manager as client:
        async with client.session() as session:
            res = await session.execute(sql, {"days": days})
            rows = res.fetchall()
            return [dict(r._mapping) for r in rows]


async def get_stuck_points(
    days: int = 30,
    limit: int = 10,
    table_name: str = EVENTS_TABLE
) -> List[Dict[str, Any]]:
    sql_base = text(f"""
        WITH recent AS (
            SELECT user_id, event_type
            FROM {table_name}
            WHERE created_at >= NOW() - (INTERVAL '1 day' * :days)
        )
        SELECT COUNT(DISTINCT r.user_id) AS users
        FROM recent r
        WHERE r.event_type = :from_event
          AND NOT EXISTS (
              SELECT 1 FROM recent r2
              WHERE r2.user_id = r.user_id
                AND r2.event_type = :to_event
          );
    """)

    points = [
        ("start", "cases_open", "Стартовали, но не открыли список кейсов"),
        ("cases_open", "case_view", "Открыли список, но не открыли кейс"),
        ("case_view", "contact_open", "Смотрели кейс, но не открыли контакты"),
    ]

    results: List[Dict[str, Any]] = []
    async with db_manager as client:
        async with client.session() as session:
            for from_event, to_event, label in points:
                res = await session.execute(sql_base, {
                    "days": days,
                    "from_event": from_event,
                    "to_event": to_event
                })
                users = int(res.scalar_one())
                results.append({"label": label, "users": users})

    return results[:limit]


async def get_recent_users(
    limit: int = 100,
    table_users: str = USERS_TABLE,
    table_events: str = EVENTS_TABLE
) -> List[Dict[str, Any]]:
    sql = text(f"""
        SELECT
            u.user_id,
            u.user_login AS username,
            u.full_name,
            MAX(e.created_at) AS last_activity
        FROM {table_events} e
        JOIN {table_users} u ON u.user_id = e.user_id
        GROUP BY u.user_id, u.user_login, u.full_name
        ORDER BY last_activity DESC
        LIMIT :limit;
    """)
    async with db_manager as client:
        async with client.session() as session:
            res = await session.execute(sql, {"limit": limit})
            rows = res.fetchall()
            return [dict(r._mapping) for r in rows]
