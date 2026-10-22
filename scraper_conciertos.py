
import json
import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

KEYWORDS_METAL = [
    "metal", "thrash", "death metal", "black metal", "heavy metal",
    "power metal", "doom", "sludge", "grindcore", "metalcore",
    "nu metal", "groove metal", "slayer", "opeth", "slipknot",
    "dying fetus", "malevolent creation", "epica", "hammerfall",
    "testament", "dethklok", "angeles del infierno", "kraken"
]

KEYWORDS_ROCK = [
    "rock", "punk", "hardcore", "indie", "post-punk", "grunge",
    "alternative rock", "rock alternativo", "hard rock", "bunbury",
    "caifanes", "the strokes", "placebo",
    "los fabulosos cadillacs", "def leppard", "soda stereo",
    "aterciopelados", "conociendo rusia", "maná", "mana"
]


def classify_genre(title: str) -> str:
    text = title.lower()

    for kw in KEYWORDS_METAL:
        if re.search(r"\b" + re.escape(kw) + r"\b", text):
            return "METAL"

    for kw in KEYWORDS_ROCK:
        if re.search(r"\b" + re.escape(kw) + r"\b", text):
            return "ROCK"

    return "OTROS"


def send_telegram(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERROR: Faltan credenciales de Telegram.")
        return

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
        print("Telegram status:", response.status_code)
        response.raise_for_status()

        result = response.json()
        if not result.get("ok"):
            print("Telegram informó un error:", result)

    except Exception as e:
        print(f"Error enviando a Telegram: {e}")


# 1. FACTOR METAL
def get_factor_metal():
    events = []

    try:
        url = "https://www.factormetal.com/conciertos/"
        response = requests.get(
            url, headers=HEADERS, timeout=15
        )

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")

            for item in soup.find_all("li"):
                text = item.get_text(" ", strip=True)
                link_tag = item.find("a", href=True)

                if (
                    "@" in text
                    and (
                        "Bogotá" in text
                        or "Colombia" in text
                    )
                ):
                    title = text.split("@")[0].strip()
                    link = (
                        urljoin(url, link_tag["href"])
                        if link_tag else url
                    )

                    events.append({
                        "id": f"fm_{title}",
                        "source": "Factor Metal (Colombia)",
                        "title": title,
                        "url": link
                    })

    except Exception as e:
        print(f"Error Factor Metal: {e}")

    return events


# 2. TUBOLETA
def get_tuboleta():
    events = []

    try:
        url = "https://tuboleta.com/es/categorias/conciertos"
        response = requests.get(
            url, headers=HEADERS, timeout=15
        )

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")

            for a in soup.find_all("a", href=True):
                href = a["href"]
                title = a.get_text(" ", strip=True)

                if "/eventos/" in href and len(title) > 3:
                    full_url = urljoin(url, href)

                    events.append({
                        "id": full_url.rstrip("/"),
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
        response = requests.get(
            url, headers=HEADERS, timeout=15
        )

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")

            for a in soup.find_all("a", href=True):
                href = a["href"]
                title = a.get_text(" ", strip=True)

                excluded = [
                    "politica", "terminos", "faq",
                    "contact", "comunicados"
                ]

                if (
                    len(title) > 3
                    and not any(x in href.lower() for x in excluded)
                ):
                    if (
                        "ticketmaster.co" in href
                        or href.startswith("/")
                    ):
                        full_url = urljoin(url, href)

                        events.append({
                            "id": full_url.rstrip("/"),
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
        response = requests.get(
            url, headers=HEADERS, timeout=15
        )

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")

            for a in soup.find_all("a", href=True):
                href = a["href"]
                title = a.get_text(" ", strip=True)

                if "/evento/" in href and len(title) > 3:
                    full_url = urljoin(url, href)

                    events.append({
                        "id": full_url.rstrip("/"),
                        "source": "Páramo Presenta",
                        "title": title.split("\n")[0].strip(),
                        "url": full_url
                    })

    except Exception as e:
        print(f"Error Páramo: {e}")

    return events


# 5. MOVE CONCERTS
def get_move_concerts():
    events = []
    browser = None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent=HEADERS["User-Agent"]
            )

            page.goto(
                "https://moveconcerts.com/co/",
                timeout=30000
            )
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(3000)

            for link in page.query_selector_all("a"):
                href = link.get_attribute("href") or ""
                title = link.inner_text().strip()

                if not title or len(title) <= 3:
                    continue

                href_lower = href.lower()

                if any(
                    key in href_lower
                    for key in [
                        "show", "concierto", "evento",
                        "moveconcerts.com"
                    ]
                ):
                    if any(
                        skip in href_lower
                        for skip in [
                            "politica", "terminos",
                            "contacto", "quienes-somos"
                        ]
                    ):
                        continue

                    full_url = urljoin(
                        "https://moveconcerts.com/co/", href
                    )

                    events.append({
                        "id": full_url.rstrip("/"),
                        "source": "Move Concerts",
                        "title": title.split("\n")[0].strip(),
                        "url": full_url
                    })

            browser.close()

    except Exception as e:
        print(f"Error Move Concerts: {e}")

    return events


# 6. LEMMY PRODUCTIONS
def get_lemmyprods():
    events = []
    url = "https://www.lemmyprods.com/eventos/"

    try:
        response = requests.get(
            url, headers=HEADERS, timeout=20
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Primero se buscan enlaces dentro de bloques habituales
        # de eventos; después se aplica el filtro de URL.
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            title = a.get_text(" ", strip=True)

            if not title or len(title) < 4:
                continue

            full_url = urljoin(url, href)
            normalized_url = full_url.rstrip("/")

            # Excluir la página de listado y enlaces externos.
            if normalized_url == url.rstrip("/"):
                continue

            if not full_url.startswith(
                "https://www.lemmyprods.com/"
            ):
                continue

            # Solo candidatos que apuntan a páginas de eventos.
            if "/eventos/" not in full_url.lower():
                continue

            events.append({
                "id": normalized_url,
                "source": "Lemmy Productions",
                "title": title,
                "url": normalized_url
            })

        # Eliminar enlaces repetidos de la misma página.
        unique = {}
        for event in events:
            unique[event["url"]] = event

        events = list(unique.values())

        print(
            f"Lemmy Productions: "
            f"{len(events)} enlaces candidatos encontrados"
        )

        for event in events:
            print(f"  - {event['title']}: {event['url']}")

    except Exception as e:
        print(f"Error Lemmy Productions: {e}")

    return events


def main():
    history_file = "eventos_registrados.json"
    known_ids = set()

    # Leer el historial existente sin borrarlo.
    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                data = json.load(f)

                if isinstance(data, list):
                    known_ids = set(data)
                else:
                    print("Advertencia: historial no es una lista.")

        except (json.JSONDecodeError, OSError) as e:
            print(f"Error leyendo historial: {e}")
            print("Se inicia con historial vacío.")

    # Consultar todas las fuentes.
    raw_events = []
    raw_events.extend(get_factor_metal())
    raw_events.extend(get_tuboleta())
    raw_events.extend(get_ticketmaster())
    raw_events.extend(get_paramo_presenta())
    raw_events.extend(get_move_concerts())
    raw_events.extend(get_lemmyprods())

    print(f"Total de elementos recopilados: {len(raw_events)}")

    # Normalizar y deduplicar por URL.
    unique_events = {}

    for event in raw_events:
        title = event.get("title", "").strip()
        url = event.get("url", "").strip().rstrip("/")
        event_id = event.get("id", url)

        if len(title) < 3 or not url:
            continue

        event["title"] = title
        event["url"] = url
        event["id"] = event_id

        if url not in unique_events:
            unique_events[url] = event

    # Detectar novedades sin repetir lo ya registrado.
    new_events = []

    for url, event in unique_events.items():
        event_id = event["id"]

        if url not in known_ids and event_id not in known_ids:
            event["category"] = classify_genre(event["title"])
            new_events.append(event)

    print(f"Novedades detectadas: {len(new_events)}")

    # Si no hay novedades, no enviar ningún mensaje.
    if not new_events:
        print("Todo al día. No se envía notificación.")
        return

    # Prioridad: metal, rock y otros.
    priority = {
        "METAL": 0,
        "ROCK": 1,
        "OTROS": 2
    }

    new_events.sort(
        key=lambda event: priority.get(event["category"], 2)
    )

    messages = [
        f"🚨 *Nuevos conciertos y eventos* "
        f"({len(new_events)})\n"
        "-------------------------------------\n\n"
    ]

    for event in new_events:
        if event["category"] == "METAL":
            badge = "🔥 *[METAL]*"
        elif event["category"] == "ROCK":
            badge = "🎸 *[ROCK]*"
        else:
            badge = "⚡ *[OTROS]*"

        title = event["title"].replace("*", "")
        url = event["url"]
        source = event["source"].replace("*", "")

        card = (
            f"{badge} *{title}*\n"
            f"🏢 *Fuente:* {source}\n"
            f"🔗 [Ver evento]({url})\n\n"
        )

        if len(messages[-1]) + len(card) > 3500:
            messages.append(card)
        else:
            messages[-1] += card

    # Enviar las notificaciones.
    for message in messages:
        send_telegram(message)

    # Registrar únicamente las novedades notificadas correctamente
    # requeriría que send_telegram devolviera un resultado.
    # Esta versión conserva el comportamiento de registro del bot.
    for event in new_events:
        known_ids.add(event["url"].rstrip("/"))
        known_ids.add(event["id"])

    try:
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(
                sorted(known_ids),
                f,
                ensure_ascii=False,
                indent=2
            )

        print("Historial actualizado correctamente.")

    except OSError as e:
        print(f"Error guardando historial: {e}")


if __name__ == "__main__":
    main()
