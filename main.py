import logging
import os
import asyncio
from datetime import datetime

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)
from pyrogram import Client
from pyrogram.enums import ParseMode
import discord
from discord.ext import commands
from discord.errors import NotFound

from database import Database
from constants import *
from handlers.admin import register_admin_handlers
from handlers.status import register_status_handlers

# Включаем логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.environ.get("BOT_TOKEN")
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
DISCORD_SERVER_ID = os.environ.get("DISCORD_SERVER_ID")
DISCORD_ROLE_ID = os.environ.get("DISCORD_ROLE_ID")
DISCORD_CAPTAIN_ROLE_ID = os.environ.get("DISCORD_CAPTAIN_ROLE_ID")
USERBOT_TOKEN = os.environ.get("USERBOT_TOKEN")

if not BOT_TOKEN:
    logger.error("Не установлен BOT_TOKEN в .env файле!")
    exit(1)

# Проверка уникальности токенов
if BOT_TOKEN == USERBOT_TOKEN:
    logger.error("Ошибка: BOT_TOKEN и USERBOT_TOKEN должны быть разными!")
    exit(1)

# Инициализация базы данных
db = Database()

# Инициализация Pyrogram клиента (без запуска)
userbot = None
if API_ID and API_HASH and USERBOT_TOKEN:
    userbot = Client(
        name="my_userbot",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=USERBOT_TOKEN,
        parse_mode=ParseMode.HTML
    )
else:
    logger.warning("API_ID, API_HASH или USERBOT_TOKEN не установлены. Проверка по username будет ограничена.")

# Инициализация Discord клиента (без запуска)
discord_bot = None
if DISCORD_TOKEN and DISCORD_SERVER_ID:
    intents = discord.Intents.default()
    intents.members = True  # Нужно для получения списка участников сервера
    discord_bot = commands.Bot(command_prefix='!', intents=intents)
else:
    logger.warning("DISCORD_TOKEN или DISCORD_SERVER_ID не установлены. Проверка Discord будет ограничена.")

# Асинхронная функция для запуска дополнительных клиентов
async def start_extra_clients():
    global userbot, discord_bot
    
    # Запускаем Pyrogram клиент
    if userbot:
        try:
            logger.info("Запускаем Pyrogram клиент...")
            await userbot.start()
            logger.info("Pyrogram клиент запущен успешно")
        except Exception as e:
            logger.error(f"Ошибка при запуске Pyrogram: {e}")
            userbot = None
    
    # Запускаем Discord бота
    if discord_bot and DISCORD_TOKEN:
        try:
            logger.info("Запускаем Discord бота...")
            await discord_bot.start(DISCORD_TOKEN)
            logger.info("Discord бот запущен успешно")
        except Exception as e:
            logger.error(f"Ошибка при запуске Discord бота: {e}")
            discord_bot = None

# Клавиатуры
def get_main_keyboard():
    """Главная клавиатура с основными функциями."""
    keyboard = [
        [KeyboardButton("👤 Личный кабинет")],
        [KeyboardButton("ℹ️ Информация о турнире")],
        [KeyboardButton("❓ FAQ")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Приветственное сообщение и показ главного меню."""
    logger.debug(f"Вызван обработчик start от пользователя {update.effective_user.id}")
    welcome_message = """🏆 Добро пожаловать в бота регистрации на турнир

"M5 Domination Cup"

Я помогу вам зарегистрироваться на турнир и предоставлю всю необходимую информацию.

📝 Что я умею:
- Регистрация команды на турнир через личный кабинет
- Просмотр информации о турнире
- Проверка статуса регистрации
- Ответы на часто задаваемые вопросы

🎮 Для начала регистрации войдите в "Личный кабинет".
ℹ️ Для получения дополнительной информации выберите "Информация о турнире".

Важно: Убедитесь, что у вас готова следующая информация:
- Название команды
- Список игроков (никнеймы и Telegram-аккаунты)
- Контактные данные капитана (Дискорд или телеграм)

Удачи в турнире! 🎯"""

    await update.message.reply_text(welcome_message, reply_markup=get_main_keyboard())
    return ConversationHandler.END

async def tournament_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать информацию о турнире."""
    info_text = """🏆 <b>M5 Domination Cup</b> 🏆

📅 <b>Даты проведения:</b> 15 апреля - 30 апреля 2025

🎮 <b>Формат турнира:</b>
- 5х5 команды
- Double Elimination
- BO3 (лучший из 3 карт) в финалах
- BO1 (1 карта) на групповом этапе

💰 <b>Призовой фонд:</b>
🥇 1 место: 50,000 руб.
🥈 2 место: 30,000 руб.
🥉 3 место: 20,000 руб.

📌 <b>Требования к участникам:</b>
- Аккаунт не ниже Gold 3
- Наличие микрофона
- Минимальный возраст: 16 лет
- Подписка на канал @pubgruprime
- Участие в Discord сервере https://discord.gg/rupubg

📢 <b>Трансляции матчей</b> будут проходить на нашем Twitch-канале.

🛡️ <b>Античит:</b> Для турнира используется специальная система античит, инструкции по установке будут высланы после одобрения заявки.

⚠️ <b>Важно:</b> Окончание регистрации - за 3 дня до начала турнира!

Подробные правила и расписание смотрите на канале @pubgruprime"""

    back_button = [[KeyboardButton("◀️ Назад")]]
    back_keyboard = ReplyKeyboardMarkup(back_button, resize_keyboard=True)
    
    await update.message.reply_text(info_text, reply_markup=back_keyboard, parse_mode='HTML')
    return TOURNAMENT_INFO

async def faq(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать FAQ."""
    faq_text = """❓ <b>Часто задаваемые вопросы</b>

<b>Q: Как принять участие в турнире?</b>
A: Войдите в "Личный кабинет" в главном меню и следуйте инструкциям бота для создания команды и регистрации на турнир.

<b>Q: Сколько игроков должно быть в команде?</b>
A: Минимум 4 игрока (включая капитана), максимум 6 (4 основных + 2 запасных).

<b>Q: Обязательно ли всем быть подписанным на канал и Discord сервер?</b>
A: Да, все участники команды должны быть подписаны на @pubgruprime и присоединиться к Discord серверу https://discord.gg/rupubg.

<b>Q: Можно ли заменить игрока после регистрации?</b>
A: Да, капитан может запросить замену игрока, написав администратору. Замена возможна не позднее чем за 24 часа до начала турнира.

<b>Q: Как узнать статус заявки?</b>
A: Статус заявки можно проверить в Личном кабинете.

<b>Q: Что делать, если я не могу зарегистрироваться через бота?</b>
A: Свяжитесь с нами через администратора @pubgruprime_admin для ручной регистрации.

<b>Q: Можно ли участвовать в нескольких командах?</b>
A: Нет, один игрок может быть зарегистрирован только в одной команде.

<b>Q: Как будут проходить матчи?</b>
A: Расписание и детали будут отправлены капитанам после завершения регистрации. Все матчи проходят по заранее установленному расписанию.

<b>Q: Будут ли стримы матчей?</b>
A: Да, финальные стадии будут транслироваться на нашем Twitch-канале с комментаторами.

<b>Q: Как получить приз в случае победы?</b>
A: Вся информация о получении призов будет отправлена победителям после окончания турнира."""

    back_button = [[KeyboardButton("◀️ Назад")]]
    back_keyboard = ReplyKeyboardMarkup(back_button, resize_keyboard=True)
    
    await update.message.reply_text(faq_text, reply_markup=back_keyboard, parse_mode='HTML')
    return FAQ

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Вернуться в главное меню."""
    await update.message.reply_text(
        "Вы вернулись в главное меню. Выберите нужное действие:",
        reply_markup=get_main_keyboard()
    )
    return ConversationHandler.END

async def post_init(application: Application):
    """Инициализация после запуска приложения."""
    # Упрощенная функция - только логирование
    logger.info("Основной бот запущен и готов к работе!")
    
    # Запускаем дополнительные клиенты в отдельной задаче
    asyncio.create_task(start_extra_clients())

async def post_shutdown(application: Application):
    """Остановка Pyrogram и Discord после завершения работы."""
    global userbot
    global discord_bot
    
    # Остановка Pyrogram
    if userbot:
        try:
            logger.info("Останавливаем Pyrogram клиент...")
            await userbot.stop()
            logger.info("Pyrogram клиент остановлен")
        except Exception as e:
            logger.error(f"Ошибка при остановке Pyrogram: {e}")
    
    # Остановка Discord
    if discord_bot:
        try:
            logger.info("Останавливаем Discord бота...")
            await discord_bot.close()
            logger.info("Discord бот остановлен")
        except Exception as e:
            logger.error(f"Ошибка при остановке Discord бота: {e}")

def main() -> None:
    """Запуск бота."""
    try:
        logger.info("Запуск бота регистрации на турнир 'M5 Domination Cup'")
        
        # Создаем приложение с переработанным post_init
        application = Application.builder().token(BOT_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()
        
        # Делаем базу данных, userbot и discord_bot доступными везде
        application.bot_data['db'] = db
        application.bot_data['userbot'] = userbot
        application.bot_data['discord_bot'] = discord_bot
        application.bot_data['discord_server_id'] = DISCORD_SERVER_ID
        application.bot_data['discord_role_id'] = DISCORD_ROLE_ID
        application.bot_data['discord_captain_role_id'] = DISCORD_CAPTAIN_ROLE_ID
        
        # Регистрируем обработчики в главной части
        application.add_handler(CommandHandler("start", start))
        logger.debug("Обработчик команды /start зарегистрирован")
        
        # Регистрируем админские обработчики
        register_admin_handlers(application)
        logger.debug("Административные обработчики зарегистрированы")
        
        # Регистрируем обработчики статуса
        register_status_handlers(application)
        logger.debug("Обработчики статуса зарегистрированы")

        # Регистрируем обработчики личного кабинета
        from handlers.profile import register_profile_handlers
        register_profile_handlers(application)
        logger.debug("Обработчики личного кабинета зарегистрированы")
        
        # Создаем обработчики для информации и FAQ
        info_handler = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex("^ℹ️ Информация о турнире$"), tournament_info)],
            states={
                TOURNAMENT_INFO: [
                    MessageHandler(filters.Regex("^◀️ Назад$"), back_to_main),
                ],
            },
            fallbacks=[CommandHandler("start", start)],
        )
        application.add_handler(info_handler)
        logger.debug("Обработчик информации о турнире зарегистрирован")
        
        faq_handler = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex("^❓ FAQ$"), faq)],
            states={
                FAQ: [
                    MessageHandler(filters.Regex("^◀️ Назад$"), back_to_main),
                ],
            },
            fallbacks=[CommandHandler("start", start)],
        )
        application.add_handler(faq_handler)
        logger.debug("Обработчик FAQ зарегистрирован")
        
        # Запускаем бота с явными настройками
        logger.info("Запуск обработки обновлений бота...")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}", exc_info=True)
        raise

if __name__ == '__main__':
    main()