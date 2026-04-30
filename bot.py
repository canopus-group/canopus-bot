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

# Настройка логирования для Railway (все ошибки будут видны во вкладке Logs)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Railway подтянет токен из раздела Variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")

def get_kbank_rates():
    """Функция парсинга курсов с защитой от блокировок"""
    try:
        # Используем cloudscraper для обхода базовой защиты сайта
        scraper = cloudscraper.create_scraper()
        url = "https://www.kasikornbank.com/en/rate/pages/foreign-exchange.aspx"
        response = scraper.get(url, timeout=15)
        
        if response.status_code != 200:
            logger.error(f"Ошибка сайта банка: статус {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, 'html.parser')
        rates = {}
        table = soup.find('table', id='table-exchangerate')
        
        if not table:
            logger.error("Не удалось найти таблицу курсов на странице")
            return None

        rows = table.find_all('tr')
        for row in rows[2:]:  # Пропускаем шапку таблицы
            cols = row.find_all('td')
            if len(cols) >= 6:
                raw_name = cols[0].get_text(strip=True)
                currency = raw_name[:3]
                
                # Фильтр для USD: берем только банкноты 50-100 (самый выгодный курс)
                if currency == "USD" and "50-100" not in raw_name:
                    continue
                
                buy = cols[3].get_text(strip=True)
                sell = cols[5].get_text(strip=True)
                
                if buy and sell and buy != '-':
                    rates[currency] = {"buy": buy, "sell": sell}
        
        return rates
    except Exception as e:
        logger.error(f"Критическая ошибка парсинга: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ответ на команду /start"""
    await update.message.reply_html(
        "🚀 <b>Бот CANOPUS запущен на Railway!</b>\n\n"
        "Напишите /rates, чтобы получить свежие курсы валют от Kasikornbank."
    )

async def rates_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ответ на команду /rates"""
    await update.message.reply_text("⏳ Запрашиваю данные у Kasikornbank...")
    
    data = get_kbank_rates()
    
    if not data:
        await update.message.reply_text(
            "❌ Не удалось получить данные.\n"
            "Скорее всего, сайт банка временно заблокировал серверный запрос."
        )
        return

    message = "🏦 <b>Курсы Kasikornbank (THB)</b>\n"
    message += "<i>Наличные (Bank Notes)</i>\n\n"
    
    # Список валют для вывода
    for code in ['USD', 'EUR', 'GBP', 'RUB', 'CNY']:
        if code in data:
            message += f"• <b>{code}</b>: {data[code]['buy']} | {data[code]['sell']}\n"
    
    message += "\n📌 <i>Курс за 1 единицу валюты</i>"
    await update.message.reply_html(message)

def main():
    """Запуск бота"""
    if not BOT_TOKEN:
        logger.error("ПЕРЕМЕННАЯ BOT_TOKEN НЕ НАЙДЕНА! Проверьте настройки Railway Variables.")
        return

    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()

    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("rates", rates_cmd))

    logger.info("Бот начинает опрос Telegram (Polling)...")
    
    # drop_pending_updates=True игнорирует сообщения, присланные, пока бот был выключен
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
