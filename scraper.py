import datetime, hashlib, json, os, smtplib
from email.message import EmailMessage
from urllib.parse import quote, urljoin
import feedparser, requests
from bs4 import BeautifulSoup

TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CLAVES = ["arcosur", "sector 89/3", "rey fernando de aragón"]
FASES = ["plan parcial", "junta de compensación", "reparcelación", "estudio de detalle",
         "proyecto de urbanización", "urbanización", "enajenación", "subasta",
         "licitación", "parcela", "manzana", "licencia", "vivienda", "construcción"]
FUENTES = [(f"https://news.google.com/rss/search?q={quote(q)}&hl=es&gl=ES&ceid=ES:es", "Noticias", True)
           for q in ["Arcosur parcelas", "Arcosur viviendas", "Arcosur Ayuntamiento Zaragoza", "Arcosur urbanización"]]
FUENTES += [("https://www.boa.aragon.es/", "BOA", False),
            ("https://bop.dpz.es/BOPZ/", "BOPZ", False),
            ("https://www.zaragoza.es/sede/portal/urbanismo/", "Ayuntamiento", False)]
S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (Linux; Android 13) ArcosurBot"


def leer(n, d):
    try:
        return json.load(open(n))
    except Exception:
        return d


def tg(metodo, **p):
    return S.post(f"https://api.telegram.org/bot{TOKEN}/{metodo}", data=p, timeout=60).json()


def main():
    st = leer("estado.json", {"seen": [], "chat": None, "offset": 0})
    if TOKEN:
        for u in tg("getUpdates", offset=st["offset"]).get("result", []):
            st["offset"] = u["update_id"] + 1
            m = u.get("message", {})
            if m.get("text", "").startswith("/start") and not st["chat"]:
                st["chat"] = m["chat"]["id"]
                tg("sendMessage", chat_id=st["chat"], text="Activo. Recibirás aquí las novedades de Arcosur.")
    datos, nuevos, errs = leer("hallazgos.json", []), [], []
    hoy = str(datetime.date.today())
    for u, src, rss in FUENTES:
        try:
            r = S.get(u, timeout=30)
            r.raise_for_status()
            if rss:
                items = [(e.title, e.link) for e in feedparser.parse(r.content).entries]
            else:
                items = [(a.get_text(" ", strip=True), urljoin(u, a["href"]))
                         for a in BeautifulSoup(r.text, "html.parser").find_all("a", href=True)]
                items = [i for i in items if any(k in i[0].lower() for k in CLAVES)]
            for t, l in items:
                h = hashlib.md5(l.encode()).hexdigest()
                if h not in st["seen"]:
                    st["seen"].append(h)
                    f = [x for x in FASES if x in t.lower()]
                    datos.insert(0, {"t": t, "l": l, "s": src, "f": f, "d": hoy})
                    nuevos.append(f"• [{src}] {t}\n{l}")
        except Exception:
            errs.append(src)
    st["seen"] = st["seen"][-3000:]
    json.dump(datos[:1000], open("hallazgos.json", "w"), ensure_ascii=False)
    json.dump(st, open("estado.json", "w"))
    if nuevos:
        texto = "\n\n".join(nuevos)
        if TOKEN and st["chat"]:
            for i in range(0, len(texto), 4000):
                tg("sendMessage", chat_id=st["chat"], text=texto[i:i + 4000], disable_web_page_preview="true")
        if os.environ.get("SMTP_HOST"):
            try:
                m = EmailMessage()
                m["Subject"], m["From"], m["To"] = "Arcosur: novedades", os.environ["SMTP_USER"], os.environ["SMTP_TO"]
                m.set_content(texto)
                port = int(os.environ.get("SMTP_PORT") or 587)
                c = smtplib.SMTP_SSL(os.environ["SMTP_HOST"], 465) if port == 465 else smtplib.SMTP(os.environ["SMTP_HOST"], port)
                if port != 465:
                    c.starttls()
                c.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
                c.send_message(m)
                c.quit()
            except Exception as x:
                print("email:", x)
    print("nuevos:", len(nuevos), "fallos:", errs)


main()
