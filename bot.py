#!/usr/bin/env python3
"""
CANOPUS Telegram Bot
A bot with /start, /help commands, echo functionality, and currency conversion.
Uses Kasikornbank exchange rates (Bank Buying Rate / Bank Selling Rate).
"""

import os
import logging
import cloudscraper
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Railway подтянет это из раздела Variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")

def get_kbank_rates():
    try:
        scraper = cloudscraper.create_scraper()
        url = "https://www.kasikornbank.com/en/rate/pages/foreign-exchange.aspx"
        response = scraper.get(url, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        rates = {}
        table = soup.find('table', id='table-exchangerate')
        if not table: return None

        for row in table.find_all('tr')[2:]:
            cols = row.find_all('td')
            if len(cols) >= 6:
                currency = cols[0].get_text(strip=True)[:3]
                if currency == "USD" and "50-100" not in cols[0].get_text(): continue
                buy = cols[3].get_text(strip=True)
                sell = cols[5].get_text(strip=True)
                if buy and sell and buy != '-':
                    rates[currency] = {"buy": buy, "sell": sell}
        return rates
    except Exception as e:
        logger.error(f"Error fetching rates: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот на Railway запущен! Команда: /rates")

async def rates_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_kbank_rates()
    if not data:
        await update.message.reply_text("❌ Ошибка связи с банком.")
        return
    text = "📊 Курсы:\n"
    for c in ['USD', 'EUR', 'GBP']:
        if c in data:
            text += f"{c}: {data[c]['buy']} / {data[c]['sell']}\n"
    await update.message.reply_text(text)

def main():
    if not BOT_TOKEN:
        logger.error("No BOT_TOKEN found in environment variables!")
        return

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("rates", rates_cmd))

    logger.info("Starting bot...")
    # Railway требует, чтобы бот работал постоянно
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
