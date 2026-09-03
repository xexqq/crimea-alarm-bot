import asyncio
import os
import logging

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiohttp import web

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)


@dp.message_handler(commands=["start"])
async def start_handler(message: types.Message):
    await message.answer("Привет! Бот запущен и работает.")


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
