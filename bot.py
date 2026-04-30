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

# Логи в консоль, чтобы видеть ошибки в реальном времени
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# СЮДА ВСТАВЬТЕ ВАШ ТОКЕН
BOT_TOKEN = "8429560559:AAEzhVnJ87oW1pDKnwTZ9mVPTSQLn2H7ZAQ"

def get_kbank_rates():
    try:
        scraper = cloudscraper.create_scraper()
        # Запрашиваем страницу банка
        response = scraper.get("https://www.kasikornbank.com/en/rate/pages/foreign-exchange.aspx", timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        rates = {}
        table = soup.find('table', id='table-exchangerate')
        if not table:
            return None

        for row in table.find_all('tr')[2:]:  # Пропускаем заголовки
            cols = row.find_all('td')
            if len(cols) >= 6:
                currency = cols[0].get_text(strip=True)[:3] # Берем код типа USD
                # Пропускаем мелкие купюры USD, берем только основной курс
                if currency == "USD" and "50-100" not in cols[0].get_text():
                    continue
                
                try:
                    buy = cols[3].get_text(strip=True)
                    sell = cols[5].get_text(strip=True)
                    rates[currency] = {"buy": buy, "sell": sell}
                except:
                    continue
        return rates
    except Exception as e:
        logger.error(f"Ошибка при получении данных: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Бот запущен! Напиши /rates чтобы получить курсы.")

async def rates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Запрашиваю данные у банка...")
    data = get_kbank_rates()
    
    if not data:
        await update.message.reply_text("❌ Не удалось получить курсы. Возможно, сайт банка временно недоступен.")
        return

    text = "📊 КУРСЫ В K-BANK:\n\n"
    # Выберем самые популярные
    for curr in ['USD', 'EUR', 'GBP', 'JPY', 'CNY']:
        if curr in data:
            text += f"▪️ {curr}: Покупка: {data[curr]['buy']} | Продажа: {data[curr]['sell']}\n"
    
    await update.message.reply_text(text)

def main():
    # Создаем приложение
    app = Application.builder().token(BOT_TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("rates", rates))

    print("Бот работает... Нажмите Ctrl+C для остановки.")
    app.run_polling()

if __name__ == '__main__':
    main()
