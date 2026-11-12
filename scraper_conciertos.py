import os
import re
import sys
import json
import time
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

def log(msg):
    print(msg, flush=True)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
JSON_FILE = "eventos_registrados.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8"
}

MESES = {
    "ene": "Enero", "feb": "Febrero", "mar": "Marzo", "abr": "Abril",
    "may": "Mayo", "jun": "Junio", "jul": "Julio", "ago": "Agosto",
    "sep": "Septiembre", "oct": "Octubre", "nov": "Noviembre", "dic": "Diciembre"
}

def normalizar_url(url, base_url=None):
    if not url:
        return ""
    url = str(url).strip()
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/") or not url.startswith("http"):
        if base_url:
            from urllib.parse import urljoin
            url = urljoin(base_url, url)
    return url.rstrip("/")


def load_registered_events():
    if os.path.exists(JSON_FILE):
        try:
            with open(JSON_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, list):
                    return []

                historial = []
                vistos = set()
                for item in data:
                    if not isinstance(item, str):
                        continue
                    url = normalizar_url(item)
                    if not url or url in vistos:
                        continue
                    vistos.add(url)
                    historial.append(url)
                return historial
        except Exception as e:
            log(f"Aviso cargando JSON ({e}). Iniciando vacío.")
            return []
    return []

def save_registered_events(events):
    try:
        historial_limpio = []
        vistos = set()
        for event_url in events:
            url = normalizar_url(event_url)
            if not url or url in vistos:
                continue
            vistos.add(url)
            historial_limpio.append(url)

        with open(JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(historial_limpio, f, indent=2, ensure_ascii=False)
        log("Historial persistido correctamente en eventos_registrados.json")
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
            meta_date = soup.select_one("meta[property='event:start_time'], time, .tribe-event-date-start, .event-date")
            if meta_date:
                fecha = (meta_date.get_text(strip=True) or meta_date.get("datetime") or "").strip()
            
            return img_url, fecha
    except Exception as e:
        log(f"Aviso metadata {url}: {e}")
    return None, None

# 1. LEMMY PRODUCTIONS
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
        log(f"Lemmy Productions: {len(links)} enlaces candidatos")

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

# 2. PÁRAMO PRESENTA
def scrape_paramo_playwright(page):
    eventos = []
    url = "https://paramopresenta.com/"
    nombres_vistos = set()
    links_vistos = set()

    try:
        log("Abriendo Páramo Presenta (Home)...")
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        
        cards = soup.select("a[href*='/evento'], a[href*='tickets'], div[class*='event'] a, div[class*='card'] a")
        
        for a in cards:
            href = (a.get("href") or "").strip()
            clean_href = href.rstrip("/")
            if not clean_href or clean_href in ["https://paramopresenta.com", "https://www.paramopresenta.com"] or clean_href in links_vistos:
                continue
            if not clean_href.startswith("http"):
                clean_href = f"https://paramopresenta.com{clean_href}"

            texto = a.get_text(" ", strip=True)
            if not texto or len(texto) < 3:
                continue

            texto = re.sub(r"(?i)\b(ver evento|comprar|comprar boletas|entradas|tickets)\b", "", texto).strip(" -·")
            if not texto or texto.lower() in ["eventos", "ver más", "conciertos"]:
                continue

            key_artista = re.sub(r"[^a-zA-Z0-9]", "", texto.lower())
            if key_artista in nombres_vistos:
                continue

            nombres_vistos.add(key_artista)
            links_vistos.add(clean_href)

            img_card = a.select_one("img")
            img_url = img_card.get("src").strip() if (img_card and img_card.get("src")) else None

            eventos.append({
                "titulo": texto,
                "fecha": "Consultar fecha oficial",
                "lugar": "Bogotá",
                "link": clean_href,
                "img": img_url,
                "fuente": "Páramo Presenta"
            })
    except Exception as e:
        log(f"Error Páramo: {e}")

    log(f"Páramo Presenta: {len(eventos)} eventos únicos encontrados")
    return eventos

# 3. FACTOR METAL
def scrape_factormetal_playwright(page):
    eventos = []
    url = "https://www.factormetal.com/conciertos/"
    vistos = set()

    try:
        log("Abriendo Factor Metal (Agenda de Conciertos)...")
        page.goto(url, timeout=25000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")

        # La agenda actual presenta los eventos como bloques con H2 + fecha + ubicación.
        headings = soup.select("h2")
        log(f"Factor Metal: {len(headings)} títulos de eventos potenciales detectados")

        meses = (
            "enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
            "septiembre|octubre|noviembre|diciembre"
        )
        fecha_re = re.compile(
            rf"(\\d{{1,2}}\\s+(?:{meses})\\s*,\\s*\\d{{4}})",
            re.IGNORECASE
        )

        for h2 in headings:
            titulo = h2.get_text(" ", strip=True)
            if not titulo or "@" not in titulo or len(titulo) < 4:
                continue

            # Factor Metal es una agenda nacional; BogotáSuena solo debe
            # procesar eventos cuya ciudad sea Bogotá.
            ciudad_match = re.search(r"@\\s*([^@]+?)\\s*$", titulo)
            if not ciudad_match:
                continue

            ciudad = ciudad_match.group(1).strip()
            if ciudad.lower().replace(".", "") not in {"bogotá", "bogota"}:
                continue

            # Buscar el bloque mínimo que contiene este evento completo.
            contenedor = None
            padre = h2
            for _ in range(7):
                padre = padre.parent
                if not padre:
                    break
                texto_padre = padre.get_text(" ", strip=True)
                if (
                    fecha_re.search(texto_padre)
                    and "Agregar a Calendario" in texto_padre
                    and len(padre.find_all("h2")) == 1
                ):
                    contenedor = padre
                    break

            if not contenedor:
                continue

            texto = contenedor.get_text(" ", strip=True)
            fecha_match = fecha_re.search(texto)
            if not fecha_match:
                continue

            fecha = fecha_match.group(1)

            # Solo usar el venue si Factor Metal lo publica explícitamente.
            # Si no aparece, no inventamos uno.
            lugar = ""
            ubicacion_match = re.search(
                r"📍\\s*(.+?)(?=\\s+(?:Ver Mapa|Agregar a Calendario)\\b|$)",
                texto
            )
            if ubicacion_match:
                lugar = ubicacion_match.group(1).strip(" -")

            # La agenda no ofrece un enlace individual utilizable por evento.
            # Se conserva un fragmento estable para deduplicación/historial.
            slug_base = f"{fecha}-{titulo}"
            slug = re.sub(r"[^a-z0-9]+", "-", slug_base.lower()).strip("-")
            link = f"{url}#{slug}"

            if link in vistos:
                continue
            vistos.add(link)

            img_tag = contenedor.select_one("img")
            img_url = None
            if img_tag:
                img_url = (
                    img_tag.get("src")
                    or img_tag.get("data-src")
                    or ""
                ).strip() or None

            eventos.append({
                "titulo": titulo,
                "fecha": fecha,
                "lugar": lugar or "Bogotá",
                "link": link,
                "img": img_url,
                "fuente": "Factor Metal"
            })

    except Exception as e:
        log(f"Error Factor Metal: {e}")

    log(f"Factor Metal: {len(eventos)} conciertos encontrados")
    return eventos

# 4. TICKETSHOWS (ticketshows.co)
def scrape_ticketshows_playwright(page):
    eventos = []
    url = "https://ticketshows.co/"
    vistos = set()

    try:
        log("Abriendo Ticketshows en Chromium...")
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(3500)

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("a[href*='/evento/'], a[href*='/eventos/'], div[class*='event'] a, div[class*='card'] a")

        for a in cards:
            href = (a.get("href") or "").strip()
            clean_href = normalizar_url(href, url)
            if not clean_href or clean_href in vistos:
                continue

            path = clean_href.lower()
            if not any(x in path for x in ["/events/", "/evento/", "/eventos/"]):
                continue

            texto = a.get_text(" ", strip=True)
            if not texto or len(texto) < 4:
                continue

            texto = re.sub(r"(?i)\b(comprar|entradas|tickets|ver más|más info|boletas)\b", "", texto).strip(" -·")
            if not texto or texto.lower() in ["eventos", "inicio", "conciertos"]:
                continue

            vistos.add(clean_href)

            img_card = a.select_one("img")
            img_url = img_card.get("src").strip() if (img_card and img_card.get("src")) else None

            eventos.append({
                "titulo": texto,
                "fecha": "Consultar fecha en Ticketshows",
                "lugar": "Bogotá",
                "link": clean_href,
                "img": img_url,
                "fuente": "Ticketshows"
            })
    except Exception as e:
        log(f"Error Ticketshows: {e}")

    log(f"Ticketshows: {len(eventos)} eventos encontrados")
    return eventos

# DISPATCHER A TELEGRAM
def notificar_telegram(evento):
    titulo = evento.get("titulo") or "N/A"
    fecha = evento.get("fecha") or "N/A"
    lugar = evento.get("lugar") or "N/A"
    fuente = evento.get("fuente") or "N/A"
    link = evento.get("link") or "N/A"
    img_url = evento.get("img")

    if (not img_url or fecha in ["N/A", "Consultar fecha oficial", "Consultar fecha en Ticketshows"]) and link != "N/A":
        flyer_det, fecha_det = extraer_detalles_pagina(link)
        if not img_url and flyer_det:
            img_url = flyer_det
        if fecha in ["N/A", "Consultar fecha oficial", "Consultar fecha en Ticketshows"] and fecha_det:
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
                log(f"✅ Enviado con flyer: {titulo}")
                return True
            log(f"Aviso foto HTTP {resp.status_code}. Pasando a texto plano...")
        except Exception as e:
            log(f"Excepción en envío de foto: {e}. Pasando a texto plano...")

    try:
        url_api = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": texto,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        resp = requests.post(url_api, data=payload, timeout=10)
        if resp.status_code == 200:
            log(f"✅ Enviado en texto: {titulo}")
            return True
        log(f"❌ Error Telegram ({resp.status_code}): {resp.text}")
        return False
    except Exception as e:
        log(f"❌ Error de red en sendMessage: {e}")
        return False

def main():
    log("=== INICIANDO EJECUCIÓN DEL SCRAPER ===")
    
    if not BOT_TOKEN or not CHAT_ID:
        log("ERROR CRÍTICO: Credenciales de Telegram faltantes.")
        return

    historial = load_registered_events()
    log(f"Historial inicial: {len(historial)} URLs registradas.")

    todos_eventos = []
    
    # 1. Lemmy
    todos_eventos.extend(scrape_lemmy())

    # 2. Páramo, Factor Metal y Ticketshows en Chromium
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            
            todos_eventos.extend(scrape_paramo_playwright(page))
            todos_eventos.extend(scrape_factormetal_playwright(page))
            todos_eventos.extend(scrape_ticketshows_playwright(page))
            
            browser.close()
    except Exception as e:
        log(f"Error general en Playwright: {e}")

    log(f"Total eventos recopilados: {len(todos_eventos)}")

    novedades = []
    nombres_enviados = set()

    for ev in todos_eventos:
        link = (ev.get("link") or "").strip()
        titulo = (ev.get("titulo") or "").strip()
        key_tit = re.sub(r"[^a-zA-Z0-9]", "", titulo.lower())

        if link and link != "N/A" and link not in historial:
            if key_tit not in nombres_enviados:
                nombres_enviados.add(key_tit)
                novedades.append(ev)

    log(f"Novedades reales a despachar: {len(novedades)}")

    if not novedades:
        log("Todo al día. No se envían notificaciones.")
        return

    enviados_ok = 0
    for n in novedades:
        ok = notificar_telegram(n)
        if ok:
            historial.append(n["link"].strip())
            enviados_ok += 1
            time.sleep(2.0)
        else:
            log(f"Fallo al entregar '{n.get('titulo')}'. Quedará pendiente para reintentar.")

    log(f"Total notificados con éxito: {enviados_ok}")
    save_registered_events(historial)
    log("=== FIN DE LA EJECUCIÓN ===")

if __name__ == "__main__":
    main()
