from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, FSInputFile, CallbackQuery, InputMediaPhoto, InputMediaVideo
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.utils.chat_action import ChatActionSender
from aiogram.fsm.context import FSMContext
from create_bot import bot, admins
from db_handler.db_funk import get_user_data, insert_user, get_cases_page, get_case_by_id, get_case_images, log_event, get_setting, get_case_review, get_case_cta
from keyboards.kbs import aboutMe_kb, main_kb, public_cases_kb, public_case_view_kb, public_review_view_kb, public_review_empty_kb, cantact_kb, steps_kb
import random
import time


user_router = Router()
PAGE_SIZE = 8
MAINTENANCE_CACHE_TTL = 10
_maintenance_cache = {"value": "0", "ts": 0.0}
CTA_TEXTS = [
    "Начать работать со мной",
    "Хочу обсудить проект",
    "Записаться на созвон",
    "Хочу так же",
    "Давайте сделаем",
    "Нужна консультация",
    "Хочу результат",
    "Обсудить идею",
    "Связаться и начать",
    "Запустить проект",
    "Давайте пообщаемся",
    "Хочу стратегию",
    "Готов стартовать",
    "Запросить стоимость",
    "Нужен разбор",
    "Хочу решение",
    "Связаться с Ильей",
    "Давайте работать",
    "Хочу прототип",
    "Сделаем вместе",
]

contact_text = f"""
Есть идея? Просто напиши мне...
"""

aboutMe_text = f"""
Привет, меня зовут..
"""

steps_text = f"""
<b>Этапы работ</b>

01 / Знакомство

02 / Договор

03 / Разработка

04 / Тестирование и доработки

05 / Запуск и поддержка
"""
# Единый хелпер для удаления предыдущих сообщений
async def delete_event_message(event: Message | CallbackQuery):
    try:
        if isinstance(event, CallbackQuery):
            await event.message.delete()
            await event.answer()
        else:
            await event.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass


async def safe_delete_event_message(event: Message | CallbackQuery):
    try:
        await delete_event_message(event)
    except Exception:
        pass

async def safe_log_event(user_id: int, event_type: str, event_context: str | None = None, event_value: str | None = None, payload: dict | None = None):
    try:
        await log_event(user_id=user_id, event_type=event_type, event_context=event_context, event_value=event_value, payload=payload)
    except Exception:
        pass


async def is_maintenance_enabled() -> bool:
    now_ts = time.monotonic()
    if (now_ts - _maintenance_cache["ts"]) > MAINTENANCE_CACHE_TTL:
        try:
            value = await get_setting("maintenance", "0")
        except Exception:
            value = "0"
        _maintenance_cache["value"] = value or "0"
        _maintenance_cache["ts"] = now_ts
    return _maintenance_cache["value"] == "1"


async def cleanup_public_cases_view(state: FSMContext, bot, chat_id: int):
    data = await state.get_data()
    album_ids = data.get("public_case_album_ids", [])
    card_id = data.get("public_case_card_message_id")

    for mid in album_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=mid)
        except TelegramBadRequest:
            pass
        except Exception:
            pass
    if card_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=card_id)
        except TelegramBadRequest:
            pass
        except Exception:
            pass

    await state.update_data(public_case_album_ids=[], public_case_card_message_id=None, last_case_cta_case_id=None)


async def cleanup_public_review_view(state: FSMContext, bot, chat_id: int):
    data = await state.get_data()
    message_ids = data.get("public_review_message_ids", [])
    card_id = data.get("public_review_card_message_id")

    for mid in message_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=mid)
        except TelegramBadRequest:
            pass
        except Exception:
            pass
    if card_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=card_id)
        except TelegramBadRequest:
            pass
        except Exception:
            pass

    await state.update_data(public_review_message_ids=[], public_review_card_message_id=None)


async def render_public_case_list(message_obj, state: FSMContext, page: int):
    cases = await get_cases_page(page=page, limit=PAGE_SIZE + 1, status="published")
    has_next = len(cases) > PAGE_SIZE
    cases = cases[:PAGE_SIZE]
    has_prev = page > 0

    photo = FSInputFile("src/images/cases.png")
    # пользователь | кейсы | показать список кейсов
    await message_obj.answer_photo(
        photo=photo,
        caption="Кейсы",
        reply_markup=public_cases_kb(
            cases=cases,
            page=page,
            has_prev=has_prev,
            has_next=has_next
        )
    )





async def render_public_case_view(message_obj, state: FSMContext, case_id: int, back_page: int):
    case = await get_case_by_id(case_id)
    if not case or case.get("status") != "published":
        # пользователь | просмотр кейса | кейс не найден
        await message_obj.answer("Кейс не найден")
        return

    images = await get_case_images(case_id)
    if images:
        media = []
        for img in images[:10]:
            media_type = img.get("media_type") or "photo"
            if media_type == "video":
                media.append(InputMediaVideo(media=img["tg_file_id"]))
            else:
                media.append(InputMediaPhoto(media=img["tg_file_id"]))
        # пользователь | просмотр кейса | отправка альбома изображений
        album_msgs = await message_obj.answer_media_group(media=media)
        album_ids = [m.message_id for m in album_msgs]
        await state.update_data(public_case_album_ids=album_ids)
    else:
        photo = FSInputFile("src/images/cases.png")
        # пользователь | просмотр кейса | показать заглушку 'Нет изображений'
        msg = await message_obj.answer_photo(photo=photo, caption="Нет изображений")
        await state.update_data(public_case_album_ids=[msg.message_id])

    caption = f"<b>{case['title']}</b>\n\n{case['description']}"
    # пользователь | просмотр кейса | показать карточку кейса
    card_msg = await message_obj.answer(
        caption,
        reply_markup=public_case_view_kb(case_id, back_page, await get_case_cta(case_id))
    )
    await state.update_data(public_case_card_message_id=card_msg.message_id)
    await state.update_data(last_case_cta_case_id=case_id)


async def render_contact_screen(message_obj, user_id: int):
    await safe_log_event(user_id, "contact_open", "contact_page")
    photo = FSInputFile("src/images/contact.png")
    # пользователь | контакт | показать экран контакта
    await message_obj.answer_photo(
        photo=photo,
        caption=f"{contact_text}",
        reply_markup=cantact_kb()
    )

# Проверяем регистрацию пользователя и добавляем в базу при первом запуске
@user_router.message(CommandStart())
async def cmd_start(message: Message):
    await safe_log_event(message.from_user.id, "start", "system", payload={"username": message.from_user.username, "full_name": message.from_user.full_name})
    async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
        await insert_user(user_data={
            'user_id': message.from_user.id,
            'full_name': message.from_user.full_name,
            'user_login': message.from_user.username,
        })
        response_text = ""
        photo = FSInputFile("src/images/mainMenu.png")

    # пользователь | главное меню | показать стартовый экран
    await message.answer_photo(
        photo=photo,
        caption=response_text,
        reply_markup=main_kb(message.from_user.id))


# Проверяем регистрацию пользователя и добавляем в базу при первом запуске
@user_router.message(Command('restart'))
async def restart(message: Message):
    response_text = ""
    photo = FSInputFile("src/images/mainMenu.png")
    await delete_event_message(message)

    # пользователь | главное меню | показать стартовый экран
    await message.answer_photo(
        photo=photo,
        caption=response_text,
        reply_markup=main_kb(message.from_user.id))


# ------------------------------------------------------------------------ Весь инлайн  -----------------------------------------------------------------

@user_router.callback_query(F.data.startswith("menu:"))
async def open_main_panel(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    action = parts[1] if len(parts) > 1 else "main"

    data = await state.get_data()
    last_case_cta_id = data.get("last_case_cta_case_id")

    if callback.from_user.id not in admins:
        try:
            if await is_maintenance_enabled():
                await safe_delete_event_message(callback)
                # пользователь | сервис | уведомление: бот на обслуживании
                await callback.message.answer("Бот на обслуживании, напишите @RuviconChief")
                return
        except Exception:
            pass

    await safe_log_event(callback.from_user.id, "menu_click", "main_menu", event_value=action, payload={"callback": callback.data})
    if action == "contact" and last_case_cta_id:
        await safe_log_event(callback.from_user.id, "case_contact_click", "case_cta", event_value=str(last_case_cta_id), payload={"source": "case_view"})
    await cleanup_public_cases_view(state, callback.bot, callback.message.chat.id)
    await cleanup_public_review_view(state, callback.bot, callback.message.chat.id)

    if action == "main":
        await safe_log_event(callback.from_user.id, "menu_open", "main_menu")
        photo = FSInputFile("src/images/mainMenu.png")
        await safe_delete_event_message(callback)
        # пользователь | главное меню | показать главное меню
        await callback.message.answer_photo(
            photo=photo,
            caption="Главное меню",
            reply_markup=main_kb(callback.from_user.id)
        )
        return


    if action == "contact":
        await safe_delete_event_message(callback)
        await render_contact_screen(callback.message, callback.from_user.id)
        return
    

    if action == "aboutMe":
        await safe_log_event(callback.from_user.id, "about_open", "about_page")
        photo = FSInputFile("src/images/aboutMe.png")
        await safe_delete_event_message(callback)
        # пользователь | о себе | показать страницу 'О себе'
        await callback.message.answer_photo(
            photo = photo,
            caption = f"{aboutMe_text}",
            reply_markup = aboutMe_kb()
        )
        return
    

    if action == "cases":
        sub_action = parts[2] if len(parts) > 2 else "list"
        payload = parts[3] if len(parts) > 3 else None

        if sub_action == "list":
            try:
                page = int(payload) if payload is not None else 0
            except ValueError:
                page = 0
            await safe_log_event(callback.from_user.id, "cases_open", "cases_list", event_value=str(page), payload={"page": page})
            await safe_delete_event_message(callback)
            await cleanup_public_review_view(state, callback.bot, callback.message.chat.id)
            await render_public_case_list(callback.message, state, page)
            return

        if sub_action == "view":
            back_page = 0
            try:
                if payload and "|" in payload:
                    case_id_str, back_page_str = payload.split("|", 1)
                    case_id = int(case_id_str)
                    back_page = int(back_page_str)
                else:
                    case_id = int(payload) if payload is not None else 0
            except ValueError:
                case_id = 0

            if case_id <= 0:
                await callback.answer("Invalid case", show_alert=True)
                return

            await safe_log_event(callback.from_user.id, "case_view", "case_view", event_value=str(case_id), payload={"case_id": case_id, "back_page": back_page})

            await safe_delete_event_message(callback)
            await cleanup_public_review_view(state, callback.bot, callback.message.chat.id)
            await render_public_case_view(callback.message, state, case_id, back_page)
            return

        if sub_action == "review":
            back_page = 0
            try:
                if payload and "|" in payload:
                    case_id_str, back_page_str = payload.split("|", 1)
                    case_id = int(case_id_str)
                    back_page = int(back_page_str)
                else:
                    case_id = int(payload) if payload is not None else 0
            except ValueError:
                case_id = 0

            if case_id <= 0:
                await callback.answer("Invalid case", show_alert=True)
                return

            await safe_log_event(callback.from_user.id, "review_open", "case_review", event_value=str(case_id), payload={"case_id": case_id})
            await cleanup_public_cases_view(state, callback.bot, callback.message.chat.id)
            await cleanup_public_review_view(state, callback.bot, callback.message.chat.id)
            await safe_delete_event_message(callback)

            review = await get_case_review(case_id)
            if not review or not review.get("items"):
                # пользователь | отзывы | показать сообщение: нет отзывов
                msg = await callback.message.answer(
                    "Пока нет отзыва по этому кейсу",
                    reply_markup=public_review_empty_kb(case_id, back_page)
                )
                await state.update_data(public_review_message_ids=[], public_review_card_message_id=msg.message_id)
                return

            items = review["items"]
            texts = [i.get("text_content") for i in items if i.get("media_type") == "text" and i.get("text_content")]
            media_items = [i for i in items if i.get("media_type") in ("photo", "video")]
            voice_item = next((i for i in items if i.get("media_type") == "voice"), None)
            video_note_item = next((i for i in items if i.get("media_type") == "video_note"), None)

            message_ids: list[int] = []

            if video_note_item and video_note_item.get("tg_file_id"):
                # пользователь | отзывы | отправка видео-заметки
                msg = await callback.message.answer_video_note(video_note_item["tg_file_id"])
                message_ids.append(msg.message_id)

            if voice_item and voice_item.get("tg_file_id"):
                # пользователь | отзывы | отправка голосового сообщения
                msg = await callback.message.answer_voice(voice_item["tg_file_id"])
                message_ids.append(msg.message_id)

            if media_items:
                media = []
                for item in media_items[:10]:
                    if item.get("media_type") == "video":
                        media.append(InputMediaVideo(media=item.get("tg_file_id")))
                    else:
                        media.append(InputMediaPhoto(media=item.get("tg_file_id")))
                # пользователь | отзывы | отправка медиа-альбома
                album_msgs = await callback.message.answer_media_group(media=media)
                message_ids.extend([m.message_id for m in album_msgs])

            if texts:
                # пользователь | отзывы | отправка текстовых отзывов
                msg = await callback.message.answer("\n\n".join(texts))
                message_ids.append(msg.message_id)

            cta_index = random.randrange(len(CTA_TEXTS))
            cta_text = CTA_TEXTS[cta_index]
            # пользователь | отзывы | показать карточку отзыва с CTA
            card_msg = await callback.message.answer(
                "Выбери действие:",
                reply_markup=public_review_view_kb(case_id, back_page, cta_text, cta_index)
            )

            await state.update_data(public_review_message_ids=message_ids, public_review_card_message_id=card_msg.message_id)
            return

        if sub_action == "review_cta":
            back_page = 0
            cta_index = -1
            try:
                if payload and "|" in payload:
                    case_id_str, back_page_str, cta_index_str = payload.split("|", 2)
                    case_id = int(case_id_str)
                    back_page = int(back_page_str)
                    cta_index = int(cta_index_str)
                else:
                    case_id = int(payload) if payload is not None else 0
            except ValueError:
                case_id = 0

            if case_id <= 0:
                await callback.answer("Invalid case", show_alert=True)
                return

            cta_text = CTA_TEXTS[cta_index] if 0 <= cta_index < len(CTA_TEXTS) else ""
            await safe_log_event(
                callback.from_user.id,
                "cta_click",
                "case_review",
                event_value=str(case_id),
                payload={"cta_index": cta_index, "cta_text": cta_text}
            )
            await safe_log_event(
                callback.from_user.id,
                "case_contact_click",
                "case_cta",
                event_value=str(case_id),
                payload={"source": "review_cta", "cta_index": cta_index, "cta_text": cta_text}
            )
            await cleanup_public_review_view(state, callback.bot, callback.message.chat.id)
            await safe_delete_event_message(callback)
            await render_contact_screen(callback.message, callback.from_user.id)
            return

        # пользователь | навигация | неизвестная команда (уведомление)
        await callback.answer("Unknown command", show_alert=True)
        return

    if action == "steps":
        await safe_log_event(callback.from_user.id, "steps_open", "steps_page")
        photo = FSInputFile("src/images/workStep.png")
        await safe_delete_event_message(callback)
        # пользователь | этапы | показать этапы работ
        await callback.message.answer_photo(
            photo = photo,
            caption = f"{steps_text}",
            reply_markup = steps_kb()
        )
        return
    
    # пользователь | навигация | неизвестная команда (уведомление)
    await callback.answer("Неизвестная команда", show_alert=True)
