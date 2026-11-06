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
    "sep": "Septiembre", "oct": "Octubre", "nov": "Noviembre", "dic": "Diciembre",
    "jan": "Enero", "apr": "Abril", "aug": "Agosto", "dec": "Diciembre"
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
            meta_date = soup.select_one("meta[property='event:start_time'], time, .tribe-event-date-start, .event-date")
            if meta_date:
                fecha = (meta_date.get_text(strip=True) or meta_date.get("datetime") or "").strip()
            
            return img_url, fecha
    except Exception as e:
        log(f"Aviso metadata {url}: {e}")
    return None, None

# 1. LEMMY PRODUCTIONS (Impecable)
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
        log(f"Error Lemmy: {e}")
    return eventos

# 2. PÁRAMO PRESENTA (Sin repeticiones y con extracción de fecha)
def scrape_paramo_playwright(page):
    eventos = []
    url = "https://www.paramopresenta.com/eventos"
    titulos_vistos = set()
    links_vistos = set()

    try:
        log("Abriendo Páramo Presenta (/eventos)...")
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        
        # En Páramo cada concierto es un bloque card o enlace con /evento/
        cards = soup.select("a[href*='/evento/'], a[href*='paramopresenta.com/evento/']")
        
        for a in cards:
            href = (a.get("href") or "").strip()
            clean_href = href.rstrip("/")
            if not clean_href or clean_href.endswith("/eventos") or clean_href in links_vistos:
                continue
            if not clean_href.startswith("http"):
                clean_href = f"https://www.paramopresenta.com{clean_href}"

            # Extraer todo el texto dentro de la tarjeta
            texto_completo = a.get_text("\n", strip=True)
            lineas = [l.strip() for l in texto_completo.split("\n") if l.strip()]
            
            if not lineas:
                continue

            # El título suele ser la primera línea relevante
            titulo = lineas[0]
            titulo = re.sub(r"(?i)\b(ver evento|comprar|comprar boletas|entradas|tickets)\b", "", titulo).strip(" -·")
            if not titulo or len(titulo) < 3 or titulo.lower() in ["eventos", "ver más", "conciertos"]:
                continue

            # Normalizar para deduplicar shows idénticos
            key_tit = re.sub(r"[^a-zA-Z0-9]", "", titulo.lower())
            if key_tit in titulos_vistos:
                continue

            titulos_vistos.add(key_tit)
            links_vistos.add(clean_href)

            # Intentar buscar fecha dentro del texto de la card
            fecha = "Bogotá (Ver enlace oficial)"
            for linea in lineas[1:]:
                if re.search(r"\b(\d{1,2}\s+de\s+[a-z]+|\d{1,2}\s+[a-z]{3}|\d{1,2}/\d{1,2})\b", linea, re.IGNORECASE):
                    fecha = linea
                    break

            img_card = a.select_one("img")
            img_url = img_card.get("src").strip() if (img_card and img_card.get("src")) else None

            eventos.append({
                "titulo": titulo,
                "fecha": fecha,
                "lugar": "Bogotá",
                "link": clean_href,
                "img": img_url,
                "fuente": "Páramo Presenta"
            })
    except Exception as e:
        log(f"Error Páramo: {e}")

    log(f"Páramo Presenta: {len(eventos)} eventos únicos encontrados")
    return eventos

# 3. FACTOR METAL (Con fecha real extraída del artículo)
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
            # Buscar el enlace del título en h1, h2, h3 o entry-title
            a_tag = p.select_one("h2 a, h3 a, h1 a, .entry-title a, a[rel='bookmark']")
            if not a_tag:
                continue

            link = (a_tag.get("href") or "").strip().rstrip("/")
            if not link or link in vistos or "category/conciertos" in link:
                continue

            titulo = a_tag.get_text(" ", strip=True)
            if not titulo or len(titulo) < 6:
                continue

            # Descartar botones y widgets
            bad_words = ["ver mapa", "agregar a calendario", "google calendar", "inicio", "facebook", "twitter", "contacto"]
            if any(bad in titulo.lower() for bad in bad_words):
                continue

            vistos.add(link)

            # Extraer fecha real de WordPress
            time_tag = p.select_one("time, .entry-date, .published, span.date")
            fecha = "N/A"
            if time_tag:
                fecha = time_tag.get_text(strip=True)
            else:
                # Buscar patrón de fecha en el texto del post
                text_post = p.get_text(" ", strip=True)
                f_match = re.search(r"(\d{1,2}\s+de\s+[a-zA-Z]+\s+de\s+\d{4}|\d{1,2}\s+[a-zA-Z]{3,9}\s+\d{4})", text_post)
                if f_match:
                    fecha = f_match.group(1)

            img_tag = p.select_one("img")
            img_url = img_tag.get("src").strip() if (img_tag and img_tag.get("src")) else None

            eventos.append({
                "titulo": titulo,
                "fecha": fecha,
                "lugar": "Bogotá",
                "link": link,
                "img": img_url,
                "fuente": "Factor Metal"
            })

        log(f"Factor Metal: {len(eventos)} conciertos encontrados")
    except Exception as e:
        log(f"Error Factor Metal: {e}")
    return eventos

# 4. ENVÍO A TELEGRAM
def notificar_telegram(evento):
    titulo = evento.get("titulo") or "N/A"
    fecha = evento.get("fecha") or "N/A"
    lugar = evento.get("lugar") or "N/A"
    fuente = evento.get("fuente") or "N/A"
    link = evento.get("link") or "N/A"
    img_url = evento.get("img")

    # Si la fecha o el flyer vienen vacíos, intentamos raspar la URL interna del evento
    if (not img_url or fecha in ["N/A", "Bogotá (Ver enlace oficial)"]) and link != "N/A":
        flyer_det, fecha_det = extraer_detalles_pagina(link)
        if not img_url and flyer_det:
            img_url = flyer_det
        if fecha in ["N/A", "Bogotá (Ver enlace oficial)"] and fecha_det:
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
            log(f"Excepción foto: {e}. Pasando a texto plano...")

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
        log(f"❌ Excepción mensaje: {e}")
        return False

def main():
    log("=== INICIANDO EJECUCIÓN DEL SCRAPER ===")
    
    if not BOT_TOKEN or not CHAT_ID:
        log("ERROR CRÍTICO: Credenciales de Telegram faltantes.")
        return

    historial = load_registered_events()
    log(f"Historial cargado: {len(historial)} URLs registradas.")

    todos_eventos = []
    
    # 1. Lemmy
    todos_eventos.extend(scrape_lemmy())

    # 2. Páramo y Factor Metal
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

    # Filtro global estricto: evita repeticiones por URL y por Nombre del artista
    novedades = []
    nombres_enviados_en_esta_corrida = set()

    for ev in todos_eventos:
        link = (ev.get("link") or "").strip()
        titulo = (ev.get("titulo") or "").strip()
        key_tit = re.sub(r"[^a-zA-Z0-9]", "", titulo.lower())

        if link and link != "N/A" and link not in historial:
            if key_tit not in nombres_enviados_en_esta_corrida:
                nombres_enviados_en_esta_corrida.add(key_tit)
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
            log(f"Fallo al entregar '{n.get('titulo')}'. Queda pendiente para reintentar.")

    log(f"Total notificados con éxito: {enviados_ok}")
    save_registered_events(historial)
    log("=== FIN DE LA EJECUCIÓN ===")

if __name__ == "__main__":
    main()
