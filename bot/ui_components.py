from __future__ import annotations

import html

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from backend_client import UserStats, VpnConfig

PARSE_HTML = "HTML"

TEXT_BUY = "🛡 Купить VPN"
TEXT_PROFILE = "👤 Профиль"
TEXT_HELP = "❓ Помощь"


def reply_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=TEXT_BUY)],
            [
                KeyboardButton(text=TEXT_PROFILE),
                KeyboardButton(text=TEXT_HELP),
            ],
        ],
        resize_keyboard=True,
        input_field_placeholder="Меню VPN-сервиса…",
    )


def inline_tariff_keyboard(price_30: int, price_90: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"30 дней — ⭐ {price_30}",
                    callback_data="tariff_30",
                ),
                InlineKeyboardButton(
                    text=f"90 дней — ⭐ {price_90}",
                    callback_data="tariff_90",
                ),
            ],
            [InlineKeyboardButton(text="« В меню", callback_data="menu_main")],
        ]
    )


def format_profile_html(stats: UserStats) -> str:
    subscription_status = "✅ активна" if stats.subscription_active else "○ неактивна"
    return (
        "<b>👤 Профиль</b>\n\n"
        f"<code>Telegram ID</code>: <code>{stats.telegram_id}</code>\n"
        f"<code>Client ID</code>: <code>{stats.client_id}</code>\n"
        f"Подписка: {subscription_status}\n"
        f"Осталось дней: <b>{stats.days_left}</b>\n"
        f"Трафик: ↑ <code>{stats.tx_bytes}</code> · ↓ <code>{stats.rx_bytes}</code> байт\n"
        f"Онлайн: <b>{stats.online_connections}</b>"
    )


def format_vpn_config_html(config: VpnConfig) -> str:
    return (
        "<b>🔐 Конфигурация готова</b>\n\n"
        f"Осталось дней: <b>{config.days_left}</b>\n\n"
        "<b>Ссылка для клиента</b> (нажмите, чтобы скопировать):\n"
        f"<code>{config.config_url}</code>"
    )


def build_help_html() -> str:
    return (
        "<b>❓ Помощь</b>\n\n"
        "<b>Команды</b>\n"
        "/start — регистрация и меню\n"
        "/vpn — выдать конфиг (тест, без оплаты)\n"
        "/profile — статистика и подписка\n"
        "/help — эта справка\n\n"
        "<b>Оплата</b>\n"
        "«Купить VPN» → выберите срок → оплатите <b>Telegram Stars</b> (⭐).\n"
        "После оплаты бот пришлёт ссылку конфигурации.\n\n"
        "<i>Для приёма Stars включите платежи у бота в @BotFather.</i>"
    )


def welcome_html(full_name: str) -> str:
    safe_name = html.escape(full_name)
    return (
        f"Привет, <b>{safe_name}</b>.\n\n"
        "Это бот доступа к VPN на базе <b>Hysteria 2</b>.\n"
        "Выберите действие кнопками ниже или воспользуйтесь меню."
    )
