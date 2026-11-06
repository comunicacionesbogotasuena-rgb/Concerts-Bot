import os
import re
import sys
import json
import time
import requests
from bs4 import BeautifulSoup

def log(msg):
    print(msg, flush=True)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
JSON_FILE = "eventos_registrados.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
    "Referer": "https://www.google.com/"
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
            log(f"Aviso cargando JSON ({e}). Iniciando vacío.")
            return []
    return []

def save_registered_events(events):
    try:
        with open(JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=2, ensure_ascii=False)
        log("Historial guardado en eventos_registrados.json")
    except Exception as e:
        log(f"Error guardando JSON: {e}")

def extraer_detalles_pagina(url):
    if not url or url == "N/A" or not url.startswith("http"):
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
        log(f"Aviso metadata {url}: {e}")
    return None, None

def scrape_lemmy():
    eventos = []
    url = "https://www.lemmyprods.com/eventos"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.encoding = "utf-8"
        if r.status_code != 200:
            log(f"Lemmy HTTP error: {r.status_code}")
            return eventos

        soup = BeautifulSoup(r.text, "html.parser")
        links = soup.select("a[href*='/eventos/']")
        log(f"Lemmy Productions: {len(links)} enlaces encontrados")

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
        log(f"Error procesando Lemmy: {e}")
    return eventos

def scrape_paramo():
    eventos = []
    # Usar la home de paramopresenta.com que dio 23 elementos en el diagnóstico
    url = "https://paramopresenta.com/"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.encoding = "utf-8"
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            cards = soup.select("a[href*='/evento'], a[href*='tickets'], div[class*='event'] a, div[class*='card'] a")
            vistos = set()

            for a in cards:
                href = (a.get("href") or "").strip()
                clean_href = href.rstrip("/")
                if not clean_href or clean_href in ["https://paramopresenta.com", "https://www.paramopresenta.com"]:
                    continue
                if not clean_href.startswith("http"):
                    clean_href = f"https://paramopresenta.com{clean_href}"

                if clean_href in vistos:
                    continue
                vistos.add(clean_href)

                texto = a.get_text(" ", strip=True) or ""
                if not texto or len(texto) < 3 or texto.lower() in ["eventos", "ver más", "comprar boletas", "conciertos"]:
                    continue

                img_card = a.select_one("img")
                img_url = img_card.get("src").strip() if (img_card and img_card.get("src")) else None

                eventos.append({
                    "titulo": texto,
                    "fecha": "Consultar enlace oficial",
                    "lugar": "Bogotá",
                    "link": clean_href,
                    "img": img_url,
                    "fuente": "Páramo Presenta"
                })
        log(f"Páramo Presenta: {len(eventos)} eventos encontrados")
    except Exception as e:
        log(f"Error procesando Páramo: {e}")
    return eventos

def scrape_factormetal():
    eventos = []
    url = "https://factormetal.com/conciertos/"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.encoding = "utf-8"
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            # Buscar todos los enlaces que no sean menús ni categorías
            links = soup.find_all("a", href=True)
            vistos = set()

            for a in links:
                href = a["href"].strip()
                clean_href = href.rstrip("/")
                # Filtrar enlaces reales a artículos de conciertos
                if not clean_href or clean_href in vistos:
                    continue
                if any(x in clean_href.lower() for x in ["/category/", "/tag/", "/author/", "/page/", "facebook.com", "instagram.com", "twitter.com", "youtube.com"]):
                    continue
                if not clean_href.startswith("http") or clean_href == "https://factormetal.com/conciertos":
                    continue

                texto = a.get_text(" ", strip=True)
                # Debe tener longitud de título de concierto
                if not texto or len(texto) < 5 or texto.lower() in ["internacional", "latinoamérica", "entrevistas", "reseñas conciertos", "reseñas de discos", "conciertos"]:
                    continue

                vistos.add(clean_href)

                # Buscar imagen
                img_card = a.select_one("img")
                img_url = img_card.get("src").strip() if (img_card and img_card.get("src")) else None

                eventos.append({
                    "titulo": texto,
                    "fecha": "N/A",
                    "lugar": "Bogotá",
                    "link": clean_href,
                    "img": img_url,
                    "fuente": "Factor Metal"
                })
        log(f"Factor Metal: {len(eventos)} eventos encontrados")
    except Exception as e:
        log(f"Error procesando Factor Metal: {e}")
    return eventos

def notificar_telegram(evento):
    titulo = evento.get("titulo") or "N/A"
    fecha = evento.get("fecha") or "N/A"
    lugar = evento.get("lugar") or "N/A"
    fuente = evento.get("fuente") or "N/A"
    link = evento.get("link") or "N/A"
    img_url = evento.get("img")

    if (not img_url or fecha in ["N/A", "Consultar enlace oficial"]) and link != "N/A":
        flyer_det, fecha_det = extraer_detalles_pagina(link)
        if not img_url and flyer_det:
            img_url = flyer_det
        if fecha in ["N/A", "Consultar enlace oficial"] and fecha_det:
            fecha = fecha_det

    texto = (
        f"⚡ <b>NUEVO CONCIERTO DETECTADO</b>\n\n"
        f"🎸 <b>Evento:</b> {titulo}\n"
        f"📅 <b>Fecha:</b> {fecha}\n"
        f"📍 <b>Lugar:</b> {lugar}\n"
        f"🏛️ <b>Organiza / Fuente:</b> {fuente}\n\n"
        f"🎟️ <b>Boletería / Info:</b> {link}"
    )

    if img_url and isinstance(img_url, str) and img_url.startswith("http"):
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
            log(f"sendPhoto status {resp.status_code}. Pasando a texto simple...")
        except Exception as e:
            log(f"Aviso sendPhoto: {e}. Pasando a texto simple...")

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
        log(f"Error enviando mensaje: {e}")
        return False

def main():
    log("=== INICIANDO EJECUCIÓN DEL SCRAPER ===")
    
    if not BOT_TOKEN or not CHAT_ID:
        log("ERROR: Credenciales de Telegram no configuradas.")
        return

    historial = load_registered_events()
    log(f"Historial cargado: {len(historial)} URLs registradas.")

    todos_eventos = []
    todos_eventos.extend(scrape_lemmy())
    todos_eventos.extend(scrape_paramo())
    todos_eventos.extend(scrape_factormetal())

    log(f"Total eventos recolectados en esta pasada: {len(todos_eventos)}")

    novedades = []
    for ev in todos_eventos:
        link = (ev.get("link") or "").strip()
        if link and link != "N/A" and link not in historial:
            novedades.append(ev)

    log(f"Novedades reales a notificar: {len(novedades)}")

    if not novedades:
        log("Todo al día. No se envía notificación.")
        return

    enviados_ok = 0
    for n in novedades:
        log(f"Enviando alerta a Telegram: {n.get('titulo', 'N/A')}")
        ok = notificar_telegram(n)
        if ok:
            historial.append(n["link"].strip())
            enviados_ok += 1
            time.sleep(1.2)

    log(f"Se notificaron con éxito {enviados_ok} conciertos nuevos.")
    save_registered_events(historial)
    log("=== FIN DE LA EJECUCIÓN ===")

if __name__ == "__main__":
    main()
