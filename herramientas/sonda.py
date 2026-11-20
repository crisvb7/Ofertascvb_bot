"""Sonda temporal (2): qué trae del vendedor la página de búsqueda de Vinted (la que ya leemos)."""
import re, sys
sys.path.insert(0, ".")
from ofertas.red import sesion_navegador

s = sesion_navegador()
r = s.get("https://www.vinted.es/catalog", params={"search_text": "ps5", "order": "newest_first",
          "price_from": 300, "currency": "EUR"}, timeout=30, headers={"Accept": "text/html"})
pag = r.text
ids = re.findall(r'data-testid="product-item-id-(\d+)--overlay-link"', pag)[:3]
print("catalog", r.status_code, len(pag), "ids", ids)
for pat in (ids[0], r'\\"user\\":', r'"user":', "feedback", "reputation", "profile_url", "business", "created_at_ts", "photo"):
    ms = [m.start() for m in re.finditer(pat, pag)]
    print(f"[{pat}] x{len(ms)}")
    for p in ms[:2]:
        print("   ", pag[max(0, p - 200):p + 500].replace("\n", " "))
