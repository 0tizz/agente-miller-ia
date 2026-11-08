"""MILLER · test.probar_volumen: PRUEBA: subir y bajar volumen SIEMPRE con fundido (FadeController), nunca de golpe."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent      # carpeta raíz de MILLER
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
import threading
import time
from types import SimpleNamespace
try:
    import pygame  # noqa: F401
except ImportError:
    import types
    class _M:
        def __getattr__(self, n):
            return lambda *a, **k: None
    pygame = types.ModuleType("pygame"); pygame.mixer = _M(); pygame.mixer.music = _M(); pygame.init = lambda *a, **k: None
    _sys.modules["pygame"] = pygame
from audio.fade_controller import FadeController
from audio.reproductor import Reproductor
fallos = []
def comprobar(condicion, mensaje):
    print(("  OK    " if condicion else "  FALLO ") + mensaje)
    if not condicion:
        fallos.append(mensaje)
nivel, valores = [0.5], []
def poner(v):
    nivel[0] = v; valores.append(round(v, 3))
fade = FadeController(lambda: nivel[0], poner)
# Reproductor "sonando" sin abrir el audio real: solo se usa establecer_volumen y su fundido.
rep = SimpleNamespace(volumen=0.5, _volumen_antes_silencio=0.5, inicializado=True, cerrado=False,
                      reproduciendo=True, pausado=False, _lock=threading.RLock(), fade_controller=fade,
                      DURACION_FADE_IN=2.0, DURACION_FADE_OUT=1.2, DURACION_FADE_VOLUMEN=0.6,
                      guardar_memoria_musical=lambda: True)
rep._fundido_volumen = lambda o, d: Reproductor._fundido_volumen(rep, o, d)
def subir_a(v):
    valores.clear()
    inicio = time.monotonic()
    ok = Reproductor.establecer_volumen(rep, v)
    respuesta = time.monotonic() - inicio
    time.sleep(0.9)
    return ok, respuesta
print("1. Subir volumen 50 % -> 80 %")
ok, t = subir_a(0.8)
comprobar(ok and t < 0.3, f"responde al instante ({t:.2f} s), el fundido sigue en segundo plano")
comprobar(len(valores) >= 8, f"{len(valores)} pasos intermedios")
comprobar(all(b >= a for a, b in zip(valores, valores[1:])), "sube de forma continua")
comprobar(abs(nivel[0] - 0.8) < 0.001, "llega exactamente al 80 %")
comprobar(max(abs(b - a) for a, b in zip([0.5] + valores, valores)) < 0.08, "sin saltos bruscos")
print("2. Bajar volumen 80 % -> 30 %")
ok, t = subir_a(0.3)
comprobar(all(b <= a for a, b in zip(valores, valores[1:])) and abs(nivel[0] - 0.3) < 0.001, "baja suave hasta el 30 %")
print("3. Órdenes seguidas: la nueva continúa desde donde iba la anterior")
valores.clear()
Reproductor.establecer_volumen(rep, 0.9)
time.sleep(0.25)
Reproductor.establecer_volumen(rep, 0.6)
time.sleep(0.9)
comprobar(abs(nivel[0] - 0.6) < 0.001, "termina en el último volumen pedido")
comprobar(max(abs(b - a) for a, b in zip(valores, valores[1:])) < 0.08, "sin saltos al cambiar de orden")
fade.cerrar()
print()
print("RESULTADO:", "OK" if not fallos else f"FALLO ({len(fallos)})")
if fallos:
    raise SystemExit(1)
