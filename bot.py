#!/usr/bin/env python3
"""
CANOPUS Telegram Bot
A bot with /start, /help commands, echo functionality, and currency conversion
from Kasikornbank exchange rates.
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

# Kasikornbank URL
KASIKORNBANK_URL = "https://www.kasikornbank.com/en/rate/pages/foreign-exchange.aspx"

# Base currency
BASE_CURRENCY = "THB"


# ==================== EXCHANGE RATES MODULE ====================

def fetch_exchange_rates() -> Dict[str, Dict[str, float]]:
    """Fetch exchange rates from Kasikornbank website."""
    try:
        logger.info(f"Fetching exchange rates from {KASIKORNBANK_URL}")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(KASIKORNBANK_URL, headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        table = soup.find('table', {'id': 'table-exchangerate'})
        if not table:
            logger.error("Could not find exchange rate table")
            return {}

        rates = {}
        rows = table.find_all('tr')[1:]  # Skip header

        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 5:
                continue
            try:
                text = cells[0].get_text(strip=True).replace('\n', '').strip()
                match = re.match(r'([A-Z]{3})\s*(.*)', text)
                if not match:
                    continue

                currency_code = match.group(1)
                currency_name = match.group(2).strip()

                # Skip USD denomination rows, keep only first one
                if currency_code == 'USD' and any(x in text for x in [':', '-', '5', '50']):
                    if 'USD' not in rates:
                        try:
                            buy_text = cells[2].get_text(strip=True)
                            sell_text = cells[4].get_text(strip=True)
                            buy_rate = float(buy_text) if buy_text != '-' else None
                            sell_rate = float(sell_text) if sell_text != '-' else None
                            if buy_rate or sell_rate:
                                rates['USD'] = {'buy': buy_rate, 'sell': sell_rate, 'name': 'US Dollar'}
                        except (ValueError, IndexError):
                            pass
                    continue

                # Extract rates
                buy_text = cells[2].get_text(strip=True)
                sell_text = cells[4].get_text(strip=True)

                buy_rate = float(buy_text) if buy_text != '-' else None
                sell_rate = float(sell_text) if sell_text != '-' else None

                if buy_rate is not None or sell_rate is not None:
                    rates[currency_code] = {
                        'buy': buy_rate,
                        'sell': sell_rate,
                        'name': currency_name
                    }

            except (ValueError, IndexError) as e:
                continue

        logger.info(f"Successfully fetched {len(rates)} currency rates")
        return rates

    except requests.RequestException as e:
        logger.error(f"Error fetching exchange rates: {e}")
        return {}
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {}


def convert_currency(amount: float, from_currency: str, to_currency: str, rates: Dict) -> Optional[Dict]:
    """Convert amount from one currency to another via THB."""
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()

    # To THB
    if to_currency == BASE_CURRENCY:
        if from_currency not in rates:
            return None
        sell_rate = rates[from_currency].get('sell')
        if sell_rate is None:
            return None
        result = amount * sell_rate
        return {
            'amount': amount, 'from': from_currency, 'to': to_currency,
            'result': round(result, 2), 'rate': sell_rate
        }

    # From THB
    if from_currency == BASE_CURRENCY:
        if to_currency not in rates:
            return None
        sell_rate = rates[to_currency].get('sell')
        if sell_rate is None:
            return None
        result = amount / sell_rate
        return {
            'amount': amount, 'from': from_currency, 'to': to_currency,
            'result': round(result, 2), 'rate': round(1 / sell_rate, 6)
        }

    # Between two non-THB currencies (via THB)
    if from_currency not in rates or to_currency not in rates:
        return None
    from_sell = rates[from_currency].get('sell')
    to_sell = rates[to_currency].get('sell')
    if from_sell is None or to_sell is None:
        return None

    amount_in_thb = amount * from_sell
    result = amount_in_thb / to_sell
    return {
        'amount': amount, 'from': from_currency, 'to': to_currency,
        'result': round(result, 4), 'rate': round(from_sell / to_sell, 6)
    }


# ==================== BOT HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    welcome_message = (
        f"Привет, {user.mention_html()}! 👋\n\n"
        f"Я <b>CANOPUS</b> — бот для конвертации валют.\n\n"
        f"💱 Курсы валют получаю с сайта Kasikornbank (Таиланд).\n\n"
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
        "/rates — Показать текущие курсы валют\n"
        "/convert — Пересчет валют\n\n"
        "💱 <b>Примеры использования /convert:</b>\n"
        "<code>/convert 100 USD THB</code>\n"
        "<code>/convert 5000 THB USD</code>\n"
        "<code>/convert 100 USD EUR</code>\n"
        "<code>/convert 50 EUR THB</code>\n\n"
        "💬 Отправьте любое текстовое сообщение — я его повторю."
    )
    await update.message.reply_html(help_text)


async def rates_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show current exchange rates."""
    await update.message.reply_text("⏳ Загружаю курсы валют...")

    rates = fetch_exchange_rates()
    if not rates:
        await update.message.reply_text("❌ Не удалось получить курсы валют. Попробуйте позже.")
        return

    text = "📊 <b>Курсы валют Kasikornbank</b>\n"
    text += "<i>(Базовая валюта: THB)</i>\n\n"
    text += "<code>Валюта  | Покупка  | Продажа</code>\n"
    text += "<code>--------|----------|--------</code>\n"

    # Show main currencies first
    main_currencies = ['USD', 'EUR', 'GBP', 'JPY', 'CHF', 'AUD', 'CAD', 'SGD', 'CNY', 'MYR', 'HKD', 'NZD']
    for code in main_currencies:
        if code in rates:
            r = rates[code]
            buy = f"{r['buy']:.4f}" if r['buy'] else "-"
            sell = f"{r['sell']:.4f}" if r['sell'] else "-"
            text += f"<code>{code:7s} | {buy:>8s} | {sell:>8s}</code>\n"

    text += f"\n📌 Всего доступно валют: {len(rates)}\n"
    text += "Используйте <code>/convert сумма ВАЛЮТА1 ВАЛЮТА2</code>"

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
            "<code>/convert 100 USD EUR</code>"
        )
        return

    try:
        amount = float(context.args[0])
        from_currency = context.args[1].upper()
        to_currency = context.args[2].upper()

        if amount <= 0:
            await update.message.reply_text("❌ Сумма должна быть больше 0")
            return

        rates = fetch_exchange_rates()
        if not rates:
            await update.message.reply_text("❌ Не удалось получить курсы валют. Попробуйте позже.")
            return

        # Check if currencies are valid
        valid_currencies = list(rates.keys()) + [BASE_CURRENCY]
        if from_currency not in valid_currencies:
            await update.message.reply_html(
                f"❌ Валюта <b>{from_currency}</b> не найдена.\n"
                f"Используйте /rates для списка доступных валют."
            )
            return
        if to_currency not in valid_currencies:
            await update.message.reply_html(
                f"❌ Валюта <b>{to_currency}</b> не найдена.\n"
                f"Используйте /rates для списка доступных валют."
            )
            return

        result = convert_currency(amount, from_currency, to_currency, rates)

        if result:
            text = (
                f"💱 <b>Конвертация валют</b>\n\n"
                f"<code>{result['amount']:,.2f} {result['from']} = {result['result']:,.2f} {result['to']}</code>\n\n"
                f"📈 Курс: 1 {result['from']} = {result['rate']} {result['to']}\n"
                f"🏦 Источник: Kasikornbank"
            )
            await update.message.reply_html(text)
        else:
            await update.message.reply_html(
                f"❌ Не удалось конвертировать <b>{from_currency}</b> → <b>{to_currency}</b>.\n"
                f"Возможно, курс для одной из валют недоступен."
            )

    except ValueError:
        await update.message.reply_text("❌ Неверная сумма. Введите число.")
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
