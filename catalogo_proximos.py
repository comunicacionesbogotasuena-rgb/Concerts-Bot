import os
import re
from datetime import datetime
import requests
from bs4 import BeautifulSoup

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def parse_date(texto):
    m_cal = re.search(r"dates=(\d{4})(\d{2})(\d{2})", texto)
    if m_cal:
        return datetime(int(m_cal.group(1)), int(m_cal.group(2)), int(m_cal.group(3)))

    m_iso = re.search(r"(\d{4})-(\d{2})-(\d{2})", texto)
    if m_iso:
        return datetime(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3)))

    m_lat = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", texto)
    if m_lat:
        return datetime(int(m_lat.group(3)), int(m_lat.group(2)), int(m_lat.group(1)))

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
        print(f"Status Factor Metal: {r.status_code}")
        if r.status_code != 200:
            return conciertos

        soup = BeautifulSoup(r.text, "html.parser")
        eventos = soup.select(".type-tribe_events, article, .event-item, .tribe-events-calendar-list__event-row")
        print(f"Bloques encontrados: {len(eventos)}")

        for ev in eventos:
            title_tag = ev.select_one("h2, h3, .tribe-events-list-event-title, .tribe-events-calendar-list__event-title")
            if not title_tag or not title_tag.get_text(strip=True):
                continue

            titulo = title_tag.get_text(strip=True)
            a_tag = title_tag.find("a") or ev.select_one("a[href*='factormetal.com/evento/']")
            link = a_tag["href"] if (a_tag and a_tag.has_attr("href")) else url

            raw_txt = ev.get_text(" ", strip=True)
            cal_a = ev.select_one("a[href*='calendar.google.com']")
            if cal_a and cal_a.has_attr("href"):
                raw_txt += " " + cal_a["href"]

            dt = parse_date(raw_txt)
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
        print("ERROR: Faltan credenciales de Telegram.")
        return

    conciertos = scrape_conciertos()
    print(f"Total conciertos procesados: {len(conciertos)}")

    if not conciertos:
        print("Enviando aviso de cartelera vacía a Telegram...")
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": "🎸 No hay conciertos registrados en Factor Metal en este momento."},
            timeout=10
        )
        return

    # Mensaje resumen
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": f"📋 <b>PRÓXIMOS CONCIERTOS EN BOGOTÁ</b>\nTotal confirmados: {len(conciertos)}",
            "parse_mode": "HTML"
        },
        timeout=10
    )

    # Envío individual por concierto
    for c in conciertos:
        fecha_str = c["dt"].strftime("%d/%m/%Y") if c["dt"].year != 2099 else "Fecha por confirmar"
        texto = (
            f"🤘 <b>Concierto:</b> {c['concierto']}\n"
            f"📅 <b>Fecha:</b> {fecha_str}\n"
            f"📍 <b>Lugar:</b> {c['lugar']}"
        )
        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={
                "chat_id": CHAT_ID,
                "text": texto,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            },
            timeout=10
        )
        print(f"Envío '{c['concierto']}': HTTP {resp.status_code}")

if __name__ == "__main__":
    main()
