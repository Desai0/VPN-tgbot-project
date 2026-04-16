from __future__ import annotations

import asyncio
import logging
import os
import socket

from aiogram import Bot, Dispatcher, F, types
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from backend_client import BackendClient, BackendClientError, UserStats, VpnConfig
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is required.")


def build_telegram_session() -> AiohttpSession:
    session = AiohttpSession()
    session._connector_init["family"] = socket.AF_INET
    return session


bot = Bot(token=BOT_TOKEN, session=build_telegram_session())
dp = Dispatcher()
backend_client = BackendClient()


def get_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Купить VPN", callback_data="buy_vpn")],
            [InlineKeyboardButton(text="Мой профиль", callback_data="my_profile")],
            [InlineKeyboardButton(text="Помощь", callback_data="help")],
        ]
    )


def format_profile(stats: UserStats) -> str:
    subscription_status = "активна" if stats.subscription_active else "неактивна"
    return (
        "Профиль пользователя\n\n"
        f"Telegram ID: {stats.telegram_id}\n"
        f"Client ID: {stats.client_id}\n"
        f"Подписка: {subscription_status}\n"
        f"Дней осталось: {stats.days_left}\n"
        f"TX: {stats.tx_bytes} bytes\n"
        f"RX: {stats.rx_bytes} bytes\n"
        f"Online connections: {stats.online_connections}"
    )


def format_vpn_config(config: VpnConfig) -> str:
    return (
        "VPN конфигурация готова\n\n"
        f"Telegram ID: {config.telegram_id}\n"
        f"Дней осталось: {config.days_left}\n"
        f"Config URL:\n{config.config_url}"
    )


def build_help_text() -> str:
    return (
        "Скелет бота подключен к backend.\n\n"
        "Что уже работает:\n"
        "/start - регистрация пользователя в backend и главное меню\n"
        '"Купить VPN" - вызов генерации конфигурации\n'
        '"Мой профиль" - чтение статуса подписки и трафика\n\n'
        "Переменные окружения:\n"
        "BOT_TOKEN - токен Telegram-бота\n"
        "BACKEND_URL - адрес backend, по умолчанию http://backend:8000\n"
        "BACKEND_TIMEOUT_SECONDS - timeout запросов к backend"
    )


async def send_backend_error(
    target: types.Message | types.CallbackQuery,
    error: BackendClientError,
) -> None:
    logger.warning("Backend error surfaced to user: %s", error)
    text = f"Ошибка backend: {error}"
    if isinstance(target, types.CallbackQuery):
        await target.message.answer(text, reply_markup=get_main_keyboard())
    else:
        await target.answer(text, reply_markup=get_main_keyboard())


@dp.message(CommandStart())
async def command_start_handler(message: types.Message) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя Telegram.")
        return

    logger.info(
        "Received /start from user_id=%s username=%s",
        message.from_user.id,
        message.from_user.username,
    )
    try:
        await backend_client.register_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )
    except BackendClientError as exc:
        await send_backend_error(message, exc)
        return

    welcome_text = (
        f"Привет, {message.from_user.full_name}.\n\n"
        "Бот подключен к backend и готов к базовым сценариям.\n"
        "Выбери действие в меню ниже."
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard())


@dp.message(Command("profile"))
async def profile_command_handler(message: types.Message) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя Telegram.")
        return

    logger.info("Received /profile from user_id=%s", message.from_user.id)
    try:
        stats = await backend_client.get_user_stats(message.from_user.id)
    except BackendClientError as exc:
        await send_backend_error(message, exc)
        return

    await message.answer(format_profile(stats), reply_markup=get_main_keyboard())


@dp.message(Command("vpn"))
async def vpn_command_handler(message: types.Message) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя Telegram.")
        return

    logger.info("Received /vpn from user_id=%s", message.from_user.id)
    try:
        config = await backend_client.generate_vpn_config(message.from_user.id)
    except BackendClientError as exc:
        await send_backend_error(message, exc)
        return

    await message.answer(format_vpn_config(config), reply_markup=get_main_keyboard())


@dp.message(Command("help"))
async def help_command_handler(message: types.Message) -> None:
    if message.from_user is not None:
        logger.info("Received /help from user_id=%s", message.from_user.id)
    await message.answer(build_help_text(), reply_markup=get_main_keyboard())


@dp.callback_query(F.data == "buy_vpn")
async def buy_vpn_callback_handler(callback: types.CallbackQuery) -> None:
    if callback.from_user is None:
        await callback.answer("Не удалось определить пользователя.", show_alert=True)
        return

    logger.info("Callback buy_vpn from user_id=%s", callback.from_user.id)
    await callback.answer()
    try:
        config = await backend_client.generate_vpn_config(callback.from_user.id)
    except BackendClientError as exc:
        await send_backend_error(callback, exc)
        return

    await callback.message.answer(
        format_vpn_config(config),
        reply_markup=get_main_keyboard(),
    )


@dp.callback_query(F.data == "my_profile")
async def my_profile_callback_handler(callback: types.CallbackQuery) -> None:
    if callback.from_user is None:
        await callback.answer("Не удалось определить пользователя.", show_alert=True)
        return

    logger.info("Callback my_profile from user_id=%s", callback.from_user.id)
    await callback.answer()
    try:
        stats = await backend_client.get_user_stats(callback.from_user.id)
    except BackendClientError as exc:
        await send_backend_error(callback, exc)
        return

    await callback.message.answer(
        format_profile(stats),
        reply_markup=get_main_keyboard(),
    )


@dp.callback_query(F.data == "help")
async def help_callback_handler(callback: types.CallbackQuery) -> None:
    if callback.from_user is not None:
        logger.info("Callback help from user_id=%s", callback.from_user.id)
    await callback.answer()
    await callback.message.answer(build_help_text(), reply_markup=get_main_keyboard())


async def main() -> None:
    await backend_client.start()
    try:
        logger.info("Starting bot polling")
        await dp.start_polling(bot)
    finally:
        logger.info("Stopping bot polling")
        await backend_client.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
