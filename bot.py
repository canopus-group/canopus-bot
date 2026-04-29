#!/usr/bin/env python3
"""
CANOPUS Telegram Bot
A bot with /start, /help commands, echo functionality, and currency conversion.
Uses ExchangeRate-API (free) with Kasikornbank as fallback source.
"""

import os
import re
import logging
import requests
from bs4 import BeautifulSoup
from typing import Dict, Optional
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token from environment variable
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8429560559:AAFFec1INAOwPFIj6Cx1_5IzLtUGBk3br4E")

# Base currency
BASE_CURRENCY = "THB"

# API URLs
EXCHANGE_RATE_API_URL = "https://open.er-api.com/v6/latest/{base}"
KASIKORNBANK_URL = "https://www.kasikornbank.com/en/rate/pages/foreign-exchange.aspx"


# ==================== EXCHANGE RATES MODULE ====================

def fetch_rates_from_api(base: str = "THB") -> Dict[str, float]:
    """Fetch exchange rates from ExchangeRate-API (free, no key needed)."""
    try:
        url = EXCHANGE_RATE_API_URL.format(base=base)
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get('result') == 'success':
            logger.info(f"Successfully fetched rates from ExchangeRate-API. Base: {base}")
            return data.get('rates', {})
        else:
            logger.error(f"API returned error: {data}")
            return {}
    except Exception as e:
        logger.error(f"Error fetching from ExchangeRate-API: {e}")
        return {}


def fetch_rates_from_kasikornbank() -> Dict[str, Dict]:
    """Fetch exchange rates from Kasikornbank website (fallback)."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        response = requests.get(KASIKORNBANK_URL, headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        table = soup.find('table', {'id': 'table-exchangerate'})
        if not table:
            return {}

        rates = {}
        rows = table.find_all('tr')

        for row in rows[2:]:
            cells = row.find_all('td')
            if len(cells) != 7:
                continue

            first_cell_text = cells[0].get_text(separator='|', strip=True)
            match = re.match(r'([A-Z]{3})', first_cell_text)
            if not match:
                continue

            currency_code = match.group(1)
            if currency_code == 'USD' and 'USD' in rates:
                continue

            def parse_rate(cell_text):
                text = cell_text.strip()
                if text in ('-', '', 'N/A'):
                    return None
                try:
                    return float(text)
                except ValueError:
                    return None

            buying_telex = parse_rate(cells[2].get_text(strip=True))
            selling_tt = parse_rate(cells[4].get_text(strip=True))

            if buying_telex or selling_tt:
                rates[currency_code] = {
                    'buy': buying_telex,
                    'sell': selling_tt
                }

        return rates
    except Exception as e:
        logger.error(f"Error fetching from Kasikornbank: {e}")
        return {}


def get_exchange_rates() -> Dict[str, float]:
    """Get exchange rates. Primary: ExchangeRate-API, Fallback: Kasikornbank."""
    # Primary source: ExchangeRate-API
    rates = fetch_rates_from_api("THB")
    if rates:
        return rates
    
    # Fallback: Kasikornbank
    logger.info("Primary API failed, trying Kasikornbank...")
    kbank_rates = fetch_rates_from_kasikornbank()
    if kbank_rates:
        # Convert to simple format: 1 THB = X currency
        converted = {'THB': 1.0}
        for code, data in kbank_rates.items():
            sell = data.get('sell')
            if sell and sell > 0:
                converted[code] = 1.0 / sell
        return converted
    
    return {}


def convert_currency(amount: float, from_curr: str, to_curr: str) -> Optional[Dict]:
    """Convert amount between currencies using THB as base."""
    rates = get_exchange_rates()
    if not rates:
        return None

    from_curr = from_curr.upper()
    to_curr = to_curr.upper()

    if from_curr not in rates or to_curr not in rates:
        return None

    # rates are: 1 THB = X currency
    # So: amount FROM -> THB -> TO
    from_rate = rates[from_curr]  # 1 THB = from_rate FROM
    to_rate = rates[to_curr]      # 1 THB = to_rate TO

    if from_rate == 0:
        return None

    # amount FROM * (1/from_rate) = amount in THB
    # amount in THB * to_rate = result in TO
    result = amount * (to_rate / from_rate)
    exchange_rate = to_rate / from_rate

    return {
        'amount': amount,
        'from': from_curr,
        'to': to_curr,
        'result': round(result, 4),
        'rate': round(exchange_rate, 6)
    }


# ==================== BOT HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    welcome_message = (
        f"Привет, {user.mention_html()}! 👋\n\n"
        f"Я <b>CANOPUS</b> — бот для конвертации валют.\n\n"
        f"💱 Курсы валют обновляются в реальном времени.\n"
        f"🏦 Источник: ExchangeRate-API / Kasikornbank\n\n"
        f"Используйте /help для списка доступных команд."
    )
    await update.message.reply_html(welcome_message)
    logger.info(f"User {user.id} started the bot")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    help_text = (
        "📋 <b>Доступные команды:</b>\n\n"
        "/start — Приветственное сообщение\n"
        "/help — Список доступных команд\n"
        "/rates — Показать основные курсы валют\n"
        "/convert — Пересчет валют\n\n"
        "💱 <b>Примеры использования /convert:</b>\n"
        "<code>/convert 100 USD THB</code>\n"
        "<code>/convert 5000 THB USD</code>\n"
        "<code>/convert 100 USD EUR</code>\n"
        "<code>/convert 50 EUR RUB</code>\n"
        "<code>/convert 1000 RUB THB</code>\n\n"
        "💬 Отправьте любое текстовое сообщение — я его повторю."
    )
    await update.message.reply_html(help_text)


async def rates_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show current exchange rates."""
    await update.message.reply_text("⏳ Загружаю курсы валют...")

    rates = get_exchange_rates()
    if not rates:
        await update.message.reply_text("❌ Не удалось получить курсы валют. Попробуйте позже.")
        return

    text = "📊 <b>Курсы валют (базовая: THB)</b>\n\n"
    
    # Main currencies to show
    main_currencies = ['USD', 'EUR', 'GBP', 'JPY', 'CHF', 'AUD', 'CAD', 'SGD', 'CNY', 'MYR', 'HKD', 'RUB', 'KRW', 'NZD', 'INR']
    
    text += "<code>Валюта |  1 THB =        | 1 Валюта = THB</code>\n"
    text += "<code>-------|-----------------|---------------</code>\n"

    for code in main_currencies:
        if code in rates and rates[code] != 0:
            rate_from_thb = rates[code]  # 1 THB = X currency
            rate_to_thb = 1.0 / rate_from_thb  # 1 currency = X THB
            text += f"<code>{code:6s} | {rate_from_thb:>14.6f} | {rate_to_thb:>13.4f}</code>\n"

    text += f"\n📌 Всего доступно валют: {len(rates)}\n"
    text += "\nИспользуйте: <code>/convert сумма ВАЛЮТА1 ВАЛЮТА2</code>"

    await update.message.reply_html(text)


async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /convert command for currency conversion."""
    if not context.args or len(context.args) < 3:
        await update.message.reply_html(
            "❌ <b>Неверный формат</b>\n\n"
            "Использование: <code>/convert сумма ВАЛЮТА1 ВАЛЮТА2</code>\n\n"
            "Примеры:\n"
            "<code>/convert 100 USD THB</code>\n"
            "<code>/convert 5000 THB USD</code>\n"
            "<code>/convert 100 USD EUR</code>\n"
            "<code>/convert 50 EUR RUB</code>"
        )
        return

    try:
        amount = float(context.args[0].replace(',', ''))
        from_currency = context.args[1].upper()
        to_currency = context.args[2].upper()

        if amount <= 0:
            await update.message.reply_text("❌ Сумма должна быть больше 0")
            return

        result = convert_currency(amount, from_currency, to_currency)

        if result:
            text = (
                f"💱 <b>Конвертация валют</b>\n\n"
                f"<code>{result['amount']:,.2f} {result['from']} = {result['result']:,.4f} {result['to']}</code>\n\n"
                f"📈 Курс: 1 {result['from']} = {result['rate']} {result['to']}\n"
                f"🏦 Источник: ExchangeRate-API"
            )
            await update.message.reply_html(text)
        else:
            await update.message.reply_html(
                f"❌ Не удалось конвертировать <b>{from_currency}</b> → <b>{to_currency}</b>.\n"
                f"Проверьте коды валют. Используйте /rates для списка."
            )

    except ValueError:
        await update.message.reply_text("❌ Неверная сумма. Введите число.\n\nПример: /convert 100 USD THB")
    except Exception as e:
        logger.error(f"Error in convert_command: {e}")
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте позже.")


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Echo the user message."""
    await update.message.reply_text(f"Вы написали: {update.message.text}")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors."""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)


def main() -> None:
    """Start the bot."""
    logger.info("Starting CANOPUS bot...")

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("rates", rates_command))
    application.add_handler(CommandHandler("convert", convert_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    application.add_error_handler(error_handler)

    logger.info("CANOPUS bot is running!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
