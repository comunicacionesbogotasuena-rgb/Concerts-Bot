import os
import re
from datetime import datetime
import requests
from bs4 import BeautifulSoup

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
HEADERS = {"User-Agent": "Mozilla/5.0"}

def parse_date(ev_tag, raw_text):
    cal = ev_tag.select_one("a[href*='calendar.google.com']")
    if cal and cal.has_attr("href"):
        m = re.search(r"dates=(\d{4})(\d{2})(\d{2})", cal["href"])
        if m:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    t = ev_tag.select_one("time")
    if t and t.get("datetime"):
        try:
            return datetime.strptime(t["datetime"][:10], "%Y-%m-%d")
        except Exception:
            pass

    m2 = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw_text)
    if m2:
        try:
            return datetime(int(m2.group(3)), int(m2.group(2)), int(m2.group(1)))
        except Exception:
            pass

    return datetime(2099, 12, 31)

def extract_venue(ev_tag, link):
    venue_el = ev_tag.select_one(".tribe-events-venue-details, .tribe-events-calendar-list__event-venue-title, .tribe-venue, .event-venue, .tribe-events-address")
    if venue_el and venue_el.get_text(strip=True):
        return venue_el.get_text(" ", strip=True)

    if link and "factormetal.com/evento/" in link:
        try:
            r = requests.get(link, headers=HEADERS, timeout=6)
            if r.status_code == 200:
                s = BeautifulSoup(r.text, "html.parser")
                v = s.select_one(".tribe-events-venue-details, .tribe-venue-link, .tribe-events-single-event-meta .tribe-venue")
                if v and v.get_text(strip=True):
                    return v.get_text(" ", strip=True)
        except Exception:
            pass

    return "Bogotá (Por confirmar recinto)"

def scrape_conciertos():
    url = "https://factormetal.com/eventos/"
    conciertos = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return conciertos
        soup = BeautifulSoup(r.text, "html.parser")
        eventos = soup.select(".type-tribe_events, article, .event-item, .tribe-events-calendar-list__event-row")

        for ev in eventos:
            title_tag = ev.select_one("h2, h3, .tribe-events-list-event-title, .tribe-events-calendar-list__event-title")
            if not title_tag or not title_tag.get_text(strip=True):
                continue
            titulo = title_tag.get_text(strip=True)
            a_tag = title_tag.find("a") or ev.select_one("a[href*='factormetal.com/evento/']")
            link = a_tag["href"] if (a_tag and a_tag.has_attr("href")) else url
            dt = parse_date(ev, ev.get_text(" ", strip=True))
            lugar = extract_venue(ev, link)

            conciertos.append({
                "concierto": titulo,
                "dt": dt,
                "lugar": lugar
            })
    except Exception as e:
        print(f"Error scraping: {e}")

    conciertos.sort(key=lambda x: x["dt"])
    return conciertos

def main():
    if not BOT_TOKEN or not CHAT_ID:
        print("Faltan variables TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID")
        return

    eventos = scrape_conciertos()
    if not eventos:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": "No se encontraron conciertos programados en Bogotá."},
            timeout=10
        )
        return

    # Mensaje resumen
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": f"📋 <b>PRÓXIMOS CONCIERTOS EN BOGOTÁ</b>\nTotal: {len(eventos)}",
            "parse_mode": "HTML"
        },
        timeout=10
    )

    # Envío de cada concierto
    for ev in eventos:
        fecha_str = ev["dt"].strftime("%d/%m/%Y") if ev["dt"].year != 2099 else "Fecha por confirmar"
        
