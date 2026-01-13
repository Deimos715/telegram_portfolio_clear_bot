import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from asyncpg_lite import DatabaseManager
from decouple import config



# Получаем список администраторов из .env
admins = [int(a.strip()) for a in config('ADMINS', default='').split(',') if a.strip()]

# Настраиваем логирование и выводим в переменную для отдельного использования в нужных местах
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Иициируем объект, который будет отвечать за взаимодействие с базой данных
db_manager = DatabaseManager(
    db_url=config('PG_LINK'),
    deletion_password=config('ROOT_PASS')
)

# Инициируем объект бота, передавая ему parse_mode=ParseMode.HTML по умолчанию
bot = Bot(token=config('TOKEN'), default=DefaultBotProperties(parse_mode=ParseMode.HTML))

# Инициируем объект бота
dp = Dispatcher()


