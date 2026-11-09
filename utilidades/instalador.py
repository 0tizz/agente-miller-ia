"""MILLER · Instalación inicial: comprueba e instala librerías, descarga los modelos que faltan
o copia los que ya existen en otra carpeta de MILLER (importar_desde)."""
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
# Dónde están cada modelo dentro de una copia de MILLER (carpeta modelos/ de esa copia).
UBICACION_EN_COPIA = {
    "vosk": ("voz", "vosk-model-small-es-0.42"),
    "voz": ("voces", "es_ES-davefx-medium"),
    "ffmpeg": ("ffmpeg-master-gpl",),
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


def _sin_progreso(_fraccion, _texto):
    pass


def instalar_librerias(avisar=print, progreso=_sin_progreso):
    """pip install de lo que falta. avisar(texto) recibe cada línea; progreso(fraccion, texto) mueve la barra."""
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
        progreso(None, "Instalando librerías con pip…")
        proceso = subprocess.Popen([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", *paquetes],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                   errors="replace", creationflags=_SIN_VENTANA)
        for linea in proceso.stdout:
            linea = linea.strip()
            if linea and not linea.startswith(("  ", "Requirement already")):
                avisar(linea[:90])
                progreso(None, linea[:90])
        ok = proceso.wait() == 0
        avisar("Librerías instaladas." if ok else "La instalación de librerías falló. Revise el registro.")
        return ok
    except Exception as error:
        avisar(f"Error instalando librerías: {error}")
        return False
    finally:
        _ocupado.release()


def _descargar(url, destino, avisar, progreso=_sin_progreso):
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
                progreso(leido / total, f"Descargando… {leido >> 20} de {total >> 20} MB ({porcentaje} %)")
                if porcentaje >= ultimo + 10:
                    ultimo = porcentaje
                    avisar(f"  {porcentaje} % ({leido >> 20} de {total >> 20} MB)")
            else:
                progreso(None, f"Descargando… {leido >> 20} MB")


def _dentro(base, nombre):
    destino = (base / nombre).resolve()
    destino.relative_to(base.resolve())               # evita rutas maliciosas dentro del archivo comprimido
    return destino


def descargar_modelo(clave, avisar=print, progreso=_sin_progreso):
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
        _descargar(m["url"], archivo, avisar, progreso)
        avisar("Descomprimiendo…")
        progreso(None, f"Descomprimiendo {m['nombre']}…")
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


def importar_desde(carpeta, avisar=print):
    """Copia los modelos que ya existen en otra copia de MILLER (su carpeta modelos/). No descarga nada.
    Acepta la carpeta de MILLER o directamente su carpeta modelos/. Devuelve True si todo quedó verificado."""
    origen = Path(carpeta)
    base = origen / "modelos" if (origen / "modelos").is_dir() else origen
    if not _ocupado.acquire(blocking=False):
        avisar("Ya hay una instalación en curso.")
        return False
    try:
        listos = 0
        for clave, m in MODELOS.items():
            origen_modelo = base.joinpath(*UBICACION_EN_COPIA[clave])
            destino = Path(m["destino"])
            if not origen_modelo.is_dir():
                avisar(f"{m['nombre']}: no está en esa carpeta.")
                continue
            if origen_modelo.resolve() == destino.resolve():
                avisar(f"{m['nombre']}: ya está en esta copia.")
                listos += 1 if m["prueba"]() else 0
                continue
            avisar(f"Copiando {m['nombre']}…")
            shutil.copytree(origen_modelo, destino, dirs_exist_ok=True)
            ok = bool(m["prueba"]())
            avisar(f"{m['nombre']}: {'copiado.' if ok else 'copiado, pero no se pudo verificar.'}")
            listos += 1 if ok else 0
        return listos == len(MODELOS)
    except Exception as error:
        avisar(f"Error copiando modelos: {error}")
        return False
    finally:
        _ocupado.release()


def instalar_todo(avisar=print, progreso=_sin_progreso):
    """Librerías y modelos que falten, en orden. Cada paso se protege: un fallo no detiene los demás."""
    try:
        ok = instalar_librerias(avisar, progreso)
    except Exception as error:
        avisar(f"Librerías: {error}")
        ok = False
    for clave, m in MODELOS.items():
        if not m["prueba"]():
            try:
                ok = descargar_modelo(clave, avisar, progreso) and ok
            except Exception as error:
                avisar(f"{m['nombre']}: {error}")
                ok = False
    listo = todo_listo()
    avisar("Todo listo." if listo else "Quedan componentes pendientes.")
    progreso(1.0 if listo else 0.0, "Todo listo." if listo else "Quedan componentes pendientes.")
    return ok and listo
