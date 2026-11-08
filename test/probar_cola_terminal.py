"""Prueba no interactiva: quitar canciones de la cola y órdenes de la TERMINAL.
Trabaja en una carpeta temporal; nunca toca audios/ ni datos reales."""
import os
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

TEMPORAL = Path(tempfile.mkdtemp(prefix="miller_cola_"))
os.environ["MILLER_DIR_SEGURIDAD"] = str(TEMPORAL / "seguridad")
import configuracion  # noqa: E402

configuracion.RUTA_AUDIOS = TEMPORAL / "audios"
configuracion.RUTA_AUDIOS.mkdir()
for nombre in ("Alfa cancion.mp3", "Beta tema.mp3", "Gamma pieza.mp3"):
    (configuracion.RUTA_AUDIOS / nombre).write_bytes(b"x")

from audio.reproductor import Reproductor  # noqa: E402
from cerebro.cerebro import Cerebro  # noqa: E402
from cerebro.comandos import Comandos  # noqa: E402

fallos = 0


def comprobar(nombre, condicion, detalle=""):
    global fallos
    if condicion:
        print(f"  OK    {nombre}")
    else:
        fallos += 1
        print(f"  FALLO {nombre} {detalle}")


reproductor = Reproductor(configuracion.RUTA_AUDIOS)
comandos = Comandos.__new__(Comandos)
comandos.reproductor = reproductor


def nombres():
    return [p.name for p in reproductor.obtener_cola()]


def con_cola():
    reproductor.cola.clear()
    reproductor.cola.extend(reproductor.canciones[:3])


casos = [
    ("quita la cancion dos de la cola", ["Alfa cancion.mp3", "Gamma pieza.mp3"]),
    ("quita la cancion 1 de la cola", ["Beta tema.mp3", "Gamma pieza.mp3"]),
    ("saca la cancion beta de la cola", ["Alfa cancion.mp3", "Gamma pieza.mp3"]),
    ("quita la canción Alfa cancion de la cola", ["Beta tema.mp3", "Gamma pieza.mp3"]),
    ("quitar cancion de la cola alfa", ["Beta tema.mp3", "Gamma pieza.mp3"]),
    ("quita de la cola beta", ["Alfa cancion.mp3", "Gamma pieza.mp3"]),
]
print("Quitar de la cola")
for orden, esperado in casos:
    con_cola()
    comandos.quitar_cola_audio(orden)
    comprobar(orden, nombres() == esperado, f"-> {nombres()}")

for orden in ("quita de la cola", "quita la cancion de la cola", "quitar cancion de la cola"):
    con_cola()
    respuesta = comandos.quitar_cola_audio(orden)
    comprobar(f"sin objetivo: {orden}", len(nombres()) == 3 and "Indique" in respuesta, respuesta)

con_cola()
comprobar("posición fuera de la cola", "inexistente" in comandos.quitar_cola_audio("quita la cancion 7 de la cola"))

print("Órdenes de la TERMINAL")
import ast  # noqa: E402
principal_src = (RAIZ / "principal.py").read_text(encoding="utf-8")
arbol = ast.parse(principal_src)
funcion = next(n for n in arbol.body if isinstance(n, ast.FunctionDef) and n.name == "_comando_de_terminal")
import re  # noqa: E402
enviados = []
espacio = {"re": re, "interfaz": lambda metodo, *a: enviados.append((metodo,) + a)}
exec(compile(ast.Module([funcion], []), "principal", "exec"), espacio)


class CerebroFalso:
    def __init__(self):
        self.reiniciado = False

    def olvidar_contexto(self):
        self.reiniciado = True


for orden in ("limpiar terminal", "Limpia la terminal.", "miller, borra la pantalla", "vacía la consola de miller"):
    enviados.clear()
    cerebro = CerebroFalso()
    atendida = espacio["_comando_de_terminal"](cerebro, orden)
    comprobar(f"'{orden}' se atiende", atendida and cerebro.reiniciado and ("limpiar_terminal",) in enviados)
for orden in ("limpiar cola", "quita la cancion alfa", "limpia la terminal de la cola"):
    enviados.clear()
    cerebro = CerebroFalso()
    comprobar(f"'{orden}' no es de la TERMINAL", not espacio["_comando_de_terminal"](cerebro, orden) and not cerebro.reiniciado)

cerebro = Cerebro.__new__(Cerebro)
cerebro.contexto = [{"rol": "usuario", "contenido": "hola"}]
cerebro.ultima_entrada = "hola"
cerebro.olvidar_contexto()
comprobar("olvidar_contexto vacía la conversación reciente", cerebro.contexto == [] and cerebro.ultima_entrada is None)

print(f"Resultado: {'todo correcto' if not fallos else str(fallos) + ' fallo(s)'}")
raise SystemExit(1 if fallos else 0)
