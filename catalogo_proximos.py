import os
import requests
from bs4 import BeautifulSoup

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

def send_telegram_photo(caption: str, photo_url: str):
    """Envía la imagen promocional con los datos del concierto como pie de foto."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    data = {
        "chat_id": CHAT_ID,
        "caption": caption[:1024]
    }
    
    if photo_url and photo_url.startswith("http"):
        data["photo"] = photo_url
        try:
            resp = requests.post(url, data=data, timeout=15)
            if resp.status_code == 200:
                return
            print(f"Fallo al enviar imagen {photo_url}, status: {resp.status_code}")
        except Exception as e:
            print(f"Error enviando foto: {e}")

    # Si falla la imagen o no tiene URL válida, envía el texto
    text_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(text_url, data={"chat_id": CHAT_ID, "text": caption}, timeout=15)

def scrape_factor_metal():
    """Extrae conciertos vigentes y sus pósteres de Factor Metal."""
    url = "https://factormetal.com/eventos/"
    conciertos = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return conciertos
        
        soup = BeautifulSoup(resp.text, "html.parser")
        eventos = soup.select(".type-tribe_events, article, .event-item")
        
        for ev in eventos[:10]:
            title_tag = ev.select_one("h2, h3, .tribe-events-list-event-title")
            img_tag = ev.select_one("img")
            link_tag = ev.select_one("a")
            date_tag = ev.select_one(".tribe-event-date-start, .event-date, time")

            if not title_tag:
                continue

            titulo = title_tag.get_text(strip=True)
            link = link_tag["href"] if link_tag and link_tag.has_attr("href") else url
            fecha = date_tag.get_text(strip=True) if date_tag else "Próximamente"
            img_src = ""
            if img_tag:
                img_src = img_tag.get("src") or img_tag.get("data-src") or ""

            conciertos.append({
                "titulo": titulo,
                "fecha": fecha,
                "link": link,
                "imagen": img_src
            })
    except Exception as e:
        print(f"Error scraping Factor Metal: {e}")
    
    return conciertos

def main():
    if not BOT_TOKEN or not CHAT_ID:
        print("Faltan las credenciales de Telegram.")
        return

    print("Buscando conciertos vigentes...")
    eventos = scrape_factor_metal()

    if not eventos:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": "🎸 No se encontraron eventos programados con póster en este momento."},
            timeout=10
        )
        return

    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": f"📢 Cartelera de próximos conciertos confirmados ({len(eventos)} eventos):"},
        timeout=10
    )

    for c in eventos:
        caption = (
            f"🤘 {c['titulo']}\n"
            f"📅 Fecha: {c['fecha']}\n"
            f"🔗 Info / Boletas: {c['link']}"
        )
        send_telegram_photo(caption, c["imagen"])

if __name__ == "__main__":
    main()
