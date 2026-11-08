"""MILLER · Prueba de la bienvenida: el arranque espera el nombre que se pone en la ventana, el nombre se pone una sola
vez, Cerebro y el activador de voz usan ese nombre y PURGAR hace que MILLER se despida antes de borrar nada.
Sin ventana ni voz reales: trabaja en una carpeta temporal y no toca los datos ni el código sellado."""
import sys as _sys
import os
import shutil
import tempfile
import threading
from pathlib import Path as _Path

RAIZ = _Path(__file__).resolve().parent.parent
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
TEMPORAL = _Path(tempfile.mkdtemp(prefix="miller_bienvenida_"))
(TEMPORAL / "seguridad").mkdir()
os.environ["MILLER_DIR_SEGURIDAD"] = str(TEMPORAL / "seguridad")
fallos = []


def comprobar(condicion, mensaje):
    print(("  OK    " if condicion else "  FALLO ") + mensaje)
    if not condicion:
        fallos.append(mensaje)


import configuracion  # noqa: E402
from utilidades import nombre, purga  # noqa: E402
import principal  # noqa: E402

print("1. El nombre se pone una sola vez y el arranque lo sabe")
configuracion.RUTA_NOMBRE_ASISTENTE = TEMPORAL / "nombre.json"
comprobar(not nombre.esperar_fijado(0.05), "sin nombre guardado, la espera no termina")
threading.Timer(0.1, lambda: nombre.fijar("Ana")).start()
comprobar(nombre.esperar_fijado(3.0), "al ponerlo desde otro hilo, la espera termina")
comprobar(nombre.clave() == "Ana", "el nombre de esta sesión es el que se puso")
ok, motivo = nombre.fijar("Luis")
comprobar(not ok and "Solo se puede poner una vez" in motivo, "un segundo intento no cambia el nombre")

print("2. El arranque espera el nombre que se pone en la ventana, o termina si la ventana se cierra")


def reiniciar_nombre(archivo):
    """Como un primer arranque: sin nombre fijado y con la ventana todavía abierta."""
    nombre._fijado.clear()
    nombre._actual = None
    configuracion.RUTA_NOMBRE_ASISTENTE = TEMPORAL / archivo
    principal.CIERRE.clear()


reiniciar_nombre("cierre.json")
threading.Timer(0.2, principal.CIERRE.set).start()
comprobar(principal.esperar_nombre_en_ventana() is False, "si la ventana se cierra antes, no se sigue esperando")

reiniciar_nombre("ventana.json")
threading.Timer(0.2, lambda: nombre.fijar("Luis")).start()
comprobar(principal.esperar_nombre_en_ventana() is True, "si el nombre se pone en la ventana, el arranque sigue")
comprobar(nombre.clave() == "Luis", "y el nombre de esta sesión es ese")

print("3. Cerebro y el activador de voz usan el nombre elegido")


class CerebroFalso:
    nombre = "Miller"
    activador = None


cerebro_falso = CerebroFalso()
activador = principal.aplicar_nombre(cerebro_falso, None)
comprobar(cerebro_falso.nombre == "Luis", "Cerebro lo usa como su nombre")
if principal.USAR_PALABRA_ACTIVACION:
    comprobar(activador is not None and activador.obtener_palabra() == "luis",
              "el activador de voz escucha ese nombre")
    comprobar(cerebro_falso.activador is activador, "y queda conectado a Cerebro")

print("4. PURGAR: MILLER se despide en voz alta antes de borrar, y solo si se pidió la purga")
orden = []


class HabladorFalso:
    disponible = True

    def hablar(self, texto):
        orden.append(("hablar", texto))
        return True

    def detener(self):
        return True


purga_original = purga.ejecutar_si_pedida
purga.ejecutar_si_pedida = lambda raiz=None: orden.append(("purga", None))   # aquí no se borra nada de verdad
principal.HABLAR_RESPUESTAS = True
try:
    principal.cerrar_miller(None, HabladorFalso(), None, None)
    comprobar(not any(paso[0] == "hablar" for paso in orden), "sin PURGAR, MILLER no se despide")
    orden.clear()
    purga.pedir()
    principal.cerrar_miller(None, HabladorFalso(), None, None)
    comprobar(orden[:1] == [("hablar", configuracion.MENSAJE_DESPEDIDA_PURGA)],
              "con PURGAR, lo primero es la despedida en voz alta")
    comprobar(orden[-1:] == [("purga", None)], "y la purga se hace después")
finally:
    purga._pedida.clear()
    purga.ejecutar_si_pedida = purga_original

shutil.rmtree(TEMPORAL, ignore_errors=True)
print()
if fallos:
    print(f"FALLARON {len(fallos)} comprobaciones:")
    for f in fallos:
        print("  -", f)
    raise SystemExit(1)
print("Todas las comprobaciones de la bienvenida pasaron.")
