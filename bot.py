#!/usr/bin/env python3
"""
CANOPUS Telegram Bot
A bot with /start, /help commands, echo functionality, and currency conversion.
Uses Kasikornbank exchange rates (Bank Buying Rate / Bank Selling Rate).
"""

import os
import re
import logging
import requests
from bs4 import BeautifulSoup
from typing import Dict, Optional, Tuple
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

# Cache for rates (avoid hitting the site too often)
_rates_cache = {}
_cache_timestamp = 0
CACHE_TTL = 300  # 5 minutes


# ==================== EXCHANGE RATES MODULE ====================

def fetch_kasikornbank_rates() -> Dict[str, Dict]:
    """
    Fetch exchange rates from Kasikornbank website.
    All rates are in THB per 1 unit of foreign currency.
    
    Returns dict like:
    {
        'USD': {'name': 'US Dollar', 'buying_notes': 31.52, 'selling_notes': 32.96, 
                'buying_telex': 32.52, 'selling_tt': 32.82},
        ...
    }
    """
    import time
    global _rates_cache, _cache_timestamp
    
    # Check cache
    if _rates_cache and (time.time() - _cache_timestamp) < CACHE_TTL:
        logger.info("Using cached rates")
        return _rates_cache
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,th;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        }
        
        response = requests.get(KASIKORNBANK_URL, headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        table = soup.find('table', {'id': 'table-exchangerate'})
        
        if not table:
            logger.error("Exchange rate table not found on page")
            return _rates_cache  # Return old cache if available

        rates = {}
        rows = table.find_all('tr')

        # Structure:
        # Row 0: Header
        # Row 1: Sub-header (EXPORT SIGHT BILL | TELEX TRANSFER | BANK NOTES | TT&DRAFT | BANK NOTES)
        # Row 2+: Data rows (7 cells) alternating with calculator rows (1 cell)
        
        for row in rows[2:]:
            cells = row.find_all('td')
            if len(cells) != 7:
                continue

            # First cell: currency code and name
            first_cell_text = cells[0].get_text(separator='|', strip=True)
            match = re.match(r'([A-Z]{3})', first_cell_text)
            if not match:
                continue

            currency_code = match.group(1)
            
            # Get currency name
            parts = first_cell_text.split('|')
            if len(parts) >= 2:
                name_part = parts[1].strip()
                if ':' in name_part:
                    currency_name = currency_code
                else:
                    currency_name = name_part
            else:
                currency_name = currency_code

            # Skip duplicate USD entries (USD 5-20, USD 50-100)
            if currency_code == 'USD' and 'USD' in rates:
                continue
            if currency_code == 'USD':
                currency_name = "US Dollar"

            def parse_rate(cell_text):
                text = cell_text.strip()
                if text in ('-', '', 'N/A'):
                    return None
                try:
                    return float(text)
                except ValueError:
                    return None

            # Bank Buying Rate columns (bank buys foreign currency from you):
            buying_sight = parse_rate(cells[1].get_text(strip=True))    # Export Sight Bill
            buying_telex = parse_rate(cells[2].get_text(strip=True))    # Telex Transfer
            buying_notes = parse_rate(cells[3].get_text(strip=True))    # Bank Notes (Buy)
            
            # Bank Selling Rate columns (bank sells foreign currency to you):
            selling_tt = parse_rate(cells[4].get_text(strip=True))      # TT&Draft T/Cheques
            selling_notes = parse_rate(cells[5].get_text(strip=True))   # Bank Notes (Sell)

            if buying_notes or buying_telex or buying_sight or selling_tt or selling_notes:
                rates[currency_code] = {
                    'name': currency_name,
                    'buying_sight': buying_sight,
                    'buying_telex': buying_telex,
                    'buying_notes': buying_notes,
                    'selling_tt': selling_tt,
                    'selling_notes': selling_notes,
                }

        if rates:
            _rates_cache = rates
            _cache_timestamp = time.time()
            logger.info(f"Successfully fetched {len(rates)} currencies from Kasikornbank")
        
        return rates

    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP Error fetching Kasikornbank: {e}")
        return _rates_cache
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error fetching Kasikornbank: {e}")
        return _rates_cache
    except Exception as e:
        logger.error(f"Error parsing Kasikornbank: {e}")
        return _rates_cache


def convert_currency(amount: float, from_curr: str, to_curr: str) -> Optional[Dict]:
    """
    Convert amount between currencies using Kasikornbank rates.
    All rates are in THB per 1 unit of foreign currency.
    
    Logic:
    - If converting FROM foreign currency TO THB: use Bank Buying Rate (bank buys from you)
    - If converting FROM THB TO foreign currency: use Bank Selling Rate (bank sells to you)
    - If converting between two foreign currencies: go through THB
    """
    rates = fetch_kasikornbank_rates()
    if not rates:
        return None

    from_curr = from_curr.upper()
    to_curr = to_curr.upper()

    # Validate currencies
    if from_curr != 'THB' and from_curr not in rates:
        return None
    if to_curr != 'THB' and to_curr not in rates:
        return None

    result = None
    rate_info = ""

    if from_curr == 'THB' and to_curr == 'THB':
        result = amount
        rate_info = "1.0"
    elif from_curr == 'THB':
        # THB -> Foreign: use Bank Selling Rate (bank sells foreign to you)
        to_data = rates[to_curr]
        sell_rate = to_data['selling_notes'] or to_data['selling_tt']
        if sell_rate and sell_rate > 0:
            result = amount / sell_rate
            rate_info = f"1 {to_curr} = {sell_rate} THB (Sell)"
        else:
            return None
    elif to_curr == 'THB':
        # Foreign -> THB: use Bank Buying Rate (bank buys foreign from you)
        from_data = rates[from_curr]
        buy_rate = from_data['buying_notes'] or from_data['buying_telex'] or from_data['buying_sight']
        if buy_rate and buy_rate > 0:
            result = amount * buy_rate
            rate_info = f"1 {from_curr} = {buy_rate} THB (Buy)"
        else:
            return None
    else:
        # Foreign -> Foreign: go through THB
        # Step 1: from_curr -> THB (bank buys from_curr from you)
        from_data = rates[from_curr]
        buy_rate = from_data['buying_notes'] or from_data['buying_telex'] or from_data['buying_sight']
        
        # Step 2: THB -> to_curr (bank sells to_curr to you)
        to_data = rates[to_curr]
        sell_rate = to_data['selling_notes'] or to_data['selling_tt']
        
        if buy_rate and sell_rate and buy_rate > 0 and sell_rate > 0:
            thb_amount = amount * buy_rate
            result = thb_amount / sell_rate
            cross_rate = buy_rate / sell_rate
            rate_info = f"1 {from_curr} = {cross_rate:.6f} {to_curr}"
        else:
            return None

    if result is not None:
        return {
            'amount': amount,
            'from': from_curr,
            'to': to_curr,
            'result': round(result, 4),
            'rate_info': rate_info
        }
    return None


# ==================== BOT HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    welcome_message = (
        f"Привет, {user.mention_html()}! 👋\n\n"
        f"Я <b>CANOPUS</b> — бот для конвертации валют.\n\n"
        f"💱 Курсы валют берутся с сайта Kasikornbank\n"
        f"🏦 Источник: kasikornbank.com\n\n"
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
        "/rates — Показать курсы валют Kasikornbank\n"
        "/convert — Пересчет валют\n\n"
        "💱 <b>Примеры использования /convert:</b>\n"
        "<code>/convert 100 USD THB</code> — 100 долларов в баты\n"
        "<code>/convert 5000 THB USD</code> — 5000 батов в доллары\n"
        "<code>/convert 100 USD EUR</code> — 100 долларов в евро\n"
        "<code>/convert 1000 EUR THB</code> — 1000 евро в баты\n\n"
        "📊 <b>Столбцы курсов:</b>\n"
        "• <b>Buy</b> — банк покупает у вас (Bank Buying Rate)\n"
        "• <b>Sell</b> — банк продает вам (Bank Selling Rate)\n\n"
        "💬 Отправьте любое текстовое сообщение — я его повторю."
    )
    await update.message.reply_html(help_text)


async def rates_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show current exchange rates from Kasikornbank."""
    await update.message.reply_text("⏳ Загружаю курсы с Kasikornbank...")

    rates = fetch_kasikornbank_rates()
    if not rates:
        await update.message.reply_text(
            "❌ Не удалось получить курсы валют с Kasikornbank.\n"
            "Попробуйте позже или проверьте сайт:\n"
            "https://www.kasikornbank.com/en/rate/pages/foreign-exchange.aspx"
        )
        return

    text = "📊 <b>Курсы валют Kasikornbank</b>\n"
    text += "<i>(THB за 1 единицу валюты)</i>\n\n"
    
    # Show main currencies first
    main_currencies = ['USD', 'EUR', 'GBP', 'JPY', 'CHF', 'AUD', 'CAD', 'SGD', 'CNY', 'MYR', 'HKD', 'NZD']
    
    text += "<code>      Buy Notes  Sell Notes</code>\n"
    text += "<code>      (банк пок) (банк прод)</code>\n"
    text += "<code>─────────────────────────────</code>\n"

    shown = set()
    for code in main_currencies:
        if code in rates:
            data = rates[code]
            bn = f"{data['buying_notes']:.4f}" if data['buying_notes'] else "   -   "
            sn = f"{data['selling_notes']:.4f}" if data['selling_notes'] else "   -   "
            text += f"<code>{code:4s} {bn:>10s} {sn:>10s}</code>\n"
            shown.add(code)

    # Show remaining currencies
    remaining = [c for c in sorted(rates.keys()) if c not in shown]
    if remaining:
        text += f"\n<code>─── Другие валюты ───</code>\n"
        for code in remaining:
            data = rates[code]
            bn = f"{data['buying_notes']:.4f}" if data['buying_notes'] else "   -   "
            sn = f"{data['selling_notes']:.4f}" if data['selling_notes'] else "   -   "
            text += f"<code>{code:4s} {bn:>10s} {sn:>10s}</code>\n"

    text += f"\n📌 Всего валют: {len(rates)}\n"
    text += "🏦 Источник: Kasikornbank\n"
    text += "\nИспользуйте: <code>/convert сумма ВАЛЮТА1 ВАЛЮТА2</code>"

    await update.message.reply_html(text)


async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /convert command for currency conversion."""
    if not context.args or len(context.args) < 3:
        await update.message.reply_html(
            "❌ <b>Неверный формат</b>\n\n"
            "Использование: <code>/convert сумма ВАЛЮТА1 ВАЛЮТА2</code>\n\n"
            "Примеры:\n"
            "<code>/convert 100 USD THB</code> — продать 100$ банку\n"
            "<code>/convert 5000 THB USD</code> — купить доллары за 5000 батов\n"
            "<code>/convert 100 USD EUR</code> — пересчет через THB\n\n"
            "Доступные валюты: /rates"
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
                f"💱 <b>Конвертация валют (Kasikornbank)</b>\n\n"
                f"<code>{result['amount']:,.2f} {result['from']} = {result['result']:,.4f} {result['to']}</code>\n\n"
                f"📈 {result['rate_info']}\n"
                f"🏦 Источник: Kasikornbank"
            )
            await update.message.reply_html(text)
        else:
            rates = fetch_kasikornbank_rates()
            available = ', '.join(sorted(rates.keys())) if rates else "нет данных"
            await update.message.reply_html(
                f"❌ Не удалось конвертировать <b>{from_currency}</b> → <b>{to_currency}</b>.\n\n"
                f"Доступные валюты: {available}\n"
                f"Также можно использовать: <b>THB</b>\n\n"
                f"Используйте /rates для списка курсов."
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
