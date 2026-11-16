"""Lee los RSS de la lista blanca y deja las notas de las ultimas N horas en JSON.

Uso:
  python3 fuentes.py [horas]        -> JSON con las notas (default 30 horas)
  python3 fuentes.py --og URL       -> imprime la imagen principal (og:image) de una nota
Solo librerias estandar (Python 3.9).
"""
import json, re, sys, html
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"

# Lista blanca. Para sumar o sacar una fuente se edita solo esta lista.
FEEDS = [
    ("chile", "La Tercera", "https://www.latercera.com/arc/outboundfeeds/rss/category/politica/?outputType=xml"),
    ("chile", "Cooperativa", "https://www.cooperativa.cl/noticias/site/tax/port/all/rss_3___1.xml"),
    ("chile", "CIPER", "https://www.ciperchile.cl/feed/"),
    ("chile", "Ex-Ante", "https://www.ex-ante.cl/feed/"),
    ("economia", "La Tercera Pulso", "https://www.latercera.com/arc/outboundfeeds/rss/category/pulso/?outputType=xml"),
    ("economia", "CNBC", "https://www.cnbc.com/id/20910258/device/rss/rss.html"),
    ("economia", "BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("mundo", "BBC Mundo", "https://feeds.bbci.co.uk/mundo/rss.xml"),
    ("mundo", "The Guardian", "https://www.theguardian.com/world/rss"),
    ("mundo", "DW", "https://rss.dw.com/xml/rss-sp-all"),
    ("mundo", "France 24", "https://www.france24.com/es/rss"),
    ("ia", "TechCrunch", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("ia", "The Verge", "https://www.theverge.com/rss/index.xml"),
    ("ia", "MIT Technology Review", "https://www.technologyreview.com/feed/"),
    ("ia", "OpenAI", "https://openai.com/news/rss.xml"),
    ("ia", "Google", "https://blog.google/technology/ai/rss/"),
    ("mineria", "Mining.com", "https://www.mining.com/feed/"),
    ("mineria", "Minería Chilena", "https://www.mch.cl/feed/"),
]


def get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def local(tag):
    return tag.rsplit("}", 1)[-1]


def limpiar(texto, largo=280):
    texto = re.sub(r"<[^>]+>", " ", html.unescape(texto or ""))
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto[:largo]


def fecha(txt):
    if not txt:
        return None
    try:
        d = parsedate_to_datetime(txt)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(txt.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def parsear(xml_bytes):
    """Devuelve dicts {titulo, link, fecha, resumen, imagen} de un RSS o Atom."""
    if b"<!ENTITY" in xml_bytes:  # el expat de Python 3.9 del Mac (2.2.8) no frena el ataque billion laughs
        raise ValueError("feed con entidades XML, se descarta")
    raiz = ET.fromstring(xml_bytes)
    notas = []
    for it in raiz.iter():
        if local(it.tag) not in ("item", "entry"):
            continue
        n = {"titulo": "", "link": "", "fecha": None, "resumen": "", "imagen": ""}
        for c in it:
            t = local(c.tag)
            if t == "title":
                n["titulo"] = limpiar(c.text, 200)
            elif t == "link":
                n["link"] = n["link"] or (c.text or "").strip() or c.get("href", "")
            elif t in ("pubDate", "published", "updated", "date") and not n["fecha"]:
                n["fecha"] = fecha(c.text)
            elif t in ("description", "summary") and not n["resumen"]:
                n["resumen"] = limpiar(c.text)
            elif t in ("content", "thumbnail", "enclosure") and c.get("url") and not n["imagen"]:
                if t != "enclosure" or c.get("type", "image").startswith("image"):
                    n["imagen"] = c.get("url")
            elif t == "group":  # media:group de algunos medios
                for g in c:
                    if g.get("url") and not n["imagen"]:
                        n["imagen"] = g.get("url")
        if n["titulo"] and n["link"]:
            notas.append(n)
    return notas


def og_image(url):
    pagina = get(url).decode("utf-8", "ignore")
    for patron in (r'property=["\']og:image["\'][^>]*content=["\']([^"\']+)',
                   r'content=["\']([^"\']+)["\'][^>]*property=["\']og:image'):
        m = re.search(patron, pagina)
        if m:
            return html.unescape(m.group(1))
    return ""


def main(horas):
    corte = datetime.now(timezone.utc) - timedelta(hours=horas)
    salida, fallas = [], []
    for grupo, fuente, url in FEEDS:
        try:
            notas = parsear(get(url))
        except Exception as e:  # una fuente caida no bota el diario
            fallas.append(f"{fuente}: {e}")
            continue
        for n in notas:
            if n["fecha"] and n["fecha"] >= corte:
                n["fecha"] = n["fecha"].astimezone().strftime("%d-%m %H:%M")
                salida.append({"grupo": grupo, "fuente": fuente, **n})
    print(json.dumps({"notas": salida, "fuentes_caidas": fallas}, ensure_ascii=False, indent=0))


def _autoprueba():
    rss = b"""<rss xmlns:media="http://search.yahoo.com/mrss/"><channel><item><title>Hola &amp; chao</title>
    <link>https://a.cl/1</link><pubDate>Mon, 16 Nov 2026 10:00:00 -0300</pubDate>
    <description><![CDATA[<p>Texto</p>]]></description><media:content url="https://a.cl/i.jpg"/></item></channel></rss>"""
    atom = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>X</title><link href="https://b.com/2"/>
    <updated>2026-11-16T14:45:56+00:00</updated></entry></feed>"""
    a, b = parsear(rss)[0], parsear(atom)[0]
    assert a["titulo"] == "Hola & chao" and a["link"] == "https://a.cl/1" and a["imagen"] == "https://a.cl/i.jpg"
    assert a["resumen"] == "Texto" and a["fecha"].astimezone(timezone.utc).hour == 13
    try:
        parsear(b'<!DOCTYPE r [<!ENTITY a "x">]><rss/>'); assert False
    except ValueError:
        pass
    assert b["link"] == "https://b.com/2" and b["fecha"].day == 16


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        _autoprueba(); print("ok")
    elif len(sys.argv) > 2 and sys.argv[1] == "--og":
        print(og_image(sys.argv[2]))
    else:
        main(float(sys.argv[1]) if len(sys.argv) > 1 else 30)
