import os
import re
from datetime import datetime
import requests
from bs4 import BeautifulSoup

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def parse_date(ev_tag, raw_text: str) -> datetime:
    """Extrae fecha para ordenar cronológicamente."""
    cal = ev_tag.select_one("a[href*='calendar.google.com']")
    if cal and cal.has_attr("href"):
        m = re.search(r"dates=(\d{4})(\d{2})(\d{2})", cal["href"])
        if m:
            return datetime(int(m[1]), int(m[2]), int(m[3]))

    t = ev_tag.select_one("time")
    if t and t.get("datetime"):
        try:
            return datetime.strptime(t["datetime"][:10], "%Y-%m-%d")
        except:
            pass

    m2 = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw_text)
    if m2:
        try:
            return datetime(int(m2[3]), int(m2[2]), int(m2[1]))
        except:
            pass

    return datetime(2099, 12, 31)

def extract_venue(ev_tag, event_url: str) -> str:
    """Extrae el lugar / recinto del concierto."""
    # 1. Intentar desde la tarjeta de la lista
    venue_tag = ev_tag.select_one(
        ".tribe-events-venue-details, .tribe-events-calendar-list__event-venue-title, "
        ".tribe-venue, .event-venue, .tribe-events-address"
    )
    if venue_tag and venue_tag.get_text(strip=True):
        return venue_tag.get_text(" ", strip=True)

    # 2. Si no viene en la lista, consultar la página del evento
    if event_url and event_url.startswith("http") and "factormetal.com/evento/" in event_url:
        try:
