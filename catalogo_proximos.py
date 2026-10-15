import os
import re
import time
from datetime import datetime
import requests
from bs4 import BeautifulSoup

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def parse_date(ev_tag, raw_text: str) -> datetime:
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
    if time_tag and time_tag.get("datetime"):
        dt_str = time_tag["datetime"][:10]
        try:
            return datetime.strptime(dt_str, "%Y-%m-%d")
        except Exception:
            pass

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

def get_event_poster(event_url: str) -> str:
    """Entra a la página del evento para extraer el afiche oficial específico."""
    if not event_url or "factormetal.com/eventos/" == event_url:
        return ""
    try:
        resp = requests.get(event_url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            # Buscar la imagen principal dentro del artículo del evento
            img = soup.select_one(".tribe-events-event-image img, .tribe-events-single-event-description img, article img")
            if img:
                return (
                    img.get("data-lazy-src")
                    or img.get("data-src")
                    or img.get("data-orig-file")
                    or img.get("src")
                    or ""
                )
    except Exception:
        pass
    return ""

def send_telegram_photo(caption: str, photo_url: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    data = {
        "chat_id": CHAT_ID,
        "caption": caption[:1024],
        "parse_mode": "HTML"
    }

    if photo_url and photo_url.startswith("http") and "logo" not in photo_url.lower():
        data["photo"] = photo_url
        try:
            resp = requests.post(url, data=data, timeout=15)
            if resp.status_code == 200:
                return
        except Exception:
            pass

    # Si no hay imagen disponible, envía solo el texto deshabilitando previsualizaciones
    text_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": caption,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    requests.post(text_url, data=payload, timeout=15)

def scrape_factor_metal():
    url = "https://factormetal.com/eventos/"
    conciertos = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return conciertos

        soup = BeautifulSoup(resp.text, "html.parser")
        eventos = soup.select(".type-tribe_events, article, .event-item, .tribe-events-calendar-list__event-row")

        for ev in eventos:
            title_tag = ev.select_one("h2, h3, .tribe-events-list-event-title, .tribe-events-calendar-list__event-title")
            if not title_tag:
                continue

            titulo = title_tag.get_text(strip=True)
            if not titulo:
                continue

            link = url
            enlace_tag = title_tag.find("a") or ev.select_one("a:not([href*='calendar.google.com']):not([href*='maps.google.com'])")
            if enlace_tag and enlace_tag.has_attr("href"):
                link = enlace_tag["href"]

            time_tag = ev.select_one("time, .tribe-event-date-start, .tribe-events-calendar-list__event-datetime")
            fecha_str = time_tag.get_text(strip=True) if time_tag else "Próximamente"
            dt_obj = parse_date(ev, ev.get_text(" ", strip=True))

            conciertos.append({
                "titulo": titulo,
                "fecha": fecha_str,
                "dt": dt_obj,
                "link": link
            })
    except Exception as e:
        print(f"Error scraping Factor Metal: {e}")

    # Ordenar por fecha más próxima primero
    conciertos.sort(key=lambda x: x["dt"])
    return conciertos

def main():
    if not BOT_TOKEN or not CHAT_ID:
        print("Faltan credenciales.")
        return

    print("Obteniendo cartelera...")
    eventos = scrape_factor_metal()

    if not eventos:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": "🎸 No hay eventos en cartelera actualmente."},
            timeout=10
        )
        return

    # Limitar a los 15 más próximos para no saturar la API
    proximos = eventos[:15]

    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": f"📅 <b>CARTELERA CON AFICHES OFICIALES</b>\n(Top {len(proximos)} conciertos confirmados ordenados por fecha):",
            "parse_mode": "HTML"
        },
        timeout=10
    )

    for c in proximos:
        fecha_display = c['fecha']
        if c['dt'].year != 2099:
            fecha_display = c['dt'].strftime("%d/%m/%Y")

        # Extraer afiche individual
        afiche_url = get_event_poster(c["link"])
        time.sleep(0.5)

        caption = (
            f"🤘 <b>{c['titulo']}</b>\n"
            f"📅 <b>Fecha:</b> {fecha_display}\n"
            f"🔗 <a href='{c['link']}'>Ver detalles y boletas</a>"
        )
        send_telegram_photo(caption, afiche_url)

if __name__ == "__main__":
    main()
