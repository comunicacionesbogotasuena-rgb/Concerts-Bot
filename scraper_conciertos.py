import json
import os
import re
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

KEYWORDS_METAL = [
    "metal", "thrash", "death metal", "black metal", "heavy metal", "power metal",
    "doom", "sludge", "grindcore", "metalcore", "nu metal", "groove metal"
]
KEYWORDS_ROCK = [
    "rock", "punk", "hardcore", "indie rock", "post-punk", "grunge",
    "alternative rock", "rock alternativo", "hard rock", "rock en espanol",
    "rock en español", "psychedelic", "stoner", "shoegaze"
]

def classify_genre(title: str, hint: str = "") -> str:
    text = f"{title} {hint}".lower()
    for kw in KEYWORDS_METAL:
        if re.search(r'\b' + re.escape(kw) + r'\b', text):
            return "METAL"
    for kw in KEYWORDS_ROCK:
        if re.search(r'\b' + re.escape(kw) + r'\b', text):
            return "ROCK"
    return "OTROS"

def send_telegram(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Faltan credenciales de Telegram.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        print("Telegram status:", res.status_code)
    except Exception as e:
        print(f"Error Telegram: {e}")

def get_move_concerts():
    events = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            page.goto("https://moveconcerts.com/co/", timeout=30000)
            page.wait_for_load_state("networkidle")

            cards = page.query_selector_all(".event-card, .concierto-item, article")
            for card in cards:
                title_el = card.query_selector("h2, h3, .title")
                link_el = card.query_selector("a")
                date_el = card.query_selector(".date, time")

                if title_el and link_el:
                    title = title_el.inner_text().strip()
                    url = link_el.get_attribute("href") or ""
                    date = date_el.inner_text().strip() if date_el else "TBA"
                    events.append({
                        "id": url,
                        "source": "Move Concerts",
                        "title": title,
                        "date": date,
                        "url": url,
                        "hint": ""
                    })
            browser.close()
    except Exception as e:
        print(f"Error Move Concerts: {e}")
    return events

def get_paramo_presenta():
    events = []
    try:
        res = requests.get("https://paramopresenta.com", headers=HEADERS, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            for item in soup.select(".evento-card, .post-event, article"):
                title_el = item.select_one("h2, h3, .titulo")
                link_el = item.select_one("a")
                date_el = item.select_one(".fecha, time")
                if title_el and link_el:
                    events.append({
                        "id": link_el.get("href", ""),
                        "source": "Páramo Presenta",
                        "title": title_el.get_text(strip=True),
                        "date": date_el.get_text(strip=True) if date_el else "TBA",
                        "url": link_el.get("href", ""),
                        "hint": ""
                    })
    except Exception as e:
        print(f"Error Páramo: {e}")
    return events

def main():
    history_file = "eventos_registrados.json"
    known_ids = set()

    if os.path.exists(history_file):
        with open(history_file, "r", encoding="utf-8") as f:
            try:
                known_ids = set(json.load(f))
            except Exception:
                known_ids = set()

    events = []
    events.extend(get_move_concerts())
    events.extend(get_paramo_presenta())

    new_events = []
    for ev in events:
