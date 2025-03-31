import asyncio
import logging
from pyrogram import Client
from discord.ext import commands

logger = logging.getLogger(__name__)

async def start_extra_clients(userbot, discord_bot, discord_token, discord_server_id):
    # Запускаем Pyrogram клиент
    if userbot:
        try:
            logger.info("Запускаем Pyrogram клиент...")
            await userbot.start()
            logger.info("Pyrogram клиент запущен успешно")
        except Exception as e:
            logger.error(f"Ошибка при запуске Pyrogram: {e}")
            return None, None
    
    # Запускаем Discord бота
    if discord_bot and discord_token:
        try:
            logger.info("Запускаем Discord бота...")
            # Запускаем бота в отдельном потоке
            asyncio.create_task(discord_bot.start(discord_token))
            # Ждем пока бот не будет готов
            await asyncio.sleep(2)
            logger.info("Discord бот запущен успешно")
        except Exception as e:
            logger.error(f"Ошибка при запуске Discord бота: {e}")
            discord_bot = None
    
    return userbot, discord_bot