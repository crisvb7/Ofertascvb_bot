"""Sonda temporal: qué datos del vendedor y de las fotos dan Wallapop y Vinted."""
import json, re, sys, html
sys.path.insert(0, ".")
from ofertas.red import sesion_navegador
from ofertas.fuentes import wallapop

def corto(x, n=1500):
    s = json.dumps(x, ensure_ascii=False, default=str)
    return s[:n]

s = sesion_navegador()
print("===== WALLAPOP búsqueda")
r = s.get(wallapop.URL_BUSQUEDA, params={"keywords": "ps5", "order_by": "newest", "source": "search_box",
          "latitude": 43.36, "longitude": -5.85, "min_sale_price": 300}, headers=wallapop.CABECERAS, timeout=20)
items = wallapop.extraer_items(r.json())
print("n", len(items)); it = items[0]
print("claves", sorted(it.keys()))
print("item0", corto({k: v for k, v in it.items() if k not in ("description",)}, 2500))
for it in items[:3]:
    uid = it.get("user_id") or (it.get("user") or {}).get("id")
    print("--- user", uid, "item", it["id"])
    for url in (f"https://api.wallapop.com/api/v3/users/{uid}", f"https://api.wallapop.com/api/v3/users/{uid}/stats",
                f"https://api.wallapop.com/api/v3/users/{uid}/reviews"):
        x = s.get(url, headers=wallapop.CABECERAS, timeout=20)
        print(url.rsplit("/", 2)[-2:], x.status_code, x.text[:1200])
    x = s.get(f"https://api.wallapop.com/api/v3/items/{it['id']}", headers=wallapop.CABECERAS, timeout=20)
    d = x.json() if x.ok else {}
    print("detalle", x.status_code, sorted(d.keys()) if isinstance(d, dict) else d)
    print("detalle user/fechas/imagenes", corto({k: d.get(k) for k in ("user", "user_id", "created_at", "modified_at", "images", "counters", "views")}, 1500))
img = wallapop._imagen(items[0])
x = s.get(img, timeout=20); print("foto wallapop", img, x.status_code, x.headers.get("content-type"), len(x.content))

print("===== VINTED")
base = "https://www.vinted.es"
r = s.get(base + "/catalog", params={"search_text": "ps5", "order": "newest_first", "price_from": 300, "currency": "EUR"},
          timeout=30, headers={"Accept": "text/html"})
pag = r.text
print("catalog", r.status_code, len(pag))
ids = re.findall(r'data-testid="product-item-id-(\d+)--overlay-link"', pag)[:3]
print("ids", ids)
for m in re.finditer(r'(feedback|reputation|user_id|"user":|login|created_at)', pag[:2000000]):
    print("catalog contiene", m.group(1), pag[max(0, m.start()-80):m.start()+160].replace("\n", " ")); break
print("cookies", list(s.cookies.keys()) if hasattr(s.cookies, "keys") else s.cookies)
for iid in ids[:2]:
    x = s.get(f"{base}/items/{iid}", timeout=30, headers={"Accept": "text/html"})
    t = x.text
    print("--- item", iid, x.status_code, len(t))
    for pat in ("feedback_count", "feedback_reputation", "positive_feedback", "created_at", "\\\"user\\\"", "user_id",
                "member", "login", "photos", "is_verified", "reviews", "rating", "valoraci", "evaluaci"):
        ms = [mm.start() for mm in re.finditer(pat, t)][:2]
        for p in ms:
            print(f"  [{pat}]", t[max(0, p-120):p+220].replace("\n", " "))
    for path in (f"/api/v2/items/{iid}", f"/api/v2/items/{iid}/details"):
        y = s.get(base + path, timeout=30, headers={"Accept": "application/json"})
        print("  api", path, y.status_code, y.text[:600])
    uid = re.search(r'\\?"user_id\\?":\s*(\d+)', t) or re.search(r'/member/(\d+)', t)
    if uid:
        uid = uid.group(1); print("  uid", uid)
        for path in (f"/api/v2/users/{uid}", f"/member/{uid}"):
            y = s.get(base + path, timeout=30, headers={"Accept": "application/json" if "api" in path else "text/html"})
            print("  user", path, y.status_code, len(y.text))
            tt = y.text
            for pat in ("feedback_count", "feedback_reputation", "created_at", "positive_feedback_count", "item_count", "valoraci", "Miembro", "member_since"):
                for p in [mm.start() for mm in re.finditer(pat, tt)][:1]:
                    print(f"    [{pat}]", tt[max(0, p-100):p+200].replace("\n", " "))
src = re.search(r'<img src="([^"]+)"[^>]*?data-testid="product-item-id-\d+--image--img"', pag)
if src:
    u = html.unescape(src.group(1)); x = s.get(u, timeout=20); print("foto vinted", u, x.status_code, x.headers.get("content-type"), len(x.content))
try:
    import PIL; print("Pillow", PIL.__version__)
except Exception as e:
    print("sin Pillow", e)
