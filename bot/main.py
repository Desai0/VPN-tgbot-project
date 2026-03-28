import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv()

# Настраиваем логирование (понадобится для отладки)
logging.basicConfig(level=logging.INFO)

# Получаем токен из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("Не найден BOT_TOKEN в файле .env")

# Инициализируем бота и диспетчер
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Создаем клавиатуру главного меню
def get_main_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Купить VPN", callback_data="buy_vpn")],
            [InlineKeyboardButton(text="👤 Мой профиль", callback_data="my_profile")],
            [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")]
        ]
    )
    return keyboard

# Хэндлер на команду /start
@dp.message(CommandStart())
async def command_start_handler(message: types.Message) -> None:
    # Здесь позже мы добавим запись пользователя в БД
    welcome_text = (
        f"Привет, {message.from_user.full_name}! 👋\n\n"
        f"Это сервис быстрого и безопасного VPN (Hysteria 2).\n"
        f"Выбери нужное действие в меню ниже:"
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard())

# Хэндлер для кнопки "Помощь" (для примера обработки callback'ов)
@dp.callback_query(F.data == "help")
async def help_callback_handler(callback: types.CallbackQuery):
    help_text = "Здесь будет инструкция по настройке клиента Hysteria 2 на вашем устройстве."
    # Отвечаем на callback, чтобы часики на кнопке пропали
    await callback.answer()
    # Отправляем сообщение
    await callback.message.answer(help_text)

async def main() -> None:
    # Запускаем поллинг
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())