"""MILLER · Instalación inicial: comprueba e instala librerías y descarga los modelos que faltan."""
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import urllib.request
import zipfile
from pathlib import Path

import configuracion
from utilidades import entorno, seguridad

# Descargas permitidas (solo estas URLs, nunca otras).
MODELOS = {
    "vosk": {"nombre": "Reconocimiento de voz (Vosk, 40 MB)",
             "destino": configuracion.RUTA_MODELO_VOZ,
             "prueba": lambda: configuracion.RUTA_MODELO_VOZ.is_dir(),
             "url": "https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip",
             "dominios": ("alphacephei.com",)},
    "voz": {"nombre": "Voz masculina española (Piper, 65 MB)",
            "destino": configuracion.RUTA_VOCES / "es_ES-davefx-medium",
            "prueba": lambda: (configuracion.RUTA_VOCES / "es_ES-davefx-medium" / "es_ES-davefx-medium.onnx").is_file(),
            "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-es_ES-davefx-medium.tar.bz2",
            "dominios": ("github.com",)},
    "ffmpeg": {"nombre": "FFmpeg (reparar y descargar música, 130 MB)",
               "destino": configuracion.RUTA_MODELOS / "ffmpeg-master-gpl",
               "prueba": lambda: (configuracion.RUTA_MODELOS / "ffmpeg-master-gpl" / "bin" / "ffmpeg.exe").is_file()
               or bool(shutil.which("ffmpeg")),
               "url": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
               "dominios": ("github.com",)},
}
_SIN_VENTANA = 0x08000000 if os.name == "nt" else 0
_ocupado = threading.Lock()


def estado():
    """Lista de componentes: (clave, nombre, listo, tipo) para mostrar en la ventana."""
    filas = []
    faltan = entorno.faltantes()
    for modulo, (paquete, uso, imprescindible) in entorno.LIBRERIAS.items():
        filas.append((modulo, f"{uso[0].upper()}{uso[1:]} ({paquete.split('>')[0].split('=')[0]})", modulo not in faltan, "libreria"))
    for clave, m in MODELOS.items():
        filas.append((clave, m["nombre"], bool(m["prueba"]()), "modelo"))
    return filas


def todo_listo():
    return all(listo for _, _, listo, _ in estado())


def puede_instalar_librerias():
    """En el .exe las librerías ya van dentro; pip solo existe ejecutando con Python."""
    return not getattr(sys, "frozen", False)


def instalar_librerias(avisar=print):
    """pip install de lo que falta. avisar(texto) recibe cada línea de progreso."""
    if not puede_instalar_librerias():
        avisar("Las librerías ya van incluidas en MILLER.exe.")
        return True
    faltan = entorno.faltantes()
    if not faltan:
        avisar("Todas las librerías están instaladas.")
        return True
    if not _ocupado.acquire(blocking=False):
        avisar("Ya hay una instalación en curso.")
        return False
    try:
        paquetes = [p for p, _, _ in faltan.values()]
        avisar("Instalando: " + ", ".join(paquetes))
        proceso = subprocess.Popen([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", *paquetes],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                   errors="replace", creationflags=_SIN_VENTANA)
        for linea in proceso.stdout:
            linea = linea.strip()
            if linea and not linea.startswith(("  ", "Requirement already")):
                avisar(linea[:90])
        ok = proceso.wait() == 0
        avisar("Instalación completada. Reinicie MILLER para usarlas." if ok else "La instalación falló. Revise el registro.")
        return ok
    except Exception as error:
        avisar(f"Error instalando: {error}")
        return False
    finally:
        _ocupado.release()


def _descargar(url, destino, avisar):
    peticion = urllib.request.Request(url, headers={"User-Agent": "MILLER/0.1"})
    with urllib.request.urlopen(peticion, timeout=30) as r, open(destino, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        leido, ultimo = 0, -10
        while True:
            bloque = r.read(1 << 20)
            if not bloque:
                break
            f.write(bloque)
            leido += len(bloque)
            if total:
                porcentaje = leido * 100 // total
                if porcentaje >= ultimo + 10:
                    ultimo = porcentaje
                    avisar(f"  {porcentaje} % ({leido >> 20} de {total >> 20} MB)")


def _dentro(base, nombre):
    destino = (base / nombre).resolve()
    destino.relative_to(base.resolve())               # evita rutas maliciosas dentro del archivo comprimido
    return destino


def descargar_modelo(clave, avisar=print):
    """Descarga y coloca un modelo en modelos/. Solo desde las URLs de MODELOS."""
    m = MODELOS.get(clave)
    if m is None:
        return False
    if m["prueba"]():
        avisar(f"{m['nombre']}: ya instalado.")
        return True
    if not seguridad.url_segura(m["url"], m["dominios"]):
        avisar("Descarga bloqueada por seguridad.")
        return False
    if not _ocupado.acquire(blocking=False):
        avisar("Ya hay una instalación en curso.")
        return False
    temporal = Path(tempfile.mkdtemp(prefix="miller_"))
    try:
        archivo = temporal / Path(m["url"]).name
        avisar(f"Descargando {m['nombre']}…")
        _descargar(m["url"], archivo, avisar)
        avisar("Descomprimiendo…")
        extraido = temporal / "extraido"
        extraido.mkdir()
        if archivo.suffix == ".zip":
            with zipfile.ZipFile(archivo) as z:
                for miembro in z.infolist():
                    _dentro(extraido, miembro.filename)
                z.extractall(extraido)
        else:
            with tarfile.open(archivo) as t:
                miembros = [x for x in t.getmembers() if x.isfile() and "espeak-ng-data" not in x.name]
                for x in miembros:
                    _dentro(extraido, x.name)
                t.extractall(extraido, members=miembros)
        raiz = next(p for p in extraido.iterdir() if p.is_dir())
        destino = Path(m["destino"])
        destino.parent.mkdir(parents=True, exist_ok=True)
        if clave == "voz":
            destino.mkdir(parents=True, exist_ok=True)
            for nombre in ("es_ES-davefx-medium.onnx", "es_ES-davefx-medium.onnx.json", "MODEL_CARD"):
                if (raiz / nombre).is_file():
                    shutil.move(str(raiz / nombre), str(destino / nombre))
        else:
            if destino.exists():
                shutil.rmtree(destino, ignore_errors=True)
            shutil.move(str(raiz), str(destino))
        listo = m["prueba"]()
        avisar(f"{m['nombre']}: {'instalado.' if listo else 'no se pudo verificar.'}")
        return listo
    except Exception as error:
        avisar(f"Error con {m['nombre']}: {error}")
        return False
    finally:
        shutil.rmtree(temporal, ignore_errors=True)
        _ocupado.release()


def instalar_todo(avisar=print):
    """Librerías y modelos que falten, en orden."""
    ok = instalar_librerias(avisar)
    for clave, m in MODELOS.items():
        if not m["prueba"]():
            ok = descargar_modelo(clave, avisar) and ok
    avisar("Todo listo." if todo_listo() else "Quedan componentes pendientes.")
    return ok
