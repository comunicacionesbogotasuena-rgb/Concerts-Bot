
import json
import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
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
    "testament", "dethklok", "angeles del infierno", "kraken",
    "hellripper", "saor", "kanonenfieber", "avatar", "equilibrium",
    "slaughter to prevail", "eleine", "roberto tiranti"
]

KEYWORDS_ROCK = [
    "rock", "punk", "hardcore", "indie", "post-punk", "grunge",
    "alternative rock", "rock alternativo", "hard rock", "bunbury",
    "caifanes", "the strokes", "placebo",
    "los fabulosos cadillacs", "def leppard", "soda stereo",
    "aterciopelados", "conociendo rusia", "maná", "mana",
    "the rasmus", "hombres g", "hammerfall"
]


def classify_genre(title: str) -> str:
    text = title.lower()

    for keyword in KEYWORDS_METAL:
        if re.search(r"\b" + re.escape(keyword) + r"\b", text):
            return "METAL"

    for keyword in KEYWORDS_ROCK:
        if re.search(r"\b" + re.escape(keyword) + r"\b", text):
            return "ROCK"

    return "OTROS"


def send_telegram(message: str) -> bool:
    """Envía un mensaje y devuelve True solo si Telegram lo acepta."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERROR: Faltan credenciales de Telegram.")
        return False

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }

    try:
        response = requests.post(url, json=payload, timeout=20)
        print("Telegram status:", response.status_code)
        response.raise_for_status()

        result = response.json()

        if result.get("ok"):
            return True

        print("Telegram informó un error:", result)
        return False

    except Exception as error:
        print(f"Error enviando a Telegram: {error}")
        return False


def make_event(source: str, title: str, url: str) -> dict:
    normalized_url = url.rstrip("/")
    return {
        "id": normalized_url,
        "source": source,
        "title": title.strip(),
        "url": normalized_url
    }


# 1. FACTOR METAL
def get_factor_metal():
    events = []
    url = "https://www.factormetal.com/conciertos/"

    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        for item in soup.find_all("li"):
            text = item.get_text(" ", strip=True)
            link_tag = item.find("a", href=True)

            if (
                "@" in text
                and ("Bogotá" in text or "Bogota" in text
                     or "Colombia" in text)
            ):
                title = text.split("@")[0].strip()
                link = (
                    urljoin(url, link_tag["href"])
                    if link_tag else url
                )
                events.append(
                    make_event("Factor Metal", title, link)
                )

    except Exception as error:
        print(f"Error Factor Metal: {error}")

    return events


# 2. TUBOLETA
def get_tuboleta():
    events = []
    url = "https://tuboleta.com/es/categorias/conciertos"

    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            title = anchor.get_text(" ", strip=True)

            if "/eventos/" not in href or len(title) < 4:
                continue

            full_url = urljoin(url, href)
            host = urlparse(full_url).netloc.lower()

            if "tuboleta.com" not in host:
                continue

            events.append(make_event("Tuboleta", title, full_url))

    except Exception as error:
        print(f"Error Tuboleta: {error}")

    return events


# 3. TICKETMASTER COLOMBIA
def get_ticketmaster():
    events = []
    url = "https://www.ticketmaster.co/page/CONCIERTOS"

    excluded = [
        "politica", "terminos", "faq", "contact",
        "comunicados", "privacidad", "ayuda"
    ]

    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            title = anchor.get_text(" ", strip=True)

            if len(title) < 4:
                continue

            full_url = urljoin(url, href)
            host = urlparse(full_url).netloc.lower()

            if "ticketmaster.co" not in host:
                continue

            if any(word in full_url.lower() for word in excluded):
                continue

            # Limitar la selección a enlaces de contenido/eventos.
            if not any(
                word in full_url.lower()
                for word in ["event", "evento", "concert", "concierto"]
            ):
                continue

            events.append(
                make_event("Ticketmaster CO", title, full_url)
            )

    except Exception as error:
        print(f"Error Ticketmaster: {error}")

    return events


# 4. PÁRAMO PRESENTA
def get_paramo_presenta():
    events = []
    url = "https://www.paramopresenta.com/eventos"

    try:
        response = requests.get(url, headers=HEADERS, timeout=25)
        response.raise_for_status()

        # Ayuda a interpretar correctamente caracteres acentuados.
        response.encoding = response.apparent_encoding or "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            full_url = urljoin(url, href)
            normalized_url = full_url.rstrip("/")
            parsed = urlparse(full_url)

            # Aceptar únicamente páginas de eventos de Páramo.
            if parsed.netloc.lower() not in (
                "paramopresenta.com",
                "www.paramopresenta.com"
            ):
                continue

            if "/eventos/" not in parsed.path.lower():
                continue

            # Evitar que la página del listado se registre como evento.
            if normalized_url == url.rstrip("/"):
                continue

            # Intentar obtener el título de la tarjeta del evento.
            title = ""
            for parent in anchor.parents:
                if parent.name in ("article", "li", "section"):
                    heading = parent.find(
                        ["h1", "h2", "h3", "h4", "h5"]
                    )
                    if heading:
                        title = heading.get_text(" ", strip=True)
                        break

            if not title:
                title = anchor.get_text(" ", strip=True)

            # Si el enlace tiene texto genérico, usar el slug de la URL.
            generic_titles = {
                "", "ver evento", "comprar entradas",
                "más información", "ver más", "conoce más"
            }

            if title.casefold() in generic_titles:
                slug = parsed.path.rstrip("/").split("/")[-1]
                slug = re.sub(
                    r"-tickets-[a-z0-9]+$", "", slug,
                    flags=re.IGNORECASE
                )
                title = slug.replace("-", " ").replace("_", " ").title()

            if len(title) < 3:
                continue

            events.append(
                make_event("Páramo Presenta", title, normalized_url)
            )

        # Eliminar duplicados por URL.
        unique = {event["url"]: event for event in events}
        events = list(unique.values())

        print(
            f"Páramo Presenta: {len(events)} "
            "enlaces candidatos encontrados"
        )

        for event in events:
            print(f"  - {event['title']}: {event['url']}")

    except Exception as error:
        print(f"Error Páramo Presenta: {error}")

    return events


# 5. MOVE CONCERTS
def get_move_concerts():
    events = []
    browser = None
    base_url = "https://moveconcerts.com/co/"

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(user_agent=HEADERS["User-Agent"])

            page.goto(
                base_url,
                wait_until="domcontentloaded",
                timeout=45000
            )
            page.wait_for_timeout(3000)

            for anchor in page.query_selector_all("a[href]"):
                href = anchor.get_attribute("href") or ""
                title = anchor.inner_text().strip()

                if len(title) < 4:
                    continue

                full_url = urljoin(base_url, href)
                host = urlparse(full_url).netloc.lower()

                if "moveconcerts.com" not in host:
                    continue

                if not any(
                    word in full_url.lower()
                    for word in [
                        "show", "concierto", "evento",
                        "event", "tour", "artist"
                    ]
                ):
                    continue

                if any(
                    word in full_url.lower()
                    for word in [
                        "politica", "terminos", "contacto",
                        "quienes-somos", "privacy"
                    ]
                ):
                    continue

                events.append(
                    make_event("Move Concerts", title, full_url)
                )

            browser.close()
            browser = None

    except Exception as error:
        print(f"Error Move Concerts: {error}")

    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass

    return events


# 6. LEMMY PRODUCTIONS
def get_lemmyprods():
    events = []
    url = "https://www.lemmyprods.com/eventos/"

    try:
        response = requests.get(url, headers=HEADERS, timeout=25)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            full_url = urljoin(url, href)
            parsed = urlparse(full_url)
            normalized_url = full_url.rstrip("/")
            title = anchor.get_text(" ", strip=True)

            if parsed.netloc.lower() not in (
                "lemmyprods.com",
                "www.lemmyprods.com"
            ):
                continue

            if "/eventos/" not in parsed.path.lower():
                continue

            if normalized_url == url.rstrip("/"):
                continue

            if len(title) < 4:
                continue

            events.append(
                make_event("Lemmy Productions", title, normalized_url)
            )

        unique = {event["url"]: event for event in events}
        events = list(unique.values())

        print(
            f"Lemmy Productions: {len(events)} "
            "enlaces candidatos encontrados"
        )

        for event in events:
            print(f"  - {event['title']}: {event['url']}")

    except Exception as error:
        print(f"Error Lemmy Productions: {error}")

    return events


def load_history(filename: str) -> set:
    """Carga el historial existente sin borrarlo."""
    if not os.path.exists(filename):
        return set()

    try:
        with open(filename, "r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, list):
            return set(str(item) for item in data)

        print("Advertencia: el historial no es una lista.")

    except (json.JSONDecodeError, OSError) as error:
        print(f"Error leyendo historial: {error}")
        print("Se conserva el archivo y se inicia con historial vacío.")

    return set()


def save_history(filename: str, known_ids: set) -> bool:
    try:
        with open(filename, "w", encoding="utf-8") as file:
            json.dump(
                sorted(known_ids),
                file,
                ensure_ascii=False,
                indent=2
            )

        print("Historial actualizado correctamente.")
        return True

    except OSError as error:
        print(f"Error guardando historial: {error}")
        return False


def build_messages(events: list) -> list:
    priority = {"METAL": 0, "ROCK": 1, "OTROS": 2}
    events.sort(
        key=lambda event: priority.get(event["category"], 2)
    )

    messages = []
    current_message = (
        f"🚨 *Nuevos conciertos y eventos ({len(events)})*\n"
        "-------------------------------------\n\n"
    )

    for event in events:
        category = event["category"]

        if category == "METAL":
            badge = "🔥 *[METAL]*"
        elif category == "ROCK":
            badge = "🎸 *[ROCK]*"
        else:
            badge = "⚡ *[OTROS]*"

        # Evitar caracteres que alteren el formato Markdown.
        title = event["title"].replace("*", "").replace("_", "\\_")
        source = event["source"].replace("*", "").replace("_", "\\_")
        url = event["url"]

        card = (
            f"{badge} *{title}*\n"
            f"🏢 *Fuente:* {source}\n"
            f"🔗 [Ver evento]({url})\n\n"
        )

        if len(current_message) + len(card) > 3500:
            messages.append(current_message)
            current_message = card
        else:
            current_message += card

    if current_message.strip():
        messages.append(current_message)

    return messages


def main():
    history_file = "eventos_registrados.json"
    known_ids = load_history(history_file)

    # Consultar todas las fuentes.
    raw_events = []
    sources = [
        get_factor_metal,
        get_tuboleta,
        get_ticketmaster,
        get_paramo_presenta,
        get_move_concerts,
        get_lemmyprods
    ]

    for source_function in sources:
        try:
            raw_events.extend(source_function())
        except Exception as error:
            print(
                f"Error inesperado en {source_function.__name__}: "
                f"{error}"
            )

    print(f"Total de elementos recopilados: {len(raw_events)}")

    # Normalizar y deduplicar por URL.
    unique_events = {}

    for event in raw_events:
        title = event.get("title", "").strip()
        url = event.get("url", "").strip().rstrip("/")

        if len(title) < 3 or not url:
            continue

        event["title"] = title
        event["url"] = url
        event["id"] = url

        unique_events[url] = event

    # Detectar eventos no registrados previamente.
    new_events = []

    for url, event in unique_events.items():
        if url in known_ids or event["id"] in known_ids:
            continue

        event["category"] = classify_genre(event["title"])
        new_events.append(event)

    print(f"Novedades detectadas: {len(new_events)}")

    if not new_events:
        print("Todo al día. No se envía notificación.")
        return

    messages = build_messages(new_events)

    # Registrar eventos solo si todas las notificaciones se enviaron.
    all_sent = True

    for message in messages:
        if not send_telegram(message):
            all_sent = False

    if all_sent:
        for event in new_events:
            known_ids.add(event["url"])
            known_ids.add(event["id"])

        save_history(history_file, known_ids)
    else:
        print(
            "No se actualizó el historial porque al menos un mensaje "
            "no pudo enviarse. Se reintentará en la próxima ejecución."
        )


if __name__ == "__main__":
    main()
