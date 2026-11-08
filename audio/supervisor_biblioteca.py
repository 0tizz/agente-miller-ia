"""MILLER · Supervisor de biblioteca 1.0."""
from __future__ import annotations
import argparse
import atexit
import copy
import errno
import hashlib
import json
import logging
import os
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
import unicodedata
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional
__all__ = ["SupervisorBiblioteca", "ConfigSupervisor", "validar_estructura"]
VERSION = "2.0"
EXTENSIONES_POR_DEFECTO = {".mp3", ".wav", ".ogg", ".flac"}
# Audio conocido que MILLER (pygame) no reproduce. Cualquier otra extensión
EXTENSIONES_NO_COMPATIBLES = {
    ".m4a", ".aac", ".wma", ".opus", ".aiff", ".aif", ".ape", ".wv", ".amr",
    ".ac3", ".dts", ".mka", ".mid", ".midi", ".mp2", ".ra", ".au", ".caf",
}
EXTENSIONES_TEMPORALES = {".part", ".crdownload", ".tmp", ".download", ".partial", ".!ut"}
_RE_COPIA = re.compile(r"(\s*\(\d+\)|[\s_-]+(copy|copia)(\s*\(?\d+\)?)?)$", re.IGNORECASE)

@dataclass
class ConfigSupervisor:
    modo: str = "cuarentena"                 # "observar" (solo informa) | "cuarentena"
    intervalo_ciclo: float = 300.0           # revisión completa periódica (s)
    intervalo_vigilancia: float = 5.0        # sondeo ligero de cambios (s)
    retraso_inicial: float = 5.0             # espera antes del primer ciclo (s)
    estabilidad_segundos: float = 15.0       # un archivo debe llevar este tiempo sin cambiar
    tamano_minimo_bytes: int = 64
    verificacion_profunda: bool = True       # decodificar en un subproceso aislado
    timeout_verificacion: float = 30.0
    max_bytes_decodificacion_completa: int = 64 * 1024 * 1024
    pausa_entre_archivos: float = 0.05       # cortesía de CPU/disco
    pausa_entre_verificaciones: float = 0.25
    proteger_historial: bool = True          # el historial cuenta como "en uso"
    mover_no_compatibles: bool = False       # por defecto solo se informa de ellos
    purgar_cuarentena_dias: Optional[float] = None   # None = nunca borrar
    carpeta_datos: Optional[Path] = None     # por defecto: <carpeta de la memoria>/supervisor
    carpeta_cuarentena: Optional[Path] = None   # por defecto: <audios>/cuarentena
    # Reparación de adulterados (extensión que no coincide con el contenido real).
    reparacion_automatica: bool = True
    ruta_ffmpeg: Optional[str] = None         # None = buscar en modelos/ y en el PATH
    timeout_conversion: float = 600.0
    max_conversiones_por_ciclo: int = 3       # el resto sigue en los ciclos siguientes
    espacio_minimo_mb: int = 300              # no convierte ni copia si queda menos espacio libre
    verificar_duracion: bool = True           # con ffprobe: el MP3 debe durar lo mismo que el original
    # Plan de eliminación: días en cuarentena antes de borrar (None = nunca automáticamente).
    eliminacion_automatica: bool = False
    plan_eliminacion: dict = field(default_factory=lambda: {
        "danados": 15,                # dañados o irreparables
        "duplicados": 7,              # copias exactas (solo si el original sigue en la biblioteca)
        "adulterados_reparados": 7,   # originales ya convertidos a MP3
        "adulterados": None,          # sin convertir: nunca solos (son tu música)
        "papelera": 30,               # canciones que el usuario mandó borrar ("Miller, borra ...")
        "no_compatibles": None,
    })

def _clave(ruta) -> str:
    """Misma clave que usa Reproductor._clave_archivo."""
    try:
        return str(Path(ruta).resolve()).casefold()
    except (OSError, RuntimeError, TypeError):
        return str(ruta).casefold()

def _iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")

def _texto_busqueda(texto) -> str:
    s = unicodedata.normalize("NFKD", str(texto or "").casefold())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(re.sub(r"[_.()\[\]{}-]+", " ", s).split())

def _leer_json(ruta: Path, defecto):
    try:
        with ruta.open(encoding="utf-8") as f:
            datos = json.load(f)
        return datos if isinstance(datos, type(defecto)) else defecto
    except (OSError, ValueError):
        return defecto

def _escribir_json(ruta: Path, datos) -> bool:
    tmp = ruta.with_name(ruta.name + ".tmp")
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, ruta)
        return True
    except (OSError, TypeError, ValueError):
        try:
            tmp.unlink()
        except OSError:
            pass
        return False

def _pid_activo(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            h = k32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
            if not h:
                return False
            codigo = ctypes.c_ulong()
            ok = k32.GetExitCodeProcess(h, ctypes.byref(codigo))
            k32.CloseHandle(h)
            return bool(ok) and codigo.value == 259   # STILL_ACTIVE
        except Exception:
            return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True
# Validación estructural (sin dependencias; solo lee cabeceras)
_BR_V1 = {1: [0, 32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448],
          2: [0, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384],
          3: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]}
_BR_V2 = {1: [0, 32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256],
          2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
          3: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]}
_SR = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}

def _longitud_trama_mp3(c: bytes) -> int:
    if len(c) < 4 or c[0] != 0xFF or (c[1] & 0xE0) != 0xE0:
        return 0
    ver, capa_bits = (c[1] >> 3) & 3, (c[1] >> 1) & 3
    br_i, sr_i, pad = (c[2] >> 4) & 15, (c[2] >> 2) & 3, (c[2] >> 1) & 1
    if ver == 1 or capa_bits == 0 or br_i in (0, 15) or sr_i == 3:
        return 0
    capa = 4 - capa_bits
    br = (_BR_V1 if ver == 3 else _BR_V2)[capa][br_i] * 1000
    sr = _SR[ver][sr_i]
    if capa == 1:
        return (12 * br // sr + pad) * 4
    if capa == 2 or ver == 3:
        return 144 * br // sr + pad
    return 72 * br // sr + pad

def _inicio_tras_id3(f) -> int:
    f.seek(0)
    c = f.read(10)
    if len(c) == 10 and c[:3] == b"ID3" and all(b < 0x80 for b in c[6:10]):
        return 10 + ((c[6] << 21) | (c[7] << 14) | (c[8] << 7) | c[9]) + (10 if c[5] & 0x10 else 0)
    return 0

def _tipo_real(f) -> Optional[str]:
    f.seek(0)
    c = f.read(12)
    if c[:4] in (b"RIFF", b"RF64") and c[8:12] == b"WAVE":
        return "wav"
    if c[:4] == b"OggS":
        return "ogg"
    if c[:4] == b"fLaC":
        return "flac"
    ini = _inicio_tras_id3(f)
    if ini:
        f.seek(ini)
        return "flac" if f.read(4) == b"fLaC" else "mp3"
    if len(c) >= 2 and c[0] == 0xFF and (c[1] & 0xE0) == 0xE0 and (c[1] & 0x06):   # capa != 00 (00 = AAC)
        return "mp3"
    return None

def _validar_mp3(f, size):
    ini = _inicio_tras_id3(f)
    if ini >= size:
        return "danado", ["la etiqueta ID3 ocupa más que el archivo"]
    f.seek(ini)
    bloque = f.read(262144)
    pos = intentos = 0
    while intentos < 50000:
        i = bloque.find(b"\xff", pos)
        if i < 0:
            break
        intentos += 1
        pos = i + 1
        if i + 1 >= len(bloque) or (bloque[i + 1] & 0xE0) != 0xE0:
            continue
        validas, j, fin = 0, i, False
        while validas < 3:
            if j + 4 > len(bloque):
                fin = True
                break
            largo = _longitud_trama_mp3(bloque[j:j + 4])
            if not largo:
                break
            validas += 1
            j += largo
        if validas >= 3 or (fin and validas >= 1):
            return "ok", []
    return "danado", ["no se encontraron tramas MPEG válidas"]

def _validar_wav(f, size):
    f.seek(0)
    cab = f.read(12)
    if len(cab) < 12 or cab[:4] not in (b"RIFF", b"RF64") or cab[8:12] != b"WAVE":
        return "danado", ["cabecera RIFF/WAVE inválida"]
    pos, fmt, datos = 12, None, None
    while pos + 8 <= size:
        f.seek(pos)
        h = f.read(8)
        if len(h) < 8:
            break
        cid, csz = h[:4], struct.unpack("<I", h[4:])[0]
        if cid == b"fmt ":
            fmt = f.read(min(csz, 40))
        elif cid == b"data":
            datos = (pos + 8, csz)
            break
        pos += 8 + csz + (csz & 1)
    if fmt is None or len(fmt) < 16:
        return "danado", ["falta el bloque 'fmt '"]
    _tag, canales, tasa, _bps, alineacion, bits = struct.unpack("<HHIIHH", fmt[:16])
    if not (canales and tasa and alineacion and bits):
        return "danado", ["parámetros de formato inválidos"]
    if datos is None:
        return "danado", ["falta el bloque 'data'"]
    inicio, declarado = datos
    presente = size - inicio
    if presente <= 0:
        return "danado", ["no contiene muestras de audio"]
    if declarado not in (0, 0xFFFFFFFF) and presente < declarado:
        return "advertencia", [f"datos truncados (declarados {declarado} B, presentes {presente} B)"]
    return "ok", []

def _validar_ogg(f, size):
    f.seek(0)
    p = f.read(27)
    if len(p) < 27 or p[:4] != b"OggS" or p[4] != 0:
        return "danado", ["cabecera Ogg inválida"]
    tabla = f.read(p[26])
    if len(tabla) < p[26]:
        return "danado", ["primera página Ogg truncada"]
    cuerpo = f.read(sum(tabla))
    if not cuerpo.startswith((b"\x01vorbis", b"OpusHead", b"\x7fFLAC", b"Speex   ")):
        return "danado", ["cabecera de códec Ogg desconocida"]
    if f.read(4) != b"OggS":
        return "danado", ["falta la segunda página Ogg"]
    f.seek(max(0, size - 65536))
    if b"OggS" not in f.read():
        return "advertencia", ["sin página final (posible truncamiento)"]
    return "ok", []

def _validar_flac(f, size):
    ini = _inicio_tras_id3(f)
    f.seek(ini)
    if f.read(4) != b"fLaC":
        return "danado", ["marca 'fLaC' ausente"]
    pos, primero, ultimo, vueltas = ini + 4, True, False, 0
    while not ultimo and vueltas < 1000:
        vueltas += 1
        f.seek(pos)
        h = f.read(4)
        if len(h) < 4:
            return "danado", ["metadatos FLAC truncados"]
        ultimo, tipo, largo = bool(h[0] & 0x80), h[0] & 0x7F, int.from_bytes(h[1:4], "big")
        if tipo == 127:
            return "danado", ["bloque de metadatos FLAC inválido"]
        if primero:
            if tipo != 0 or largo != 34:
                return "danado", ["falta STREAMINFO"]
            si = f.read(34)
            if len(si) < 34 or ((si[10] << 12) | (si[11] << 4) | (si[12] >> 4)) == 0:
                return "danado", ["STREAMINFO inválido"]
            primero = False
        pos += 4 + largo
        if pos >= size:
            return "danado", ["los metadatos exceden el tamaño del archivo"]
    f.seek(pos)
    t = f.read(2)
    if len(t) < 2 or t[0] != 0xFF or (t[1] & 0xFC) != 0xF8:
        return "danado", ["no hay tramas de audio tras los metadatos"]
    return "ok", []
_VALIDADORES = {"mp3": _validar_mp3, "wav": _validar_wav, "ogg": _validar_ogg, "flac": _validar_flac}

def validar_estructura(f, size: int, ext: str, tamano_minimo: int = 64):
    """Valida cabeceras y estructura. Devuelve (estado, detalles)."""
    if size == 0:
        return "danado", ["archivo vacío"]
    if size < tamano_minimo:
        return "danado", [f"archivo demasiado pequeño ({size} bytes)"]
    esperado = ext.lower().lstrip(".")
    real = _tipo_real(f)
    validador = _VALIDADORES.get(real or esperado)
    if validador is None:
        return "advertencia", [f"formato {ext} no verificable estructuralmente"]
    estado, detalles = validador(f, size)
    if real and real != esperado:
        detalles = detalles + [f"la extensión {ext} no coincide con el contenido ({real})"]
        if estado == "ok":
            estado = "advertencia"
    return estado, detalles
# Identificación del contenido real (detección de archivos adulterados)
_FAMILIAS = {
    "mp3":  ({".mp3"}, ".mp3", ".mp3", "MP3"),
    "wav":  ({".wav", ".wave"}, ".wav", ".wav", "WAV"),
    "ogg":  ({".ogg", ".oga", ".opus", ".ogv"}, ".ogg", ".ogv", "OGG"),
    "flac": ({".flac"}, ".flac", ".flac", "FLAC"),
    "mp4":  ({".m4a", ".mp4", ".m4b", ".m4v", ".mov", ".3gp", ".aac"}, ".m4a", ".mp4", "MP4"),
    "webm": ({".webm", ".weba", ".mka", ".mkv"}, ".webm", ".webm", "WebM"),
    "mkv":  ({".mkv", ".mka", ".webm"}, ".mka", ".mkv", "Matroska"),
    "asf":  ({".wma", ".wmv", ".asf"}, ".wma", ".wmv", "Windows Media"),
    "aac":  ({".aac", ".adts"}, ".aac", ".aac", "AAC"),
    "amr":  ({".amr"}, ".amr", ".amr", "AMR"),
    "aiff": ({".aiff", ".aif", ".aifc"}, ".aiff", ".aiff", "AIFF"),
    "ape":  ({".ape"}, ".ape", ".ape", "Monkey's Audio"),
    "wv":   ({".wv"}, ".wv", ".wv", "WavPack"),
    "midi": ({".mid", ".midi"}, ".mid", ".mid", "MIDI"),
    "flv":  ({".flv"}, ".flv", ".flv", "FLV"),
    "avi":  ({".avi"}, ".avi", ".avi", "AVI"),
    "mpeg": ({".mpg", ".mpeg", ".vob"}, ".mpg", ".mpg", "MPEG"),
    "ts":   ({".ts", ".mts", ".m2ts"}, ".ts", ".ts", "MPEG-TS"),
}
TIPOS_COMPATIBLES = {"mp3", "wav", "ogg", "flac"}       # lo que pygame reproduce
_SOLO_VIDEO = {"flv", "avi", "mpeg", "ts"}               # contenedores de vídeo por naturaleza

def _cajas_mp4(f, inicio: int, fin: int, profundidad: int = 0):
    """Recorre cajas ISO-BMFF sin leer los datos: solo cabeceras (8-16 bytes cada una)."""
    pos, n = inicio, 0
    while pos + 8 <= fin and n < 4096:
        n += 1
        f.seek(pos)
        cab = f.read(8)
        if len(cab) < 8:
            return
        tam, tipo = struct.unpack(">I4s", cab)
        cabecera = 8
        if tam == 1:
            ext = f.read(8)
            if len(ext) < 8:
                return
            tam, cabecera = struct.unpack(">Q", ext)[0], 16
        elif tam == 0:
            tam = fin - pos
        if tam < cabecera:
            return
        yield tipo, pos + cabecera, pos + tam, profundidad
        pos += tam

def _pistas_mp4(f, size: int):
    """Devuelve (tiene_audio, tiene_video) leyendo moov/trak/mdia/hdlr."""
    audio = video = False
    for tipo, ini, fin, _ in _cajas_mp4(f, 0, size):
        if tipo != b"moov":
            continue
        for t2, i2, f2, _ in _cajas_mp4(f, ini, fin):
            if t2 != b"trak":
                continue
            for t3, i3, f3, _ in _cajas_mp4(f, i2, f2):
                if t3 != b"mdia":
                    continue
                for t4, i4, f4, _ in _cajas_mp4(f, i3, f3):
                    if t4 == b"hdlr":
                        f.seek(i4 + 8)
                        manejador = f.read(4)
                        audio |= manejador == b"soun"
                        video |= manejador == b"vide"
    return audio, video

def _pistas_matroska(f):
    f.seek(0)
    bloque = f.read(256 * 1024)
    return b"A_" in bloque and any(c in bloque for c in (b"A_OPUS", b"A_VORBIS", b"A_AAC", b"A_MPEG", b"A_FLAC", b"A_PCM", b"A_AC3")), \
        any(c in bloque for c in (b"V_VP8", b"V_VP9", b"V_AV1", b"V_MPEG4", b"V_MPEGH", b"V_MPEG2", b"V_THEORA"))

def identificar_contenido(f, size: int) -> Optional[dict]:
    """Identifica el tipo REAL por su firma, sin fiarse de la extensión."""
    f.seek(0)
    c = f.read(64)
    if len(c) < 12:
        return None
    real, audio, video = None, True, False
    if c[4:8] == b"ftyp":
        real = "mp4"
        try:
            audio, video = _pistas_mp4(f, size)
        except (OSError, struct.error):
            audio, video = True, False
    elif c[:4] == b"\x1aE\xdf\xa3":
        real = "webm" if b"webm" in c else "mkv"
        audio, video = _pistas_matroska(f)
    elif c[:16] == b"0&\xb2u\x8ef\xcf\x11\xa6\xd9\x00\xaa\x00b\xce\x6c":
        real = "asf"
        f.seek(0)
        cab = f.read(64 * 1024)
        video = b"\xc0\xef\x19\xbcM[\xcf\x11\xa8\xfd\x00\x80_\\D+" in cab   # ASF_Video_Media
    elif c[:4] in (b"RIFF", b"RF64") and c[8:12] == b"AVI ":
        real, video = "avi", True
    elif c[:4] == b"FORM" and c[8:12] in (b"AIFF", b"AIFC"):
        real = "aiff"
    elif c[:3] == b"FLV":
        real, video = "flv", True
    elif c[:4] == b"\x00\x00\x01\xba":
        real, video = "mpeg", True
    elif c[0] == 0x47 and size > 376:
        f.seek(188)
        if f.read(1) == b"\x47":
            real, video = "ts", True
    elif c[:6] == b"#!AMR\n" or c[:9] == b"#!AMR-WB\n":
        real = "amr"
    elif c[:4] == b"MAC ":
        real = "ape"
    elif c[:4] == b"wvpk":
        real = "wv"
    elif c[:4] == b"MThd":
        real = "midi"
    elif len(c) >= 2 and c[0] == 0xFF and (c[1] & 0xF6) == 0xF0:   # ADTS (capa 00)
        real = "aac"
    if real is None:
        real = _tipo_real(f)
        if real is None:
            return None
    if real == "ogg":                       # ¿la primera pista es vídeo (Theora / Daala)?
        f.seek(0)
        bloque = f.read(64 * 1024)
        video = b"\x80theora" in bloque or b"\x80daala" in bloque
        audio = any(x in bloque for x in (b"\x01vorbis", b"OpusHead", b"\x7fFLAC", b"Speex   "))
    nombre = _FAMILIAS[real][3]
    if real in _SOLO_VIDEO or video:
        descripcion = f"vídeo {nombre}" + (" con audio" if audio else " sin audio")
    else:
        descripcion = f"audio {nombre}"
    return {"real": real, "audio": bool(audio), "video": bool(video), "descripcion": descripcion}

def diagnosticar_extension(ext: str, info: Optional[dict]) -> Optional[dict]:
    """Compara la extensión con el contenido real. None si son coherentes o no se sabe."""
    if not info:
        return None
    coherentes, ext_audio, ext_video, _ = _FAMILIAS[info["real"]]
    ext = ext.lower()
    if ext in coherentes:
        return None
    correcta = ext_video if info["video"] else ext_audio
    return {**info, "ext_actual": ext, "ext_correcta": correcta,
            "compatible": info["real"] in TIPOS_COMPATIBLES and not info["video"]}
# Verificación profunda: se ejecuta en un PROCESO APARTE con el controlador de
_SCRIPT_VERIFICACION = r'''
import json, os, sys, time
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
ruta, completa = sys.argv[1], sys.argv[2] == "1"
def emitir(**d):
    print(json.dumps(d), flush=True)
try:
    import pygame
    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
except BaseException as e:
    emitir(estado="inconcluso", detalle="mixer no disponible: %s" % e)
    sys.exit(0)
print("INIT_OK", flush=True)
try:
    pygame.mixer.music.load(ruta)
    pygame.mixer.music.set_volume(0.0)
    pygame.mixer.music.play()
    time.sleep(0.3)
    pygame.mixer.music.stop()
except Exception as e:
    emitir(estado="danado", detalle="pygame.mixer.music no puede abrirlo: %s" % str(e)[:160])
    sys.exit(0)
if completa:
    try:
        if pygame.mixer.Sound(ruta).get_length() <= 0:
            raise ValueError("duración cero")
    except Exception as e:
        emitir(estado="advertencia", detalle="la decodificación completa falló: %s" % str(e)[:160])
        sys.exit(0)
emitir(estado="ok")
'''

class SupervisorBiblioteca:
    LATIDO_CADUCADO = 90.0
    ARCHIVO_ESTADO = "estado_supervisor.json"
    ARCHIVO_INFORME = "informe_biblioteca.json"
    ARCHIVO_MANIFIESTO = "manifiesto.json"
    def __init__(self, reproductor=None, carpeta=None, config: Optional[ConfigSupervisor] = None):
        self._rep = reproductor
        origen = carpeta if carpeta is not None else getattr(reproductor, "carpeta", None)
        if origen is None:
            raise ValueError("Indica un reproductor o la carpeta de audios.")
        self.cfg = config or ConfigSupervisor()
        if self.cfg.modo not in ("observar", "cuarentena"):
            raise ValueError("modo debe ser 'observar' o 'cuarentena'.")
        self.carpeta = Path(origen).resolve()
        ruta_mem = getattr(reproductor, "ruta_memoria", None)
        self.ruta_memoria = Path(ruta_mem) if ruta_mem else self.carpeta.parent / "datos" / "memoriamusical.json"
        base = Path(self.cfg.carpeta_datos) if self.cfg.carpeta_datos else self.ruta_memoria.parent / "supervisor"
        self.dir_datos = base.resolve()
        self.dir_cuarentena = (Path(self.cfg.carpeta_cuarentena) if self.cfg.carpeta_cuarentena
                               else self.carpeta / "cuarentena").resolve()
        self.dir_datos.mkdir(parents=True, exist_ok=True)
        self._ext_ok = {e.lower() for e in (getattr(reproductor, "EXTENSIONES_AUDIO", None) or EXTENSIONES_POR_DEFECTO)}
        self._mutex = threading.RLock()          # solo estado interno; jamás se toma el lock del reproductor
        self._ciclo_lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._hilo: Optional[threading.Thread] = None
        self._proc: Optional[subprocess.Popen] = None
        self._pausado = False
        self._solicitud = False
        self._profunda_desactivada = False
        self._token = uuid.uuid4().hex
        self._tiene_instancia = False
        self._ruta_lock = self.dir_datos / "supervisor.lock"
        self._snap_abiertos = (0.0, set())
        self._memo_cache = None
        self._n_ciclos = 0
        self._ultimo_ciclo_t: Optional[float] = None
        self._firma_ciclo = None
        self._informe: dict = {}
        self._contenido: dict = {}          # clave -> (huella, diagnóstico de extensión)
        self._ffmpeg: Optional[str] = None
        self._ffmpeg_buscado = False
        self._limpieza_pedida: Optional[set] = None   # categorías pedidas por el usuario
        self._ultima_limpieza: dict = {}
        estado = _leer_json(self.dir_datos / self.ARCHIVO_ESTADO, {})
        self._cache = {k: v for k, v in estado.get("archivos", {}).items()
                       if isinstance(v, dict) and isinstance(v.get("fp"), list) and len(v["fp"]) == 2}
        self._restaurados = {k: v for k, v in estado.get("restaurados", {}).items()
                             if isinstance(v, list) and len(v) == 2}
        man = _leer_json(self.dir_cuarentena / self.ARCHIVO_MANIFIESTO, {})
        self._manifiesto = [e for e in man.get("entradas", []) if isinstance(e, dict)]
        self._log = self._configurar_log()
        atexit.register(self.detener)
    def _configurar_log(self) -> logging.Logger:
        log = logging.getLogger("MILLER.supervisor")
        if not getattr(log, "_miller_configurado", False):
            log.setLevel(logging.INFO)
            log.propagate = False
            consola = logging.StreamHandler()
            consola.setFormatter(logging.Formatter("[ SUPERVISOR ] %(message)s"))
            log.addHandler(consola)
            try:
                arch = RotatingFileHandler(self.dir_datos / "supervisor.log", maxBytes=512_000,
                                           backupCount=3, encoding="utf-8")
                arch.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
                log.addHandler(arch)
            except OSError:
                pass
            log._miller_configurado = True
        return log
    def iniciar(self) -> bool:
        with self._mutex:
            if self.esta_activo():
                return True
            if self._rep is not None and getattr(self._rep, "cerrado", False):
                self._log.warning("El reproductor ya está cerrado; no se inicia el supervisor.")
                return False
            if not self._adquirir_instancia():
                self._log.warning("Ya hay otro supervisor activo sobre esta biblioteca.")
                return False
            self._stop.clear()
            self._wake.clear()
            self._mantenimiento()
            self._hilo = threading.Thread(target=self._bucle, daemon=True, name="MILLER-SupervisorBiblioteca")
            self._hilo.start()
        self._log.info(f"Supervisor {VERSION} iniciado (modo: {self.cfg.modo}). Biblioteca: {self.carpeta}")
        return True
    def detener(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        proc = self._proc
        if proc is not None:
            try:
                proc.kill()
            except OSError:
                pass
        h = self._hilo
        if h is not None and h.is_alive() and h is not threading.current_thread():
            h.join(timeout)
        self._liberar_instancia()
    def esta_activo(self) -> bool:
        return bool(self._hilo and self._hilo.is_alive())
    def pausar(self) -> None:
        self._pausado = True
    def reanudar(self) -> None:
        self._pausado = False
        self._wake.set()
    def escanear_ahora(self) -> None:
        """Pide un ciclo inmediato al hilo en segundo plano (no bloquea)."""
        self._solicitud = True
        self._wake.set()
    def escanear_una_vez(self) -> Optional[dict]:
        """Ejecuta un ciclo síncrono (útil desde la CLI). None si hay otro supervisor activo."""
        if self.esta_activo():
            self.escanear_ahora()
            return None
        if not self._adquirir_instancia():
            self._log.warning("Ya hay otro supervisor activo sobre esta biblioteca.")
            return None
        try:
            self._mantenimiento()
            return self._ciclo("manual")
        finally:
            self._liberar_instancia()
    CATEGORIAS_LIMPIEZA = ("danados", "duplicados", "no_compatibles", "adulterados")
    def solicitar_limpieza(self, categorias=("danados", "duplicados")) -> bool:
        """Pide al hilo una limpieza inmediata (no bloquea)."""
        cats = {c for c in categorias if c in self.CATEGORIAS_LIMPIEZA}
        if not cats or not self.esta_activo():
            return False
        with self._mutex:
            self._limpieza_pedida = cats
            self._ultima_limpieza = {"estado": "en_curso", "categorias": sorted(cats), "solicitada": _iso()}
        self._wake.set()
        return True
    def obtener_ultima_limpieza(self) -> dict:
        with self._mutex:
            return copy.deepcopy(self._ultima_limpieza)
    def obtener_informe(self) -> dict:
        with self._mutex:
            return copy.deepcopy(self._informe)
    def obtener_estado(self) -> dict:
        with self._mutex:
            return {"activo": self.esta_activo(), "pausado": self._pausado, "modo": self.cfg.modo,
                    "ciclos": self._n_ciclos, "biblioteca": str(self.carpeta),
                    "carpeta_datos": str(self.dir_datos),
                    "en_cuarentena": sum(1 for e in self._manifiesto if self._vigente(e)),
                    "verificacion_profunda": self.cfg.verificacion_profunda and not self._profunda_desactivada,
                    "reparacion_automatica": self.cfg.reparacion_automatica,
                    "eliminacion_automatica": self.cfg.eliminacion_automatica,
                    "carpeta_cuarentena": str(self.dir_cuarentena)}
    def __enter__(self):
        self.iniciar()
        return self
    def __exit__(self, *_):
        self.detener()
    def _adquirir_instancia(self) -> bool:
        if self._tiene_instancia:
            return True
        self.dir_datos.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(str(self._ruta_lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    edad = time.time() - self._ruta_lock.stat().st_mtime
                    pid = int(_leer_json(self._ruta_lock, {}).get("pid", 0))
                except (OSError, ValueError, TypeError):
                    edad, pid = self.LATIDO_CADUCADO + 1, 0
                if edad < self.LATIDO_CADUCADO and _pid_activo(pid):
                    return False
                try:
                    self._ruta_lock.unlink()
                except OSError:
                    return False
                continue
            except OSError:
                return False
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"pid": os.getpid(), "token": self._token, "inicio": _iso()}, f)
            self._tiene_instancia = True
            return True
        return False
    def _liberar_instancia(self) -> None:
        if not self._tiene_instancia:
            return
        self._tiene_instancia = False
        try:
            if _leer_json(self._ruta_lock, {}).get("token") == self._token:
                self._ruta_lock.unlink()
        except OSError:
            pass
    def _latido(self) -> None:
        try:
            os.utime(self._ruta_lock, None)
        except OSError:
            pass
    def _datos_memoria_json(self):
        """Solo modo independiente (sin objeto reproductor). Lectura de milisegundos."""
        try:
            st = self.ruta_memoria.stat()
        except OSError:
            return {}, set()
        llave = (st.st_mtime_ns, st.st_size)
        if self._memo_cache and self._memo_cache[0] == llave:
            return self._memo_cache[1], self._memo_cache[2]
        datos = None
        for _ in range(3):
            try:
                datos = json.loads(self.ruta_memoria.read_bytes().decode("utf-8"))
                break
            except (OSError, ValueError):
                time.sleep(0.05)
        if isinstance(datos, dict):
            datos = datos.get("memoria_musical", datos)
        if not isinstance(datos, dict):
            return {}, set()
        estado = datos.get("estado_reproductor")
        canciones = datos.get("canciones")
        estado = estado if isinstance(estado, dict) else {}
        claves = set(canciones) if isinstance(canciones, dict) else set()
        self._memo_cache = (llave, estado, claves)
        return estado, claves
    def _protegidos(self, rapido: bool = False, historial: Optional[bool] = None) -> set:
        """Claves de los archivos que NO se pueden tocar ahora mismo."""
        historial = self.cfg.proteger_historial if historial is None else historial
        claves: set = set()
        rep = self._rep
        if rep is not None:
            try:  # lecturas de atributos públicos, sin tomar ningún lock
                actual = getattr(rep, "cancion_actual", None)
                if actual:
                    claves.add(_clave(actual))
                for p in list(getattr(rep, "cola", None) or ()):
                    claves.add(_clave(p))
                if historial:
                    for p in list(getattr(rep, "historial", None) or ()):
                        claves.add(_clave(p))
            except Exception as e:
                self._log.debug(f"No se pudo leer el estado del reproductor: {e}")
        elif not rapido:
            estado, _ = self._datos_memoria_json()
            if isinstance(estado.get("cancion_actual"), str):
                claves.add(_clave(estado["cancion_actual"]))
            for campo in (("cola", "historial") if historial else ("cola",)):
                for p in estado.get(campo, []) if isinstance(estado.get(campo), list) else []:
                    if isinstance(p, str):
                        claves.add(_clave(p))
        return claves
    def _claves_memoria(self) -> set:
        rep = self._rep
        if rep is not None:
            try:
                return set(list((getattr(rep, "memoria_musical", None) or {}).get("canciones", {})))
            except Exception:
                return set()
        return self._datos_memoria_json()[1]
    def _abiertos_linux(self) -> set:
        t, conjunto = self._snap_abiertos
        if time.monotonic() - t < 2.0:
            return conjunto
        base, nuevo = str(self.carpeta) + os.sep, set()
        try:
            for pid_dir in os.scandir("/proc"):
                if not pid_dir.name.isdigit():
                    continue
                try:
                    for fd in os.scandir(f"/proc/{pid_dir.name}/fd"):
                        try:
                            destino = os.readlink(fd.path)
                        except OSError:
                            continue
                        if destino.startswith(base):
                            nuevo.add(destino)
                except OSError:
                    continue
        except OSError:
            pass
        self._snap_abiertos = (time.monotonic(), nuevo)
        return nuevo
    def _abierto_por_otro(self, ruta: Path) -> bool:
        """Bloqueo a nivel de sistema operativo (segunda barrera)."""
        try:
            if os.name == "nt":
                try:
                    os.rename(ruta, ruta)   # no-op; falla con PermissionError si está abierto
                except PermissionError:
                    return True
                except OSError:
                    return False
                return False
            if os.path.isdir("/proc/self/fd"):
                return os.path.realpath(ruta) in self._abiertos_linux()
        except Exception:
            return False
        return False
    def _apto(self, ruta: Path):
        if _clave(ruta) in self._protegidos():
            return False, "en uso por el reproductor (actual, cola o historial)"
        if self._abierto_por_otro(ruta):
            return False, "abierto por el sistema o por otro proceso"
        return True, ""
    def _dentro_biblioteca(self, ruta: Path) -> bool:
        try:
            return ruta.parent.resolve() == self.carpeta and not ruta.is_symlink()
        except OSError:
            return False
    def _es_manual(self, e: dict) -> bool:
        return self._restaurados.get(e["clave"]) == list(e["fp"])
    @staticmethod
    def _fp_actual(ruta: Path):
        try:
            st = ruta.stat()
            return (st.st_size, st.st_mtime_ns)
        except OSError:
            return None
    def _firma(self):
        try:
            with os.scandir(self.carpeta) as it:
                return tuple(sorted((e.name, e.stat(follow_symlinks=False).st_size,
                                     e.stat(follow_symlinks=False).st_mtime_ns)
                                    for e in it if e.is_file(follow_symlinks=False)))
        except OSError:
            return None
    def _inventario(self):
        try:
            with os.scandir(self.carpeta) as it:
                crudos = sorted((e for e in it if e.is_file(follow_symlinks=False)),
                                key=lambda e: e.name.casefold())
        except OSError:
            return None
        ahora_ns, salida = time.time_ns(), []
        for e in crudos:
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            ruta = Path(e.path)
            ext = ruta.suffix.lower()
            clase = ("temporal" if ext in EXTENSIONES_TEMPORALES else
                     "soportado" if ext in self._ext_ok else
                     "no_compatible" if ext in EXTENSIONES_NO_COMPATIBLES else "otro")
            edad = (ahora_ns - st.st_mtime_ns) / 1e9
            salida.append({"ruta": ruta, "nombre": e.name, "ext": ext, "clase": clase,
                           "size": st.st_size, "fp": (st.st_size, st.st_mtime_ns),
                           "clave": _clave(ruta),
                           "estable": not (0 <= edad < self.cfg.estabilidad_segundos)})
        return salida
    def _verificacion_profunda(self, ruta: Path, size: int):
        if self._profunda_desactivada or getattr(sys, "frozen", False) or not sys.executable:
            return "inconcluso", "verificación profunda no disponible"
        completa = size <= self.cfg.max_bytes_decodificacion_completa
        env = dict(os.environ, SDL_AUDIODRIVER="dummy", SDL_VIDEODRIVER="dummy", PYGAME_HIDE_SUPPORT_PROMPT="1")
        extra = {"creationflags": 0x08000000 | 0x00004000} if os.name == "nt" else {}   # sin ventana y con prioridad baja
        try:
            proc = subprocess.Popen(
                [sys.executable, "-c", _SCRIPT_VERIFICACION, str(ruta), "1" if completa else "0"],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, env=env, cwd=str(self.dir_datos), **extra)
        except OSError as e:
            return "inconcluso", f"no se pudo lanzar el verificador: {e}"
        self._proc = proc
        limite = time.monotonic() + self.cfg.timeout_verificacion
        try:
            while True:
                try:
                    salida, _err = proc.communicate(timeout=0.5)
                    break
                except subprocess.TimeoutExpired:
                    if self._stop.is_set() or time.monotonic() > limite:
                        proc.kill()
                        proc.communicate()
                        return "inconcluso", "tiempo agotado o supervisor detenido"
        finally:
            self._proc = None
        lineas = [l.strip() for l in (salida or "").splitlines() if l.strip()]
        for l in reversed(lineas):
            if l.startswith("{"):
                try:
                    d = json.loads(l)
                except ValueError:
                    continue
                estado = d.get("estado") if d.get("estado") in ("ok", "advertencia", "danado", "inconcluso") else "inconcluso"
                return estado, str(d.get("detalle", ""))
        if "INIT_OK" in lineas:
            return "danado", f"el decodificador terminó de forma anómala (código {proc.returncode})"
        return "inconcluso", "el verificador no devolvió resultado"
    def _verificar(self, e: dict) -> Optional[dict]:
        ruta = e["ruta"]
        try:
            with ruta.open("rb") as f:
                estado, detalles = validar_estructura(f, e["size"], e["ext"], self.cfg.tamano_minimo_bytes)
        except OSError as ex:
            return {"estado": "inconcluso", "detalles": [f"no se pudo leer: {ex}"]}
        if estado != "danado" and self.cfg.verificacion_profunda and not self._profunda_desactivada:
            time.sleep(self.cfg.pausa_entre_verificaciones)
            pe, pd = self._verificacion_profunda(ruta, e["size"])
            if pd.startswith("mixer no disponible"):
                self._profunda_desactivada = True
                self._log.info("pygame/mixer no disponible para el verificador: verificación profunda desactivada.")
            elif pe == "danado":
                estado = "danado"
                detalles.append(pd)
            elif pe == "advertencia":
                estado = "advertencia" if estado == "ok" else estado
                detalles.append(pd)
        # Descartar si el archivo cambió o pasó a estar en uso durante el análisis.
        if self._fp_actual(ruta) != tuple(e["fp"]) or e["clave"] in self._protegidos(rapido=True):
            return None
        return {"estado": estado, "detalles": detalles, "comprobado": int(time.time())}
    def _calcular_hash(self, e: dict) -> Optional[str]:
        h, n = hashlib.sha256(), 0
        try:
            with e["ruta"].open("rb") as f:
                while True:
                    if self._stop.is_set():
                        return None
                    bloque = f.read(1 << 20)
                    if not bloque:
                        break
                    h.update(bloque)
                    n += 1
                    if n % 8 == 0 and e["clave"] in self._protegidos(rapido=True):
                        return None
                    time.sleep(0.002)
        except OSError:
            return None
        if self._fp_actual(e["ruta"]) != tuple(e["fp"]) or e["clave"] in self._protegidos(rapido=True):
            return None
        return h.hexdigest()
    def _obtener_hash(self, e: dict) -> Optional[str]:
        c = self._cache.get(e["clave"])
        vigente = bool(c and c["fp"] == list(e["fp"]))
        if vigente and c.get("sha256"):
            return c["sha256"]          # un archivo en uso solo aporta su hash ya guardado
        if not e["estable"] or not self._apto(e["ruta"])[0]:
            return None
        h = self._calcular_hash(e)
        if h:
            if vigente:
                c["sha256"] = h
            else:
                self._cache[e["clave"]] = {"fp": list(e["fp"]), "salud": None, "sha256": h}
        return h
    def _vigente(self, entrada: dict) -> bool:
        return not (entrada.get("restaurado") or entrada.get("purgado") or entrada.get("eliminado") or entrada.get("perdido"))
    def _ruta_en_cuarentena(self, entrada: dict) -> Optional[Path]:
        try:
            ruta = (self.dir_cuarentena / entrada["ruta_cuarentena"]).resolve()
            ruta.relative_to(self.dir_cuarentena.resolve())
            return ruta
        except (KeyError, ValueError, OSError, TypeError):
            return None
    @staticmethod
    def _destino_unico(sub: Path, nombre: str) -> Path:
        base = f"{time.strftime('%Y%m%d-%H%M%S')}_{Path(nombre).name}"
        destino, n = sub / base, 1
        while destino.exists():
            n += 1
            destino = sub / f"{Path(base).stem}~{n}{Path(base).suffix}"
        return destino
    @staticmethod
    def _copiar_y_borrar(origen: Path, destino: Path) -> bool:
        try:
            shutil.copy2(origen, destino)
            if destino.stat().st_size != origen.stat().st_size:
                destino.unlink()
                return False
            try:
                origen.unlink()
            except OSError:
                destino.unlink()
                return False
            return True
        except OSError:
            return False
    def _guardar_manifiesto(self) -> None:
        _escribir_json(self.dir_cuarentena / self.ARCHIVO_MANIFIESTO,
                       {"version": 1, "entradas": self._manifiesto})
    def _mover_a_cuarentena(self, ruta: Path, categoria: str, motivo: str, extra: Optional[dict] = None,
                            nombre_destino: Optional[str] = None, proteger_historial: Optional[bool] = None):
        with self._mutex:
            clave = _clave(ruta)
            if clave in self._protegidos(historial=proteger_historial) or not ruta.is_file() or not self._dentro_biblioteca(ruta):
                return None
            if self._abierto_por_otro(ruta):
                return None
            try:
                tam = ruta.stat().st_size
                sub = self.dir_cuarentena / categoria
                sub.mkdir(parents=True, exist_ok=True)
                destino = self._destino_unico(sub, nombre_destino or ruta.name)
            except OSError as e:
                self._log.warning(f"No se pudo preparar la cuarentena: {e}")
                return None
            try:
                os.replace(ruta, destino)
            except PermissionError:
                self._log.info(f"Omitido (el sistema lo mantiene en uso): {ruta.name}")
                return None
            except OSError:
                if not self._copiar_y_borrar(ruta, destino):
                    self._log.warning(f"No se pudo mover a cuarentena: {ruta.name}")
                    return None
            # Última barrera: si el reproductor lo eligió justo ahora, se devuelve a su sitio.
            if clave in self._protegidos(historial=proteger_historial):
                try:
                    if not ruta.exists():
                        os.replace(destino, ruta)
                        self._log.warning(f"Reproductor y supervisor coincidieron en {ruta.name}: restaurado.")
                        return None
                except OSError:
                    pass
            entrada = {"id": uuid.uuid4().hex[:8], "nombre": ruta.name, "categoria": categoria,
                       "ruta_cuarentena": f"{categoria}/{destino.name}", "motivo": motivo,
                       "tamano": tam, "ts": time.time(), "fecha": _iso(), **(extra or {})}
            self._manifiesto.append(entrada)
            self._guardar_manifiesto()
            self._cache.pop(clave, None)
            self._log.info(f"→ cuarentena/{categoria}: {ruta.name} ({motivo})")
            return entrada
    def mover_a_papelera(self, ruta, motivo: str = "orden del usuario") -> Optional[dict]:
        """Papelera: aparta una canción que el usuario mandó borrar a cuarentena/papelera/."""
        ruta = Path(ruta)
        if not ruta.is_absolute():
            ruta = self.carpeta / ruta
        return self._mover_a_cuarentena(ruta, "papelera", motivo, proteger_historial=False)
    def listar_cuarentena(self) -> list:
        with self._mutex:
            return [dict(e) for e in self._manifiesto if self._vigente(e)]
    def restaurar_de_cuarentena(self, id_o_nombre: str) -> bool:
        """Devuelve un archivo a la biblioteca. Queda exento de nuevas acciones mientras no cambie."""
        q = str(id_o_nombre or "").strip().casefold()
        with self._mutex:
            entrada = next((e for e in reversed(self._manifiesto)
                            if self._vigente(e) and q in (str(e.get("id", "")).casefold(),
                                                          str(e.get("nombre", "")).casefold())), None)
            origen = self._ruta_en_cuarentena(entrada) if entrada else None
            if origen is None or not origen.is_file():
                return False
            nombre = Path(entrada.get("nombre_restaurar") or entrada["nombre"]).name   # solo el nombre
            destino, n = self.carpeta / nombre, 0
            while destino.exists():
                n += 1
                destino = self.carpeta / f"{Path(nombre).stem} (restaurado {n}){Path(nombre).suffix}"
            try:
                os.replace(origen, destino)
            except OSError:
                if not self._copiar_y_borrar(origen, destino):
                    return False
            entrada["restaurado"] = _iso()
            fp = self._fp_actual(destino)
            if fp:
                self._restaurados[_clave(destino)] = list(fp)
            self._guardar_manifiesto()
            self._guardar_estado()
            self._log.info(f"Restaurado: {destino.name}")
            return True
    def _buscar_ffmpeg(self) -> Optional[str]:
        """FFmpeg es opcional: config > modelos/ del proyecto > PATH. Se verifica una vez."""
        if self._ffmpeg_buscado:
            return self._ffmpeg
        self._ffmpeg_buscado = True
        nombres = ("ffmpeg.exe", "ffmpeg") if os.name == "nt" else ("ffmpeg",)
        candidatos = [Path(self.cfg.ruta_ffmpeg)] if self.cfg.ruta_ffmpeg else []
        modelos = self.carpeta.parent / "modelos"
        for nombre in nombres:
            candidatos += [modelos / "ffmpeg-master-gpl" / "bin" / nombre]
            try:
                candidatos += list(modelos.rglob(nombre))[:5] if modelos.is_dir() else []
            except OSError:
                pass
            if shutil.which(nombre):
                candidatos.append(Path(shutil.which(nombre)))
        extra = {"creationflags": 0x08000000 | 0x00004000} if os.name == "nt" else {}   # sin ventana y con prioridad baja
        for c in candidatos:
            try:
                if c.is_file() and subprocess.run([str(c), "-version"], stdin=subprocess.DEVNULL,
                                                  capture_output=True, timeout=10, **extra).returncode == 0:
                    self._ffmpeg = str(c)
                    self._log.info(f"FFmpeg disponible para reparar archivos: {c}")
                    return self._ffmpeg
            except (OSError, subprocess.SubprocessError):
                continue
        self._log.info("FFmpeg no disponible: los adulterados no compatibles solo se corrigen y se apartan.")
        return None
    def _contenido_de(self, e: dict) -> Optional[dict]:
        """Diagnóstico de extensión (con caché por huella). None = coherente o desconocido."""
        guardado = self._contenido.get(e["clave"])
        if guardado and guardado[0] == tuple(e["fp"]):
            return guardado[1]
        try:
            with e["ruta"].open("rb") as f:
                diag = diagnosticar_extension(e["ext"], identificar_contenido(f, e["size"]))
        except OSError:
            return None
        self._contenido[e["clave"]] = (tuple(e["fp"]), diag)
        return diag
    @staticmethod
    def _nombre_libre(carpeta: Path, base: str, ext: str) -> Path:
        destino, n = carpeta / f"{base}{ext}", 1
        while destino.exists():
            destino = carpeta / f"{base} (reparado{'' if n == 1 else ' ' + str(n)}){ext}"
            n += 1
        return destino
    def _convertir_a_mp3(self, ffmpeg: str, origen: Path, destino: Path) -> bool:
        extra = {"creationflags": 0x08000000 | 0x00004000} if os.name == "nt" else {}   # sin ventana, prioridad baja
        cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(origen),
               "-map", "0:a:0", "-vn", "-c:a", "libmp3lame", "-q:a", "2", "-map_metadata", "0",
               "-id3v2_version", "3", "-threads", "1", str(destino)]
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.PIPE, text=True, **extra)
        except OSError as ex:
            self._log.warning(f"No se pudo lanzar FFmpeg: {ex}")
            return False
        self._proc = proc
        limite = time.monotonic() + self.cfg.timeout_conversion
        try:
            while True:
                try:
                    _, err = proc.communicate(timeout=0.5)
                    break
                except subprocess.TimeoutExpired:
                    self._latido()
                    if self._stop.is_set() or time.monotonic() > limite:
                        proc.kill()
                        proc.communicate()
                        return False
        finally:
            self._proc = None
        if proc.returncode != 0:
            self._log.warning(f"FFmpeg no pudo convertir {origen.name}: {(err or '').strip()[:160]}")
            return False
        try:
            size = destino.stat().st_size
            with destino.open("rb") as f:
                estado, _ = validar_estructura(f, size, ".mp3", self.cfg.tamano_minimo_bytes)
            if size <= 1024 or estado == "danado":
                return False
        except OSError:
            return False
        if self.cfg.verificar_duracion:
            antes, despues = self._duracion(origen), self._duracion(destino)
            if antes and despues and despues < antes * 0.9:
                self._log.warning(f"Conversión incompleta de {origen.name}: {despues:.0f}s de {antes:.0f}s")
                return False
        return True
    def _duracion(self, ruta: Path) -> Optional[float]:
        """Duración en segundos con ffprobe (junto a ffmpeg). None si no se puede medir."""
        if not self._ffmpeg:
            return None
        ffprobe = Path(self._ffmpeg).with_name("ffprobe" + Path(self._ffmpeg).suffix)
        if not ffprobe.is_file():
            ffprobe = Path(shutil.which("ffprobe") or "")
            if not ffprobe.is_file():
                return None
        extra = {"creationflags": 0x08000000 | 0x00004000} if os.name == "nt" else {}   # sin ventana y con prioridad baja
        try:
            r = subprocess.run([str(ffprobe), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                str(ruta)], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30, **extra)
            return float(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None
        except (OSError, ValueError, subprocess.SubprocessError):
            return None
    def _hay_espacio(self, necesario: int) -> bool:
        try:
            libre = shutil.disk_usage(self.carpeta).free
        except OSError:
            return True
        return libre - necesario > self.cfg.espacio_minimo_mb * 1024 * 1024
    def _mantenimiento(self) -> None:
        """Al arrancar: borra temporales huérfanos y marca entradas cuyo archivo ya no existe."""
        temporal = self.dir_cuarentena / "_temporal"
        if temporal.is_dir():
            for f in temporal.iterdir():
                try:
                    f.unlink()
                    self._log.info(f"Temporal huérfano eliminado: {f.name}")
                except OSError:
                    pass
        with self._mutex:
            perdidos = 0
            for e in self._manifiesto:
                ruta = self._ruta_en_cuarentena(e) if self._vigente(e) else None
                if self._vigente(e) and (ruta is None or not ruta.is_file()):
                    e["perdido"] = _iso()
                    perdidos += 1
            if perdidos:
                self._guardar_manifiesto()
                self._log.warning(f"{perdidos} entradas de la cuarentena sin archivo: marcadas como perdidas.")
    def _reparar(self, e: dict, d: dict) -> Optional[dict]:
        """Corrige un archivo adulterado. Nunca toca archivos en uso ni borra nada."""
        ruta = e["ruta"]
        if self._stop.is_set() or (self._rep is not None and getattr(self._rep, "cerrado", False)):
            return None
        if not self._apto(ruta)[0] or self._fp_actual(ruta) != tuple(e["fp"]):
            return None
        base, desc = ruta.stem, d["descripcion"]
        if d["compatible"]:
            with self._mutex:
                if _clave(ruta) in self._protegidos() or self._abierto_por_otro(ruta):
                    return None
                destino = self._nombre_libre(self.carpeta, base, d["ext_correcta"])
                try:
                    os.replace(ruta, destino)
                except OSError as ex:
                    self._log.warning(f"No se pudo corregir la extensión de {ruta.name}: {ex}")
                    return None
            self._log.info(f"Reparado: {ruta.name} → {destino.name} (era {desc})")
            return {"accion": "extension_corregida", "archivo": e["nombre"], "nuevo": destino.name,
                    "motivo": f"era {desc} con extensión {d['ext_actual']}"}
        nombre_real = base + d["ext_correcta"]
        info = {"tipo_real": d["real"], "contenido": desc, "nombre_restaurar": nombre_real}
        if not d["audio"]:
            r = self._mover_a_cuarentena(ruta, "danados", f"{desc} con extensión {d['ext_actual']}: no tiene audio",
                                         {**info, "irreparable": True}, nombre_destino=nombre_real)
            return r and {"accion": "cuarentena", "archivo": e["nombre"], "motivo": r["motivo"]}
        convertido = None
        ffmpeg = self._buscar_ffmpeg()
        if ffmpeg and not self._hay_espacio(e["size"] * 3):
            self._log.warning(f"Espacio en disco insuficiente: no se convierte {ruta.name}.")
            return None
        if ffmpeg:
            temporal = self.dir_cuarentena / "_temporal"
            temporal.mkdir(parents=True, exist_ok=True)
            tmp = temporal / f"{uuid.uuid4().hex}.mp3"
            if self._convertir_a_mp3(ffmpeg, ruta, tmp):
                convertido = tmp
            else:
                tmp.unlink(missing_ok=True)
        def descartar():
            if convertido is not None:
                convertido.unlink(missing_ok=True)
        if self._stop.is_set() or self._fp_actual(ruta) != tuple(e["fp"]) or not self._apto(ruta)[0]:
            descartar()
            return None
        motivo = (f"{desc} con extensión {d['ext_actual']}" +
                  ("; convertido a MP3" if convertido else "; sin FFmpeg para convertirlo"))
        r = self._mover_a_cuarentena(ruta, "adulterados", motivo, {**info, "reparado": False},
                                     nombre_destino=nombre_real)
        if not r:
            descartar()
            return None
        if convertido is None:
            return {"accion": "cuarentena", "archivo": e["nombre"], "motivo": motivo}
        destino = ruta if ruta.suffix.lower() == ".mp3" and not ruta.exists() else \
            self._nombre_libre(self.carpeta, base, ".mp3")
        try:
            os.replace(convertido, destino)
        except OSError:
            if not self._copiar_y_borrar(convertido, destino):
                descartar()
                return {"accion": "cuarentena", "archivo": e["nombre"], "motivo": motivo}
        with self._mutex:
            r["reparado"], r["reparado_como"] = True, destino.name
            self._guardar_manifiesto()
        self._log.info(f"Reparado: {e['nombre']} convertido a MP3 real → {destino.name}")
        return {"accion": "convertido", "archivo": e["nombre"], "nuevo": destino.name, "motivo": motivo}
    def _dias_plan(self, entrada: dict) -> Optional[float]:
        cat = entrada.get("categoria")
        if cat == "adulterados":
            cat = "adulterados_reparados" if entrada.get("reparado") else "adulterados"
        dias = (self.cfg.plan_eliminacion or {}).get(cat)
        return float(dias) if dias is not None else None
    def plan_eliminacion(self) -> list:
        """Cuándo se eliminará cada archivo de la cuarentena (None = nunca automáticamente)."""
        ahora, salida = time.time(), []
        with self._mutex:
            for e in self._manifiesto:
                if not self._vigente(e):
                    continue
                dias = self._dias_plan(e) if self.cfg.eliminacion_automatica else None
                cuando = None if dias is None else e.get("ts", ahora) + dias * 86400
                salida.append({"id": e.get("id"), "nombre": e.get("nombre"), "categoria": e.get("categoria"),
                               "motivo": e.get("motivo"), "en_cuarentena_desde": e.get("fecha"),
                               "eliminar_en": None if cuando is None else
                               datetime.fromtimestamp(cuando).astimezone().isoformat(timespec="minutes"),
                               "dias_restantes": None if cuando is None else max(0.0, round((cuando - ahora) / 86400, 1))})
        return sorted(salida, key=lambda x: (x["dias_restantes"] is None, x["dias_restantes"] or 0))
    def _eliminar_entrada(self, entrada: dict, motivo: str) -> bool:
        ruta = self._ruta_en_cuarentena(entrada)
        if ruta is not None and ruta.is_file():
            try:
                ruta.unlink()
            except OSError as ex:
                self._log.warning(f"No se pudo eliminar {entrada.get('nombre')}: {ex}")
                return False
        entrada["eliminado"], entrada["motivo_eliminacion"] = _iso(), motivo
        self._log.info(f"Eliminado definitivamente ({motivo}): {entrada.get('nombre')}")
        return True
    def _ejecutar_plan_eliminacion(self) -> list:
        if not self.cfg.eliminacion_automatica:
            return []
        ahora, eliminados = time.time(), []
        with self._mutex:
            for e in self._manifiesto:
                dias = self._dias_plan(e) if self._vigente(e) else None
                if dias is None or e.get("ts", ahora) + dias * 86400 > ahora:
                    continue
                # Un duplicado solo se borra si el original conservado sigue en la biblioteca.
                if e.get("categoria") == "duplicados" and not (self.carpeta / str(e.get("conservado", ""))).is_file():
                    continue
                if self._eliminar_entrada(e, f"plan automático ({dias:g} días)"):
                    eliminados.append({"accion": "eliminado", "archivo": e.get("nombre"),
                                       "motivo": f"{e.get('categoria')}: {dias:g} días en cuarentena"})
            if eliminados:
                self._guardar_manifiesto()
        return eliminados
    def eliminar_de_cuarentena(self, ids=None, categorias=None) -> int:
        """Elimina YA de la cuarentena (orden explícita del usuario). Devuelve cuántos."""
        n = 0
        with self._mutex:
            for e in self._manifiesto:
                if not self._vigente(e):
                    continue
                if ids is not None and e.get("id") not in ids:
                    continue
                if categorias and e.get("categoria") not in categorias:
                    continue
                if self._eliminar_entrada(e, "orden del usuario"):
                    n += 1
            if n:
                self._guardar_manifiesto()
        return n
    def _purgar_cuarentena(self) -> None:
        dias = self.cfg.purgar_cuarentena_dias
        if not dias:
            return
        limite = time.time() - dias * 86400
        with self._mutex:
            cambio = False
            for e in self._manifiesto:
                if self._vigente(e) and e.get("ts", time.time()) < limite:
                    ruta = self._ruta_en_cuarentena(e)
                    if ruta is not None and ruta.is_file():
                        try:
                            ruta.unlink()
                        except OSError:
                            continue
                    e["purgado"] = _iso()
                    cambio = True
            if cambio:
                self._guardar_manifiesto()
    def _guardar_estado(self) -> None:
        with self._mutex:
            _escribir_json(self.dir_datos / self.ARCHIVO_ESTADO,
                           {"version": 1, "archivos": self._cache, "restaurados": self._restaurados})
    def _ciclo(self, motivo: str = "periodico", limpiar: Optional[set] = None) -> Optional[dict]:
        if not self._ciclo_lock.acquire(blocking=False):
            return None
        try:
            return self._ciclo_interno(motivo, limpiar)
        finally:
            self._ciclo_lock.release()
    def _salud_de(self, e: dict) -> Optional[dict]:
        c = self._cache.get(e["clave"])
        return c["salud"] if c and c.get("salud") and c["fp"] == list(e["fp"]) else None
    @staticmethod
    def _elegir_conservar(grupo, protegidos, claves_mem, es_manual):
        def llave(e):
            return (e["clave"] not in protegidos, not es_manual(e), e["clave"] not in claves_mem,
                    bool(_RE_COPIA.search(e["ruta"].stem)), len(e["nombre"]), e["fp"][1], e["nombre"].casefold())
        return sorted(grupo, key=llave)[0]
    def _ciclo_interno(self, motivo: str, limpiar: Optional[set] = None) -> Optional[dict]:
        t0 = time.monotonic()
        inv = self._inventario()
        if inv is None:
            self._log.debug("La carpeta de audios no existe todavía.")
            return None
        with self._mutex:
            self._n_ciclos += 1
            n_ciclo = self._n_ciclos
        soportados = [e for e in inv if e["clase"] == "soportado"]
        no_compat = [e for e in inv if e["clase"] == "no_compatible"]
        omitidos, pendientes, acciones = [], [], []
        # 0) Adulterados: el contenido real no coincide con la extensión (p. ej. MP4 llamado .mp3).
        adulterados, reparaciones, claves_adulteradas = [], [], set()
        reparar = self.cfg.reparacion_automatica or bool(limpiar and "adulterados" in limpiar)
        conversiones = 0
        for e in soportados + no_compat:
            if self._stop.is_set():
                return None
            if self._es_manual(e) or not e["estable"] or not self._apto(e["ruta"])[0]:
                guardado = self._contenido.get(e["clave"])
                if guardado and guardado[1]:
                    claves_adulteradas.add(e["clave"])
                continue
            d = self._contenido_de(e)
            if not d:
                continue
            claves_adulteradas.add(e["clave"])
            convierte = not d["compatible"] and d["audio"]
            if reparar and not (convierte and conversiones >= self.cfg.max_conversiones_por_ciclo):
                self._latido()
                resultado = self._reparar(e, d)
                conversiones += convierte        # cuenta intentos: una conversión fallida también cuesta
                if resultado:
                    reparaciones.append(resultado)
                    acciones.append(resultado)
                    continue
            adulterados.append({"archivo": e["nombre"], "contenido": d["descripcion"],
                                "extension": d["ext_actual"], "extension_correcta": d["ext_correcta"],
                                "reproducible_al_corregir": d["compatible"]})
        if reparaciones:
            inv = self._inventario() or []
            soportados = [e for e in inv if e["clase"] == "soportado"]
            no_compat = [e for e in inv if e["clase"] == "no_compatible"]
        # 1) Salud de cada archivo (los protegidos / en uso ni se abren).
        for e in soportados:
            if self._stop.is_set():
                return None
            self._latido()
            if self._es_manual(e) or e["clave"] in claves_adulteradas:
                continue
            ok, razon = self._apto(e["ruta"])
            if not ok:
                omitidos.append({"archivo": e["nombre"], "motivo": razon})
                continue
            if not e["estable"]:
                pendientes.append(e["nombre"])
                continue
            if self._salud_de(e):
                continue
            salud = self._verificar(e)
            if salud is None or salud["estado"] == "inconcluso":
                continue
            self._cache[e["clave"]] = {"fp": list(e["fp"]), "salud": salud, "sha256": None}
            time.sleep(self.cfg.pausa_entre_archivos)
        danados = [(e, self._salud_de(e)) for e in soportados]
        danados = [(e, s) for e, s in danados if s and s["estado"] == "danado" and not self._es_manual(e)
                   and e["clave"] not in claves_adulteradas]
        advertencias = [{"archivo": e["nombre"], "detalles": s["detalles"]} for e in soportados
                        if (s := self._salud_de(e)) and s["estado"] == "advertencia"]
        claves_danadas = {e["clave"] for e, _ in danados}
        # 2) Duplicados exactos (tamaño -> SHA-256). Los dañados ya se tratan aparte.
        por_tam = defaultdict(list)
        for e in soportados:
            if e["size"] > 0 and e["clave"] not in claves_danadas and e["clave"] not in claves_adulteradas:
                por_tam[e["size"]].append(e)
        por_hash = defaultdict(list)
        for grupo in por_tam.values():
            if len(grupo) < 2:
                continue
            for e in grupo:
                if self._stop.is_set():
                    return None
                self._latido()
                h = self._obtener_hash(e)
                if h:
                    por_hash[h].append(e)
                time.sleep(self.cfg.pausa_entre_archivos)
        duplicados = [(h, g) for h, g in por_hash.items() if len(g) > 1]
        # 3) Mismo título en distintos archivos (solo informativo).
        hash_de = {e["clave"]: h for h, g in duplicados for e in g}
        por_titulo = defaultdict(list)
        for e in soportados + no_compat:
            titulo = _texto_busqueda(e["ruta"].stem)
            if titulo:
                por_titulo[titulo].append(e)
        posibles = [[e["nombre"] for e in g] for g in por_titulo.values()
                    if len(g) > 1 and len({hash_de.get(e["clave"], e["clave"]) for e in g}) > 1]
        informe_duplicados = []
        for h, g in duplicados:
            conservar = self._elegir_conservar(g, self._protegidos(), self._claves_memoria(), self._es_manual)
            informe_duplicados.append({"sha256": h, "conservar": conservar["nombre"],
                                       "duplicados": [e["nombre"] for e in g if e is not conservar]})
        # 4) Acciones (modo cuarentena o limpieza pedida; cada una revalida protección y estado).
        def mover(cat):
            return cat in limpiar if limpiar else True
        if self.cfg.modo == "cuarentena" or limpiar:
            for e, s in (danados if mover("danados") else []):
                if self._stop.is_set():
                    return None
                if not e["estable"] or not self._apto(e["ruta"])[0] or self._fp_actual(e["ruta"]) != tuple(e["fp"]):
                    continue
                confirmado = self._verificar(e)          # segunda comprobación independiente
                if confirmado and confirmado["estado"] == "danado":
                    r = self._mover_a_cuarentena(e["ruta"], "danados", "; ".join(confirmado["detalles"]) or "dañado")
                    if r:
                        acciones.append({"accion": "cuarentena", "archivo": e["nombre"], "motivo": r["motivo"]})
            for h, g in (duplicados if mover("duplicados") else []):
                conservar = self._elegir_conservar(g, self._protegidos(), self._claves_memoria(), self._es_manual)
                for e in g:
                    if e is conservar or self._es_manual(e) or not e["estable"]:
                        continue
                    if self._fp_actual(conservar["ruta"]) != tuple(conservar["fp"]) or self._fp_actual(e["ruta"]) != tuple(e["fp"]):
                        continue
                    r = self._mover_a_cuarentena(e["ruta"], "duplicados", f"duplicado exacto de {conservar['nombre']}",
                                                 {"sha256": h, "conservado": conservar["nombre"]})
                    if r:
                        acciones.append({"accion": "cuarentena", "archivo": e["nombre"], "motivo": r["motivo"]})
            if (limpiar and "no_compatibles" in limpiar) or (not limpiar and self.cfg.mover_no_compatibles):
                for e in no_compat:
                    if e["estable"] and self._apto(e["ruta"])[0]:
                        r = self._mover_a_cuarentena(e["ruta"], "no_compatibles", f"formato {e['ext']} no compatible")
                        if r:
                            acciones.append({"accion": "cuarentena", "archivo": e["nombre"], "motivo": r["motivo"]})
        acciones.extend(self._ejecutar_plan_eliminacion())
        self._purgar_cuarentena()
        # 5) Persistencia e informe.
        vivos = {e["clave"] for e in inv}
        for k in [k for k in self._cache if k not in vivos]:
            del self._cache[k]
        for k in [k for k in self._restaurados if k not in vivos]:
            del self._restaurados[k]
        self._guardar_estado()
        prot = self._protegidos()
        informe = {
            "version": VERSION, "ciclo": n_ciclo, "motivo": motivo, "generado": _iso(),
            "duracion_s": round(time.monotonic() - t0, 2), "biblioteca": str(self.carpeta), "modo": self.cfg.modo,
            "totales": {"archivos": len(inv), "audio_soportado": len(soportados), "no_compatibles": len(no_compat),
                        "otros": sum(1 for e in inv if e["clase"] == "otro"),
                        "temporales": sum(1 for e in inv if e["clase"] == "temporal"),
                        "protegidos": sum(1 for e in inv if e["clave"] in prot),
                        "en_cuarentena": sum(1 for m in self._manifiesto if self._vigente(m)),
                        "adulterados": len(adulterados), "reparados": len(reparaciones)},
            "danados": [{"archivo": e["nombre"], "detalles": s["detalles"]} for e, s in danados],
            "advertencias": advertencias, "duplicados": informe_duplicados, "posibles_duplicados": posibles,
            "no_compatibles": [e["nombre"] for e in no_compat if e["clave"] not in claves_adulteradas],
            "adulterados": adulterados, "reparaciones": reparaciones,
            "omitidos_por_uso": omitidos, "pendientes_de_estabilidad": pendientes, "acciones": acciones,
        }
        with self._mutex:
            self._informe = informe
        _escribir_json(self.dir_datos / self.ARCHIVO_INFORME, informe)
        self._log.info(f"Ciclo {n_ciclo} ({motivo}): {len(soportados)} pistas, {len(danados)} dañadas, "
                       f"{len(duplicados)} grupos duplicados, {len(adulterados)} adulterados, {len(reparaciones)} reparados, "
                       f"{len(no_compat)} no compatibles, "
                       f"{len(omitidos)} en uso omitidas, {len(acciones)} acciones.")
        return informe
    def _bucle(self) -> None:
        inicio, firma_previa, errores = time.monotonic(), None, 0
        try:
            while not self._stop.is_set():
                self._wake.wait(self.cfg.intervalo_vigilancia)
                self._wake.clear()
                if self._stop.is_set():
                    break
                try:
                    self._latido()
                    if self._rep is not None and getattr(self._rep, "cerrado", False):
                        self._log.info("El reproductor se cerró: supervisor detenido.")
                        break
                    if self._pausado or (self._limpieza_pedida is None
                                         and time.monotonic() - inicio < self.cfg.retraso_inicial):
                        continue
                    ahora, firma, motivo = time.monotonic(), self._firma(), None
                    with self._mutex:
                        limpiar, self._limpieza_pedida = self._limpieza_pedida, None
                    if limpiar:
                        motivo = "limpieza"
                    elif self._solicitud:
                        self._solicitud, motivo = False, "solicitado"
                    elif self._ultimo_ciclo_t is None:
                        motivo = "inicial"
                    elif firma is not None and firma != self._firma_ciclo and firma == firma_previa:
                        motivo = "cambios en la biblioteca"
                    elif ahora - self._ultimo_ciclo_t >= self.cfg.intervalo_ciclo:
                        motivo = "periódico"
                    firma_previa = firma
                    if motivo:
                        self._firma_ciclo = firma
                        informe = None
                        try:
                            informe = self._ciclo(motivo, limpiar)
                        except Exception:
                            self._log.exception("Error inesperado en el ciclo del supervisor")
                        if limpiar:
                            with self._mutex:
                                self._ultima_limpieza.update({
                                    "estado": "terminada" if informe else "fallida", "terminada": _iso(),
                                    "acciones": list((informe or {}).get("acciones", [])),
                                    "omitidos_por_uso": len((informe or {}).get("omitidos_por_uso", []))})
                        self._ultimo_ciclo_t = time.monotonic()
                        errores = 0
                except Exception:
                    errores += 1
                    self._log.exception(f"Error en el bucle del supervisor ({errores}); continúa.")
                    time.sleep(min(30, 2 * errores))
        finally:
            self._liberar_instancia()
# CLI opcional:  python -m audio.supervisor_biblioteca --una-vez

def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Supervisor de biblioteca de MILLER (modo independiente).")
    ap.add_argument("--carpeta", default=str(Path(__file__).resolve().parent.parent / "audios"))
    ap.add_argument("--una-vez", action="store_true", help="un solo ciclo y salir")
    ap.add_argument("--observar", action="store_true", help="no mover nada, solo informar")
    ap.add_argument("--sin-profunda", action="store_true", help="omitir la verificación por decodificación")
    a = ap.parse_args(argv)
    cfg = ConfigSupervisor(modo="observar" if a.observar else "cuarentena",
                           verificacion_profunda=not a.sin_profunda)
    sup = SupervisorBiblioteca(carpeta=a.carpeta, config=cfg)
    if a.una_vez:
        informe = sup.escanear_una_vez()
        print(json.dumps(informe, ensure_ascii=False, indent=2) if informe else "Sin informe (¿otro supervisor activo?).")
        return 0 if informe is not None else 1
    if not sup.iniciar():
        return 1
    try:
        while sup.esta_activo():
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        sup.detener()
    return 0
if __name__ == "__main__":
    sys.exit(_main())
