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

def parse_date(ev_tag, raw_text: str) -> datetime:
    """Extrae la fecha del evento para ordenar de menor a mayor."""
    # 1. Enlaces a Google Calendar (dates=YYYYMMDD...)
    cal_link = ev_tag.select_one("a[href*='calendar.google.com']")
    if cal_link and cal_link.has_attr("href"):
        match = re.search(r"dates=(\d{4})(\d{2})(\d{2})", cal_link["href"])
        if match:
            try:
                y, m, d = match.groups()
                return datetime(int(y), int(m), int(d))
            except Exception:
                pass

    # 2. Atributo datetime en <time>
    time_tag = ev_tag.select_one("time")
    if time_tag and time_tag.get("datetime"):
        dt_str = time_tag["datetime"][:10]
        try:
            return datetime.strptime(dt_str, "%Y-%m-%d")
        except Exception:
            pass

    # 3. Formato numérico YYYY-MM-DD o DD/MM/YYYY
    match_iso = re.search(r"(\d{4})-(\d{2})-(\d{2})", raw_text)
    if match_iso:
        try:
            y, m, d = match_iso.groups()
            return datetime(int(y), int(m), int(d))
        except Exception:
            pass

    match_latam = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw_text)
    if match_latam:
        try:
            d, m, y = match_latam.groups()
            return datetime(int(y), int(m), int(d))
        except Exception:
            pass

    return datetime(2099, 12, 31)

def send_telegram_photo(caption: str, photo_url: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    data = {
        "chat_id": CHAT_ID,
        "caption": caption[:1024],
        "parse_mode": "HTML"
    }

    if photo_url and photo_url.startswith("http"):
        data["photo"] = photo_url
        try:
            resp = requests.post(url, data=data, timeout=15)
            if resp.status_code == 200:
                return
        except Exception:
            pass

    # Fallback si no carga la imagen
    text_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(text_url, data={"chat_id": CHAT_ID, "text": caption, "parse_mode": "HTML"}, timeout=15)

def scrape_factor_metal():
    url = "https://factormetal.com/eventos/"
    conciertos = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return conciertos

        soup = BeautifulSoup(resp.text, "html.parser")
        # Selector flexible compatible con la estructura de Factor Metal
        eventos = soup.select(".type-tribe_events, article, .event-item, .tribe-events-calendar-list__event-row")

        for ev in eventos:
            title_tag = ev.select_one("h2, h3, .tribe-events-list-event-title, .tribe-events-calendar-list__event-title")
            if not title_tag:
                continue

            titulo = title_tag.get_text(strip=True)
            if not titulo:
                continue

            # Buscar link en el título o en el primer enlace interno del bloque
            link = url
            enlace_tag = title_tag.find("a") or ev.select_one("a:not([href*='calendar.google.com']):not([href*='maps.google.com'])")
            if enlace_tag and enlace_tag.has_attr("href"):
                link = enlace_tag["href"]

            time_tag = ev.select_one("time, .tribe-event-date-start, .tribe-events-calendar-list__event-datetime")
            fecha_str = time_tag.get_text(strip=True) if time_tag else "Próximamente"
            dt_obj = parse_date(ev, ev.get_text(" ", strip=True))

            # Obtención de imagen
            img_tag = ev.select_one("img")
            img_src = ""
            if img_tag:
                img_src = (
                    img_tag.get("data-lazy-src")
                    or img_tag.get("data-src")
                    or img_tag.get("data-orig-file")
                    or img_tag.get("src")
                    or ""
                )
                if not img_src.startswith("http") and img_tag.get("srcset"):
                    img_src = img_tag["srcset"].split()[0]

            conciertos.append({
                "titulo": titulo,
                "fecha": fecha_str,
                "dt": dt_obj,
                "link": link,
                "imagen": img_src
            })
    except Exception as e:
        print(f"Error scraping Factor Metal: {e}")

    # Orden cronológico (los más cercanos primero)
    conciertos.sort(key=lambda x: x["dt"])
    return conciertos

def main():
    if not BOT_TOKEN or not CHAT_ID:
        print("Faltan credenciales de Telegram.")
        return

    print("Scrapeando cartelera...")
    eventos = scrape_factor_metal()

    if not eventos:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": "🎸 No hay eventos en cartelera actualmente."},
            timeout=10
        )
        return

    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": f"📅 <b>CARTELERA ROCK & METAL COLOMBIA</b>\n(Ordenada por fecha — {len(eventos)} conciertos confirmados):",
            "parse_mode": "HTML"
        },
        timeout=10
    )

    for c in eventos:
        fecha_display = c['fecha']
        if c['dt'].year != 2099:
            fecha_display = c['dt'].strftime("%d/%m/%Y")

        caption = (
            f"🤘 <b>{c['titulo']}</b>\n"
            f"📅 <b>Fecha:</b> {fecha_display}\n"
            f"🔗 <a href='{c['link']}'>Ver afiche y detalles del concierto</a>"
        )
        send_telegram_photo(caption, c["imagen"])

if __name__ == "__main__":
    main()
