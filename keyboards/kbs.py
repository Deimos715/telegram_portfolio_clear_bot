from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from create_bot import admins
from typing import Sequence

# ------------------------------------------------------------------------ Главное меню -----------------------------------------------------------------
def main_kb(user_telegram_id: int) -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton(text="Связаться со мной", callback_data="menu:contact"),
            InlineKeyboardButton(text="Телеграм канал", url="https://t.me/PantelidiIlia")
        ],

        [
            InlineKeyboardButton(text="Обо мне", callback_data="menu:aboutMe"),
            InlineKeyboardButton(text="Кейсы", callback_data="menu:cases")
        ],

        [
            InlineKeyboardButton(text="Этапы работы", callback_data="menu:steps")
        ]
    ]

    if user_telegram_id in admins:
        kb.append(
            [InlineKeyboardButton(text="Админ панель", callback_data="admin:main")]
        )

    return InlineKeyboardMarkup(inline_keyboard=kb)


# ------------------------------------------------------------------------ Инлайн админ панель -----------------------------------------------------------------
def admin_panel_kb(users_count: int) -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton(text=f"Пользователей: {users_count}", callback_data="admin:main"),
        ],
        [
            InlineKeyboardButton(text="Статистика", callback_data="admin:stats"),
            InlineKeyboardButton(text="Настройки бота", callback_data="admin:settings"),
        ],
        [
            InlineKeyboardButton(text="Управление кейсами", callback_data="admin:cases"),
        ],
        [
            InlineKeyboardButton(text="← В главное меню", callback_data="menu:main"),
        ],
    ]

    return InlineKeyboardMarkup(inline_keyboard=kb)


def confirm_kb(confirm_data: str, cancel_data: str, confirm_text: str = "Да", cancel_text: str = "Отмена") -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton(text=confirm_text, callback_data=confirm_data),
            InlineKeyboardButton(text=cancel_text, callback_data=cancel_data),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def settings_kb(maintenance_enabled: bool) -> InlineKeyboardMarkup:
    maint_text = "🚧 Техработы: ВКЛ" if maintenance_enabled else "🚧 Техработы: ВЫКЛ"
    kb = [
        [
            InlineKeyboardButton(text="📊 Статус системы", callback_data="admin:settings:status"),
            InlineKeyboardButton(text=maint_text, callback_data="admin:settings:maint_toggle"),
        ],
        [
            InlineKeyboardButton(text="🧹 Очистить отчёты статистики", callback_data="admin:settings:reports_cleanup"),
        ],
        [
            InlineKeyboardButton(text="♻️ Перезапустить бота", callback_data="admin:settings:restart"),
        ],
        [
            InlineKeyboardButton(text="← Назад в админ-меню", callback_data="admin:main"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


# ------------------------------------------------------------------------ Инлайн создание кейса -----------------------------------------------------------------
def admin_cases_kb(cases: Sequence[dict], page: int, has_prev: bool, has_next: bool,) -> InlineKeyboardMarkup:
    kb: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="Создать кейс", callback_data="admin:cases:new")]
    ]

    # кнопки кейсов
    for c in cases:
        case_id = c.get("case_id")
        title = c.get("title") or "Без названия"

        if case_id is None:
                continue

        kb.append([
            InlineKeyboardButton(
                text=f"{title}",
                callback_data=f"admin:cases:view:{case_id}|{page}"
            )
        ])

    # пагинация
    nav_row: list[InlineKeyboardButton] = []
    if has_prev and page > 0:
        nav_row.append(
            InlineKeyboardButton(text="Назад", callback_data=f"admin:cases:list:{page-1}")
        )
    if has_next:
        nav_row.append(
            InlineKeyboardButton(text="Вперёд", callback_data=f"admin:cases:list:{page+1}")
        )

    if nav_row:
        kb.append(nav_row)

    kb.append([InlineKeyboardButton(text="Назад в меню", callback_data="admin:main")])

    return InlineKeyboardMarkup(inline_keyboard=kb)


def admin_case_editor_kb(case_id: int, status: str, back_page: int = 0) -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton(
                text="Название",
                callback_data=f"admin:cases:edit_title:{case_id}|{back_page}"
            ),
            InlineKeyboardButton(
                text="Описание",
                callback_data=f"admin:cases:edit_desc:{case_id}|{back_page}"
            ),
        ],
        [
            InlineKeyboardButton(
                text="Обложка",
                callback_data=f"admin:cases:edit_cover:{case_id}|{back_page}"
            ),
        ],
        [
            InlineKeyboardButton(
                text="Отзывы",
                callback_data=f"admin:cases:review:{case_id}|{back_page}"
            ),
            InlineKeyboardButton(
                text="Кнопка контакта",
                callback_data=f"admin:cases:cta:{case_id}|{back_page}"
            ),
        ],
    ]

    if status == "published":
        kb.append([
            InlineKeyboardButton(
                text="Скрыть",
                callback_data=f"admin:cases:unpublish:{case_id}|{back_page}"
            )
        ])
    else:  # draft
        kb.append([
            InlineKeyboardButton(
                text="Опубликовать",
                callback_data=f"admin:cases:publish:{case_id}|{back_page}"
            )
        ])

    kb.append([
        InlineKeyboardButton(
            text="← Назад к списку",
            callback_data=f"admin:cases:list:{back_page}"
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def admin_cancel_case_edit_kb(case_id: int, back_page: int = 0, show_done: bool = False) -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(
            text="✖️ Отмена",
            callback_data=f"admin:cases:edit_cancel:{case_id}|{back_page}"
        )
    ]
    if show_done:
        row.append(
            InlineKeyboardButton(
                text="✅ Готово",
                callback_data=f"admin:cases:cover_done:{case_id}|{back_page}"
            )
        )
    return InlineKeyboardMarkup(inline_keyboard=[row])


def admin_cancel_review_edit_kb(case_id: int, back_page: int = 0, show_done: bool = False) -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(
            text="✖️ Отмена",
            callback_data=f"admin:cases:review_cancel:{case_id}|{back_page}"
        )
    ]
    if show_done:
        row.append(
            InlineKeyboardButton(
                text="✅ Готово",
                callback_data=f"admin:cases:review_done:{case_id}|{back_page}"
            )
        )
    return InlineKeyboardMarkup(inline_keyboard=[row])


def admin_cancel_cta_edit_kb(case_id: int, back_page: int = 0) -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(
            text="✖️ Отмена",
            callback_data=f"admin:cases:cta_cancel:{case_id}|{back_page}"
        )
    ]
    return InlineKeyboardMarkup(inline_keyboard=[row])


def admin_cta_type_kb(case_id: int, back_page: int = 0) -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton(
                text="Вести в контакты",
                callback_data=f"admin:cases:cta_type:contact:{case_id}|{back_page}"
            ),
            InlineKeyboardButton(
                text="Открыть ссылку",
                callback_data=f"admin:cases:cta_type:url:{case_id}|{back_page}"
            ),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


# ------------------------------------------------------------------------ Публичные кейсы -----------------------------------------------------------------
def public_cases_kb(cases: Sequence[dict], page: int, has_prev: bool, has_next: bool) -> InlineKeyboardMarkup:
    kb: list[list[InlineKeyboardButton]] = []

    for c in cases:
        case_id = c.get("case_id")
        title = c.get("title") or "Без названия"
        if case_id is None:
            continue
        kb.append([
            InlineKeyboardButton(
                text=f"{title}",
                callback_data=f"menu:cases:view:{case_id}|{page}"
            )
        ])

    nav_row: list[InlineKeyboardButton] = []
    if has_prev and page > 0:
        nav_row.append(
            InlineKeyboardButton(text="Назад", callback_data=f"menu:cases:list:{page-1}")
        )
    if has_next:
        nav_row.append(
            InlineKeyboardButton(text="Дальше", callback_data=f"menu:cases:list:{page+1}")
        )
    if nav_row:
        kb.append(nav_row)

    kb.append([InlineKeyboardButton(text="← В главное меню", callback_data="menu:main")])

    return InlineKeyboardMarkup(inline_keyboard=kb)


def public_case_view_kb(case_id: int, back_page: int, cta_button: dict | None = None) -> InlineKeyboardMarkup:
    button_text = "Связаться со мной"
    action_type = "contact"
    action_value = None
    if cta_button:
        button_text = cta_button.get("button_text") or button_text
        action_type = cta_button.get("action_type") or action_type
        action_value = cta_button.get("action_value")

    kb: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="⭐ Посмотреть отзыв", callback_data=f"menu:cases:review:{case_id}|{back_page}"),
        ],
    ]

    if action_type == "url" and action_value:
        kb.append([InlineKeyboardButton(text=button_text, url=action_value)])
    else:
        kb.append([InlineKeyboardButton(text=button_text, callback_data="menu:contact")])

    kb.append([
        InlineKeyboardButton(text="← Назад к списку", callback_data=f"menu:cases:list:{back_page}"),
        InlineKeyboardButton(text="← В главное меню", callback_data="menu:main"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def public_review_view_kb(case_id: int, back_page: int, cta_text: str, cta_index: int) -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton(
                text=cta_text,
                callback_data=f"menu:cases:review_cta:{case_id}|{back_page}|{cta_index}"
            )
        ],
        [
            InlineKeyboardButton(text="← Вернуться к кейсу", callback_data=f"menu:cases:view:{case_id}|{back_page}"),
        ],
        [
            InlineKeyboardButton(text="К списку кейсов", callback_data=f"menu:cases:list:{back_page}"),
            InlineKeyboardButton(text="← В главное меню", callback_data="menu:main"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def public_review_empty_kb(case_id: int, back_page: int) -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton(text="← Вернуться к кейсу", callback_data=f"menu:cases:view:{case_id}|{back_page}"),
        ],
        [
            InlineKeyboardButton(text="К списку кейсов", callback_data=f"menu:cases:list:{back_page}"),
            InlineKeyboardButton(text="← В главное меню", callback_data="menu:main"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def cantact_kb() -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton(text="Напишите мне", url="https://t.me/RuviconChief"),
            InlineKeyboardButton(text="Мой канал", url="https://t.me/PantelidiIlia"),
        ],
        [
            InlineKeyboardButton(text="← В главное меню", callback_data="menu:main"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def aboutMe_kb() -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton(text="Напишите мне", url="https://t.me/RuviconChief"),
            InlineKeyboardButton(text="Личный блог", url="https://t.me/PantelidiIlia"),
        ],
        [
            InlineKeyboardButton(text="← В главное меню", callback_data="menu:main"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def steps_kb() -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton(text="Напишите мне", url="https://t.me/RuviconChief"),
            InlineKeyboardButton(text="Личный блог", url="https://t.me/PantelidiIlia"),
        ],
        [
            InlineKeyboardButton(text="← В главное меню", callback_data="menu:main"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)