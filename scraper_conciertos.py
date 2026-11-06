import os
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8"
}

def diagnostico():
    print("=== DIAGNÓSTICO EN VIVO ===", flush=True)

    # 1. Probar Factor Metal
    urls_fm = [
        "https://factormetal.com/conciertos/",
        "https://www.factormetal.com/conciertos/",
        "https://factormetal.com/category/conciertos/"
    ]
    for u in urls_fm:
        try:
            r = requests.get(u, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")
            links = soup.find_all("a")
            print(f"[Factor Metal] {u} -> Status: {r.status_code} | Longitud HTML: {len(r.text)} | Total links <a>: {len(links)}", flush=True)
            # Buscar si hay mención a algún concierto
            titulos = [a.get_text(strip=True) for a in links if len(a.get_text(strip=True)) > 10][:5]
            print(f"   Primeros textos encontrados: {titulos}", flush=True)
        except Exception as e:
            print(f"[Factor Metal] Error en {u}: {e}", flush=True)

    # 2. Probar Páramo Presenta
    urls_paramo = [
        "https://www.paramopresenta.com/eventos",
        "https://paramopresenta.com/",
        "https://paramopresenta.com/conciertos"
    ]
    for u in urls_paramo:
        try:
            r = requests.get(u, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")
            has_next = bool(soup.select_one("script#__NEXT_DATA__"))
            cards = soup.select("a[href*='evento'], a[href*='ticket'], div[class*='event']")
            print(f"[Páramo] {u} -> Status: {r.status_code} | Longitud HTML: {len(r.text)} | Tiene NEXT_DATA: {has_next} | Elementos tipo evento: {len(cards)}", flush=True)
        except Exception as e:
            print(f"[Páramo] Error en {u}: {e}", flush=True)

    print("=== FIN DIAGNÓSTICO ===", flush=True)

if __name__ == "__main__":
    diagnostico()
