"""MILLER · Cuotas de disco: cuánto puede ocupar según el modo, en dos secciones, y cómo está el disco.

- ASISTENTE: código, modelos y memorias (todo lo de la carpeta del proyecto salvo audios, dist y graphify-out).
- ARCHIVOS: lo que guarda para el usuario: canciones, vídeos, PDF... (carpeta audios).
- Cada sección tiene un tope total. Lo que ya existe no se borra, pero no puede crecer si pasa del tope.
- FREE y NIÑOS (boy) tienen cifras fijas. PRO puede usar hasta CUOTA_PRO_DISCO del espacio libre del disco.
- PRESIÓN DEL DISCO según el espacio libre del disco:
  «normal»; «baja» (poco % libre: MILLER avisa y su memoria poda solo lo muy parecido);
  «critica» (casi sin espacio: no descarga nada y no guarda recuerdos nuevos sin margen).
"""
import os
import shutil
from pathlib import Path

import configuracion
from utilidades import acceso

MB = 1024 * 1024
GB = 1024 * MB
FUERA_DE_CUENTA = {"audios", "dist", "graphify-out", "__pycache__"}
NORMAL, BAJA, CRITICA = "normal", "baja", "critica"
NOMBRE_SECCION = {"asistente": "del asistente (código, modelos y memorias)", "archivos": "de archivos (canciones)"}


def _base():
    return Path(configuracion.RUTA_BASE)


def _libre():
    return shutil.disk_usage(_base()).free


def _disco():
    """(libre, total) en una sola medición; el libre sale de _libre()."""
    return _libre(), espacio_disco()[1]


def espacio_disco():
    """(libre, total) del disco donde está MILLER, en bytes."""
    uso_disco = shutil.disk_usage(_base())
    return uso_disco.free, uso_disco.total


def _tamano(ruta):
    if ruta.is_file():
        try:
            return ruta.stat().st_size
        except OSError:
            return 0
    total = 0
    for dirpath, _, nombres in os.walk(ruta):
        for nombre in nombres:
            try:
                total += os.path.getsize(os.path.join(dirpath, nombre))
            except OSError:
                pass
    return total


def uso():
    base = _base()
    asistente = sum(_tamano(e) for e in base.iterdir() if e.name not in FUERA_DE_CUENTA)
    return {"asistente": asistente, "archivos": _tamano(base / "audios")}


def _presion_con(libre, total):
    """Nivel del disco con «libre» bytes libres de «total». No mide nada por su cuenta."""
    pct = libre / total if total else 1.0
    if libre < configuracion.CUOTA_RESERVA_DISCO_MB * MB or pct < configuracion.CUOTA_CRITICA_DISCO_PCT:
        return CRITICA
    if pct < configuracion.CUOTA_AVISO_DISCO_PCT:
        return BAJA
    return NORMAL


def estado_disco():
    """{'nivel', 'libre', 'total'}: cuánto queda en el disco y en qué nivel está."""
    libre, total = _disco()
    return {"nivel": _presion_con(libre, total), "libre": libre, "total": total}


def presion():
    return estado_disco()["nivel"]


def _limites_con(modo, usado=None, libre=None):
    """Topes de cada sección para un modo. Recibe lo ya medido para no recorrer el disco dos veces."""
    if modo == "pro":
        usado = uso() if usado is None else usado
        libre = _libre() if libre is None else libre
        total = usado["asistente"] + usado["archivos"] + configuracion.CUOTA_PRO_DISCO * libre
        reparto = configuracion.CUOTA_PRO_REPARTO_ASISTENTE
        return {"asistente": total * reparto, "archivos": total * (1 - reparto)}
    if modo == "boy":
        return {"asistente": configuracion.CUOTA_BOY_ASISTENTE_MB * MB,
                "archivos": configuracion.CUOTA_BOY_ARCHIVOS_MB * MB}
    return {"asistente": configuracion.CUOTA_FREE_ASISTENTE_MB * MB,
            "archivos": configuracion.CUOTA_FREE_ARCHIVOS_MB * MB}


def limites(modo=None):
    return _limites_con(modo or acceso.modo())


def instantanea():
    """Una sola medición para la ventana: disco libre y total, presión, lo usado y el tope de cada modo."""
    usado = uso()
    libre, total = _disco()
    return {"libre": libre, "total": total, "presion": _presion_con(libre, total), "uso": usado,
            "limites": {m: _limites_con(m, usado, libre) for m in ("free", "boy", "pro")}}


def puede_crecer(seccion, bytes_nuevos):
    """(ok, aviso). Mira el modo y el disco actuales; no cambia nada. Si no cabe, el aviso dice por qué y qué hacer."""
    if not getattr(configuracion, "CUOTA_ACTIVA", True):
        return True, ""
    modo = acceso.modo()
    usado = uso()
    libre, total = _disco()
    actual = usado[seccion]
    tope = _limites_con(modo, usado, libre)[seccion]
    if actual + bytes_nuevos > tope:
        falta = (actual + bytes_nuevos - tope) / MB
        return False, (f"Negativo, señor. La cuota {NOMBRE_SECCION[seccion]} del modo {acceso.NOMBRES[modo]} está llena: "
                       f"ocupa {actual / MB:.0f} MB de {tope / MB:.0f} MB y harían falta {falta:.0f} MB libres "
                       "en esa cuota. Borre algo de ese espacio o pase a un modo con más cuota.")
    despues = libre - bytes_nuevos
    if despues < configuracion.CUOTA_RESERVA_DISCO_MB * MB or _presion_con(despues, total) == CRITICA:
        return False, (f"Negativo, señor. El disco está al límite: quedan {libre / MB:.0f} MB libres y MILLER "
                       f"guarda una reserva de {configuracion.CUOTA_RESERVA_DISCO_MB} MB que no toca. "
                       "Libere espacio en el disco y vuelva a intentarlo.")
    return True, ""


def puede_guardar(bytes_nuevos=0):
    """Para recuerdos y ajustes pequeños: solo mira que quede un margen mínimo en el disco."""
    if not getattr(configuracion, "CUOTA_ACTIVA", True):
        return True
    return _libre() - bytes_nuevos >= configuracion.CUOTA_ESCRITURA_MINIMA_MB * MB


def aviso_presion(estado=None):
    """Frase para avisar del disco. Vacía si está en nivel normal."""
    estado = estado or estado_disco()
    libre = estado["libre"] / GB
    if estado["nivel"] == CRITICA:
        return (f"Atención, señor: el disco casi no tiene espacio ({libre:.1f} GB libres). "
                "No descargo nada y reduzco mi memoria a lo imprescindible.")
    if estado["nivel"] == BAJA:
        return f"Queda poco espacio en el disco ({libre:.1f} GB libres). Reviso mi memoria con cuidado."
    return ""


def resumen():
    s = instantanea()
    l = s["limites"][acceso.modo()]
    nivel = {NORMAL: "normal", BAJA: "poco espacio", CRITICA: "crítico"}[s["presion"]]
    return (f"Disco: {s['libre'] / GB:.1f} GB libres de {s['total'] / GB:.1f} GB ({nivel}). "
            f"Asistente: {s['uso']['asistente'] / MB:.0f} MB de {l['asistente'] / MB:.0f} MB; "
            f"archivos: {s['uso']['archivos'] / MB:.0f} MB de {l['archivos'] / MB:.0f} MB.")
