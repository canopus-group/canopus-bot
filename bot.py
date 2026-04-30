#!/usr/bin/env python3
"""
CANOPUS Telegram Bot
A bot with /start, /help commands, echo functionality, and currency conversion.
Uses Kasikornbank exchange rates (Bank Buying Rate / Bank Selling Rate).
"""
import os
import logging
import cloudscraper
import sys
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Настройка логов, чтобы видеть ошибки ПРЯМО в консоли
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ТОКЕН
BOT_TOKEN = "8429560559:AAEzhVnJ87oW1pDKnwTZ9mVPTSQLn2H7ZAQ"

def get_kbank_rates():
    try:
        scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})
        url = "https://www.kasikornbank.com/en/rate/pages/foreign-exchange.aspx"
        response = scraper.get(url, timeout=15)
        
        if response.status_code != 200:
            logger.error(f"Банк вернул статус: {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, 'html.parser')
        rates = {}
        table = soup.find('table', id='table-exchangerate')
        
        if not table:
            logger.error("Таблица не найдена на странице")
            return None

        rows = table.find_all('tr')
        for row in rows[2:]:
            cols = row.find_all('td')
            if len(cols) >= 6:
                currency_text = cols[0].get_text(strip=True)
                currency = currency_text[:3]
                
                # Фильтр для USD (берем только основной курс)
                if currency == "USD" and "50-100" not in currency_text:
                    continue
                
                buy = cols[3].get_text(strip=True)
                sell = cols[5].get_text(strip=True)
                if buy and sell and buy != '-':
                    rates[currency] = {"buy": buy, "sell": sell}
        return rates
    except Exception as e:
        logger.error(f"Ошибка парсинга: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот онлайн! Напиши /rates")

async def rates_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Запрашиваю данные у банка...")
    data = get_kbank_rates()
    
    if not data:
        await update.message.reply_text("❌ Ошибка связи с банком. Попробуй позже.")
        return

    text = "📊 **Курсы K-BANK (Тайланд):**\n\n"
    for curr in ['USD', 'EUR', 'GBP', 'JPY', 'CNY']:
        if curr in data:
            text += f"🔹 **{curr}**: {data[curr]['buy']} ➡ {data[curr]['sell']}\n"
    
    await update.message.reply_text(text, parse_mode="Markdown")

def main():
    try:
        # Проверка токена
        if ":" not in BOT_TOKEN:
            print("ОШИБКА: Токен бота выглядит неправильно!")
            return

        app = Application.builder().token(BOT_TOKEN).build()

        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("rates", rates_cmd))

        print("🚀 БОТ ЗАПУЩЕН!")
        print("Напиши /start в телеграме.")
        
        # Запуск
        app.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        print(f"💥 КРИТИЧЕСКАЯ ОШИБКА: {e}")

if __name__ == '__main__':
    main()
