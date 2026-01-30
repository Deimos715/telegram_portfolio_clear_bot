from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message, FSInputFile, InputMediaPhoto, InputMediaVideo
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from create_bot import admins
from keyboards.kbs import admin_panel_kb, admin_cases_kb, admin_case_editor_kb, admin_cancel_case_edit_kb, settings_kb, confirm_kb, admin_cancel_review_edit_kb, admin_cancel_cta_edit_kb, admin_cta_type_kb
from db_handler.db_funk import get_user_count, get_cases_page, create_case_draft, get_case_by_id, update_case_field, add_case_images, add_case_media, get_case_images, delete_case_images, log_event, get_setting, set_setting, upsert_case_review, upsert_case_cta, get_case_cta
from handlers.user_router import delete_event_message
from handlers.services.statistics_service import generate_statistics_report_file
from handlers.services.bot_control_service import request_restart
from handlers.services.system_status_service import get_system_status
from handlers.services.statistics_files_service import cleanup_statistics_reports
import asyncio
import logging
import time
import html


async def safe_answer_html(message_obj: Message, text: str, reply_markup=None, **kwargs):
    """
    Отправляет текст как HTML.
    Если HTML сломан (can't parse entities) — отправляет fallback plain text,
    но С ТОЙ ЖЕ inline-клавиатурой, чтобы меню не пропадало.
    """
    try:
        return await message_obj.answer(
            text,
            parse_mode="HTML",
            reply_markup=reply_markup,
            **kwargs,
        )
    except TelegramBadRequest as e:
        if "can't parse entities" in str(e):
            safe_text = html.escape(text)
            return await message_obj.answer(
                safe_text,
                parse_mode=None,
                reply_markup=reply_markup,
                **kwargs,
            )
        raise

admin_router = Router()
PAGE_SIZE = 8


class CaseEdit(StatesGroup):
    waiting_value = State()
    waiting_review = State()
    waiting_cta_text = State()
    waiting_cta_url = State()


# ------------------------------------------------------------------------ Хелпер вытягивает обложку -------------------------------------------------------------

async def render_case_editor(message_obj, state: FSMContext, case_id: int, back_page: int = 0, note: str | None = None):
    case = await get_case_by_id(case_id)
    if not case:
        # админ | редактор кейса | кейс не найден
        await message_obj.answer("Кейс не найден")
        return

    # 0) удалить предыдущий альбом редактора (если есть)
    data = await state.get_data()
    prev_card_id = data.get("case_editor_card_message_id")
    prev_prompt_id = data.get("prompt_message_id")
    for mid in (prev_card_id, prev_prompt_id):
        if mid:
            try:
                await message_obj.bot.delete_message(chat_id=message_obj.chat.id, message_id=mid)
            except TelegramBadRequest:
                pass
            except Exception:
                pass
    await state.update_data(case_editor_card_message_id=None, prompt_message_id=None)
    await delete_last_case_album(state, message_obj.bot, message_obj.chat.id)

    images = await get_case_images(case_id)

    caption = (
        f"<b>Редактор кейса</b>\n\n"
        f"ID: <code>{case['case_id']}</code>\n"
        f"Статус: <b>{case['status']}</b>\n\n"
        f"<b>{case['title']}</b>\n\n"
        f"{case['description']}"
    )
    if note:
        caption += f"\n\n{note}"

    # 1) альбом
    if images:
        media = []
        for img in images[:10]:
            media_type = img.get("media_type") or "photo"
            if media_type == "video":
                media.append(InputMediaVideo(media=img["tg_file_id"]))
            else:
                media.append(InputMediaPhoto(media=img["tg_file_id"]))
        # админ | редактор кейса | отправка альбома изображений
        album_msgs = await message_obj.answer_media_group(media=media)

        # сохранить ids альбома
        album_ids = [m.message_id for m in album_msgs]
        await state.update_data(case_editor_album_ids=album_ids)
    else:
        photo = FSInputFile("src/images/admin.png")
        # админ | редактор кейса | показать заглушку 'Нет изображений кейса (пока)'
        msg = await message_obj.answer_photo(photo=photo, caption="Нет изображений кейса (пока)")
        await state.update_data(case_editor_album_ids=[msg.message_id])

    # 2) панель управления отдельным сообщением
    # админ | редактор кейса | показать панель управления кейсом
    kb = admin_case_editor_kb(
        case_id=case["case_id"],
        status=case["status"],
        back_page=back_page
    )

    card_msg = await safe_answer_html(
        message_obj,
        caption,
        reply_markup=kb
    )

    await state.update_data(case_editor_card_message_id=card_msg.message_id)


async def delete_last_case_album(state: FSMContext, bot, chat_id: int):
    data = await state.get_data()
    album_ids = data.get("case_editor_album_ids", [])

    if not album_ids:
        return

    for mid in album_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=mid)
        except TelegramBadRequest:
            pass
        except Exception:
            pass

    await state.update_data(case_editor_album_ids=[])


async def cleanup_admin_messages(state: FSMContext, bot, chat_id: int):
    data = await state.get_data()
    card_id = data.get("case_editor_card_message_id")
    prompt_id = data.get("prompt_message_id")
    for mid in (card_id, prompt_id):
        if mid:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=mid)
            except TelegramBadRequest:
                pass
            except Exception:
                pass
    await state.update_data(case_editor_card_message_id=None, prompt_message_id=None)


async def safe_delete_event_message(event):
    try:
        await delete_event_message(event)
    except Exception:
        pass

async def safe_log_event(user_id: int, event_type: str, event_context: str | None = None, event_value: str | None = None, payload: dict | None = None):
    try:
        await log_event(user_id=user_id, event_type=event_type, event_context=event_context, event_value=event_value, payload=payload)
    except Exception:
        pass


async def is_action_throttled(state: FSMContext, action: str, cooldown: float = 1.5) -> bool:
    now_ts = time.monotonic()
    data = await state.get_data()
    last_action = data.get("settings_last_action")
    last_ts = data.get("settings_last_action_ts", 0.0)
    if last_action == action and (now_ts - float(last_ts)) < cooldown:
        return True
    await state.update_data(settings_last_action=action, settings_last_action_ts=now_ts)
    return False


async def render_settings_screen(message_obj):
    maintenance = await get_setting("maintenance", "0")
    maintenance_enabled = maintenance == "1"
    photo = FSInputFile("src/images/admin.png")
    caption = (
        "<b>Настройки бота</b>\n\n"
        f"Техработы: <b>{'ВКЛ' if maintenance_enabled else 'ВЫКЛ'}</b>"
    )
    # админ | настройки | показать экран настроек
    await message_obj.answer_photo(
        photo=photo,
        caption=caption,
        reply_markup=settings_kb(maintenance_enabled)
    )


# ------------------------------------------------------------------------ Основная админ панель -----------------------------------------------------------------
@admin_router.callback_query(F.data.startswith("admin:"))
async def open_admin_panel(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    section = parts[1] if len(parts) > 1 else "main"
    action = parts[2] if len(parts) > 2 else None
    payload = parts[3] if len(parts) > 3 else None

        
    chat_id = callback.message.chat.id
    await cleanup_admin_messages(state, callback.bot, chat_id)
    await delete_last_case_album(state, callback.bot, chat_id)

    if not (section == "cases" and action in ("edit_title", "edit_desc", "edit_cancel", "edit_cover", "cover_done", "review", "review_done", "review_cancel", "cta", "cta_type", "cta_cancel")):
        await state.clear()


    #Проверка на админа
    if callback.from_user.id not in admins:
            # пользователь | админка | нет доступа
            await callback.answer("Нет доступа", show_alert=True)
            return

    if section == "main":
        await safe_log_event(callback.from_user.id, "admin_open", "admin_main")
        users_count = await get_user_count()
        photo = FSInputFile("src/images/admin.png")
        await safe_delete_event_message(callback)
        # админ | главное меню | показать основное меню администратора
        await callback.message.answer_photo(
            photo = photo,
            caption = 'Основное меню администратора',
            reply_markup = admin_panel_kb(users_count)
        )
        return
    

    if section == "stats":
        await safe_log_event(callback.from_user.id, "admin_nav", "stats", event_value=action, payload={"callback": callback.data})
        await safe_delete_event_message(callback)
        # админ | статистика | прогресс: собираю отчёт
        progress_msg = await callback.message.answer("Собираю отчёт…")
        try:
            report_path = await generate_statistics_report_file("src/html/template-statistic.html")
            # админ | статистика | отправка файла отчёта
            await callback.message.answer_document(
                document=FSInputFile(report_path),
                caption="Отчёт по статистике"
            )
            try:
                await progress_msg.edit_text("Отчёт готов и отправлен ✅")
                await delete_event_message(progress_msg)
            except Exception:
                logging.exception("STAT REPORT ERROR")
                pass
        except Exception:
            logging.exception("STAT REPORT ERROR")
            try:
                await progress_msg.edit_text("Не удалось собрать отчёт, смотри логи")
            except Exception:
                logging.exception("STAT REPORT ERROR")
                pass

        users_count = await get_user_count()
        photo = FSInputFile("src/images/admin.png")
        # админ | статистика | показать статистику
        await callback.message.answer_photo(
            photo=photo,
            caption="Статистика",
            reply_markup=admin_panel_kb(users_count)
        )
        return
    

    if section == "settings":
        await safe_log_event(callback.from_user.id, "admin_nav", "settings", event_value=action, payload={"callback": callback.data})
        await safe_delete_event_message(callback)
        if action is None:
            await render_settings_screen(callback.message)
            return

        if action == "status":
            if await is_action_throttled(state, "status"):
                # админ | настройки | подтверждение нажатия
                await callback.answer()
                return
            # админ | настройки | прогресс: выполняю
            progress_msg = await callback.message.answer("Выполняю…")
            try:
                status = await get_system_status()
                text = (
                    "Готово ✅\n\n"
                    f"Uptime: <code>{status['uptime']}</code>\n"
                    f"Python: <code>{status['python']}</code>\n"
                    f"PID: <code>{status['pid']}</code>\n"
                    f"DB: <code>{status['db']}</code>"
                )
                await progress_msg.edit_text(text)
            except Exception:
                await progress_msg.edit_text("Ошибка ❌")
            await render_settings_screen(callback.message)
            return

        if action == "restart":
            # админ | перезапуск | запрос подтверждения перезапуска
            await callback.message.answer(
                "Подтвердить перезапуск бота?",
                reply_markup=confirm_kb(
                    confirm_data="admin:settings:restart_confirm",
                    cancel_data="admin:settings:restart_cancel"
                )
            )
            return

        if action == "restart_confirm":
            if await is_action_throttled(state, "restart_confirm"):
                # админ | перезапуск | подтверждение нажатия
                await callback.answer()
                return
            # админ | перезапуск | прогресс: перезапускаю
            progress_msg = await callback.message.answer("Перезапускаю…")
            try:
                await request_restart()
            except Exception:
                await progress_msg.edit_text("Ошибка ❌")
            return

        if action == "restart_cancel":
            # админ | перезапуск | отмена
            await callback.message.answer("Отменено")
            await render_settings_screen(callback.message)
            return

        if action == "maint_toggle":
            if await is_action_throttled(state, "maint_toggle"):
                # админ | настройки | подтверждение нажатия
                await callback.answer()
                return
            # админ | настройки | прогресс: выполняю
            progress_msg = await callback.message.answer("Выполняю…")
            try:
                current = await get_setting("maintenance", "0")
                new_value = "0" if current == "1" else "1"
                await set_setting("maintenance", new_value)
                await progress_msg.edit_text("Готово ✅")
            except Exception:
                await progress_msg.edit_text("Ошибка ❌")
            await render_settings_screen(callback.message)
            return

        if action == "reports_cleanup":
            # админ | отчёты | запрос подтверждения очистки
            await callback.message.answer(
                "Очистить отчёты статистики?",
                reply_markup=confirm_kb(
                    confirm_data="admin:settings:reports_cleanup_confirm",
                    cancel_data="admin:settings:reports_cleanup_cancel"
                )
            )
            return

        if action == "reports_cleanup_confirm":
            if await is_action_throttled(state, "reports_cleanup_confirm"):
                # админ | отчёты | подтверждение нажатия
                await callback.answer()
                return
            # админ | отчёты | прогресс: выполняю
            progress_msg = await callback.message.answer("Выполняю…")
            try:
                result = await cleanup_statistics_reports(days=7)
                await progress_msg.edit_text(
                    f"Готово ✅\nУдалено: {result['deleted']}\nОставлено: {result['kept']}"
                )
            except Exception:
                await progress_msg.edit_text("Ошибка ❌")
            await render_settings_screen(callback.message)
            return

        if action == "reports_cleanup_cancel":
            # админ | отчёты | отмена
            await callback.message.answer("Отменено")
            await render_settings_screen(callback.message)
            return

        # админ | навигация | неизвестная команда (уведомление)
        await callback.answer("Неизвестная команда", show_alert=True)
        return
    

    if section == "cases":
        photo = FSInputFile("src/images/admin.png")
        action = action or "list"

        if action in ("list", None):
            await safe_log_event(callback.from_user.id, "admin_nav", "cases", event_value=action, payload={"callback": callback.data})

        if action == "list":
            try:
                page = int(payload) if payload is not None else 0
            except ValueError:
                page = 0

            cases = await get_cases_page(page=page, limit=PAGE_SIZE + 1)
            has_next = len(cases) > PAGE_SIZE
            cases = cases[:PAGE_SIZE]
            has_prev = page > 0

            await safe_delete_event_message(callback)
            # админ | кейсы | показать список кейсов для управления
            await callback.message.answer_photo(
                photo=photo,
                caption="Управление кейсами",
                reply_markup=admin_cases_kb(
                    cases=cases,
                    page=page,
                    has_prev=has_prev,
                    has_next=has_next
                )
            )
            return

        if action == "new":
            case_id = await create_case_draft()
            case = await get_case_by_id(case_id)

            if not case:
                # админ | кейсы | ошибка создания кейса
                await callback.answer("Не удалось создать кейс", show_alert=True)
                return

            caption = (
                f"<b>Редактор кейса</b>\n\n"
                f"ID: <code>{case['case_id']}</code>\n"
                f"Статус: <b>{case['status']}</b>\n\n"
                f"<b>{case['title']}</b>\n\n"
                f"{case['description']}"
            )

            await safe_delete_event_message(callback)
            await render_case_editor(callback.message, state=state, case_id=case["case_id"], back_page=0)
            return

        if action == "view":
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
                # админ | кейсы | ошибка: некорректный кейс
                await callback.answer("Некорректный кейс", show_alert=True)
                return

            case = await get_case_by_id(case_id)
            if not case:
                # админ | кейсы | кейс не найден
                await callback.answer("Кейс не найден", show_alert=True)
                return

            caption = (
                f"<b>Редактор кейса</b>\n\n"
                f"ID: <code>{case['case_id']}</code>\n"
                f"Статус: <b>{case['status']}</b>\n\n"
                f"<b>{case['title']}</b>\n\n"
                f"{case['description']}"
            )

            await safe_delete_event_message(callback)
            await render_case_editor(callback.message, state=state, case_id=case["case_id"], back_page=back_page)
            return
        
        if action in ("edit_title", "edit_desc", "edit_cover"):
            await safe_delete_event_message(callback)

            if not payload or "|" not in payload:
                # админ | кейсы | некорректные данные
                await callback.answer("Некорректные данные", show_alert=True)
                return

            case_id_str, back_page_str = payload.split("|", 1)

            try:
                case_id = int(case_id_str)
                back_page = int(back_page_str)
            except ValueError:
                # админ | кейсы | некорректные данные
                await callback.answer("Некорректные данные", show_alert=True)
                return

            await safe_log_event(callback.from_user.id, "admin_case_edit", "edit", event_value=action, payload={"case_id": case_id, "action": action})

            # (желательно) проверить, что кейс существует
            case = await get_case_by_id(case_id)
            if not case:
                # админ | кейсы | кейс не найден
                await callback.answer("Кейс не найден", show_alert=True)
                return

            # Определяем, что ждём от пользователя
            if action == "edit_title":
                field = "title"
                prompt = "✏️ Введите новый заголовок одним сообщением:"
            elif action == "edit_desc":
                field = "description"
                prompt = "✏️ Введите новое описание одним сообщением:"
            else:
                field = "cover"
                prompt = "Добавьте новую обложку, просто отправьте мне нужные изображения/видео, но не больше 10."

                await state.update_data(cover_media=[])

            # Включаем ожидание ввода (текст/фото)
            await state.set_state(CaseEdit.waiting_value)
            await state.update_data(case_id=case_id, field=field, back_page=back_page)

            # админ | редактирование | подтверждение нажатия
            await callback.answer()

            show_done = (field == "cover")
            # админ | редактирование кейса | показ подсказки ввода
            msg = await callback.message.answer(
                prompt,
                reply_markup=admin_cancel_case_edit_kb(case_id=case_id, back_page=back_page, show_done=show_done)
            )
            await state.update_data(prompt_message_id=msg.message_id)

            return

        if action == "review":
            await safe_delete_event_message(callback)

            if not payload or "|" not in payload:
                # админ | отзывы | некорректные данные
                await callback.answer("Некорректные данные", show_alert=True)
                return

            case_id_str, back_page_str = payload.split("|", 1)
            try:
                case_id = int(case_id_str)
                back_page = int(back_page_str)
            except ValueError:
                # админ | ответы | некорректные данные
                await callback.answer("Некорректные данные", show_alert=True)
                return

            await state.set_state(CaseEdit.waiting_review)
            await state.update_data(case_id=case_id, back_page=back_page, review_items=[])
            # админ | отзывы | подтверждение нажатия
            await callback.answer()

            prompt = (
                "Отправь отзыв: текст/фото/видео/голос/кружок.\n"
                "Фото/видео можно несколько (до 10).\n"
                "Голос/кружок — только по одному.\n"
                "Нажми Готово когда закончишь."
            )
            # админ | отзывы | показать подсказку ввода
            msg = await callback.message.answer(
                prompt,
                reply_markup=admin_cancel_review_edit_kb(case_id=case_id, back_page=back_page, show_done=True)
            )
            await state.update_data(prompt_message_id=msg.message_id)
            return

        if action == "review_cancel":
            if not payload or "|" not in payload:
                # админ | отзывы | некорректные данные
                await callback.answer("Некорректные данные", show_alert=True)
                return

            case_id_str, back_page_str = payload.split("|", 1)
            try:
                case_id = int(case_id_str)
                back_page = int(back_page_str)
            except ValueError:
                # админ | отзывы | некорректные данные
                await callback.answer("Некорректные данные", show_alert=True)
                return

            await cleanup_admin_messages(state, callback.bot, callback.message.chat.id)
            await state.clear()
            await render_case_editor(callback.message, state=state, case_id=case_id, back_page=back_page)
            # админ | отзывы | отмена
            await callback.answer("Отменено")
            return

        if action == "review_done":
            if not payload or "|" not in payload:
                # админ | отзывы | некорректные данные
                await callback.answer("Некорректные данные", show_alert=True)
                return

            case_id_str, back_page_str = payload.split("|", 1)
            try:
                case_id = int(case_id_str)
                back_page = int(back_page_str)
            except ValueError:
                # админ | отзывы | некорректные данные
                await callback.answer("Некорректные данные", show_alert=True)
                return

            data = await state.get_data()
            items = data.get("review_items", [])
            if not items:
                # админ | отзывы | предупреждение: нет элементов отзыва
                await callback.answer("Ты ещё не добавил отзыв", show_alert=True)
                return

            await upsert_case_review(case_id=case_id, items=items)
            await cleanup_admin_messages(state, callback.bot, callback.message.chat.id)
            await state.clear()
            await render_case_editor(callback.message, state=state, case_id=case_id, back_page=back_page, note="✅ Отзыв обновлён")
            await callback.answer("Сохранено")
            return

        if action == "cta":
            await safe_delete_event_message(callback)

            if not payload or "|" not in payload:
                # админ | CTA | некорректные данные
                await callback.answer("Некорректные данные", show_alert=True)
                return

            case_id_str, back_page_str = payload.split("|", 1)
            try:
                case_id = int(case_id_str)
                back_page = int(back_page_str)
            except ValueError:
                # админ | CTA | некорректные данные
                await callback.answer("Некорректные данные", show_alert=True)
                return

            cta = await get_case_cta(case_id)
            current_text = cta.get("button_text") if cta else None
            prompt = "Введи текст кнопки взаимодействия (до 64 символов) одним сообщением."
            if current_text:
                prompt += f"\nТекущий текст: {current_text}"

            await state.set_state(CaseEdit.waiting_cta_text)
            await state.update_data(case_id=case_id, back_page=back_page)

            msg = await callback.message.answer(
                prompt,
                reply_markup=admin_cancel_cta_edit_kb(case_id=case_id, back_page=back_page)
            )
            await state.update_data(prompt_message_id=msg.message_id)
            return

        if action == "cta_type":
            if len(parts) < 5:
                # админ | CTA | некорректные данные
                await callback.answer("Некорректные данные", show_alert=True)
                return
            cta_type = parts[3]
            payload = parts[4]
            if not payload or "|" not in payload:
                # админ | CTA | некорректные данные
                await callback.answer("Некорректные данные", show_alert=True)
                return

            case_id_str, back_page_str = payload.split("|", 1)
            try:
                case_id = int(case_id_str)
                back_page = int(back_page_str)
            except ValueError:
                # админ | CTA | некорректные данные
                await callback.answer("Некорректные данные", show_alert=True)
                return

            data = await state.get_data()
            cta_text = data.get("cta_text")
            if not cta_text:
                await callback.answer("Сначала укажи текст кнопки", show_alert=True)
                return

            if cta_type == "contact":
                await upsert_case_cta(case_id=case_id, button_text=cta_text, action_type="contact", action_value=None)
                await cleanup_admin_messages(state, callback.bot, callback.message.chat.id)
                await state.clear()
                await render_case_editor(callback.message, state=state, case_id=case_id, back_page=back_page, note="✅ Кнопка обновлена")
                await callback.answer("Сохранено")
                return

            if cta_type == "url":
                prompt_message_id = data.get("prompt_message_id")
                if prompt_message_id:
                    try:
                        await callback.message.bot.delete_message(chat_id=callback.message.chat.id, message_id=prompt_message_id)
                    except Exception:
                        pass
                await state.set_state(CaseEdit.waiting_cta_url)
                await state.update_data(case_id=case_id, back_page=back_page)
                msg = await callback.message.answer(
                    "Введи ссылку для кнопки (начиная с http:// или https://).",
                    reply_markup=admin_cancel_cta_edit_kb(case_id=case_id, back_page=back_page)
                )
                await state.update_data(prompt_message_id=msg.message_id)
                # админ | CTA | подтверждение нажатия
                await callback.answer()
                return

            # админ | CTA | некорректный тип
            await callback.answer("Некорректный тип", show_alert=True)
            return

        if action == "cta_cancel":
            if not payload or "|" not in payload:
                # админ | CTA | некорректные данные
                await callback.answer("Некорректные данные", show_alert=True)
                return

            case_id_str, back_page_str = payload.split("|", 1)
            try:
                case_id = int(case_id_str)
                back_page = int(back_page_str)
            except ValueError:
                # админ | CTA | некорректные данные
                await callback.answer("Некорректные данные", show_alert=True)
                return

            await cleanup_admin_messages(state, callback.bot, callback.message.chat.id)
            await state.clear()
            await render_case_editor(callback.message, state=state, case_id=case_id, back_page=back_page)
            await callback.answer("Отменено")
            return

        
        if action == "edit_cancel":
            if not payload or "|" not in payload:
                # админ | редактирование | некорректные данные
                await callback.answer("Некорректные данные", show_alert=True)
                return

            case_id_str, back_page_str = payload.split("|", 1)

            try:
                case_id = int(case_id_str)
                back_page = int(back_page_str)
            except ValueError:
                # админ | редактирование | некорректные данные
                await callback.answer("Некорректные данные", show_alert=True)
                return

            await safe_log_event(callback.from_user.id, "admin_case_edit", "edit_cancel", event_value=action, payload={"case_id": case_id, "action": action})

            await cleanup_admin_messages(state, callback.bot, callback.message.chat.id)
            await state.clear()

            case = await get_case_by_id(case_id)
            if not case:
                await callback.answer("Кейс не найден", show_alert=True)
                return

            caption = (
                f"<b>Редактор кейса</b>\n\n"
                f"ID: <code>{case['case_id']}</code>\n"
                f"Статус: <b>{case['status']}</b>\n\n"
                f"<b>{case['title']}</b>\n\n"
                f"{case['description']}"
            )

            try:
                await callback.message.delete()
            except Exception:
                pass

            await render_case_editor(callback.message, state=state, case_id=case_id, back_page=back_page)
            await callback.answer("Отменено")
            return
        

        if action == "cover_done":
            if not payload or "|" not in payload:
                # админ | редактирование | некорректные данные
                await callback.answer("Некорректные данные", show_alert=True)
                return

            case_id_str, back_page_str = payload.split("|", 1)
            try:
                case_id = int(case_id_str)
                back_page = int(back_page_str)
            except ValueError:
                # админ | редактирование | некорректные данные
                await callback.answer("Некорректные данные", show_alert=True)
                return

            await safe_log_event(callback.from_user.id, "admin_case_edit", "cover_done", event_value=action, payload={"case_id": case_id, "action": action})

            data = await state.get_data()
            items = data.get("cover_media", [])
            if not items:
                # админ | редактирование обложки | предупреждение: нет фото
                await callback.answer("Ты ещё не добавил фото", show_alert=True)
                return

            await delete_case_images(case_id)
            await add_case_media(case_id=case_id, items=items, make_first_cover=True)
            await cleanup_admin_messages(state, callback.bot, callback.message.chat.id)
            await state.clear()

            # удаляем промпт-сообщение с кнопками
            try:
                await callback.message.delete()
            except Exception:
                pass

            await render_case_editor(callback.message, state=state, case_id=case_id, back_page=back_page, note="🖼 Альбом обновлён ✅")
            await callback.answer("Сохранено")
            return
        

        if action in ("publish", "unpublish"):
            await safe_delete_event_message(callback)

            if not payload or "|" not in payload:
                # админ | публикация | некорректные данные
                await callback.answer("Некорректные данные", show_alert=True)
                return

            case_id_str, back_page_str = payload.split("|", 1)

            try:
                case_id = int(case_id_str)
                back_page = int(back_page_str)
            except ValueError:
                # админ | публикация | некорректные данные
                await callback.answer("Некорректные данные", show_alert=True)
                return

            await safe_log_event(callback.from_user.id, "admin_case_status", "status_change", event_value=action, payload={"case_id": case_id, "action": action})

            case = await get_case_by_id(case_id)
            if not case:
                await callback.answer("Кейс не найден", show_alert=True)
                return

            now_ts = time.monotonic()
            data = await state.get_data()
            last_action = data.get("last_action")
            last_ts = data.get("last_action_ts", 0.0)
            if last_action == action and (now_ts - float(last_ts)) < 2.0:
                await callback.answer()
                return
            await state.update_data(last_action=action, last_action_ts=now_ts)

            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass

            # определяем новый статус
            if action == "publish":
                new_status = "published"
                note = "Кейс опубликован"
            else:
                new_status = "draft"
                note = "Кейс скрыт"

            # обновляем статус
            await update_case_field(
                case_id=case_id,
                field="status",
                value=new_status
            )

            # перерисовываем редактор
            await render_case_editor(
                callback.message,
                state=state,
                case_id=case_id,
                back_page=back_page,
                note=note
            )

            await callback.answer()
            return
    
    await callback.answer("Неизвестная команда", show_alert=True)


@admin_router.message(CaseEdit.waiting_value)
async def save_case_field(message: Message, state: FSMContext):
    if message.from_user.id not in admins:
        await state.clear()
        return

    data = await state.get_data()
    prompt_message_id = data.get("prompt_message_id")
    case_id = data.get("case_id")
    field = data.get("field")
    back_page = data.get("back_page", 0)
    if not case_id or field not in ("title", "description", "cover"):
        await state.clear()
        # админ | редактирование | состояние потеряно
        await message.answer("Состояние редактирования потеряно, открой кейс заново")
        return

    async def cleanup_messages():
        if prompt_message_id:
            try:
                await message.bot.delete_message(chat_id=message.chat.id, message_id=prompt_message_id)
            except Exception:
                pass
        try:
            await message.delete()
        except Exception:
            pass

    if field == "cover":
        if not message.photo and not message.video:
            # админ | редактирование обложки | просьба отправить изображение/видео
            await message.answer("Пожалуйста, отправь изображение или видео для обложки, или нажми ✖️ Отмена.")
            return

        if message.photo:
            tg_file_id = message.photo[-1].file_id
            media_type = "photo"
        else:
            tg_file_id = message.video.file_id
            media_type = "video"

        data = await state.get_data()
        items = data.get("cover_media", [])
        if len(items) >= 10:
            # админ | редактирование обложки | ошибка: больше 10 медиа
            await message.answer("ВЫ добавили больше 10 изображений/видео")
            return
        items.append({"tg_file_id": tg_file_id, "media_type": media_type})

        await state.update_data(cover_media=items)

        try:
            await message.delete()
        except Exception:
            pass

        await safe_delete_event_message(message)
        return


    value = (message.text or "").strip()
    if not value:
        # админ | редактирование | предупреждение: пустое значение
        await message.answer("Пустое значение не пойдёт. Введи текст или нажми ✖️ Отмена.")
        return

    # простая валидация по длине
    if field == "title" and len(value) > 255:
        # админ | редактирование | ошибка: название слишком длинное
        await message.answer("Слишком длинное название (макс 255). Введи короче или нажми ✖️ Отмена.")
        return

    if field == "description" and len(value) > 2000:
        # админ | редактирование | ошибка: описание слишком длинное
        await message.answer("Слишком длинное описание (макс 2000). Введи короче или нажми ✖️ Отмена.")
        return

    await update_case_field(case_id=case_id, field=field, value=value)

    # чистим чат
    await cleanup_messages()
    await state.clear()

    # Перерисуем редактор кейса
    case = await get_case_by_id(case_id)
    if not case:
        # админ | редактирование | предупреждение: кейс не найден для отображения
        await message.answer("Сохранил, но кейс не найден для отображения.")
        return

    await render_case_editor(
    message,
    state=state,
    case_id=case_id,
    back_page=back_page
    )


@admin_router.message(CaseEdit.waiting_review)
async def save_case_review(message: Message, state: FSMContext):
    if message.from_user.id not in admins:
        await state.clear()
        return

    data = await state.get_data()
    case_id = data.get("case_id")
    back_page = data.get("back_page", 0)
    items = data.get("review_items", [])

    async def warn_and_cleanup(text: str):
        try:
            # админ | отзывы | временное предупреждение
            warn_msg = await message.answer(text)
            await asyncio.sleep(1.2)
            try:
                await warn_msg.delete()
            except Exception:
                pass
        except Exception:
            pass
        try:
            await message.delete()
        except Exception:
            pass

    if not case_id:
        await state.clear()
        await warn_and_cleanup("Состояние редактирования потеряно, открой кейс заново")
        return

    if len(items) >= 10:
        await warn_and_cleanup("Нельзя добавить больше 10 элементов отзыва")
        return

    if message.voice:
        if any(i.get("media_type") == "voice" for i in items):
            await warn_and_cleanup("Голосовое может быть только одно")
            return
        items.append({"media_type": "voice", "tg_file_id": message.voice.file_id})
    elif message.video_note:
        if any(i.get("media_type") == "video_note" for i in items):
            await warn_and_cleanup("Кружок может быть только один")
            return
        items.append({"media_type": "video_note", "tg_file_id": message.video_note.file_id})
    elif message.photo:
        items.append({"media_type": "photo", "tg_file_id": message.photo[-1].file_id})
    elif message.video:
        items.append({"media_type": "video", "tg_file_id": message.video.file_id})
    else:
        text_value = (message.text or "").strip()
        if not text_value:
            await warn_and_cleanup("Отправь текст или медиа для отзыва")
            return
        items.append({"media_type": "text", "text_content": text_value})

    await state.update_data(review_items=items)

    try:
        await message.delete()
    except Exception:
        pass


@admin_router.message(CaseEdit.waiting_cta_text)
async def save_cta_text(message: Message, state: FSMContext):
    if message.from_user.id not in admins:
        await state.clear()
        return

    data = await state.get_data()
    case_id = data.get("case_id")
    back_page = data.get("back_page", 0)
    prompt_message_id = data.get("prompt_message_id")
    if not case_id:
        await state.clear()
        # админ | CTA | состояние потеряно
        await message.answer("Состояние редактирования потеряно, открой кейс заново")
        return

    text_value = (message.text or "").strip()
    if not text_value:
        # админ | CTA | предупреждение: пустое значение
        await message.answer("Пустое значение не пойдёт. Введи текст или нажми ✖️ Отмена.")
        return

    if len(text_value) > 64:
        # админ | CTA | ошибка: текст слишком длинный
        await message.answer("Слишком длинный текст (макс 64). Введи короче.")
        return

    await state.update_data(cta_text=text_value)

    if prompt_message_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=prompt_message_id)
        except Exception:
            pass

    try:
        await message.delete()
    except Exception:
        pass

    # админ | CTA | показать варианты типа кнопки
    msg = await message.answer(
        "Выбери действие для кнопки:",
        reply_markup=admin_cta_type_kb(case_id=case_id, back_page=back_page)
    )
    await state.update_data(prompt_message_id=msg.message_id)


@admin_router.message(CaseEdit.waiting_cta_url)
async def save_cta_url(message: Message, state: FSMContext):
    if message.from_user.id not in admins:
        await state.clear()
        return

    data = await state.get_data()
    case_id = data.get("case_id")
    back_page = data.get("back_page", 0)
    prompt_message_id = data.get("prompt_message_id")
    cta_text = data.get("cta_text")
    if not case_id or not cta_text:
        await state.clear()
        # админ | CTA URL | состояние потеряно
        await message.answer("Состояние редактирования потеряно, открой кейс заново")
        return

    url = (message.text or "").strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        # админ | CTA URL | ошибка: некорректная ссылка
        await message.answer("Некорректная ссылка. Укажи http:// или https://")
        return

    await upsert_case_cta(case_id=case_id, button_text=cta_text, action_type="url", action_value=url)

    if prompt_message_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=prompt_message_id)
        except Exception:
            pass

    try:
        await message.delete()
    except Exception:
        pass

    await cleanup_admin_messages(state, message.bot, message.chat.id)
    await state.clear()
    await render_case_editor(message, state=state, case_id=case_id, back_page=back_page, note="✅ Кнопка обновлена")

