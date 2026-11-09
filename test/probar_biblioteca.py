"""Prueba de la Biblioteca musical: plantilla de tarjeta y acciones de cola, reproducción y papelera.
No necesita Tkinter ni audio: los objetos del reproductor y de los comandos son falsos.
Termina en OK o con FALLO."""
import sys as _sys
from pathlib import Path as _Path

RAIZ = _Path(__file__).resolve().parent.parent
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))

from interfaz import tarjeta_cancion as t  # noqa: E402
from interfaz import acciones_audio as a  # noqa: E402

fallos = 0


def comprobar(nombre, condicion):
    global fallos
    if condicion:
        print(f"OK     {nombre}")
    else:
        fallos += 1
        print(f"FALLO  {nombre}")


class Falso:
    def __init__(self, **atributos):
        self.__dict__.update(atributos)


class ReproductorFalso:
    def __init__(self, cola=(), actual=None):
        self.cola = [_Path(p) for p in cola]
        self.cancion_actual = _Path(actual) if actual else None
        self.reproduciendo = self.cancion_actual is not None     # como el reproductor real
        self.pausado = False
        self.reproducidas = []

    def agregar_archivo_a_cola(self, ruta):
        self.cola.append(_Path(ruta))
        return True

    def eliminar_de_cola(self, posicion):
        if 1 <= posicion <= len(self.cola):
            del self.cola[posicion - 1]
            return True
        return False

    def reproducir(self, nombre):
        self.reproducidas.append(nombre)
        return True


class ComandosFalsos:
    def __init__(self, respuesta="Afirmativo. a.mp3 a la papelera. Recuperable."):
        self.llamadas, self.respuesta = [], respuesta

    def enviar_a_papelera(self, ruta):
        self.llamadas.append(str(ruta))
        return self.respuesta


CANCION = {"nombre": "a.mp3", "ruta": _Path("audios/a.mp3"), "carpeta": False}
CARPETA = {"nombre": "discos", "ruta": _Path("audios/discos"), "carpeta": True}

# ---------------------------------------------------------------- plantilla de tarjeta (sin ventana)
comprobar("canción: reproducir, cola, copiar y papelera",
          [c for c, _ in t.botones_de(CANCION)] == ["reproducir", "cola", "copiar", "papelera"])
comprobar("carpeta: solo abrir", t.botones_de(CARPETA) == (("abrir", "Abrir"),))
comprobar("cola sin canción en ella dice A la cola", t.texto_boton_cola(None) == "A la cola")
comprobar("cola con canción en ella dice Quitar cola", t.texto_boton_cola(2) == "Quitar cola")
comprobar("el botón de cola cambia con la cola",
          dict(t.botones_de(CANCION, 3))["cola"] == "Quitar cola")
comprobar("insignias: sonando y puesto en la cola",
          t.insignias({"sonando": True, "en_cola": 4}) == ["SONANDO", "COLA 4"])
comprobar("insignias vacías si no suena ni está en cola", t.insignias({}) == [])

# ---------------------------------------------------------------- acciones de la biblioteca
rf = ReproductorFalso(cola=["audios/x.mp3", "audios/a.mp3"], actual="audios/x.mp3")
acc = a.AccionesAudio(ComandosFalsos(), informar=None)
acc.reproductor = rf
comprobar("posición en la cola (1 = primera)", acc.posicion_en_cola(CANCION["ruta"]) == 2)
comprobar("canción que no está en la cola", acc.posicion_en_cola("audios/nueva.mp3") is None)
comprobar("suena la canción actual", acc.sonando(_Path("audios/x.mp3")))
comprobar("no suena otra canción", not acc.sonando(CANCION["ruta"]))
rf.reproduciendo = False                                   # parada: cancion_actual sigue, pero ya no suena
comprobar("parada: la canción ya no se marca como sonando", not acc.sonando(_Path("audios/x.mp3")))
rf.reproduciendo, rf.pausado = True, True                  # en pausa: es la actual, pero no suena
comprobar("en pausa: no suena, pero está pausada",
          not acc.sonando(_Path("audios/x.mp3")) and acc.pausada(_Path("audios/x.mp3")))
comprobar("en pausa: la insignia dice PAUSADA", t.insignias({"pausada": True}) == ["PAUSADA"])
comprobar("info de tarjeta: pausada y no sonando", acc.info_de(_Path("audios/x.mp3"))["pausada"]
          and not acc.info_de(_Path("audios/x.mp3"))["sonando"])
comprobar("info de tarjeta: su puesto en la cola", acc.info_de(CANCION["ruta"])["en_cola"] == 2)
rf.reproduciendo, rf.pausado = True, False
firma_antes = acc.firma()
rf.agregar_archivo_a_cola("audios/firma.mp3")
comprobar("la firma cambia cuando cambia la cola", acc.firma() != firma_antes)

rf2 = ReproductorFalso(cola=["audios/x.mp3"])
acc2 = a.AccionesAudio(ComandosFalsos(), informar=None)
acc2.reproductor = rf2
avisos = []
acc2.prever = lambda: avisos.append(1)
acc2._anticipar(lambda e: dict(e, cola=e["cola"] + [str(_Path("audios/y.mp3"))]))
comprobar("la vista muestra la orden antes de que termine",
          len(acc2.estado_visible()["cola"]) == 2 and len(rf2.cola) == 1)
comprobar("se avisa a la ventana al anticipar", avisos == [1])
acc2._terminar(True)
comprobar("al terminar la vista vuelve a lo real", len(acc2.estado_visible()["cola"]) == 1)
comprobar("A la cola: la añade y lo dice",
          acc.texto_cola("audios/nueva.mp3") == "Afirmativo. nueva.mp3 en la cola, señor.")
comprobar("cola de nuevo: la quita y lo dice",
          acc.texto_cola("audios/nueva.mp3") == "Afirmativo. nueva.mp3 quitada de la cola, señor.")
comprobar("reproducir usa el reproductor por nombre",
          acc.texto_reproducir("audios/a.mp3") == "Afirmativo. Reproduciendo a.mp3, señor." and rf.reproducidas == ["a.mp3"])

comandos = ComandosFalsos()
acc_p = a.AccionesAudio(comandos)
comprobar("papelera pasa por el supervisor (enviar_a_papelera)",
          acc_p.texto_papelera(CANCION["ruta"]).startswith("Afirmativo") and comandos.llamadas == ["audios/a.mp3"])
comprobar("sin supervisor la papelera se niega",
          a.AccionesAudio(None).texto_papelera(CANCION["ruta"]).startswith("Negativo"))
comprobar("sin reproductor no se puede reproducir",
          a.AccionesAudio(comandos).texto_reproducir("a.mp3").startswith("Negativo"))

recibidas = []
acc_i = a.AccionesAudio(ComandosFalsos(), informar=recibidas.append)
acc_i.informar_texto("")
acc_i.informar_texto("hola")
comprobar("el texto vacío no se informa y el resto sí", recibidas == ["hola"])

# ---------------------------------------------------------------- selección y clasificación en el explorador
from interfaz import explorador as explorador_mod  # noqa: E402


class Gancho:
    """Hace de widget sin ventana: acepta focus_set, configure y los métodos que usa la selección."""
    def focus_set(self):
        pass

    def configure(self, **_kw):
        pass


def entrada(nombre, carpeta=False):
    return {"nombre": nombre, "ruta": _Path("audios") / nombre, "carpeta": carpeta, "tipo": "Audio",
            "tamano": 1000, "modificado": "ayer"}


e1, e2, e3 = entrada("a.mp3"), entrada("b.mp3"), entrada("c.mp3")
vista = explorador_mod.ExploradorArchivos.__new__(explorador_mod.ExploradorArchivos)
vista.base, vista.actual = _Path("audios"), None
vista._entradas = [e1, e2, e3]
vista._modo_tarjetas, vista._marcos = True, []
vista._sel_rutas, vista._ancla_ruta = set(), None
vista.t = {"VERDE": "#2ee86a", "VERDE_OSCURO": "#0b2a12"}
vista.lienzo_tarjetas, vista.estado = Gancho(), Gancho()
vista.audio = a.AccionesAudio(ComandosFalsos())
vista.audio.reproductor = ReproductorFalso(cola=["audios/b.mp3"], actual="audios/a.mp3")


def clic(estado=0):
    return Falso(state=estado)


vista._seleccionar_tarjeta(e2, clic())
comprobar("clic selecciona solo una tarjeta", [x["nombre"] for x in vista._seleccionadas()] == ["b.mp3"])
vista._seleccionar_tarjeta(e3, clic(0x0004))
comprobar("Ctrl+clic añade otra", sorted(x["nombre"] for x in vista._seleccionadas()) == ["b.mp3", "c.mp3"])
vista._seleccionar_tarjeta(e1, clic(0x0004))
vista._seleccionar_tarjeta(e3, clic(0x0001))
comprobar("Mayús+clic selecciona el rango desde la última marcada",
          [x["nombre"] for x in vista._seleccionadas()] == ["a.mp3", "b.mp3", "c.mp3"])
comprobar("clic normal deshace la selección anterior", vista._seleccion_unica(e1) is None and
          [x["nombre"] for x in vista._seleccionadas()] == ["a.mp3"])
comprobar("Ctrl+A marca todas", vista._seleccionar_todo() == "break" and len(vista._seleccionadas()) == 3)

comprobar("canción: archivo de audio de la biblioteca", vista._es_cancion(e1))
comprobar("carpeta no es canción", not vista._es_cancion(entrada("discos", carpeta=True)))
comprobar("documento no es canción", not vista._es_cancion(entrada("nota.txt")))
info = vista._info_tarjeta(e2)
comprobar("la tarjeta sabe su puesto en la cola", info["en_cola"] == 1 and info["sonando"] is False)
comprobar("la canción que suena se marca", vista._info_tarjeta(e1)["sonando"] is True)
acciones = vista._acciones_de(e1)
comprobar("cada tarjeta trae sus acciones",
          set(acciones) == {"reproducir", "cola", "copiar", "papelera", "abrir", "doble", "seleccionar", "menu", "rueda"})

# ---------------------------------------------------------------- actualización en sitio y transición
comprobar("mezclar en el punto medio", t.mezclar("#000000", "#ffffff", 0.5) == "#808080")
comprobar("mezclar al final da el segundo color", t.mezclar("#102030", "#405060", 1) == "#405060")
comprobar("mezclar al principio da el primero", t.mezclar("#102030", "#405060", 0) == "#102030")


class Etiqueta:
    def configure(self, **kw):
        self.__dict__.update(kw)


tarjeta_falsa = Falso(partes={"cola": Etiqueta(), "insignia": Etiqueta()})
comprobar("primera actualización no cuenta como cambio de cola",
          t.actualizar(tarjeta_falsa, {"en_cola": None, "sonando": False}) is False)
comprobar("entrar en la cola se detecta como cambio",
          t.actualizar(tarjeta_falsa, {"en_cola": 2, "sonando": False}) is True)
comprobar("el botón pasa a Quitar cola sin recrear la tarjeta", tarjeta_falsa.partes["cola"].text == "Quitar cola")
comprobar("la insignia muestra su puesto", tarjeta_falsa.partes["insignia"].text == "COLA 2")
comprobar("sin cambio de cola no hay transición",
          t.actualizar(tarjeta_falsa, {"en_cola": 2, "sonando": True}) is False)
comprobar("al sonar aparece SONANDO", tarjeta_falsa.partes["insignia"].text == "SONANDO  COLA 2")
comprobar("salir de la cola se detecta", t.actualizar(tarjeta_falsa, {"en_cola": None, "sonando": True}) is True)
comprobar("y el botón vuelve a A la cola", tarjeta_falsa.partes["cola"].text == "A la cola")

print("TODO OK" if fallos == 0 else f"{fallos} FALLO(S)")
if fallos:
    raise SystemExit(1)
