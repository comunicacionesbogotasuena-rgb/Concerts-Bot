import os
import re
import json
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
JSON_FILE = "eventos_registrados.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"
}

MESES = {
    "ene": "Ene", "feb": "Feb", "mar": "Mar", "abr": "Abr",
    "may": "May", "jun": "Jun", "jul": "Jul", "ago": "Ago",
    "sep": "Sep", "oct": "Oct", "nov": "Nov", "dic": "Dic"
}

def load_registered_events():
    if os.path.exists(JSON_FILE):
        try:
            with open(JSON_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception as e:
            print(f"Aviso al cargar JSON ({e}).")
            return []
    return []

def save_registered_events(events):
    try:
        with open(JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=2, ensure_ascii=False)
        print("Historial guardado exitosamente en JSON.")
    except Exception as e:
        print(f"Error guardando JSON: {e}")

# ==========================================
# SCRAPERS ORIGINALES
# ==========================================

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

            # Fecha
            fecha_match = re.search(r"(\b\d{1,2}\s+(?:ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SEP|OCT|NOV|DIC)\b)", texto, re.IGNORECASE)
            fecha = "N/A"
            if fecha_match:
                f_raw = fecha_match.group(1).upper().split()
                if len(f_raw) == 2:
                    fecha = f"{f_raw[0]} {MESES.get(f_raw[1].lower(), f_raw[1])}"

            # Lugar
            lugar = "Bogotá"
            for rec in ["Ace of Spades Club", "Ace of Spades", "Royal Center", "Auditorio CUN", "Teatro Astor Plaza", "Auditorio CEG", "Movistar Arena"]:
                if re.search(rf"\b{re.escape(rec)}\b", texto, re.IGNORECASE):
                    lugar = rec
                    break

            # Título
            titulo = re.sub(r"^\d{1,2}\s+[A-Z]{3}\s*(?:En venta\s+)?", "", texto, flags=re.IGNORECASE)
            titulo = re.sub(r"(?:en Bogotá|Bogotá D\.C\.|·\s*Bogotá.*|\d{1,2}:\d{2}\s*(?:a\.\s*m\.|p\.\s*m\.).*)", "", titulo, flags=re.IGNORECASE).strip(" -·")
            if not titulo or len(titulo) < 3:
                continue

            eventos.append({
                "titulo": titulo,
                "fecha": fecha,
                "lugar": lugar,
                "link": clean_href,
                "fuente": "Lemmy Prods"
            })
    except Exception as e:
        print(f"Error Lemmy: {e}")
    return eventos

def scrape_paramo():
    eventos = []
    url = "https://www.paramopresenta.com/eventos"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.encoding = "utf-8"
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            cards = soup.select("a[href*='/eventos/']")
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
                if not t or len(t) < 3 or t.lower() in ["eventos", "ver más"]:
                    continue

                eventos.append({
                    "titulo": t,
                    "fecha": "N/A",
                    "lugar": "Bogotá",
                    "link": clean_href,
                    
