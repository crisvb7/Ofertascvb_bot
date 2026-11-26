"""Grupo aparte para las piezas de PC («PC Components») y la regla de segunda mano frente a nueva."""
import pytest

from conftest import AvisadorFalso
from ofertas.avisos import Aviso, Avisador
from ofertas.modelos import Anuncio

from test_grupo import tg
from test_motor import pasada, wp

PRINCIPAL, PIEZAS = "-100123", "-100999"


def chollo(id_, titulo, precio):
    return Anuncio(fuente="chollometro", id=id_, titulo=titulo, precio=precio,
                   url=f"https://www.chollometro.com/ofertas/x-{id_}", nuevo=True, tienda="PcComponentes")


@pytest.fixture
def motor_y_av(cfg, estado):
    from ofertas.motor import Motor
    av = AvisadorFalso(con_grupo=True)
    for p in cfg.productos:          # precios fijos para los tests
        if p.nombre == "RX 9070 XT":
            p.usado_min, p.usado_max, p.nuevo_min, p.nuevo_max, p.tope, p.precio_nuevo = 450, 600, 550, 680, 900, 659
    return Motor(cfg, estado, av, pausa=(0, 0)), av


# --- configuración -----------------------------------------------------------------------

def test_config_grupo_de_piezas(cfg):
    assert cfg.telegram_nombre_grupo_pc == "PC Components"
    assert cfg.rebaja_minima_usado == 0.15
    piezas = {p.nombre: p for p in cfg.productos if p.es_componente}
    assert {"Fuente 850W Gold", "Disipador doble torre", "SSD NVMe 1TB"} <= set(piezas)
    for p in piezas.values():                      # todas saben cuánto cuestan nuevas
        assert p.precio_nuevo and p.precio_nuevo <= p.tope, p.nombre


@pytest.mark.parametrize("producto,titulo,es", [
    ("Fuente 850W Gold", "Corsair RM850x 850W 80 Plus Gold", True),
    ("Fuente 850W Gold", "Seasonic Focus GX-1000 1000W Gold", True),
    ("Fuente 850W Gold", "Fuente 750W Gold", False),
    ("Fuente 850W Gold", "Fuente 850W Bronze", False),
    ("Fuente 850W Gold", "Cable 12VHPWR para fuente 850W Gold", False),
    ("Fuente 850W Gold", "SAI 850W Gold", False),
    ("Disipador doble torre", "Ventilador CPU Thermalright Peerless Assassin 120 SE ARGB", True),
    ("Disipador doble torre", "Disipador Deepcool AK620", True),
    ("Disipador doble torre", "Soporte AM5 Peerless Assassin", False),
    ("SSD NVMe 1TB", "Samsung 990 EVO Plus 1TB NVMe", True),
    ("SSD NVMe 1TB", "Kingston NV3 1TB PCIe 4.0", True),
    ("SSD NVMe 1TB", "SSD NVMe 2TB Samsung 990 Pro", False),
    ("SSD NVMe 1TB", "SSD SATA 1TB Crucial MX500", False),
    ("SSD NVMe 1TB", "SSD externo 1TB USB-C", False),
    ("SSD NVMe 1TB", "PS5 Slim 1TB", False),
])
def test_clasifica_el_resto_del_pc(cfg, producto, titulo, es):
    assert (cfg.producto(producto).clasificar(wp("1", titulo, 50))[0] == "consola") is es


# --- el Avisador con dos grupos ------------------------------------------------------------

def test_piezas_van_al_grupo_de_piezas_y_consolas_al_principal(monkeypatch, estado):
    t = tg([{"ok": True, "result": {"message_thread_id": 40}},      # crea el tema de la pieza
            {"ok": True, "result": {"message_id": 1}},                # oferta de la pieza
            {"ok": True, "result": {"message_id": 2}}], monkeypatch)  # oferta de consola
    av = Avisador([], telegram=t, grupo_id=PRINCIPAL, estado=estado, temas={"usada_oferton": 3},
                  grupo_pc_id=PIEZAS)
    ref = av.enviar_oferta(Aviso("<b>RX</b>", "RX"), "pc_rx-9070-xt")
    assert ref["chat_id"] == PIEZAS
    ref = av.enviar_oferta(Aviso("<b>PS5</b>", "PS5"), "usada_oferton")
    assert ref["chat_id"] == PRINCIPAL
    (m1, d1), (m2, d2), (m3, d3) = t.s.llamadas
    assert m1 == "createForumTopic" and d1["chat_id"] == PIEZAS
    assert d2["chat_id"] == PIEZAS and d2["message_thread_id"] == 40
    assert d3["chat_id"] == PRINCIPAL and d3["message_thread_id"] == 3
    assert estado.leer(f"tema:{PIEZAS}:pc_rx-9070-xt") == "40"


def test_temas_fijados_de_cada_grupo(monkeypatch, estado):
    t = tg([], monkeypatch)
    av = Avisador([], telegram=t, grupo_id=PRINCIPAL, estado=estado,
                  temas={"pc_rx-9070": 3124}, grupo_pc_id=PIEZAS, temas_pc={"pc_rx-9070": 7})
    assert av.tema("pc_rx-9070") == 7                 # el del grupo de piezas, no el del principal
    sin_pc = Avisador([], telegram=t, grupo_id=PRINCIPAL, estado=estado, temas={"pc_rx-9070": 3124})
    assert sin_pc.tema("pc_rx-9070") == 3124          # sin grupo de piezas, todo sigue como antes


def test_indice_movido_solo_edita_el_que_habia(monkeypatch, estado):
    t = tg([{"ok": True, "result": True}], monkeypatch)
    av = Avisador([], telegram=t, grupo_id=PRINCIPAL, estado=estado, grupo_pc_id=PIEZAS)
    av.indice_movido("pc_rx-9070", "➡️ movido")        # no había índice: no hace nada
    assert t.s.llamadas == []
    estado.guardar(f"indice:{PRINCIPAL}:pc_rx-9070", 55)
    av.indice_movido("pc_rx-9070", "➡️ movido")
    av.indice_movido("pc_rx-9070", "➡️ movido")        # mismo texto: no repite
    assert [(m, d["message_id"]) for m, d in t.s.llamadas] == [("editMessageText", 55)]


# --- buscar el grupo por su nombre ---------------------------------------------------------

class TelegramChats:
    def __init__(self, chats):
        self._chats, self.veces = chats, 0

    def chats(self):
        self.veces += 1
        return self._chats


def test_encuentra_el_grupo_por_nombre(motor_y_av, estado):
    motor, av = motor_y_av
    av.telegram = TelegramChats([
        {"id": PRINCIPAL, "nombre": "Ofertas", "tipo": "supergroup", "foro": True},
        {"id": "655", "nombre": "Cristian", "tipo": "private", "foro": False},
        {"id": PIEZAS, "nombre": "PC Components", "tipo": "supergroup", "foro": True}])
    motor._estrenar_grupo()
    assert av.grupo_pc_id == PIEZAS and estado.leer("grupo_pc_id") == PIEZAS
    assert any("PC Components" in a.texto and "✅" in a.texto for a in av.avisos)


def test_grupo_sin_temas_avisa_una_vez(motor_y_av, estado):
    motor, av = motor_y_av
    av.telegram = TelegramChats([{"id": PIEZAS, "nombre": "PC componentes", "tipo": "group", "foro": False}])
    motor._buscar_grupo_pc()
    estado.guardar("grupo_pc_busqueda", 0)          # pasan 10 minutos
    motor._buscar_grupo_pc()
    assert av.grupo_pc_id is None and av.telegram.veces == 2
    assert len([a for a in av.avisos if "temas activados" in a.texto]) == 1


def test_busca_como_mucho_cada_10_minutos(motor_y_av):
    motor, av = motor_y_av
    av.telegram = TelegramChats([])
    motor._buscar_grupo_pc()
    motor._buscar_grupo_pc()
    assert av.telegram.veces == 1


# --- traslado de lo ya publicado -----------------------------------------------------------

def test_al_estrenar_el_grupo_de_piezas_se_mudan_sus_ofertas(motor_y_av, cfg, estado):
    motor, av = motor_y_av
    gpu, ps5 = cfg.producto("RX 9070 XT"), cfg.producto("PS5")
    pasada(motor, [wp("g", "Sapphire Pulse RX 9070 XT", 540)], gpu)
    pasada(motor, [wp("p", "PS5 Slim", 360)], ps5)
    assert len(av.avisos) == 2
    estado.guardar(f"grupo_estrenado:{PRINCIPAL}", "1")     # el grupo principal ya estaba estrenado
    av.grupo_pc_id = PIEZAS
    av.enviar_oferta = lambda aviso, cat, _f=av.enviar_oferta: {**_f(aviso, cat),
                                                               "chat_id": PIEZAS if cat.startswith("pc_") else PRINCIPAL}
    motor._estrenar_grupo()
    pasada(motor, [wp("g", "Sapphire Pulse RX 9070 XT", 540)], gpu)
    pasada(motor, [wp("p", "PS5 Slim", 360)], ps5)          # la consola no se reenvía
    assert av.categorias == ["pc_rx-9070-xt", "usada_oferton", "pc_rx-9070-xt"]
    assert av.borrados == [1]                                # el aviso viejo de la gráfica, fuera
    assert estado.mensaje("wallapop:g")["chat_id"] == PIEZAS
    motor._actualizar_indices()
    assert "pasado al grupo «PC Components»" in av.movidos["pc_rx-9070-xt"]


# --- segunda mano frente a nueva -----------------------------------------------------------

def test_usada_casi_al_precio_de_nueva_no_se_manda(motor_y_av, cfg):
    motor, av = motor_y_av
    gpu = cfg.producto("RX 9070 XT")                 # nueva: 659 € → usada hasta 560 €
    pasada(motor, [wp("a", "RX 9070 XT", 540), wp("b", "RX 9070 XT", 575), wp("c", "RX 9070 XT", 700)], gpu)
    assert len(av.avisos) == 1 and "540" in av.avisos[0].texto


def test_la_nueva_mas_barata_vista_manda(motor_y_av, cfg):
    motor, av = motor_y_av
    gpu = cfg.producto("RX 9070 XT")
    pasada(motor, [chollo("n", "Sapphire Pulse RX 9070 XT 16GB", 600)], gpu, fuente="chollometro")
    assert motor.precio_nuevo(gpu) == 600            # baja de 659 € a lo visto en Chollometro
    av.avisos.clear()
    pasada(motor, [wp("a", "RX 9070 XT", 500), wp("b", "RX 9070 XT", 540)], gpu)
    assert len(av.avisos) == 1 and "500" in av.avisos[0].texto     # 540 > 600 × 0,85


def test_la_regla_no_toca_las_consolas(motor_y_av, cfg):
    motor, av = motor_y_av
    ps5 = cfg.producto("PS5")
    ps5.precio_nuevo = 380
    pasada(motor, [wp("p", "PS5 Slim", 370)], ps5)
    assert len(av.avisos) == 1


def test_mientras_no_existe_el_grupo_las_piezas_nuevas_van_a_tu_chat(monkeypatch, estado):
    t = tg([{"ok": True, "result": {"message_id": 5}},                # pieza con tema: al grupo
            {"ok": True, "result": {"message_id": 6}}], monkeypatch)  # pieza sin tema: a tu chat
    av = Avisador([], telegram=t, grupo_id=PRINCIPAL, estado=estado, temas={"pc_rx-9070": 3124},
                  espera_grupo_pc=True)
    assert av.enviar_oferta(Aviso("a", "a"), "pc_rx-9070")["chat_id"] == PRINCIPAL
    assert av.enviar_oferta(Aviso("b", "b"), "pc_ryzen-7-9800x3d")["chat_id"] == "655"
    av.indice("pc_ryzen-7-9800x3d", "índice")                       # ni tema ni índice en el principal
    assert av.tema("pc_ryzen-7-9800x3d") is None
    assert [m for m, _ in t.s.llamadas] == ["sendMessage", "sendMessage"]
    av.grupo_pc_id = PIEZAS                                          # ya existe: se crean allí
    t.s.respuestas = [{"ok": True, "result": {"message_thread_id": 9}}]
    assert av.tema("pc_ryzen-7-9800x3d") == 9 and t.s.llamadas[-1][1]["chat_id"] == PIEZAS


# --- compatibilidad ------------------------------------------------------------------------

def test_mensaje_de_placa_usada_lleva_la_compatibilidad(motor_y_av, cfg):
    motor, av = motor_y_av
    placa = cfg.producto("Placa B650/B850")
    placa.precio_nuevo = None
    pasada(motor, [wp("p", "ASUS Prime B650M-A WiFi II", 90)], placa)
    texto = av.avisos[0].texto
    assert "🔧 Compatibilidad" in texto and "va con el 9800X3D" in texto
    assert "Pregunta qué BIOS tiene" in texto and "botón BIOS FlashBack" in texto


@pytest.mark.parametrize("producto,titulo,nuevo,desc,esta,no_esta", [
    ("Placa B650/B850", "Gigabyte B650 Eagle AX", True, "", "ya suele venir con BIOS", "Pregunta qué BIOS"),
    ("Placa B650/B850", "MSI PRO B650-P WiFi", False, "BIOS actualizada", "BIOS al día", "Pregunta qué BIOS"),
    ("DDR5 32GB", "Corsair Vengeance DDR5 6000MHz 32GB CL30 EXPO", True, "", "6000 MHz o más", "No dice la velocidad"),
    ("DDR5 32GB", "Kingston 32GB DDR5 4800", False, "", "rinde algo menos", "6000 MHz o más"),
    ("DDR5 32GB", "Memoria RAM DDR5 32GB", False, "", "No dice la velocidad", "EXPO"),
    ("RX 9070 XT", "Sapphire Nitro+ RX 9070 XT", False, "", "12V-2x6", "nada"),
    ("Fuente 850W Gold", "MSI MAG A850GL PCIE5 850W Gold", True, "", "ATX 3.x", "3 cables PCIe"),
    ("Fuente 850W Gold", "Corsair RM850 850W Gold", False, "", "3 cables PCIe", "ATX 3.x: trae"),
    ("SSD NVMe 1TB", "Crucial T705 1TB Gen5 NVMe", True, "", "PCIe 5.0", "CrystalDiskInfo"),
])
def test_notas_de_compatibilidad(cfg, producto, titulo, nuevo, desc, esta, no_esta):
    a = Anuncio(fuente="x", id="1", titulo=titulo, precio=1, url="u", nuevo=nuevo, descripcion=desc)
    notas = " | ".join(cfg.producto(producto).notas_compat(a))
    assert esta in notas and no_esta not in notas


def test_las_piezas_retiradas_avisan_en_su_indice(motor_y_av):
    motor, av = motor_y_av
    motor._actualizar_indices()
    assert set(av.retirados) == {"pc_ryzen-7-5700x3d", "pc_ryzen-7-5800x3d", "pc_ryzen-5-5600"}
    assert "no es compatible con el PC nuevo" in av.retirados["pc_ryzen-5-5600"]


@pytest.mark.parametrize("titulo,esperado", [
    ("ASUS Prime B650M-A WiFi II", "consola"),
    ("Gigabyte B650 Eagle AX", "consola"),
    ("MSI B850M Gaming Plus Wi-Fi", "consola"),
    ("Placa base WiFi 6E AM5 B650M", "consola"),
    ("ASUS Prime B650M-R", None),               # sin WiFi
    ("Gigabyte B650M D3HP sin wifi", None),
])
def test_placa_solo_con_wifi(cfg, titulo, esperado):
    assert cfg.producto("Placa B650/B850").clasificar(wp("1", titulo, 90))[0] == esperado
