"""Prueba no interactiva: «quitar canción de la cola» se entiende (por nombre o por posición) y no se confunde con
la papelera, la cuarentena ni otras órdenes. Trabaja en una carpeta temporal con un reproductor simulado."""
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
configuracion.RUTA_DATOS = TEMPORAL / "datos"
configuracion.RUTA_BASE = TEMPORAL / "miller"
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


class Reproductor:
    def __init__(self, nombres):
        self.cola = [Path(n) for n in nombres]

    def obtener_cola(self):
        return list(self.cola)

    def eliminar_de_cola(self, posicion):
        if 1 <= posicion <= len(self.cola):
            del self.cola[posicion - 1]
            return True
        return False


CANCIONES = ["Alpha Blondy - Jerusalem.mp3", "Beta Radio.mp3", "Adele  Skyfall.mp3", "Gamma Tres.mp3"]
c = Cerebro.__new__(Cerebro)
com = Comandos.__new__(Comandos)

print("1. Detección: frases de quitar de la cola")
for frase in ["quita beta de la cola", "quitar la canción dos de la lista de reproducción",
              "quítame la pista número tres de la cola", "quita la canción en la posición 2",
              "quita de la cola la canción 2", "elimina la canción adele de la cola",
              "saca la canción gamma de la lista de reproducción", "quita la canción 3 de la cola"]:
    comprobar(f"'{frase}' -> QUITAR_COLA_AUDIO", c.detectar_intencion(frase) == "QUITAR_COLA_AUDIO",
              f"-> {c.detectar_intencion(frase)}")
print("2. Detección: no se confunde con otras órdenes")
for frase in ["borra la canción de la papelera", "elimina la canción 3 de la cuarentena",
              "quita el silencio", "pon música", "siguiente canción", "limpia la cola"]:
    comprobar(f"'{frase}' no es QUITAR_COLA_AUDIO", c.detectar_intencion(frase) != "QUITAR_COLA_AUDIO",
              f"-> {c.detectar_intencion(frase)}")

print("3. Ejecución: quita la pista correcta")
casos = [
    ("quita beta de la cola", "Beta Radio.mp3"),
    ("quitar la canción adele de la lista de reproducción", "Adele  Skyfall.mp3"),
    ("quita la canción dos de la lista de reproducción", "Beta Radio.mp3"),
    ("quítame la pista número tres de la cola", "Adele  Skyfall.mp3"),
    ("quita la canción en la posición 4", "Gamma Tres.mp3"),
    ("quita de la cola la canción 1", "Alpha Blondy - Jerusalem.mp3"),
]
for frase, esperada in casos:
    com.reproductor = Reproductor(CANCIONES)
    respuesta = com.quitar_cola_audio(frase)
    quitada = [n for n in CANCIONES if Path(n) not in com.reproductor.cola]
    comprobar(f"'{frase}' quita «{esperada}»", quitada == [esperada] and respuesta.startswith("Retirada"),
              f"quitadas={quitada} respuesta={respuesta}")
com.reproductor = Reproductor(CANCIONES)
comprobar("'quita zeta de la cola' avisa y no quita nada",
          com.quitar_cola_audio("quita zeta de la cola").startswith("'zeta'") and len(com.reproductor.cola) == 4)
com.reproductor = Reproductor(["Alphabet Song.mp3", "Beta Radio.mp3"])
comprobar("«beta» quita Beta y no Alphabet (palabra completa primero)",
          com.quitar_cola_audio("quita beta de la cola") and [p.name for p in com.reproductor.cola] == ["Alphabet Song.mp3"])
comprobar("'quita la canción 9 de la cola' avisa de posición inexistente",
          "inexistente" in com.quitar_cola_audio("quita la canción 9 de la cola"))
comprobar("'quita de la cola' sin nombre pide canción o posición",
          "Indique" in com.quitar_cola_audio("quita de la cola"))

print("4. Flujo completo: la orden llega a la cola a través de generar_respuesta")
c.comandos = com
c.ultima_accion = None
for frase, esperada in [("quita amorsura de la cola", "Amorsura.mp3"),
                        ("quita la canción 1 de la cola", "Amorsura.mp3")]:
    com.reproductor = Reproductor(["Amorsura.mp3", "Adele  Skyfall.mp3"])
    intencion = c.detectar_intencion(frase)
    respuesta = c.generar_respuesta(frase, intencion)
    comprobar(f"'{frase}' llega a la cola (no cae en «no entendí»)",
              intencion == "QUITAR_COLA_AUDIO" and respuesta.startswith("Retirada")
              and "insuficiente" not in respuesta, f"-> {intencion}: {respuesta}")
    comprobar(f"'{frase}' quita «{esperada}» y deja Adele",
              [p.name for p in com.reproductor.cola] == ["Adele  Skyfall.mp3"])

print()
print("Todas las comprobaciones de quitar de la cola pasaron." if not fallos else f"{fallos} comprobación(es) fallaron.")
raise SystemExit(1 if fallos else 0)
