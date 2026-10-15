import os, re, io, time
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageFont

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

ORANGE = (255, 92, 0)
DARK = (15, 15, 15)
WHITE = (255, 255, 255)
GRAY = (200, 200, 200)

def get_font(size: int, bold: bool = False):
    """Carga fuentes compatibles con los servidores de GitHub Actions (Ubuntu)."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf" if bold else "/usr/share/fonts/truetype/freefont/FreeSans.ttf"
    ]
    for p in font_paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except:
                pass
    return ImageFont.load_default()

def parse_date(ev_tag, raw_text: str) -> datetime:
    cal = ev_tag.select_one("a[href*='calendar.google.com']")
    if cal and cal.has_attr("href"):
        m = re.search(r"dates=(\d{4})(\d{2})(\d{2})", cal["href"])
        if m: return datetime(int(m[1]), int(m[2]), int(m[3]))
    t = ev_tag.select_one("time")
    if t and t.get("datetime"):
        try: return datetime.strptime(t["datetime"][:10], "%Y-%m-%d")
        except: pass
    m2 = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw_text)
    if m2:
        try: return datetime(int(m2[3]), int(m2[2]), int(m2[1]))
        except: pass
    return datetime(2099, 12, 31)

def extract_details(url: str):
    poster, ticket = "", ""
    if not url or "factormetal.com/eventos/" == url or "factormetal.com/conciertos/" == url:
        return poster, ticket
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            
            # 1. Buscar afiche específico descartando banners genéricos
            for img in soup.select(".tribe-events-event-image img, article img, .entry-content img"):
                src = img.get("data-orig-file") or img.get("src") or img.get("data-src") or ""
                if src and src.startswith("http"):
                    if not any(x in src.lower() for x in ["default", "factormetal-conciertos", "logo", "cropped"]):
                        poster = src
                        break

            # 2. Enlace de boletas
            kw = ["tuboleta", "ticketmaster", "eticket", "alltickets", "passline", "biciq", "entradas", "boletas", "ticket"]
            for a in soup.select("a[href]"):
                h, tx = a["href"].lower(), a.get_text().lower()
                if any(k in h or k in tx for k in kw):
                    if not any(x in h for x in ["factormetal", "facebook", "twitter", "calendar"]):
                        ticket = a["href"]
                        break
    except:
        pass
    return poster, ticket

def create_bogota_suena_poster(poster_url: str, banda: str, fecha_str: str) -> io.BytesIO:
    w, h = 1080, 1350
    canvas = Image.new("RGB", (w, h), DARK)
    draw = ImageDraw.Draw(canvas)

    orig = None
    if poster_url and poster_url.startswith("http") and not any(x in poster_url.lower() for x in ["factormetal-conciertos", "logo"]):
        try:
            r = requests.get(poster_url, headers=HEADERS, timeout=12)
            if r.status_code == 200:
                orig = Image.open(io.BytesIO(r.content)).convert("RGB")
        except:
            pass

    if orig:
        bg = orig.resize((w, h)).filter(ImageFilter.GaussianBlur(35))
        canvas.paste(ImageEnhance.Brightness(bg).enhance(0.35), (0, 0))
        
        pw, ph = orig.size
        th = int(h * 0.52)
        tw = int((pw / ph) * th)
        if tw > w - 120:
            tw = w - 120
            th = int((ph / pw) * tw)
            
        c_img = orig.resize((tw, th), Image.Resampling.LANCZOS)
        ox, oy = (w - tw) // 2, 160
        draw = ImageDraw.Draw(canvas)
        draw.rectangle([ox - 8, oy - 8, ox + tw + 8, oy + th + 8], outline=ORANGE, width=5)
        canvas.paste(c_img, (ox, oy))
    else:
        # Textura abstracta si no hay póster individual
        draw.rectangle([60, 160, w - 60, 780], outline=(60, 60, 60), width=4)
        font_temp = get_font(42, bold=True)
        draw.text((120, 440), "AFICHE OFICIAL PRÓXIMAMENTE", fill=GRAY, font=font_temp)

    # 1. Badge superior estilo Fanzine
    draw.rectangle([60, 60, 520, 125], fill=ORANGE)
    font_badge = get_font(34, bold=True)
    draw.text((85, 75), "PRÓXIMO CONCIERTO", fill=(0, 0, 0), font=font_badge)

    # 2. Franja con Nombre de la Banda
    banda_clean = banda.split("@")[0].strip().upper()[:24]
    iy = int(h * 0.72)
    draw.rectangle([50, iy, w - 50, iy + 105], fill=ORANGE)
    font_banda = get_font(52, bold=True)
    draw.text((75, iy + 22), banda_clean, fill=(0, 0, 0), font=font_banda)

    # 3. Ciudad y Fecha
    font_ciudad = get_font(40, bold=True)
    font_fecha = get_font(32, bold=False)
    draw.text((70, iy + 130), "BOGOTÁ", fill=WHITE, font=font_ciudad)
    draw.text((70, iy + 185), fecha_str.upper(), fill=GRAY, font=font_fecha)

    # 4. Logo Bogotá Suena
    if os.path.exists("logo_bogotasuena.png"):
        try:
            lg = Image.open("logo_bogotasuena.png").convert("RGBA")
            nw = 260
            nh = int((lg.size[1] / lg.size[0]) * nw)
            lg = lg.resize((nw, nh), Image.Resampling.LANCZOS)
            canvas.paste(lg, (w - nw - 60, h - nh - 55), mask=lg)
        except:
            draw.text((w - 360, h - 90), "BOGOTASUENA.COM", fill=WHITE, font=font_fecha)
    else:
        draw.text((w - 360, h - 90), "BOGOTASUENA.COM", fill=WHITE, font=font_fecha)

    out = io.BytesIO()
    canvas.save(out, format="JPEG", quality=92)
    out.seek(0)
    return out

def scrape():
    conciertos = []
    try:
        r = requests.get("https://factormetal.com/eventos/", headers=HEADERS, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            for ev in soup.select(".type-tribe_events, article, .event-item"):
                tt = ev.select_one("h2, h3, .tribe-events-list-event-title")
                if not tt or not tt.get_text(strip=True): continue
                a = tt.find("a") or ev.select_one("a[href*='factormetal.com/evento/']")
                conciertos.append({
                    "titulo": tt.get_text(strip=True),
                    "dt": parse_date(ev, ev.get_text(" ", strip=True)),
                    "link": a["href"] if a and a.has_attr("href") else "https://factormetal.com/eventos/"
                })
    except: pass
    conciertos.sort(key=lambda x: x["dt"])
    return conciertos

def main():
    if not BOT_TOKEN or not CHAT_ID: return
    eventos = scrape()[:10]
    for c in eventos:
        fecha_display = c['dt'].strftime("%d/%m/%Y") if c['dt'].year != 2099 else "Próximamente"
        poster_url, ticket_link = extract_details(c["link"])
        time.sleep(0.4)
        buf = create_bogota_suena_poster(poster_url, c["titulo"], fecha_display)
        
        caption = f"⚡ <b>{c['titulo']}</b>\n📅 <b>Fecha:</b> {fecha_display}\n📍 <b>Ciudad:</b> Bogotá, Colombia\n"
        if ticket_link:
            caption += f"🎟️ <b>Comprar Boletas:</b> <a href='{ticket_link}'>Enlace Oficial</a>\n"
        else:
            caption += f"🔗 <b>Info oficial:</b> <a href='{c['link']}'>Ver detalles</a>\n"
        caption += "\n📲 <i>Vía @bogotasuena | bogotasuena.com</i>"

        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
            data={"chat_id": CHAT_ID, "caption": caption[:1024], "parse_mode": "HTML"},
            files={"photo": ("bogotasuena_post.jpg", buf, "image/jpeg")},
            timeout=25
        )

if __name__ == "__main__":
    main()
