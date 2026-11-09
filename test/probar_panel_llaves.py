"""MILLER · Prueba de la página MILLER (una barra de espacio, dos tarjetas de llave, PURGAR y SELLAR) con un Tk falso:
no necesita tkinter. Trabaja en una carpeta temporal: no toca los datos reales ni el código sellado."""
import sys as _sys
import os
import shutil
import tempfile
import time
import types
from pathlib import Path as _Path

RAIZ = _Path(__file__).resolve().parent.parent
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
TEMPORAL = _Path(tempfile.mkdtemp(prefix="miller_panel_"))
(TEMPORAL / "seguridad").mkdir()
os.environ["MILLER_DIR_SEGURIDAD"] = str(TEMPORAL / "seguridad")
fallos = []


def comprobar(condicion, mensaje):
    print(("  OK    " if condicion else "  FALLO ") + mensaje)
    if not condicion:
        fallos.append(mensaje)


import configuracion  # noqa: E402
from utilidades import acceso, purga, seguridad  # noqa: E402
from interfaz import panel as pn  # noqa: E402

acceso.RUTA = TEMPORAL / "acceso.json"
base = TEMPORAL / "miller"
for carpeta in ("audios", "cerebro"):
    (base / carpeta).mkdir(parents=True)
(base / "audios" / "cancion.mp3").write_bytes(b"x" * 3000)
configuracion.RUTA_BASE = base
import ayuda_llave_boy  # noqa: E402
import ayuda_llave_pro  # noqa: E402
llaves = {"pro": ayuda_llave_pro.preparar()}
llaves["boy"] = ayuda_llave_boy.preparar()   # llave BOY de prueba
from utilidades import nombre as nombre_asistente  # noqa: E402
configuracion.RUTA_NOMBRE_ASISTENTE = TEMPORAL / "nombre_ya_puesto.json"
nombre_asistente.fijar("Ana")      # en las secciones 1 a 12 el nombre ya está puesto (no sale la página de primera vez)


class Widget:
    """Lo mínimo de un widget de Tk: guarda opciones, si está empaquetado, su texto o su valor."""
    visible = False

    def __init__(self, master=None, **kw):
        self.kw, self.valor, self.desplazado = dict(kw), "", None

    def pack(self, *a, **k):
        self.visible = True

    def pack_forget(self):
        self.visible = False

    def configure(self, **kw):
        self.kw.update(kw)

    def get(self):
        return self.valor

    def delete(self, inicio, fin=None):
        self.valor = ""

    def insert(self, *a):
        pass

    def index(self, *a):
        return "1.0"

    def set(self, *a):
        pass

    def yview(self, *a):
        pass

    def yview_scroll(self, paso, unidad):
        self.desplazado = (paso, unidad)

    def itemconfigure(self, *a, **k):
        pass

    def update_idletasks(self):
        pass

    def winfo_width(self):
        return 300

    def winfo_height(self):
        return 90

    def winfo_reqheight(self):
        return 210

    def winfo_children(self):
        return []

    def after(self, ms, fn):
        pass

    def invoke(self):
        self.kw["command"]()

    def __getattr__(self, nombre):
        if nombre.startswith(("create_", "tag_", "see", "bind", "focus", "pack_propagate")):
            return lambda *a, **k: None
        raise AttributeError(nombre)


tk = types.SimpleNamespace(Frame=Widget, Button=Widget, Label=Widget, Entry=Widget, Text=Widget, Canvas=Widget,
                           Scrollbar=Widget)


def esperar(condicion, segundos=5.0):
    fin = time.time() + segundos
    while time.time() < fin:
        if condicion():
            return True
        time.sleep(0.05)
    return False


terminal_lineas = []     # lo que llega a la TERMINAL de la ventana (la ventana lo anota aquí)
destellos = []           # tarjetas que destellan en rojo


def procesar_cola():
    """Atiende los mensajes de la cola, como haría la ventana."""
    for _ in range(500):
        if p.cola.empty():
            return
        p._atender_cola()


def esperar_terminal(texto, segundos=5.0):
    """Espera a que la TERMINAL reciba una línea con ese texto (los hilos escriben en la cola)."""
    fin = time.time() + segundos
    while time.time() < fin:
        procesar_cola()
        if any(texto in linea for linea in terminal_lineas):
            return True
        time.sleep(0.05)
    return False


def textos_de_la_ventana():
    """Lo que se lee en la página MILLER: etiquetas y botones (no las casillas de llave)."""
    widgets = [p.plan_llave, p.descripcion_llave, p.espacio_texto, p.disco_llave, p.boton_purgar, p.boton_sellar]
    for tarjeta in p._tarjetas.values():
        widgets += [tarjeta["pregunta"], tarjeta["estado"], tarjeta["enviar"]]
    return " | ".join(str(w.kw.get("text", "")) for w in widgets)


print("1. Estructura: perfil arriba, una sola barra y dos tarjetas compactas")
cierres = []
p = pn.PanelInteraccion(tk, Widget(), 330, 210, al_cerrar=lambda: cierres.append(1),
                          al_purgar=lambda: cierres.append(1))
p._anadir = lambda widget, linea, etiqueta=None: terminal_lineas.append(linea)   # la TERMINAL solo se anota
p._destellar_tarjeta = lambda plan: destellos.append(plan)                        # el destello solo se anota
comprobar(p.botones["llaves"].kw["text"].endswith("MILLER"), "el botón de la ventana se llama MILLER")
comprobar(p.boton_purgar.kw["text"] == "PURGAR" and p.boton_sellar.kw["text"] == "SELLAR",
          "arriba hay dos acciones: PURGAR y SELLAR")
comprobar(hasattr(p, "espacio_barra") and not hasattr(p, "disco_barra"), "hay una sola barra de progreso")
comprobar(set(p._tarjetas) == {"boy", "pro"}, "hay una tarjeta para la llave NIÑOS y otra para la PRO")
comprobar(p._tarjetas["boy"]["pregunta"].kw["text"] == "ingresa clave boy", "la tarjeta 1 pide: ingresa clave boy")
comprobar(p._tarjetas["pro"]["pregunta"].kw["text"] == "ingresa clave pro", "la tarjeta 2 pide: ingresa clave pro")
comprobar(p._tarjetas["boy"]["entrada"].kw["show"] == "•", "lo que se escribe en la casilla se oculta (•)")
comprobar(p._tarjetas["boy"]["entrada"].visible and p._tarjetas["pro"]["entrada"].visible,
          "al empezar, cada tarjeta enseña su casilla")
comprobar(not any("retirar" in t or "barras" in t for t in p._tarjetas.values()),
          "no hay RETIRAR ni barras dentro de las tarjetas")
comprobar("yscrollcommand" in p.lienzo_llaves.kw and "command" in p.barra_llaves.kw,
          "las tarjetas están en una zona con desplazamiento y barra")

print("2. Espacio: la única barra cuenta lo consumido según la llave que manda")
p.mostrar("llaves")
comprobar(p.actual == "llaves", "la página MILLER se abre")
comprobar(p.plan_llave.kw["text"] == "Plan actual: FREE", "sin llaves el plan es FREE")
comprobar(esperar(lambda: p._instantanea is not None), "la medición del espacio llega en segundo plano")
p._refrescar_llaves()
comprobar(p.espacio_texto.kw["text"].startswith("Consumido (FREE)"), "la barra dice lo consumido en el modo FREE")
comprobar("de 2.0 GB" in p.espacio_texto.kw["text"], "el tope FREE es 1 GB asistente + 1 GB archivos = 2.0 GB")
comprobar(p.disco_llave.kw["text"].startswith("Disco:"), "debajo de la barra, el disco libre y total")
fraccion = p.espacio_barra.dato[0]
comprobar(0.0 <= fraccion <= 1.0, "la barra se dibuja entre 0 y 100 %")

print("3. Una clave incorrecta: la casilla se vacía, la tarjeta destella y la respuesta va a la TERMINAL")
p._tarjetas["boy"]["entrada"].valor = "ABCD-EFGH-IJKL-MNOP"
p._tarjetas["boy"]["enviar"].invoke()
comprobar(p._tarjetas["boy"]["entrada"].valor == "", "al enviar, la casilla se vacía al instante")
comprobar(esperar(lambda: not p._comprobando), "la comprobación termina en segundo plano")
procesar_cola()
comprobar(esperar_terminal("Negativo"), "la respuesta (Negativo) llega a la TERMINAL")
comprobar(destellos == ["boy"], "la tarjeta NIÑOS destella en rojo")
pn.PanelInteraccion._destellar_tarjeta(p, "pro")
comprobar(p._tarjetas["pro"]["marco"].kw["highlightbackground"] == pn.ROJO, "el destello pone el borde en rojo")
comprobar(p._tarjetas["boy"]["entrada"].visible and not p._tarjetas["boy"]["estado"].visible,
          "la tarjeta NIÑOS sigue pidiendo la clave")
comprobar(p._tarjetas["boy"]["marco"].kw["bg"] == pn.TARJETA_LIBRE, "la tarjeta NIÑOS no cambia de color")
comprobar(p.actual == "llaves", "una clave mala no cambia de página")
comprobar(not any(palabra in textos_de_la_ventana() for palabra in ("Negativo", "Afirmativo", "Comprobando")),
          "en la página MILLER no aparece ninguna respuesta")

print("4. Una llave de otro plan se rechaza en la casilla equivocada")
p._tarjetas["pro"]["entrada"].valor = llaves["boy"]
p._tarjetas["pro"]["enviar"].invoke()
comprobar(esperar(lambda: not p._comprobando), "la comprobación termina")
comprobar("pro" not in acceso.activas(), "la llave NIÑOS no entra en la tarjeta PRO")
comprobar("no va en esta casilla" in acceso.ultimo_aviso(), "el aviso dice que esa llave va en otra casilla")
comprobar(esperar_terminal("no va en esta casilla"), "la TERMINAL dice que esa llave va en otra casilla")

print("5. La clave de NIÑOS: la tarjeta se pone verde y ya no pide nada")
p._tarjetas["boy"]["entrada"].valor = llaves["boy"]
p._tarjetas["boy"]["enviar"].invoke()
comprobar(esperar(lambda: "boy" in acceso.activas()), "la llave NIÑOS queda puesta")
comprobar(esperar_terminal("Afirmativo"), "la TERMINAL confirma la llave NIÑOS")
esperar(lambda: not p._comprobando)            # el hilo termina del todo (ya anotó su respuesta)
p._refrescar_llaves()
boy = p._tarjetas["boy"]
comprobar(not boy["entrada"].visible and not boy["pregunta"].visible and not boy["enviar"].visible,
          "la tarjeta NIÑOS ya no muestra casilla ni pide clave")
comprobar(boy["estado"].visible and "LLAVE 1 · NIÑOS" in boy["estado"].kw["text"] and "PUESTA" in boy["estado"].kw["text"],
          "la tarjeta NIÑOS dice que la llave está puesta")
comprobar(boy["marco"].kw["bg"] == pn.TARJETA_PUESTA, "la tarjeta NIÑOS se pone verde")
comprobar(p._tarjetas["pro"]["entrada"].visible and p._tarjetas["pro"]["marco"].kw["bg"] == pn.TARJETA_LIBRE,
          "la tarjeta PRO sigue pidiendo su clave y sin color")
comprobar(p.plan_llave.kw["text"] == "Plan actual: NIÑOS", "el plan de arriba pasa a NIÑOS")
comprobar(p.espacio_texto.kw["text"].startswith("Consumido (NIÑOS)") and "de 10.0 GB" in p.espacio_texto.kw["text"],
          "la barra pasa al tope NIÑOS (2 GB + 8 GB = 10.0 GB)")
comprobar(p.botones["llaves"].kw["text"].endswith("●") and p._avatar_hay is True,
          "el botón MILLER y el avatar marcan que hay una llave puesta")

print("6. El registro es único: una llave puesta no vuelve a pedir clave")
boy["entrada"].valor = "OTRA-CLAVE"
p._aplicar_llave("boy")
comprobar(not p._comprobando, "enviar en la tarjeta verde no comprueba nada")
comprobar(not boy["entrada"].visible, "la casilla no vuelve a aparecer")
comprobar("boy" in acceso.activas(), "la llave NIÑOS sigue puesta")

print("7. SELLAR solo con llave PRO: la respuesta va a la TERMINAL y la ventana pasa a esa página")
llamadas_sello = []
sellar_original = seguridad.sellar_codigo
seguridad.sellar_codigo = lambda raiz=None: llamadas_sello.append(1) or 7
p._pulsar_sellar()
comprobar(esperar_terminal("modo PRO"), "con NIÑOS puesta, SELLAR dice en la TERMINAL que es del modo PRO")
comprobar(esperar_terminal("ventana MILLER"), "el aviso indica la ventana MILLER para poner la llave")
comprobar(p.actual == "terminal", "la ventana pasa a la página TERMINAL para ver la respuesta")
comprobar(not llamadas_sello, "con NIÑOS puesta, SELLAR no sella el código")
comprobar("modo PRO" not in textos_de_la_ventana(), "el aviso no aparece en la página MILLER")

print("8. La clave PRO: las dos llaves a la vez")
p.mostrar("llaves")
p._tarjetas["pro"]["entrada"].valor = llaves["pro"]
p._tarjetas["pro"]["enviar"].invoke()
comprobar(esperar(lambda: "pro" in acceso.activas()), "la llave PRO queda puesta en su tarjeta")
p._refrescar_llaves()
comprobar(not p._tarjetas["pro"]["entrada"].visible and p._tarjetas["pro"]["marco"].kw["bg"] == pn.TARJETA_PUESTA,
          "la tarjeta PRO se pone verde y sin casilla")
comprobar(p.plan_llave.kw["text"] == "Plan actual: PRO", "con las dos llaves el plan es PRO")
comprobar(p.espacio_texto.kw["text"].startswith("Consumido (PRO)"), "la barra pasa al modo PRO")

print("9. SELLAR con llave PRO sella el código en segundo plano y lo dice en la TERMINAL")
p._pulsar_sellar()
comprobar(esperar(lambda: not p._sellando), "el sellado termina en segundo plano")
comprobar(esperar_terminal("Código sellado"), "la TERMINAL dice que el código quedó sellado")
comprobar(llamadas_sello == [1], "el código se sella una vez")
comprobar(esperar_terminal("7 archivos"), "la TERMINAL dice cuántos archivos se sellaron")
comprobar("Código sellado" not in textos_de_la_ventana(), "el resultado no aparece en la página MILLER")
seguridad.sellar_codigo = sellar_original

print("10. PURGAR pide confirmación: la primera pulsación pone el botón en rojo sin escribir en él")
purga._pedida.clear()
p.boton_purgar.invoke()
comprobar(p.boton_purgar.kw["text"] == "PURGAR" and p.boton_purgar.kw["bg"] == pn.ROJO,
          "la primera pulsación pone PURGAR en rojo y no cambia su texto")
comprobar(esperar_terminal("Purga armada"), "la TERMINAL explica que hay que confirmar")
comprobar(not purga.pedida() and not cierres, "con una sola pulsación no se purga ni se cierra")
comprobar("SEGURO" not in textos_de_la_ventana(), "la ventana no escribe ¿SEGURO? en ningún sitio")
p._purga_armada = time.monotonic() - 60
p._desarmar_purga()
comprobar(p.boton_purgar.kw["bg"] == pn.VERDE_OSCURO, "si pasa el tiempo sin confirmar, el botón vuelve a su color")
comprobar(esperar_terminal("Purga cancelada"), "la TERMINAL dice que la purga se canceló")
p.boton_purgar.invoke()
p.boton_purgar.invoke()
comprobar(purga.pedida(), "la segunda pulsación pide la purga")
comprobar(cierres == [1], "y pide a MILLER el cierre tras la purga (sin cerrar la ventana aún)")
comprobar(esperar_terminal("Purga pedida"), "la TERMINAL avisa de que hay que reabrir MILLER para empezar de nuevo")
comprobar(any("nombre" in linea for linea in terminal_lineas if "Purga pedida" in linea),
          "la purga avisa de que también borra el nombre")
purga._pedida.clear()
p.mostrar("llaves")                    # vuelve a la página MILLER para las secciones siguientes

print("11. Desplazamiento con la rueda")
p._rueda_llaves(types.SimpleNamespace(delta=-120))
comprobar(p.lienzo_llaves.desplazado == (1, "units"), "la rueda hacia abajo baja las tarjetas")
p._rueda_llaves(types.SimpleNamespace(delta=120))
comprobar(p.lienzo_llaves.desplazado == (-1, "units"), "la rueda hacia arriba sube las tarjetas")
p._ajustar_scroll_llaves()
comprobar("scrollregion" in p.lienzo_llaves.kw, "la zona de desplazamiento se ajusta al alto de las tarjetas")
comprobar(p.lienzo_llaves.kw.get("height") == 150, "la zona de tarjetas pide su alto, con tope de 150 px")

print("12. Cerrar la página")
p.alternar("llaves")
comprobar(p.actual is None, "un segundo clic en MILLER cierra la página")
p.lienzo_llaves.desplazado = None
p._rueda_llaves(types.SimpleNamespace(delta=-120))
comprobar(p.lienzo_llaves.desplazado is None, "con la página cerrada la rueda no mueve nada")

print("13. Primera vez: el nombre se pone en la página INSTALACIÓN (saludo, ENVIAR, Enter; vacío = Miller)")


def arrancar_panel(ruta):
    """Un panel nuevo con ese archivo de nombre; devuelve el panel y lo que se anota en la TERMINAL."""
    configuracion.RUTA_NOMBRE_ASISTENTE = ruta
    lineas = []
    q = pn.PanelInteraccion(tk, Widget(), 330, 210)
    q._anadir = lambda widget, linea, etiqueta=None: lineas.append(linea)
    q._destellar_tarjeta = lambda plan: None
    return q, lineas


def atender(q, segundos=5.0):
    """Atiende la cola de la ventana hasta que el guardado del nombre (otro hilo) haya contestado."""
    fin = time.time() + segundos
    while time.time() < fin:
        q._atender_cola()
        if not q._nombrando and q.cola.empty():
            return
        time.sleep(0.05)


q1, lineas1 = arrancar_panel(TEMPORAL / "nombre_primera_vez.json")
comprobar(q1.nombre_pendiente, "sin nombre guardado, el panel sabe que es la primera vez")
atender(q1)
comprobar(q1.actual == "instalacion", "la primera vez se abre sola la página INSTALACIÓN")
comprobar(q1.bloque_nombre.visible, "y en ella se ve el campo del nombre")
comprobar(any("Buenas, señor" in linea for linea in lineas1), "MILLER saluda en la TERMINAL")
q1.entrada_nombre.valor = "M1"
q1._enviar_nombre()                                   # Enter con un nombre que no vale
atender(q1)
comprobar(not nombre_asistente.fijado(), "un nombre no válido no se guarda")
comprobar(any(linea.startswith("MILLER: Negativo.") for linea in lineas1), "y MILLER lo dice en la TERMINAL")
comprobar(q1.bloque_nombre.visible, "el campo sigue visible para corregirlo")
q1.entrada_nombre.valor = "  Ana  "
q1.boton_nombre.invoke()                              # ENVIAR
atender(q1)
comprobar(nombre_asistente.fijado() and nombre_asistente.clave() == "Ana",
          "con ENVIAR y un nombre válido, queda guardado")
comprobar(not q1.bloque_nombre.visible and not q1.nombre_pendiente, "al quedar fijado, el campo desaparece")
comprobar(q1.actual == "terminal", "y se pasa a la TERMINAL")
comprobar(any("Afirmativo" in linea and "Ana" in linea for linea in lineas1), "MILLER confirma el nombre en la TERMINAL")
ok_otra, motivo = nombre_asistente.fijar("Luis")
comprobar(not ok_otra and "Solo se puede poner una vez" in motivo, "un segundo intento no cambia el nombre")

q2, lineas2 = arrancar_panel(TEMPORAL / "nombre_primera_vez.json")          # ya está guardado
comprobar(not q2.nombre_pendiente, "con el nombre guardado no hay primera vez")
atender(q2)
comprobar(q2.actual is None and not lineas2, "y no sale ni la página ni el saludo")

q3, lineas3 = arrancar_panel(TEMPORAL / "nombre_vacio.json")
atender(q3)
q3.entrada_nombre.valor = ""
q3.boton_nombre.invoke()                              # ENVIAR con el campo vacío
atender(q3)
comprobar(nombre_asistente.fijado() and nombre_asistente.clave() == "Miller",
          "con el campo vacío, el nombre queda Miller")

shutil.rmtree(TEMPORAL, ignore_errors=True)
print()
if fallos:
    print(f"FALLARON {len(fallos)} comprobaciones:")
    for f in fallos:
        print("  -", f)
    raise SystemExit(1)
print("Todas las comprobaciones de la página MILLER pasaron.")
