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

# Список локаций для поочередной проверки
LOCATIONS = [
    {
        "name": "Германия (Кельн)",
        "country_value": "5",
        "center_value": "https://cologne.pasport.org.ua/solutions/e-queue",
    },
    # {
    #     "name": "Бельгия (Кортрейк)",
    #     "country_value": "30",
    #     "center_value": "https://kortrijk.pasport.org.ua/solutions/e-queue",
    # },
]

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
    time.sleep(random.uniform(1.5, 3.5))


def get_sleep_time():
    return random.randint(MIN_SLEEP_SECONDS, MAX_SLEEP_SECONDS)


def main():
    with sync_playwright() as p:
        logger.info("Starting isolated Chrome with Anti-Bot flags...")

        user_data_dir = os.path.join(os.getcwd(), "browser_profile")

        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            user_agent=USER_AGENT,
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            viewport={"width": 1280, "height": 720},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-sandbox",
            ],
            ignore_default_args=["--enable-automation"],
        )

        page = context.pages[0] if context.pages else context.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        try:
            page.goto(START_URL, timeout=60000)
        except Exception as e:
            logger.error(f"Failed to load start page: {e}")

        consecutive_errors = 0
        location_index = 0  # Индекс текущей локации для карусели

        while True:
            try:
                # Берем одну локацию из списка по очереди
                loc = LOCATIONS[location_index]
                logger.info(f"--- Starting check cycle for: {loc['name']} ---")

                # Убеждаемся, что мы на стартовой странице
                if START_URL not in page.url:
                    page.goto(START_URL, timeout=30000)
                    random_delay()

                logger.info(f"[{loc['name']}] Selecting country...")
                page.locator("select#country").select_option(
                    value=loc["country_value"]
                )
                random_delay()

                logger.info(f"[{loc['name']}] Selecting center...")
                page.locator("select#center").select_option(
                    value=loc["center_value"]
                )
                random_delay()

                logger.info(f"[{loc['name']}] Clicking 'Продовжити'...")
                page.locator("button[type='submit']").click()
                random_delay()

                logger.info(f"[{loc['name']}] Waiting for result...")
                is_full = False
                try:
                    page.get_by_text("Наразі всі місця зайняті").wait_for(
                        state="visible", timeout=7000
                    )
                    is_full = True
                except:
                    pass

                if is_full:
                    logger.info(f"[{loc['name']}] Мест нет.")
                    # Успешная проверка (хоть мест и нет, но сайт ответил нормально), сбрасываем ошибки
                    consecutive_errors = 0
                else:
                    body_text = page.locator("body").inner_text().lower()
                    if "too many requests" in body_text or "429" in body_text:
                        raise Exception(
                            f"Too many requests detected while checking {loc['name']}."
                        )

                    logger.info(
                        f"!!! [{loc['name']}] МЕСТО НАЙДЕНО ИЛИ ПРОПУСТИЛО ДАЛЬШЕ !!!"
                    )
                    send_telegram_message(
                        f"🔔 <b>ДП Документ</b>\nВозможно, появилось свободное место:\n<b>{loc['name']}</b>\nПроверьте браузер немедленно!"
                    )

                    logger.info(
                        "Sleeping for 10 minutes to avoid notification spam..."
                    )
                    time.sleep(600)
                    consecutive_errors = 0

                # Переключаемся на следующую локацию для следующего цикла
                location_index = (location_index + 1) % len(LOCATIONS)

                # Спим перед следующим запросом (к другой локации)
                sleep_time = get_sleep_time()
                logger.info(
                    f"Check finished. Sleeping for {sleep_time} seconds before checking next location..."
                )
                time.sleep(sleep_time)

            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Error during check cycle: {e}")
                error_sleep = min(get_sleep_time() * consecutive_errors, 3600)
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
