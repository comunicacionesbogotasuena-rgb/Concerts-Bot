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
        log("Historial persistido correctamente.")
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
    url = "https://www.paramopresenta.com/eventos"
    try:
        log("Abriendo Páramo Presenta...")
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(3500)

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("a[href*='/eventos/'], a[href*='/evento/'], a[href*='paramopresenta.com/evento']")
        
        vistos = set()
        for a in cards:
            href = (a.get("href") or "").strip()
            clean_href = href.rstrip("/")
            if not clean_href or clean_href.endswith("/eventos") or clean_href in vistos:
                continue
            if not clean_href.startswith("http"):
                clean_href = f"https://www.paramopresenta.com{clean_href}"

            vistos.add(clean_href)
            texto = a.get_text(" ", strip=True)
            if not texto or len(texto) < 3:
                continue

            texto = re.sub(r"(?i)\b(ver evento|comprar|comprar boletas|entradas|tickets)\b", "", texto).strip(" -·")
            if not texto or texto.lower() in ["eventos", "ver más"]:
                continue

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
        log(f"Páramo Presenta: {len(eventos)} eventos encontrados")
    except Exception as e:
        log(f"Error Páramo: {e}")
    return eventos

# 3. FACTOR METAL (Lectura directa de notas de prensa de conciertos)
def scrape_factormetal_playwright(page):
    eventos = []
    url = "https://factormetal.com/category/conciertos/"
    vistos = set()
    try:
        log("Abriendo Factor Metal (Categoría Conciertos)...")
        page.goto(url, timeout=25000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        
        posts = soup.select("article, .post, .entry, div[class*='post-']")
        log(f"Factor Metal: {len(posts)} notas detectadas")

        for p in posts:
            a_tag = p.select_one("h2 a, h3 a, .entry-title a")
            if not a_tag:
                continue

            link = (a_tag.get("href") or "").strip()
            clean_link = link.rstrip("/")

            if not clean_link or clean_link in vistos or clean_link in ["https://factormetal.com/category/conciertos", "https://factormetal.com/conciertos"]:
                continue

            titulo = a_tag.get_text(" ", strip=True)
            if not titulo or len(titulo) < 6:
                continue
            if any(bad in titulo.lower() for bad in ["inicio", "contacto", "política", "privacidad", "factor d studio", "facebook", "twitter", "instagram"]):
                continue

            vistos.add(clean_link)

            time_tag = p.select_one("time, .entry-date, .published")
            fecha = time_tag.get_text(strip=True) if time_tag else "Consultar enlace"

            img_tag = p.select_one("img")
            img_url = img_tag.get("src").strip() if (img_tag and img_tag.get("src")) else None

            eventos.append({
                "titulo": titulo,
                "fecha": fecha,
                "lugar": "Bogotá",
                "link": clean_link,
                "img": img_url,
                "fuente": "Factor Metal"
            })

        log(f"Factor Metal: {len(eventos)} conciertos encontrados")
    except Exception as e:
        log(f"Error Factor Metal: {e}")
    return eventos

# 4. DISPATCHER A TELEGRAM
def notificar_telegram(evento):
    titulo = evento.get("titulo") or "N/A"
    fecha = evento.get("fecha") or "N/A"
    lugar = evento.get("lugar") or "N/A"
    fuente = evento.get("fuente") or "N/A"
    link = evento.get("link") or "N/A"
    img_url = evento.get("img")

    if (not img_url or fecha in ["N/A", "Consultar fecha oficial", "Consultar enlace"]) and link != "N/A":
        flyer_det, fecha_det = extraer_detalles_pagina(link)
        if not img_url and flyer_det:
            img_url = flyer_det
        if fecha in ["N/A", "Consultar fecha oficial", "Consultar enlace"] and fecha_det:
            fecha = fecha_det

    texto = (
        f"⚡ <b>NUEVO CONCIERTO DETECTADO</b>\n\n"
        f"🎸 <b>Evento:</b> {titulo}\n"
        f"📅 <b>Fecha:</b> {fecha}\n"
        f"📍 <b>Lugar:</b> {lugar}\n"
        f"🏛️ <b>Organiza / Fuente:</b> {fuente}\n\n"
        f"🎟️ <b>Boletería / Info:</b> {link}"
    )

    # Intento 1: Con foto
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
            log(f"Aviso sendPhoto HTTP {resp.status_code}. Pasando a texto plano...")
        except Exception as e:
            log(f"Excepción en foto: {e}. Pasando a texto plano...")

    # Intento 2: Con texto directo
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
        log(f"❌ Excepción en mensaje: {e}")
        return False

def main():
    log("=== INICIANDO EJECUCIÓN DEL SCRAPER ===")
    
    if not BOT_TOKEN or not CHAT_ID:
        log("ERROR CRÍTICO: Credenciales de Telegram faltantes.")
        return

    historial = load_registered_events()
    log(f"Historial cargado: {len(historial)} URLs registradas.")

    todos_eventos = []
    
    # Lemmy
    todos_eventos.extend(scrape_lemmy())

    # Páramo y Factor Metal
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            
            todos_eventos.extend(scrape_paramo_playwright(page))
            todos_eventos.extend(scrape_factormetal_playwright(page))
            
            browser.close()
    except Exception as e:
        log(f"Error en sesión Playwright: {e}")

    log(f"Total eventos recopilados: {len(todos_eventos)}")

    novedades = []
    for ev in todos_eventos:
        link = (ev.get("link") or "").strip()
        if link and link != "N/A" and link not in historial:
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
            # Pausa obligatoria para evitar límites de ráfaga
            time.sleep(2.0)
        else:
            log(f"Fallo al entregar '{n.get('titulo')}'. Queda pendiente para reintentar.")

    log(f"Total notificados con éxito: {enviados_ok}")
    save_registered_events(historial)
    log("=== FIN DE LA EJECUCIÓN ===")

if __name__ == "__main__":
    main()
