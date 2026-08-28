# flake8: noqa

import os
import time
import random
import logging
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
import requests

# Load environment variables
load_dotenv()

# Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
MIN_SLEEP_SECONDS = int(os.getenv("MIN_SLEEP_SECONDS", "300"))
MAX_SLEEP_SECONDS = int(os.getenv("MAX_SLEEP_SECONDS", "600"))

START_URL = "https://pasport.org.ua/solutions/e-queue"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def send_telegram_message(text):
    if not BOT_TOKEN or not CHAT_ID:
        logger.error("Telegram credentials not found in .env")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("Telegram notification sent successfully!")
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")


def random_delay():
    delay = random.uniform(1.5, 3.5)
    time.sleep(delay)


def get_sleep_time():
    return random.randint(MIN_SLEEP_SECONDS, MAX_SLEEP_SECONDS)


def main():
    with sync_playwright() as p:
        logger.info("Starting browser...")
        # Запускаем браузер только один раз
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()

        logger.info(f"Navigating to {START_URL}")
        try:
            page.goto(START_URL, timeout=60000)
        except Exception as e:
            logger.error(f"Failed to load start page: {e}")

        consecutive_errors = 0

        while True:
            try:
                logger.info("Starting check cycle...")

                # Если мы не на стартовой странице - возвращаемся
                if START_URL not in page.url:
                    page.goto(START_URL, timeout=30000)
                    random_delay()

                # Шаг 1: Выбор страны
                logger.info("Selecting country (Німеччина)...")
                page.locator("select#country").select_option(value="5")
                random_delay()

                # Шаг 2: Выбор центра
                logger.info("Selecting center (Кельн)...")
                page.locator("select#center").select_option(
                    value="https://cologne.pasport.org.ua/solutions/e-queue"
                )
                random_delay()

                # Шаг 3: Подтверждение
                logger.info("Clicking 'Продовжити'...")
                page.locator("button[type='submit']").click()
                random_delay()

                # Ждем результаты
                logger.info("Waiting for result...")

                failure_text = "Наразі всі місця зайняті"
                is_full = False

                try:
                    # Ждем появления текста отказа до 7 секунд
                    page.get_by_text(failure_text).wait_for(
                        state="visible", timeout=7000
                    )
                    is_full = True
                except Exception:
                    # Если текст не появился за таймаут - возможно, есть место или капча
                    is_full = False

                if is_full:
                    logger.info("Мест нет.")
                    sleep_time = get_sleep_time()
                    logger.info(
                        f"Sleeping for {sleep_time} seconds before next check..."
                    )
                    time.sleep(sleep_time)
                    # Перезагружаем страницу для следующего цикла
                    page.goto(START_URL, timeout=30000)
                else:
                    # Проверяем, не словили ли мы блок "Too many requests" или похожую ошибку
                    body_text = page.locator("body").inner_text().lower()
                    if "too many requests" in body_text or "429" in body_text:
                        raise Exception("Too many requests detected on page.")

                    logger.info("!!! МЕСТО НАЙДЕНО ИЛИ ПРОПУСТИЛО ДАЛЬШЕ !!!")
                    send_telegram_message(
                        "🔔 <b>ДП Документ</b>\nВозможно, появилось свободное место в Кельне!\nПроверьте браузер немедленно."
                    )

                    # Спим дольше после отправки уведомления, чтобы не спамить
                    logger.info(
                        "Sleeping for 10 minutes to avoid notification spam..."
                    )
                    time.sleep(600)
                    page.goto(START_URL, timeout=30000)

                # Сбрасываем счетчик ошибок при успешном проходе
                consecutive_errors = 0

            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Error during check cycle: {e}")

                # Адаптивное ожидание при ошибках, чтобы не забанили наглухо
                base_sleep = get_sleep_time()
                error_sleep = min(
                    base_sleep * consecutive_errors, 3600
                )  # Максимум 1 час
                logger.info(
                    f"Sleeping for {error_sleep} seconds due to error..."
                )
                time.sleep(error_sleep)

                try:
                    page.goto(START_URL, timeout=30000)
                except Exception as nav_e:
                    logger.error(f"Failed to reload page after error: {nav_e}")


if __name__ == "__main__":
    main()
