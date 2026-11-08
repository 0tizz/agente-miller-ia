"""MILLER · Prueba de rendimiento: guardado diferido de la música, ventana sin bloqueos, cachés y noticias sin internet."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
import tempfile
import threading
import time
from pathlib import Path
try:
    import pygame  # noqa: F401
except ImportError:
    import types
    class _M:
        def __getattr__(self, n):
            return lambda *a, **k: None
    pygame = types.ModuleType("pygame"); pygame.mixer = _M(); pygame.mixer.music = _M(); pygame.init = lambda *a, **k: None
    _sys.modules["pygame"] = pygame
from utilidades import seguridad
fallos = []


def comprobar(condicion, mensaje):
    print(("  OK    " if condicion else "  FALLO ") + mensaje)
    if not condicion:
        fallos.append(mensaje)


base = Path(tempfile.mkdtemp())
seguridad.DIR_SEGURIDAD = base / "seguridad"
seguridad._clave = None
(base / "audios").mkdir()
(base / "datos").mkdir()
print("1. La memoria musical se guarda sin frenar la reproducción")
from audio.reproductor import Reproductor
rep = Reproductor(base / "audios", ruta_memoria=base / "datos" / "memoriamusical.json")
rep.RETRASO_GUARDADO = 0.5
escrituras = []
original = seguridad.escribir_json
seguridad.escribir_json = lambda *a, **k: (escrituras.append(1), original(*a, **k))[1]
inicio = time.monotonic()
for _ in range(50):                                   # como un cambio de canción: muchos eventos seguidos
    rep.guardar_memoria_musical()
tiempo = time.monotonic() - inicio
comprobar(tiempo < 0.1, f"50 guardados encolados en {tiempo * 1000:.1f} ms")
time.sleep(1.0)
comprobar(1 <= len(escrituras) <= 2, f"se agrupan en {len(escrituras)} escritura(s) a disco")
seguridad.escribir_json = original
print("2. La ventana nunca espera al candado del reproductor")
from interfaz.esencia import VentanaEsencia


class CerebroFalso:
    iniciativa = emociones = None
    comandos = type("C", (), {"reproductor": rep})()
    def estado_emocional(self):
        return {"emocion": "calma"}


v = VentanaEsencia(CerebroFalso())
rep.cancion_actual, rep.reproduciendo = base / "audios" / "Flaca.mp3", True
retenido = threading.Event()
def retener():
    with rep._lock:                                   # simula el fundido del cambio de canción
        retenido.set()
        time.sleep(1.5)
threading.Thread(target=retener, daemon=True).start()
retenido.wait()
inicio = time.monotonic()
v._reflexionar()
espera = time.monotonic() - inicio
comprobar(espera < 0.2, f"pensamientos leídos en {espera * 1000:.0f} ms aunque el reproductor está ocupado")
comprobar("FLACA" in v._pensamientos, "sabe qué canción suena")
rep.reproduciendo = False
print("3. Caché de intenciones")
from cerebro.cerebro import Cerebro
c = object.__new__(Cerebro)
inicio = time.monotonic(); c.detectar_intencion("pon alarma en media hora y sube el volumen"); primera = time.monotonic() - inicio
inicio = time.monotonic(); r = c.detectar_intencion("pon alarma en media hora y sube el volumen"); segunda = time.monotonic() - inicio
comprobar(segunda < primera and segunda < 0.001, f"la misma frase: {primera * 1000:.2f} ms la primera vez, {segunda * 1000:.3f} ms después")
print("4. Noticias sin internet")
import utilidades.noticias as mod_noticias
mod_noticias._RUTA_DATOS = base / "datos"
n = mod_noticias.Noticias()
n._obtener_noticias_red = lambda cantidad, tema: [{"titulo": f"Titular {i}", "fuente": "Diario"} for i in range(1, 6)][:cantidad]
comprobar(len(n.obtener_noticias(1)) == 1, "con internet trae el titular")
n._cache.clear()
n._obtener_noticias_red = lambda cantidad, tema: []
guardadas = n.obtener_noticias(3)
comprobar(len(guardadas) == 3 and all(g.get("guardada") for g in guardadas), "sin internet usa las 3 últimas guardadas")
resumen = n.obtener_resumen()
comprobar(resumen.startswith("Sin conexión") and "Titular 3" in resumen, f"lo dice con su fecha: {resumen[:70]}…")
rep.cerrar()
print()
print("RESULTADO:", "OK" if not fallos else f"FALLO ({len(fallos)})")
if fallos:
    raise SystemExit(1)
