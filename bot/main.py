from __future__ import annotations

import asyncio
import html
import logging
import os
import socket
import uuid

from aiogram import Bot, Dispatcher, F, types
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command, CommandStart
from aiogram.types import LabeledPrice, PreCheckoutQuery
from dotenv import load_dotenv

from backend_client import BackendClient, BackendClientError, VpnConfig
from ui_components import (
    PARSE_HTML,
    TEXT_BUY,
    TEXT_HELP,
    TEXT_PROFILE,
    build_help_html,
    format_profile_html,
    format_vpn_config_html,
    inline_tariff_keyboard,
    reply_main_menu,
    welcome_html,
)


load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is required.")

STARS_CURRENCY = "XTR"
STAR_PRICE_30 = max(1, int(os.getenv("VPN_STARS_PRICE_30", "50")))
STAR_PRICE_90 = max(1, int(os.getenv("VPN_STARS_PRICE_90", "120")))
ALLOWED_TARIFF_DAYS = frozenset({30, 90})


def stars_for_days(days: int) -> int:
    if days == 30:
        return STAR_PRICE_30
    if days == 90:
        return STAR_PRICE_90
    raise ValueError(f"Unsupported tariff days: {days}")


def build_invoice_payload(telegram_id: int, days: int) -> str:
    token = uuid.uuid4().hex[:16]
    raw = f"vpn|{telegram_id}|{days}|{token}"
    if len(raw) > 128:
        token = uuid.uuid4().hex[:8]
        raw = f"vpn|{telegram_id}|{days}|{token}"
    return raw


def parse_invoice_payload(payload: str) -> tuple[int, int] | None:
    parts = payload.split("|")
    if len(parts) < 4 or parts[0] != "vpn":
        return None
    try:
        telegram_id = int(parts[1])
        days = int(parts[2])
    except ValueError:
        return None
    if days not in ALLOWED_TARIFF_DAYS:
        return None
    return telegram_id, days


def build_telegram_session() -> AiohttpSession:
    session = AiohttpSession()
    session._connector_init["family"] = socket.AF_INET
    return session


bot = Bot(token=BOT_TOKEN, session=build_telegram_session())
dp = Dispatcher()
backend_client = BackendClient()


async def send_backend_error(
    target: types.Message | types.CallbackQuery,
    error: BackendClientError,
) -> None:
    logger.warning("Backend error surfaced to user: %s", error)
    text = f"⚠️ <b>Ошибка сервиса</b>\n{html.escape(str(error))}"
    markup = reply_main_menu()
    if isinstance(target, types.CallbackQuery):
        if target.message:
            await target.message.answer(text, parse_mode=PARSE_HTML, reply_markup=markup)
    else:
        await target.answer(text, parse_mode=PARSE_HTML, reply_markup=markup)


async def show_tariff_choice(message: types.Message) -> None:
    await message.answer(
        "<b>Выберите тариф</b>\n\n"
        "Оплата — <b>Telegram Stars</b> (⭐). После успешной оплаты пришлю "
        "ссылку конфигурации <b>Hysteria 2</b>.",
        parse_mode=PARSE_HTML,
        reply_markup=inline_tariff_keyboard(STAR_PRICE_30, STAR_PRICE_90),
    )


async def deliver_vpn_config(message: types.Message, config: VpnConfig) -> None:
    await message.answer(
        format_vpn_config_html(config),
        parse_mode=PARSE_HTML,
        reply_markup=reply_main_menu(),
    )


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

    await message.answer(
        welcome_html(message.from_user.full_name),
        parse_mode=PARSE_HTML,
        reply_markup=reply_main_menu(),
    )


@dp.message(Command("profile"))
@dp.message(F.text == TEXT_PROFILE)
async def profile_handler(message: types.Message) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя Telegram.")
        return

    logger.info("Profile request from user_id=%s", message.from_user.id)
    try:
        stats = await backend_client.get_user_stats(message.from_user.id)
    except BackendClientError as exc:
        await send_backend_error(message, exc)
        return

    await message.answer(
        format_profile_html(stats),
        parse_mode=PARSE_HTML,
        reply_markup=reply_main_menu(),
    )


@dp.message(Command("vpn"))
async def vpn_command_handler(message: types.Message) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя Telegram.")
        return

    logger.info("Free /vpn config from user_id=%s", message.from_user.id)
    try:
        config = await backend_client.generate_vpn_config(message.from_user.id)
    except BackendClientError as exc:
        await send_backend_error(message, exc)
        return

    await deliver_vpn_config(message, config)


@dp.message(Command("help"))
@dp.message(F.text == TEXT_HELP)
async def help_handler(message: types.Message) -> None:
    if message.from_user is not None:
        logger.info("Help from user_id=%s", message.from_user.id)
    await message.answer(
        build_help_html(),
        parse_mode=PARSE_HTML,
        reply_markup=reply_main_menu(),
    )


@dp.message(F.text == TEXT_BUY)
@dp.callback_query(F.data == "buy_vpn")
async def buy_vpn_entry(event: types.Message | types.CallbackQuery) -> None:
    if isinstance(event, types.CallbackQuery):
        if event.from_user is None:
            await event.answer("Не удалось определить пользователя.", show_alert=True)
            return
        logger.info("Callback buy_vpn from user_id=%s", event.from_user.id)
        await event.answer()
        if event.message is None:
            return
        await show_tariff_choice(event.message)
        return

    message = event
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя Telegram.")
        return
    logger.info("Text buy from user_id=%s", message.from_user.id)
    await show_tariff_choice(message)


@dp.callback_query(F.data.in_({"tariff_30", "tariff_90"}))
async def tariff_callback_handler(callback: types.CallbackQuery) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer("Ошибка: нет данных.", show_alert=True)
        return

    days = 30 if callback.data == "tariff_30" else 90
    stars = stars_for_days(days)
    telegram_id = callback.from_user.id
    payload = build_invoice_payload(telegram_id, days)

    await callback.answer()
    try:
        await bot.send_invoice(
            chat_id=callback.message.chat.id,
            title=f"VPN — {days} дн.",
            description=(
                f"Подписка Hysteria 2 на {days} календарных дней. "
                "Цифровой товар, доставка — сообщением в чат."
            ),
            payload=payload,
            currency=STARS_CURRENCY,
            prices=[LabeledPrice(label=f"VPN {days} дн.", amount=stars)],
            provider_token="",
        )
    except Exception as exc:
        logger.exception("send_invoice failed: %s", exc)
        await callback.message.answer(
            "Не удалось выставить счёт. Проверьте, что у бота включены "
            "платежи (Stars) в @BotFather.",
            reply_markup=reply_main_menu(),
        )


@dp.callback_query(F.data == "help")
async def help_callback_handler(callback: types.CallbackQuery) -> None:
    if callback.from_user is not None:
        logger.info("Callback help from user_id=%s", callback.from_user.id)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            build_help_html(),
            parse_mode=PARSE_HTML,
            reply_markup=reply_main_menu(),
        )


@dp.callback_query(F.data == "menu_main")
async def menu_main_callback_handler(callback: types.CallbackQuery) -> None:
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "<b>Главное меню</b>\nИспользуйте кнопки внизу экрана.",
            parse_mode=PARSE_HTML,
            reply_markup=reply_main_menu(),
        )


@dp.callback_query(F.data == "my_profile")
async def my_profile_callback_handler(callback: types.CallbackQuery) -> None:
    if callback.from_user is None:
        await callback.answer("Не удалось определить пользователя.", show_alert=True)
        return

    logger.info("Callback my_profile from user_id=%s", callback.from_user.id)
    await callback.answer()
    if callback.message is None:
        return
    try:
        stats = await backend_client.get_user_stats(callback.from_user.id)
    except BackendClientError as exc:
        await send_backend_error(callback, exc)
        return

    await callback.message.answer(
        format_profile_html(stats),
        parse_mode=PARSE_HTML,
        reply_markup=reply_main_menu(),
    )


@dp.pre_checkout_query()
async def pre_checkout_handler(query: PreCheckoutQuery) -> None:
    if query.from_user is None:
        await bot.answer_pre_checkout_query(query.id, ok=False, error_message="Нет данных пользователя.")
        return

    parsed = parse_invoice_payload(query.invoice_payload)
    if parsed is None:
        await bot.answer_pre_checkout_query(query.id, ok=False, error_message="Некорректный счёт.")
        return

    telegram_id, days = parsed
    if telegram_id != query.from_user.id:
        await bot.answer_pre_checkout_query(query.id, ok=False, error_message="Счёт выписан другому пользователю.")
        return

    if query.currency != STARS_CURRENCY:
        await bot.answer_pre_checkout_query(query.id, ok=False, error_message="Неверная валюта.")
        return

    expected = stars_for_days(days)
    if query.total_amount != expected:
        await bot.answer_pre_checkout_query(
            query.id,
            ok=False,
            error_message="Сумма не совпадает с тарифом. Запросите счёт заново.",
        )
        return

    await bot.answer_pre_checkout_query(query.id, ok=True)


@dp.message(F.successful_payment)
async def successful_payment_handler(message: types.Message) -> None:
    payment = message.successful_payment
    if payment is None or message.from_user is None:
        return

    parsed = parse_invoice_payload(payment.invoice_payload)
    if parsed is None:
        logger.error("Bad invoice payload after payment: %s", payment.invoice_payload)
        await message.answer(
            "Оплата прошла, но не удалось разобрать данные счёта. Обратитесь в поддержку.",
            reply_markup=reply_main_menu(),
        )
        return

    telegram_id, days = parsed
    if telegram_id != message.from_user.id:
        await message.answer(
            "Оплата получена от другого аккаунта. Конфигурация не выдана.",
            reply_markup=reply_main_menu(),
        )
        return

    try:
        config = await backend_client.subscribe_vpn(telegram_id, days)
    except BackendClientError as exc:
        await send_backend_error(message, exc)
        return

    await message.answer(
        "<b>✅ Оплата принята</b>\nСпасибо! Ниже ваша конфигурация.",
        parse_mode=PARSE_HTML,
    )
    await deliver_vpn_config(message, config)


async def main() -> None:
    await backend_client.start()
    try:
        logger.info("Starting bot polling (Stars tariffs: 30d=%s, 90d=%s)", STAR_PRICE_30, STAR_PRICE_90)
        await dp.start_polling(bot)
    finally:
        logger.info("Stopping bot polling")
        await backend_client.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
