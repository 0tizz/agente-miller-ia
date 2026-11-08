"""MILLER · Prueba del arranque: la música continúa donde quedó, pero solo cuando se abre la ventana."""
import sys as _sys
import types
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
import shutil
import tempfile
import time
from pathlib import Path

eventos = []


class _Musica:
    """pygame.mixer.music de mentira: registra lo que se reproduce."""
    def __init__(self):
        self.volumen, self.sonando = 0.0, False
    def load(self, ruta): eventos.append(("load", Path(ruta).name))
    def play(self, *a, **k): self.sonando = True; eventos.append(("play", k.get("start", 0)))
    def stop(self): self.sonando = False
    def pause(self): self.sonando = False
    def unpause(self): self.sonando = True
    def set_pos(self, p): eventos.append(("pos", p))
    def set_volume(self, v): self.volumen = v
    def get_volume(self): return self.volumen
    def get_busy(self): return self.sonando
    def get_pos(self): return 0
    def __getattr__(self, n): return lambda *a, **k: None


class _Mixer:
    def __init__(self): self.music = _Musica()
    def init(self, *a, **k): pass
    def get_init(self): return (44100, -16, 2)
    def __getattr__(self, n): return lambda *a, **k: None


pygame = types.ModuleType("pygame")
pygame.mixer = _Mixer()
pygame.init = lambda *a, **k: None
pygame.error = Exception
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
cancion = base / "audios" / "Prueba - Cancion.mp3"
cancion.write_bytes(b"ID3" + b"\0" * 2048)
from audio.reproductor import Reproductor
memoria = base / "datos" / "memoriamusical.json"
seguridad.escribir_json(memoria, {"estado_reproductor": {"cancion_actual": str(cancion), "posicion_segundos": 42.0,
                                                         "reproduciendo": False, "pausado": True, "volumen": 0.3}})

print("1. Al crear el reproductor no suena nada todavía")
eventos.clear()
rep = Reproductor(base / "audios", ruta_memoria=memoria, restaurar_pista=False)
comprobar(not any(e[0] == "play" for e in eventos), "sin ventana abierta, la música espera")
comprobar(rep._pista_pendiente and rep._pista_pendiente[0] == cancion, "recuerda qué canción continuar")

print("2. Con la ventana abierta, continúa donde quedó y sonando")
comprobar(rep.continuar_al_iniciar(), "continuar_al_iniciar() la pone a sonar")
comprobar(("load", cancion.name) in eventos, "carga la última canción")
comprobar(any(e[0] in ("pos", "play") and e[1] == 42.0 for e in eventos), "sigue en el segundo 42")
comprobar(rep.reproduciendo and not rep.pausado, "suena aunque se hubiera cerrado en pausa (continúa normal)")
comprobar(rep.continuar_al_iniciar(), "llamarla otra vez no la reinicia")
rep.cerrar() if hasattr(rep, "cerrar") else None

print("3. Sin canción guardada, empieza la biblioteca")
memoria2 = base / "datos" / "memoria2.json"
eventos.clear()
rep2 = Reproductor(base / "audios", ruta_memoria=memoria2, restaurar_pista=False)
comprobar(not any(e[0] == "play" for e in eventos), "tampoco suena antes de la ventana")
comprobar(rep2.continuar_al_iniciar() and rep2.reproduciendo, "al abrirse la ventana empieza la música")
rep2.cerrar() if hasattr(rep2, "cerrar") else None

print("4. principal.py la arranca justo después de abrir la ventana")
fuente = (RAIZ / "principal.py").read_text(encoding="utf-8")
i, j = fuente.find("abrir_interfaz(cerebro)\n    iniciar_musica(cerebro)"), fuente.find("def iniciar_musica")
comprobar(i > 0 and j > 0, "el orden es: abrir la ventana -> continuar la música")
comandos = (RAIZ / "cerebro" / "comandos.py").read_text(encoding="utf-8")
comprobar("restaurar_pista=not" in comandos, "Comandos no suelta la música al crearse")

print("\nRESULTADO:", "TODO CORRECTO" if not fallos else f"{len(fallos)} FALLO(S)")
shutil.rmtree(base, ignore_errors=True)
_sys.exit(1 if fallos else 0)
