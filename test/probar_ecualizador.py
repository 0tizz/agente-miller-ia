"""MILLER · Prueba del ecualizador: la copia ecualizada nunca cambia la canción que suena sin que usted lo pida,
y al empezar una canción suena ya ecualizada. Usa un pygame falso: esta prueba no hace sonar nada."""
import sys as _sys
import os
import shutil
import subprocess
import tempfile
import time
import types
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
from utilidades import acceso as _acceso   # estas pruebas usan funciones de pago: modo PRO
_acceso._puestas.add("pro")
from pathlib import Path

fallos = []


def comprobar(condicion, mensaje):
    print(("  OK    " if condicion else "  FALLO ") + mensaje)
    if not condicion:
        fallos.append(mensaje)


class _Musica:
    def __init__(self):
        self.volumen, self.sonando, self.pausa = 1.0, False, False

    def load(self, ruta):
        pass

    def play(self, loops=0, start=0.0):
        self.sonando, self.pausa = True, False

    def stop(self):
        self.sonando = False

    def pause(self):
        self.pausa = True

    def unpause(self):
        self.pausa = False

    def set_pos(self, posicion):
        pass

    def get_busy(self):
        return self.sonando and not self.pausa

    def get_volume(self):
        return self.volumen

    def set_volume(self, v):
        self.volumen = max(0.0, min(1.0, float(v)))


class _Mezclador:
    def __init__(self):
        self.music, self._activo = _Musica(), False

    def init(self, *a, **k):
        self._activo = True

    def get_init(self):
        return (44100, -16, 2) if self._activo else None

    def quit(self):
        self._activo = False


_pygame_falso = types.ModuleType("pygame")
_pygame_falso.mixer = _Mezclador()
_pygame_falso.error = type("error", (Exception,), {})
_sys.modules["pygame"] = _pygame_falso

FFMPEG = shutil.which("ffmpeg") or next(
    (str(p) for p in [RAIZ / "modelos" / "ffmpeg-master-gpl" / "bin" / "ffmpeg.exe"] if p.is_file()), None)
if not FFMPEG:
    print("  Sin ffmpeg (modelos/ffmpeg-master-gpl): prueba del ecualizador omitida.")
    _sys.exit(0)

from utilidades import seguridad
from audio.reproductor import Reproductor
from utilidades.ecualizador import Ecualizador

base = Path(tempfile.mkdtemp(prefix="miller_eq_"))
seguridad.DIR_SEGURIDAD = base / "seguridad"
seguridad._clave = None
audios, datos = base / "audios", base / "datos"
audios.mkdir()
datos.mkdir()
for nombre in "abcd":
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"sine=frequency={180 + 40 * ord(nombre) % 200}:duration=45", "-c:a", "libmp3lame", "-b:a", "128k",
                    str(audios / f"cancion_{nombre}.mp3")], check=True)

rep = Reproductor(audios, ruta_memoria=datos / "memoriamusical.json")
eq = Ecualizador(datos / "ecualizador.json", datos / "cache" / "ecualizador", ffmpeg=FFMPEG)
rep.ecualizador = eq
eq.al_listo = lambda original, _copia: rep.ecualizada_lista(original)
cambios = []
_cambiar_original = rep.cambiar_fuente_en_vivo


def _contar(*args, **kwargs):
    cambios.append(args)
    return _cambiar_original(*args, **kwargs)


rep.cambiar_fuente_en_vivo = _contar
A, B, C, D = (audios / f"cancion_{n}.mp3" for n in "abcd")
copia = lambda c: Path(eq.ruta_cache(c, eq.filtro(eq.ganancias(c))))

print("1. Canción nueva con curva: espera la copia y suena ecualizada desde el inicio")
eq.poner_perfil("graves")
rep.ESPERA_COPIA_INICIO = 3.0
comprobar(rep.reproducir("cancion_a") is True, "reproducir devuelve True")
comprobar(str(rep.fuente_actual).endswith(".ogg"), "suena la copia ecualizada desde el primer segundo")
comprobar(len(cambios) == 0, "no hubo cambio en vivo")

print("2. La copia termina en segundo plano sin pedirlo: no cambia la canción que suena")
rep.ESPERA_COPIA_INICIO = 0.0
rep.reproducir("cancion_b")
comprobar(Path(rep.fuente_actual) == B, "empieza con la original mientras la copia se crea")
time.sleep(5)
comprobar(copia(B).is_file(), "la copia se creó en segundo plano")
comprobar(Path(rep.fuente_actual) == B and len(cambios) == 0, "y la canción sigue igual: sin bajón de volumen")

print("3. Cambio pedido por el usuario: se aplica cuando la copia está lista")
eq.poner_perfil("agudos")
comprobar(rep.reaplicar_ecualizacion() is True, "reaplicar devuelve True")
comprobar(Path(rep.fuente_actual) == B, "no cambia al instante (la copia aún no existe)")
time.sleep(5)
comprobar(str(rep.fuente_actual).endswith(".ogg") and len(cambios) == 1, "al estar lista cambia una sola vez")

print("4. Quitar el ecualizador a mitad de canción: vuelve a la original")
eq.poner_perfil("plano")
rep.reaplicar_ecualizacion()
comprobar(Path(rep.fuente_actual) == B, "la original vuelve a sonar")

print("5. Modo automático: medir y ecualizar sin cortes")
eq.poner_automatico()
rep.ESPERA_COPIA_INICIO = 0.0
n0 = len(cambios)
rep.reproducir("cancion_c")
time.sleep(7)
comprobar(len(cambios) == n0, "sin pedido del usuario no hubo cambio automático")
rep.reaplicar_ecualizacion()
time.sleep(5)
comprobar(str(rep.fuente_actual).endswith(".ogg") and len(cambios) == n0 + 1, "el cambio pedido se aplica al estar lista")

print("6. Curva plana: al empezar no espera nada")
eq.poner_perfil("plano")
inicio = time.monotonic()
comprobar(Path(rep._fuente_al_empezar(D)) == D and time.monotonic() - inicio < 0.5, "no espera si no hay ecualización")

print("7. Estados de sin_efecto y preparando")
eq.poner_perfil("graves")
comprobar(eq.sin_efecto(A) is False, "curva graves: no es plana")
eq.poner_perfil("plano")
comprobar(eq.sin_efecto(A) is True, "curva plana: suena la original")
eq.desactivar()
comprobar(eq.sin_efecto(A) is True, "ecualizador desactivado: suena la original")
comprobar(eq.preparando(A) is False, "preparando() es False cuando no hay trabajo")

try:
    rep.cerrar()
except Exception:
    pass
shutil.rmtree(base, ignore_errors=True)
print()
if fallos:
    print(f"RESULTADO: {len(fallos)} FALLO(S)")
    _sys.exit(1)
print("RESULTADO: TODO OK")
