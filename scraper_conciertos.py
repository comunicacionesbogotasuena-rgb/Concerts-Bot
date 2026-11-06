import os
import re
import json
import time
import requests
from bs4 import BeautifulSoup

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
JSON_FILE = "eventos_registrados.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"
}

MESES = {
    "ene": "Enero", "feb": "Febrero", "mar": "Marzo", "abr": "Abril",
    "may": "Mayo", "jun": "Junio", "jul": "Julio", "ago": "Agosto",
    "sep": "Septiembre", "oct": "Octubre", "nov": "Noviembre", "dic": "Diciembre"
}

def load_registered_events():
    if os.path.exists(JSON_FILE):
        try:
            with open(JSON_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception as e:
            print(f"Aviso al cargar JSON ({e}). Iniciando vacio.")
            return []
    return []

def save_registered_events(events):
    try:
        with open(JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=2, ensure_ascii=False)
        print("Historial guardado en eventos_registrados.json")
    except Exception as e:
        print(f"Error guardando JSON: {e}")

def extraer_detalles_pagina(url):
    if not url or url == "N/A":
        return None, None
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        r.encoding = "utf-8"
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            img_url = None
            og_img = soup.select_one("meta[property='og:image'], meta[name='twitter:image']")
            if og_img and og_img.get("content"):
                img_url = og_img["content"].strip()
            else:
                img_tag = soup.select_one(".event-image img, .tribe-events-event-image img, .wp-post-image, article img")
                if img_tag and img_tag.get("src"):
                    img_url = img_tag["src"].strip()

            fecha = None
            meta_date = soup.select_one("meta[property='event:start_time'], time")
            if meta_date:
                fecha = (meta_date.get_text(strip=True) or meta_date.get("datetime") or "").strip()
            
            return img_url, fecha
    except Exception as e:
        print(f"Aviso metadata {url}: {e}")
    return None, None

def scrape_lemmy():
    eventos = []
    url = "https://www.lemmyprods.com/eventos"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.encoding = "utf-8"
        if r.status_code != 200:
            return eventos

        soup = BeautifulSoup(r.text, "html.parser")
        links = soup.select("a[href*='/eventos/']")
        print(f"Lemmy Productions: {len(links)} enlaces encontrados")

        vistos = set()
        for a in links:
            href = (a.get("href") or "").strip()
            clean_href = href.rstrip("/")
            if not clean_href or clean_href == "https://www.lemmyprods.com/eventos" or clean_href.endswith("/eventos"):
                continue
            if not clean_href.startswith("http"):
                clean_href = f"https://www.lemmyprods.com{clean_href}"

            if clean_href in vistos:
                continue
            vistos.add(clean_href)

            texto = a.get_text(" ", strip=True) or ""
            if texto.lower() in ["eventos", "bogotá", "bogota", "medellín", "medellin", "cali", "ver más", "comprar"]:
                continue

            fecha_match = re.search(r"(\b\d{1,2}\s+(?:ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SEP|OCT|NOV|DIC)\b)", texto, re.IGNORECASE)
            fecha = "N/A"
            if fecha_match:
                f_raw = fecha_match.group(1).upper()
                partes = f_raw.split()
                if len(partes) == 2:
                    dia = partes[0]
                    mes_nombre = MESES.get(partes[1].lower(), partes[1])
                    fecha = f"{dia} de {mes_nombre}"

            lugar = "Bogotá"
            for rec in ["Ace of Spades Club", "Ace of Spades", "Royal Center", "Auditorio CUN", "Teatro Astor Plaza", "Auditorio CEG", "Movistar Arena"]:
                if re.search(rf"\b{re.escape(rec)}\b", texto, re.IGNORECASE):
                    lugar = rec
                    break

            titulo = re.sub(r"^\d{1,2}\s+[A-Z]{3}\s*(?:En venta\s+)?", "", texto, flags=re.IGNORECASE)
            titulo = re.sub(r"(?:en Bogotá|Bogotá D\.C\.|·\s*Bogotá.*|\d{1,2}:\d{2}\s*(?:a\.\s*m\.|p\.\s*m\.).*)", "", titulo, flags=re.IGNORECASE).strip(" -·")
            if not titulo or len(titulo) < 3:
                continue

            img_card = a.select_one("img")
            img_url = img_card.get("src").strip() if (img_card and img_card.get("src")) else None

            eventos.append({
                "titulo": titulo,
                "fecha": fecha,
                "lugar": lugar,
                "link": clean_href,
                "img": img_url,
                "fuente": "Lemmy Productions"
            })
    except Exception as e:
        print(f"Error procesando Lemmy: {e}")
    return eventos

def scrape_paramo():
    eventos = []
    url = "https://www.paramopresenta.com/eventos"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.encoding = "utf-8"
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            cards = soup.select("a[href*='/eventos/'], a[href*='paramopresenta.com/evento/']")
            vistos = set()
            for a in cards:
                href = (a.get("href") or "").strip()
                clean_href = href.rstrip("/")
                if not clean_href or clean_href.endswith("/eventos"):
                    continue
                if not clean_href.startswith("http"):
                    clean_href = f"https://www.paramopresenta.com{clean_href}"

                if clean_href in vistos:
                    continue
                vistos.add(clean_href)

                t = a.get_text(" ", strip=True) or ""
                if not t or len(t) < 3 or t.lower() in ["eventos", "ver más", "comprar boletas"]:
                    continue

                img_card = a.select_one("img")
                img_url = img_card.get("src").strip() if (img_card and img_card.get("src")) else None

                eventos.append({
                    "titulo": t,
                    "fecha": "N/A",
                    "lugar": "Bogotá",
                    "link": clean_href,
                    "img": img_url,
                    "fuente": "Páramo Presenta"
                })
        print(f"Páramo Presenta: {len(eventos)} eventos encontrados")
    except Exception as e:
        print(f"Error procesando Páramo: {e}")
    return eventos

def scrape_factormetal():
    eventos = []
    urls = ["https://www.factormetal.com/conciertos/", "https://www.factormetal.com/eventos/"]
    vistos = set()

    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=12)
            r.encoding = "utf-8"
            if r.status_code != 200:
                continue

            soup = BeautifulSoup(r.text, "html.parser")
            items = soup.select(".type-tribe_events, article, .event-item, .post")
            for it in items:
                a_tag = it.select_one("a[href*='/concierto/'], a[href*='/evento/'], h2 a, h3 a")
                if not a_tag:
                    continue
                link = (a_tag.get("href") or "").strip()
                if not link or link in vistos:
                    continue
                vistos.add(link)

                t_tag = it.select_one("h2, h3, .tribe-events-list-event-title")
                titulo = t_tag.get_text(strip=True) if t_tag else a_tag.get_text(strip=True)
                if not titulo or len(titulo) < 3:
                    continue

                time_tag = it.select_one(".tribe-event-date-start, time, .date")
                fecha = time_tag.get_text(strip=True) if time_tag else "N/A"
                
                img_tag = it.select_one("img")
                img_url = img_tag.get("src").strip() if (img_tag and img_tag.get("src")) else None

                eventos.append({
                    "titulo": titulo,
                    "fecha": fecha,
                    "lugar": "Bogotá",
                    "link": link,
                    "img": img_url,
                    "fuente": "Factor Metal"
                })
            if eventos:
                break
        except Exception as e:
            print(f"Error procesando Factor Metal en {url}: {e}")

    print(f"Factor Metal: {len(eventos)} eventos encontrados")
    return eventos

def notificar_telegram(evento):
    titulo = evento.get("titulo") or "N/A"
    fecha = evento.get("fecha") or "N/A"
    lugar = evento.get("lugar") or "N/A"
    fuente = evento.get("fuente") or "N/A"
    link = evento.get("link") or "N/A"
    img_url = evento.get("img")

    if (not img_url or fecha == "N/A") and link != "N/A":
        flyer_det, fecha_det = extraer_detalles_pagina(link)
        if not img_url and flyer_det:
            img_url = flyer_det
        if fecha == "N/A" and fecha_det:
            fecha = fecha_det

    texto = (
        f"⚡ <b>NUEVO CONCIERTO DETECTADO</b>\n\n"
        f"🎸 <b>Evento:</b> {titulo}\n"
        f"📅 <b>Fecha:</b> {fecha}\n"
        f"📍 <b>Lugar:</b> {lugar}\n"
        f"🏛️ <b>Organiza / Fuente:</b> {fuente}\n\n"
        f"🎟️ <b>Boletería / Info:</b> {link}"
    )

    if img_url:
        try:
            url_api = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
            payload = {
                "chat_id": CHAT_ID,
                "photo": img_url,
                "caption": texto,
                "parse_mode": "HTML"
            }
            resp = requests.post(url_api, data=payload, timeout=12)
            if resp.status_code == 200:
                return True
        except Exception as e:
            print(f"Aviso sendPhoto: {e}. Intentando texto simple...")

    try:
        url_api = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": texto,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        resp = requests.post(url_api, data=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"Error enviando mensaje a Telegram: {e}")
        return False

def main():
    if not BOT_TOKEN or not CHAT_ID:
        print("ERROR: Variables TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no configuradas.")
        return

    historial = load_registered_events()
    print(f"Historial actual: {len(historial)} URLs registradas.")

    todos_eventos = []
    todos_eventos.extend(scrape_lemmy())
    todos_eventos.extend(scrape_paramo())
    todos_eventos.extend(scrape_factormetal())

    print(f"Total eventos escaneados: {len(todos_eventos)}")

    novedades = []
    for ev in todos_eventos:
        link = (ev.get("link") or "").strip()
        if link and link != "N/A" and link not in historial:
            novedades.append(ev)

    print(f"Novedades detectadas: {len(novedades)}")

    if not novedades:
        print("Todo al dia. No se envia notificacion.")
        return

    enviados_ok = 0
    for n in novedades:
        print(f"Procesando novedad: {n.get('titulo', 'N/A')}")
        ok = notificar_telegram(n)
        if ok:
            historial.append(n["link"].strip())
            enviados_ok += 1
            time.sleep(1.2)

    print(f"Se notificaron con exito {enviados_ok} conciertos nuevos.")
    save_
