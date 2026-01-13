import asyncio
from aiogram.types import BotCommand, BotCommandScopeDefault
from create_bot import bot, dp, admins
from handlers.admin_panel import admin_router
from handlers.user_router import user_router
from db_handler.db_funk import get_all_users, init_db


# Функция, которая настроит командное меню (дефолтное для всех пользователей)
async def set_commands():
    commands = [
        BotCommand(command='restart', description='Перезапуск бота'),
    ]
    await bot.set_my_commands(commands, BotCommandScopeDefault())


# Функция, которая выполнится когда бот запустится
async def start_bot():
    # создаём таблицы, команды, уведомляем админов
    await init_db()
    # подключаем командное меню (/start, /profile, /help)
    await set_commands()
    try:
        count_users = await get_all_users(count=True)
        for admin_id in admins:
            await bot.send_message(admin_id, f'Я запущен. <b>{count_users}</b> пользователей.')
    except Exception:
        pass

# Функция, которая выполнится когда бот завершит свою работу
async def stop_bot():
    try:
        for admin_id in admins:
            await bot.send_message(admin_id, 'Кажется я всё... Пока!')
    except Exception:
        pass


async def main():
    # регистрация роутеров
    dp.include_router(user_router)
    dp.include_router(admin_router)

    # регистрация функций при старте и завершении работы бота
    dp.startup.register(start_bot)
    dp.shutdown.register(stop_bot)

    # запуск бота в режиме long polling при запуске бот очищает все обновления, которые были за его моменты бездействия
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()

if __name__ == '__main__':
    asyncio.run(main())
