import json
import os
import re
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

KEYWORDS_METAL = [
    "metal", "thrash", "death metal", "black metal", "heavy metal", "power metal",
    "doom", "sludge", "grindcore", "metalcore", "nu metal", "groove metal",
    "slayer", "opeth", "slipknot", "dying fetus", "malevolent creation", "epica",
    "hammerfall", "testament", "dethklok", "angeles del infierno", "kraken"
]

KEYWORDS_ROCK = [
    "rock", "punk", "hardcore", "indie", "post-punk", "grunge",
    "alternative rock", "rock alternativo", "hard rock", "bunbury", "caifanes",
    "the strokes", "placebo", "los fabulosos cadillacs", "def leppard", "soda stereo",
    "aterciopelados", "conociendo rusia", "maná", "mana"
]

def classify_genre(title: str) -> str:
    text = title.lower()
    for kw in KEYWORDS_METAL:
        if re.search(r'\b' + re.escape(kw) + r'\b', text):
            return "METAL"
    for kw in KEYWORDS_ROCK:
        if re.search(r'\b' + re.escape(kw) + r'\b', text):
            return "ROCK"
    return "OTROS"

def send_telegram(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Faltan credenciales de Telegram.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    try:
        res = requests.post(url, json=payload, timeout=15)
        print("Telegram status:", res.status_code)
    except Exception as e:
        print(f"Error enviando a Telegram: {e}")

# 1. AGENDA ESPECIALIZADA ROCK & METAL EN COLOMBIA
def get_factor_metal():
    events = []
    try:
        url = "https://www.factormetal.com/conciertos/"
        res = requests.get(url, headers=HEADERS, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            for item in soup.find_all("li"):
                text = item.get_text(strip=True)
                a = item.find("a", href=True)
                if "@" in text and ("Bogotá" in text or "Colombia" in text):
                    title = text.split("@")[0].strip()
                    link = a["href"] if a else url
                    events.append({
                        "id": f"fm_{title}",
                        "source": "Factor Metal (Colombia)",
                        "title": title,
                        "url": link
                    })
    except Exception as e:
        print(f"Error Factor Metal: {e}")
    return events

# 2. TUBOLETA COLOMBIA
def get_tuboleta():
    events = []
    try:
        url = "https://tuboleta.com/es/categorias/conciertos"
        res = requests.get(url, headers=HEADERS, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                title = a.get_text(strip=True)
                if "/eventos/" in href and len(title) > 3:
                    full_url = href if href.startswith("http") else f"https://tuboleta.com{href}"
                    events.append({
                        "id": full_url,
                        "source": "Tuboleta",
                        "title": title,
                        "url": full_url
                    })
    except Exception as e:
        print(f"Error Tuboleta: {e}")
    return events

# 3. TICKETMASTER COLOMBIA
def get_ticketmaster():
    events = []
    try:
        url = "https://www.ticketmaster.co/page/CONCIERTOS"
        res = requests.get(url, headers=HEADERS, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                title = a.get_text(strip=True)
                if len(title) > 3 and not any(skip in href for skip in ["politica", "terminos", "faq", "contact"]):
                    if "ticketmaster.co" in href or href.startswith("/"):
                        full_url = href if href.startswith("http") else f"https://www.ticketmaster.co{href}"
                        events.append({
                            "id": full_url,
                            "source": "Ticketmaster CO",
                            "title": title,
                            "url": full_url
                        })
    except Exception as e:
        print(f"Error Ticketmaster: {e}")
    return events

# 4. PÁRAMO PRESENTA
def get_paramo_presenta():
    events = []
    try:
        url = "https://paramopresenta.com"
        res = requests.get(url, headers=HEADERS, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                title = a.get_text(strip=True)
                if "/evento/" in href and len(title) > 3:
                    events.append({
                        "id": href,
                        "source": "Páramo Presenta",
                        "title": title.split("\n")[0].strip(),
                        "url": href
                    })
    except Exception as e:
        print(f"Error Páramo: {e}")
    return events

# 5. MOVE CONCERTS COLOMBIA (usa Playwright para JS dinámico)
def get_move_concerts():
    events = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            page.goto("https://moveconcerts.com/co/", timeout=30000)
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(3000)

            for link in page.query_selector_all("a"):
                href = link.get_attribute("href") or ""
                text = link.inner_text().strip()
                if text and len(text) > 3:
                    if any(key in href.lower() for key in ["show", "concierto", "evento", "moveconcerts.com"]):
                        if not any(skip in href.lower() for skip in ["politica", "terminos", "contacto", "quienes-somos"]):
                            events.append({
                                "id": href,
                                "source": "Move Concerts",
                                "title": text.split("\n")[0].strip(),
                                "url": href
                            })
            browser.close()
    except Exception as e:
        print(f"Error Move Concerts: {e}")
    return events

def main():
    history_file = "eventos_registrados.json"
    known_ids = set()

    if os.path.exists(history_file):
        with open(history_file, "r", encoding="utf-8") as f:
            try:
                known_ids = set(json.load(f))
            except Exception:
                known_ids = set()

    raw_events = []
    raw_events.extend(get_factor_metal())
    raw_events.extend(get_tuboleta())
    raw_events.extend(get_ticketmaster())
    raw_events.extend(get_paramo_presenta())
    raw_events.extend(get_move_concerts())

    # Deduplicar por URL o nombre
    unique_events = {}
    for ev in raw_events:
        clean_url = ev["url"].strip().rstrip("/")
        if clean_url not in unique_events and len(ev["title"]) > 2:
            unique_events[clean_url] = ev

    # Filtrar solo novedades
    new_events = []
    for url, ev in unique_events.items():
        if url not in known_ids and ev["id"] not in known_ids:
            ev["category"] = classify_genre(ev["title"])
            new_events.append(ev)

    if not new_events:
        send_telegram("🤖 *Bot de Conciertos:* Se revisaron Tuboleta, Ticketmaster, Move, Páramo y Factor Metal. Todo al día, sin fechas nuevas.")
        return

    # Priorización: 1° Metal, 2° Rock, 3° Otros
    priority = {"METAL": 0, "ROCK": 1, "OTROS": 2}
    new_events.sort(key=lambda x: priority.get(x["category"], 2))

    messages = [f"🚨 *Nuevos Conciertos en Colombia* ({len(new_events)})\n-------------------------------------\n\n"]
    for ev in new_events:
        badge = "⚡ [OTROS]"
        if ev["category"] == "METAL":
            badge = "🔥 *[METAL]*"
        elif ev["category"] == "ROCK":
            badge = "🎸 *[ROCK]*"

        card = (
            f"{badge} *{ev['title']}*\n"
            f"🏢 *Plataforma:* {ev['source']}\n"
            f"🔗 [Ver Entradas / Info]({ev['url']})\n\n"
        )
        if len(messages[-1]) + len(card) > 3500:
            messages.append(card)
        else:
            messages[-1] += card

    for msg in messages:
        send_telegram(msg)

    # Guardar en historial
    for ev in new_events:
        known_ids.add(ev["url"].strip().rstrip("/"))
        known_ids.add(ev["id"])

    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(list(known_ids), f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
