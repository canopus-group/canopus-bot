#!/usr/bin/env python3
"""
CANOPUS Telegram Bot
A bot with /start, /help commands, echo functionality, and currency conversion.
Uses Kasikornbank exchange rates (Bank Buying Rate / Bank Selling Rate).
"""

import os
import re
import logging
import time
import cloudscraper
from bs4 import BeautifulSoup
from typing import Dict, Optional
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ТОКЕН (Рекомендуется использовать переменную окружения)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8429560559:AAEzhVnJ87oW1pDKnwTZ9mVPTSQLn2H7ZAQ")

# Настройки кеша
KASIKORNBANK_URL = "https://www.kasikornbank.com/en/rate/pages/foreign-exchange.aspx"
_rates_cache = {}
_cache_timestamp = 0
CACHE_TTL = 600  # 10 минут

# ==================== МОДУЛЬ ПАРСИНГА ====================

def fetch_kasikornbank_rates() -> Dict[str, Dict]:
    global _rates_cache, _cache_timestamp
    
    if _rates_cache and (time.time() - _cache_timestamp) < CACHE_TTL:
        return _rates_cache
    
    try:
        # cloudscraper помогает обойти защиту от ботов
        scraper = cloudscraper.create_scraper()
        response = scraper.get(KASIKORNBANK_URL, timeout=20)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        # Ищем таблицу по классу или ID
        table = soup.find('table', {'id': 'table-exchangerate'}) or soup.find('table', class_='table-rate')
        
        if not table:
            logger.error("Таблица курсов не найдена на странице")
            return _rates_cache

        new_rates = {}
        rows = table.find_all('tr')

        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 6:
                continue

            # Извлекаем код валюты (например, USD)
            text = cells[0].get_text(strip=True)
            match = re.search(r'([A-Z]{3})', text)
            if not match:
                continue
            
            code = match.group(1)
            
            # Пропускаем дубликаты USD (у банка их несколько для разных купюр)
            if code == 'USD' and code in new_rates:
                continue

            def to_float(val):
                try:
                    return float(val.get_text(strip=True).replace(',', ''))
                except (ValueError, AttributeError):
                    return None

            # Индексы могут меняться, но обычно: 
            # 3 - Buying Notes, 5 - Selling Notes
            new_rates[code] = {
                'name': code,
                'buying_notes': to_float(cells[3]),
                'selling_notes': to_float(cells[5]),
                'buying_telex': to_float(cells[2]),
                'selling_tt': to_float(cells[4])
            }

        if new_rates:
            _rates_cache = new_rates
            _cache_timestamp = time.time()
            return new_rates
            
    except Exception as e:
        logger.error(f"Ошибка парсинга: {e}")
    
    return _rates_cache

def convert_currency(amount: float, from_curr: str, to_curr: str) -> Optional[Dict]:
    rates = fetch_kasikornbank_rates()
    if not rates: return None

    from_curr, to_curr = from_curr.upper(), to_curr.upper()
    
    # Логика конвертации через THB
    try:
        # 1. Переводим из валюты А в баты (банк покупает у нас)
        if from_curr == 'THB':
            thb_amount = amount
        else:
            data = rates.get(from_curr)
            rate = data['buying_notes'] or data['buying_telex']
            thb_amount = amount * rate

        # 2. Переводим из батов в валюту Б (банк продает нам)
        if to_curr == 'THB':
            result = thb_amount
            rate_info = f"1 {from_curr} = {thb_amount/amount:.2f} THB"
        else:
            data = rates.get(to_curr)
            rate = data['selling_notes'] or data['selling_tt']
            result = thb_amount / rate
            rate_info = f"Курс через THB (Sell: {rate})"

        return {
            'amount': amount, 'from': from_curr, 'to': to_curr,
            'result': round(result, 2), 'rate_info': rate_info
        }
    except:
        return None

# ==================== ХЕНДЛЕРЫ БОТА ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_html(
        "👋 <b>Привет! Я CANOPUS.</b>\n\n"
        "Я подскажу актуальный курс в <b>Kasikornbank (Тайланд)</b>.\n"
        "Используй /rates чтобы увидеть курсы или\n"
        "<code>/convert 100 USD THB</code> для расчета."
    )

async def rates_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_chat_action("typing")
    rates = fetch_kasikornbank_rates()
    
    if not rates:
        await update.message.reply_text("❌ Ошибка связи с банком. Попробуйте позже.")
        return

    msg = "📊 <b>Курсы Kasikornbank (Наличные)</b>\n\n"
    msg += "<code>Валюта | Купить | Продать</code>\n"
    msg += "<code>-----------------------</code>\n"
    
    for code in ['USD', 'EUR', 'GBP', 'JPY', 'RUB', 'CNY']:
        if code in rates:
            r = rates[code]
            bn = r['buying_notes'] or "—"
            sn = r['selling_notes'] or "—"
            msg += f"<code>{code:6} | {bn:6} | {sn:6}</code>\n"
            
    msg += "\nПосмотреть все: /help"
    await update.message.reply_html(msg)

async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3:
        await update.message.reply_text("Пример: /convert 100 USD THB")
        return

    try:
        amount = float(context.args[0])
        res = convert_currency(amount, context.args[1], context.args[2])
        if res:
            await update.message.reply_html(
                f"✅ <b>Результат:</b>\n"
                f"<code>{res['amount']} {res['from']} = {res['result']} {res['to']}</code>\n\n"
                f"ℹ️ {res['rate_info']}"
            )
        else:
            await update.message.reply_text("❌ Валюта не найдена.")
    except ValueError:
        await update.message.reply_text("Введите число.")

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("rates", rates_command))
    application.add_handler(CommandHandler("convert", convert_command))

    logger.info("Бот запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()
