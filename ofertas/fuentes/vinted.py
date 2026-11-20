"""Vinted: API interna del catálogo. Necesita la cookie anónima que pone su portada."""
from __future__ import annotations

from ..modelos import Anuncio
from ..red import Bloqueado
from ..utiles import parsear_precio


class Vinted:
    def __init__(self, sesion, dominio: str = "www.vinted.es"):
        self.s = sesion
        self.base = f"https://{dominio}"
        self._listo = False

    def _arrancar(self) -> None:
        """Visita la portada para recibir la cookie access_token_web."""
        r = self.s.get(self.base + "/", timeout=20,
                       headers={"Accept": "text/html,application/xhtml+xml"})
        if r.status_code in (403, 429):
            raise Bloqueado(f"Vinted (portada) respondió {r.status_code}")
        self._listo = True

    def buscar(self, consulta: str, precio_min: float | None = None,
               por_pagina: int = 48) -> list[Anuncio]:
        if not self._listo:
            self._arrancar()
        params = {"search_text": consulta, "order": "newest_first",
                  "per_page": por_pagina, "page": 1}
        if precio_min:
            params.update(price_from=int(precio_min), currency="EUR")
        cabeceras = {"Accept": "application/json, text/plain, */*",
                     "Referer": f"{self.base}/catalog"}
        r = None
        for intento in range(2):
            r = self.s.get(self.base + "/api/v2/catalog/items", params=params,
                           headers=cabeceras, timeout=20)
            if r.status_code == 401 and intento == 0:   # cookie caducada: renovar
                self._arrancar()
                continue
            break
        if r.status_code in (401, 403, 429):
            self._listo = False
            raise Bloqueado(f"Vinted respondió {r.status_code}")
        r.raise_for_status()
        items = r.json().get("items") or []
        return [a for a in (self.a_anuncio(it) for it in items) if a]

    def a_anuncio(self, it: dict) -> Anuncio | None:
        if not isinstance(it, dict) or "id" not in it:
            return None
        url = it.get("url") or f"{self.base}/items/{it['id']}"
        if url.startswith("/"):
            url = self.base + url
        foto = it.get("photo") or {}
        return Anuncio(
            fuente="vinted",
            id=str(it["id"]),
            titulo=(it.get("title") or "").strip(),
            precio=_precio(it.get("price")),
            url=url,
            descripcion=it.get("description") or "",
            imagen=foto.get("url") if isinstance(foto, dict) else None,
            envio=True,
            reservado=bool(it.get("is_reserved") or it.get("reserved")),
            estado=it.get("status") if isinstance(it.get("status"), str) else None,
            precio_total=_precio(it.get("total_item_price")),
        )


def _precio(valor) -> float | None:
    if isinstance(valor, dict):
        valor = valor.get("amount")
    return parsear_precio(valor)
