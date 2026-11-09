"""Duración de una pista, medida con ffmpeg y guardada en caché.

La primera vez que se pide un archivo, la medición se hace en un hilo aparte: duracion_de devuelve None
hasta que está lista. Un archivo que ffmpeg no puede leer se marca una sola vez y no se vuelve a medir.
"""
import os
import re
import subprocess
import threading

_RE_DURACION = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_cache = {}                 # ruta -> segundos (None si no se pudo leer)
_midiendo = set()
_candado = threading.Lock()


def analizar_salida(texto):
    """Saca los segundos de la línea 'Duration: HH:MM:SS.cc' que escribe ffmpeg. None si no aparece."""
    m = _RE_DURACION.search(texto or "")
    if not m:
        return None
    horas, minutos, segundos = m.groups()
    total = int(horas) * 3600 + int(minutos) * 60 + float(segundos)
    return total if total > 0 else None


def formatear(segundos):
    """0:05, 3:07, 1:02:05. Sin dato, --:--."""
    if segundos is None:
        return "--:--"
    s = max(0, int(segundos))
    horas, resto = divmod(s, 3600)
    minutos, s = divmod(resto, 60)
    return f"{horas}:{minutos:02d}:{s:02d}" if horas else f"{minutos}:{s:02d}"


def fraccion(posicion, duracion):
    """Parte recorrida de la pista, entre 0 y 1. Sin duración conocida, 0."""
    if posicion is None or not duracion or duracion <= 0:
        return 0.0
    return min(1.0, max(0.0, float(posicion) / float(duracion)))


def _medir(ruta, ffmpeg):
    extra = {"creationflags": 0x08000000 | 0x00004000} if os.name == "nt" else {}   # sin ventana y prioridad baja
    try:
        r = subprocess.run([ffmpeg, "-hide_banner", "-i", str(ruta)], capture_output=True, text=True,
                           errors="replace", stdin=subprocess.DEVNULL, timeout=60, **extra)
        return analizar_salida(r.stderr)
    except Exception:
        return None


def duracion_de(ruta, ffmpeg):
    """Segundos de la pista si ya se conocen. La primera vez lanza la medición en segundo plano y devuelve None."""
    clave = str(ruta)
    with _candado:
        if clave in _cache:
            return _cache[clave]
        if not ffmpeg or clave in _midiendo:
            return None
        _midiendo.add(clave)

    def trabajar():
        total = _medir(clave, ffmpeg)
        with _candado:
            _cache[clave] = total
            _midiendo.discard(clave)

    threading.Thread(target=trabajar, daemon=True).start()
    return None
