import os
import re
import sys
import json
import time
from urllib.parse import urljoin, urlparse
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
            url = urljoin(base_url, url)
    return url.rstrip("/")


def normalizar_historial_url(url):
    if not url:
        return ""
    url = str(url).strip()
    if url.startswith("/"):
        return urljoin("https://factormetal.com", url)
    if url.startswith("//"):
        return "https:" + url
    return url.rstrip("/")


def normalizar_titulo(texto):
    if not texto:
        return ""
    texto = texto.lower()
    texto = re.sub(r"[^a-z0-9áéíóúüñ]+", " ", texto)
    return re.sub(r"\\s+", " ", texto).strip()


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
                url = normalizar_historial_url(item)
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
            url = normalizar_historial_url(event_url)
            if not url or url in vistos:
                continue
            vistos.add(url)
            historial_limpio.append(url)

        with open(JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(historial_limpio, f, indent=2, ensure_ascii=False)

        log("Historial persistido correctamente en eventos_registrados.json")
    except Exception as e:
        log(f"Error guardando JSON: {e}")
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
            # CRÍTICO: solo aceptar enlaces individuales de eventos.
            # Esto evita convertir noticias/artículos antiguos en conciertos.
            enlaces_evento = []
            for lk in p.find_all("a", href=True):
                href = normalizar_url(lk["href"].strip(), "https://factormetal.com")
                if not href:
                    continue
                if "/evento/" not in urlparse(href).path.lower():
                    continue
                enlaces_evento.append(lk)

            if not enlaces_evento:
                continue

            a_tag = None
            for lk in enlaces_evento:
                tx = lk.get_text(" ", strip=True)
                if len(tx) < 4:
                    continue
                bad_words = [
                    "ver mapa", "agregar a calendario", "google calendar", "ical",
                    "inicio", "contacto", "política", "privacidad", "facebook",
                    "twitter", "comentarios", "leer más", "compartir"
                ]
                if not any(bad in tx.lower() for bad in bad_words):
                    a_tag = lk
                    break

            if not a_tag:
                continue

            link = normalizar_url(a_tag["href"].strip(), "https://factormetal.com")
            if not link or link in vistos:
                continue

            titulo = a_tag.get_text(" ", strip=True)
            if not titulo:
                continue
            vistos.add(link)

            time_tag = p.select_one("time, .entry-date, .published, span.date")
            fecha = "N/A"
            if time_tag:
                fecha = time_tag.get_text(strip=True)
            else:
                m_f = re.search(
                    r"(\\d{1,2}\\s+de\\s+[a-zA-Z]+\\s+de\\s+\\d{4}|\\d{1,2}\\s+[a-zA-Z]{3,9}\\s+\\d{4})",
                    p.get_text(" ", strip=True)
                )
                if m_f:
                    fecha = m_f.group(1)

            img_tag = p.select_one("img")
            img_url = None
            if img_tag and img_tag.get("src"):
                img_url = normalizar_url(img_tag["src"].strip(), link)

            eventos.append({
                "titulo": titulo,
                "fecha": fecha,
                "lugar": "Bogotá",
                "link": link,
                "img": img_url,
                "fuente": "Factor Metal"
            })

    except Exception as e:
        log(f"Error Factor Metal: {e}")

    log(f"Factor Metal: {len(eventos)} conciertos encontrados")
    return eventos
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
        cards = soup.select(
            "a[href*='/evento/'], a[href*='/eventos/'], "
            "div[class*='event'] a, div[class*='card'] a"
        )

        for a in cards:
            href = (a.get("href") or "").strip()
            clean_href = normalizar_url(href, url)
            if not clean_href or clean_href in vistos:
                continue

            path = urlparse(clean_href).path.lower()
            if not any(x in path for x in ["/events/", "/evento/", "/eventos/"]):
                continue

            texto = a.get_text(" ", strip=True)
            if not texto or len(texto) < 4:
                continue

            texto = re.sub(
                r"(?i)\\b(comprar|entradas|tickets|ver más|más info|boletas)\\b",
                "",
                texto
            ).strip(" -·")

            if not texto or texto.lower() in ["eventos", "inicio", "conciertos"]:
                continue

            vistos.add(clean_href)

            img_card = a.select_one("img")
            img_url = None
            if img_card and img_card.get("src"):
                img_url = normalizar_url(img_card["src"].strip(), clean_href)

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

