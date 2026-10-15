import os
import re
import io
import time
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Paleta Bogotá Suena (Estilo Fanzine)
COLOR_ORANGE = (255, 92, 0)
COLOR_DARK = (15, 15, 15)
COLOR_WHITE = (255, 255, 255)
COLOR_GRAY = (180, 180, 180)

def parse_date(ev_tag, raw_text: str) -> datetime:
    """Extrae la fecha del evento para ordenar de menor a mayor."""
    cal_link = ev_tag.select_one("a[href*='calendar.google.com']")
    if cal_link and cal_link.has_attr("href"):
        match = re.search(r"dates=(\d{4})(\d{2})(\d{2})", cal_link["href"])
        if match:
            try:
                y, m, d = match.groups()
                return datetime(int(y), int(m), int(d))
            except Exception:
                pass

    time_tag = ev_tag.select_one("time")
    if time_tag and time_tag.get("
