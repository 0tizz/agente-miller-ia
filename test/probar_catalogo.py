"""Prueba no interactiva: catálogo de comandos por versión, detección de «comandos» y la cascada de la llave BOY
(solo se mira bajo el orbe, señuelos, aviso con adjunto para la terminal, historial sin claves).
Trabaja en una carpeta temporal; nunca toca datos ni audios reales."""
import os
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

TEMPORAL = Path(tempfile.mkdtemp(prefix="miller_catalogo_"))
os.environ["MILLER_DIR_SEGURIDAD"] = str(TEMPORAL / "seguridad")
import configuracion  # noqa: E402
configuracion.RUTA_DATOS = TEMPORAL / "datos"
configuracion.RUTA_BASE = TEMPORAL / "miller"
from utilidades import acceso, catalogo, llave_boy  # noqa: E402
import ayuda_llave_boy  # noqa: E402

llave_boy.RUTA = TEMPORAL / "llave_boy.json"
fallos = 0


def comprobar(nombre, condicion, detalle=""):
    global fallos
    if condicion:
        print(f"  OK    {nombre}")
    else:
        fallos += 1
        print(f"  FALLO {nombre} {detalle}")


from cerebro.cerebro import Cerebro  # noqa: E402
c = Cerebro.__new__(Cerebro)

print("1. Catálogo: cada ejemplo es un comando de su versión")
for frase, _ in catalogo.FREE:
    intencion = c.detectar_intencion(frase)
    comprobar(f"FREE «{frase}»", intencion not in acceso.REQUIERE, f"-> {intencion}")
for frase, _ in catalogo.BOY:
    intencion = c.detectar_intencion(frase)
    comprobar(f"NIÑOS «{frase}»", acceso.REQUIERE.get(intencion) == "boy", f"-> {intencion}")
for frase, _ in catalogo.PRO:
    intencion = c.detectar_intencion(frase)
    multiple = len(c.dividir_ordenes(frase)) > 1
    comprobar(f"PRO «{frase}»", acceso.REQUIERE.get(intencion) == "pro" or multiple, f"-> {intencion}")

print("2. Listado: terminal completa, voz corta")
completo = catalogo.listado_completo("free")
comprobar("la terminal lista todos los comandos de FREE, NIÑOS y PRO",
          all(f in completo for f, _ in catalogo.FREE + catalogo.BOY + catalogo.PRO))
comprobar("en voz solo se dice que están en la terminal", completo.voz == catalogo.VOZ_COMANDOS)
comprobar("FREE: NIÑOS y PRO aparecen como llaves por obtener",
          "NIÑOS (con la llave NIÑOS)" in completo and "PRO (con la llave PRO)" in completo)
pro = catalogo.listado_completo("pro")
comprobar("PRO: todo activo", "PRO (activa)" in pro and "NIÑOS (incluida)" in pro and "FREE (incluida)" in pro)
comprobar("la versión actual va marcada", "Versión actual: NIÑOS" in catalogo.listado_completo("boy"))
c2 = Cerebro.__new__(Cerebro)
c2.__dict__["_ultima_intencion_respuesta"] = None
respuesta = c2.generar_respuesta("comandos", "AYUDA")
comprobar("la respuesta de AYUDA lleva la voz corta", getattr(respuesta, "voz", None) == catalogo.VOZ_COMANDOS)

print("3. «comandos» se detecta como AYUDA")
for frase in ("miller comandos", "comandos", "que comandos tengo", "lista de comandos", "que comandos hay"):
    comprobar(f"'{frase}' -> AYUDA", c.detectar_intencion(frase) == "AYUDA", f"-> {c.detectar_intencion(frase)}")
comprobar("'comandos de la biblioteca' no es AYUDA", c.detectar_intencion("comandos de la biblioteca") != "AYUDA")

print("4. La clave BOY: solo bajo el orbe, con señuelos")
llave = ayuda_llave_boy.preparar()
reales = list(llave_boy._fragmentos())               # los de la llave de prueba, ya puesta
llave_boy.RUTA = TEMPORAL / "llave_boy_2.json"
llave_boy._piezas_cache = None
llave_boy._guardar({})
senuelo = llave_boy.senuelo()
comprobar("un señuelo nunca es un fragmento real",
          senuelo.replace("BOY-", "") not in llave_boy._fragmentos())
comprobar("un señuelo no cuenta como fragmento", llave_boy.observar(senuelo)[0] is None)
from interfaz.esencia import VentanaEsencia  # noqa: E402


class Ini:
    ALTA = 3

    def __init__(self):
        self.llamadas = []

    def agregar(self, clave, texto, prioridad=2, una_vez=True, tono=None, adjunto=None):
        self.llamadas.append((clave, texto, adjunto))


class Cer:
    pass


cer = Cer()
cer.iniciativa = Ini()
v = VentanaEsencia.__new__(VentanaEsencia)
v.cerebro = cer
v.registros = []
v.registrar = lambda q, t: v.registros.append((q, t))
v.pos = (100.0, 100.0)
v.columnas = [{"x": 100, "y": 110.0, "n": 4, "palabra": reales[0]},
              {"x": 200, "y": 110.0, "n": 4, "palabra": reales[1]}]
v._observar_bajo_orbe()
comprobar("el fragmento bajo el orbe se guarda", llave_boy.progreso() == 1)
v._observar_bajo_orbe()
comprobar("la misma palabra bajo el orbe no se mira dos veces", llave_boy.progreso() == 1)
v.pos = (150.0, 100.0)
v._observar_bajo_orbe()
comprobar("el otro fragmento, lejos del orbe, no cuenta", llave_boy.progreso() == 1)
v.pos = (200.0, 100.0)
v._observar_bajo_orbe()
comprobar("el segundo fragmento bajo el orbe sí cuenta", llave_boy.progreso() == 2)
v.columnas = [{"x": 300, "y": 110.0, "n": 4, "palabra": reales[2]}]
v.pos = (300.0, 100.0)
v._observar_bajo_orbe()
comprobar("con los tres, MILLER pide permiso (iniciativa) con la clave como adjunto",
          len(cer.iniciativa.llamadas) == 1 and cer.iniciativa.llamadas[0][2] == f"Clave BOY encontrada: {llave}"
          and cer.iniciativa.llamadas[0][1] == "encontré la clave boy", str(cer.iniciativa.llamadas))
comprobar("la clave no sale en la terminal antes de que MILLER la diga", v.registros == [])

print("5. Adjunto de la iniciativa: sale solo al decir la frase")
from cerebro.iniciativa import Iniciativa  # noqa: E402
ini = Iniciativa.__new__(Iniciativa)
import threading  # noqa: E402
ini._lock = threading.RLock()
ini._pendientes = []
ini._estado = {"dichos": {}}
ini._esperando_desde = 1.0
ini.cerebro = None
ini.agregar("clave_boy", "encontré la clave boy", 3, True, adjunto=f"Clave BOY encontrada: {llave}")
ini._guardar_estado = lambda: None
ini._sentir = lambda *a, **k: None
frase = ini.entregar()
comprobar("la frase no lleva la clave", llave not in frase and "clave boy" in frase.lower(), frase)
comprobar("el adjunto va a la terminal con la frase", ini.adjunto_terminal() == f"Clave BOY encontrada: {llave}")
comprobar("el adjunto se entrega una sola vez", ini.adjunto_terminal() is None)

print("6. Historial de la terminal sin claves")
from interfaz import panel  # noqa: E402
comprobar("'acceso <llave>' no se guarda", panel._es_clave("acceso BOY-AAAA-BBBB-CCCC"))
comprobar("'ingresa clave boy' no se guarda", panel._es_clave("ingresa clave boy"))
comprobar("'pon música' sí se guarda", not panel._es_clave("pon música"))
panel._guardar_historial(["pon música", "qué hora es"])
comprobar("el historial se guarda y se vuelve a leer", panel._leer_historial() == ["pon música", "qué hora es"])

print()
print("Todas las comprobaciones del catálogo, la cascada y el historial pasaron." if not fallos
      else f"{fallos} comprobación(es) fallaron.")
raise SystemExit(1 if fallos else 0)
