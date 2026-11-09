"""MILLER · Purga (reestablecimiento de fábrica): borra recuerdos, aprendizaje, cachés, el nombre, el historial de
órdenes de la terminal y las llaves puestas para que MILLER empiece de cero.

Se pide desde la ventana MILLER (botón PURGAR, con doble pulsación). No se hace en ese momento: se ejecuta al cerrar
MILLER, cuando ya están parados el reproductor, la escucha y los hilos de fondo. Al volver a abrirlo, MILLER empieza
sin recuerdos, sin aprendizaje, sin cachés y sin nombre.

No toca: el código, las canciones (audios/, con la papelera), los modelos, las alarmas, el ecualizador, el registro
del supervisor. Olvida qué llaves estaban puestas (datos/seguridad/llaves_puestas): al reabrir MILLER las pide una vez.
No toca las llaves, clave.bin, sellos ni alertas.
"""
import os
import shutil
import threading
from pathlib import Path

import configuracion

# Conocimiento de MILLER. Cada archivo se borra con sus copias: .bak (respaldo) y .firma (firma HMAC).
ARCHIVOS_DATOS = ("terminal_historial.json", "memoria.json", "memoriamusical.json", "nombre_aprendido.json", "nombre_asistente.json", "emociones.json",
                  "equilibrio.json", "iniciativa.json", "movimiento.json", "aplicaciones.json", "orbe.json")
# Estado del supervisor de la biblioteca. Su registro supervisor.log se conserva.
ARCHIVOS_SUPERVISOR = ("estado_supervisor.json", "informe_biblioteca.json")
# Carpetas que nunca se recorren buscando cachés de Python.
NO_RECORRER = {"datos", "audios", "modelos", "dist", "build", "graphify-out", ".git", ".venv", "venv"}

_pedida = threading.Event()


def pedir():
    """Marca la purga: se hará cuando MILLER se cierre."""
    _pedida.set()


def pedida():
    """True mientras la purga está pedida y aún no se ha hecho."""
    return _pedida.is_set()


def _borrar(ruta, base, borrados, errores):
    try:
        if ruta.is_dir() and not ruta.is_symlink():
            shutil.rmtree(ruta)
        else:
            ruta.unlink()
        borrados.append(ruta.relative_to(base).as_posix())
    except OSError as error:
        errores.append(f"{ruta.name}: {error}")


def _quitar_llaves_puestas(base, borrados, errores):
    """Olvida qué llaves estaban puestas: al reabrir MILLER se pesan una vez y luego quedan puestas otra vez.
    Solo si la carpeta de seguridad está dentro de esta instalación (así una prueba con carpeta temporal no toca
    las llaves reales). No borra las llaves en sí, ni clave.bin, sellos ni alertas."""
    try:
        from utilidades import acceso, seguridad
        if not Path(seguridad.DIR_SEGURIDAD).resolve().is_relative_to(Path(base).resolve()):
            return
        for ruta in sorted(acceso.RUTA_PUESTAS.parent.glob(acceso.RUTA_PUESTAS.name + "*")):
            try:
                ruta.unlink()
                borrados.append(ruta.name)
            except OSError as error:
                errores.append(f"{ruta.name}: {error}")
    except Exception as error:
        errores.append(f"llaves puestas: {error}")


def purgar(raiz=None):
    """Borra recuerdos, aprendizaje y cachés. Devuelve (borrados, errores), listas de texto.
    raiz: carpeta de MILLER. Por defecto, la real; las pruebas pasan una carpeta temporal."""
    base = Path(raiz or configuracion.RUTA_BASE)
    datos = base / "datos"
    borrados, errores = [], []
    for nombre in ARCHIVOS_DATOS:
        for ruta in sorted(datos.glob(nombre + "*")):
            _borrar(ruta, base, borrados, errores)
    for nombre in ARCHIVOS_SUPERVISOR:
        for ruta in sorted((datos / "supervisor").glob(nombre + "*")):
            _borrar(ruta, base, borrados, errores)
    cache = datos / "cache"
    if cache.is_dir():
        for ruta in sorted(cache.iterdir()):          # la carpeta cache se queda, vacía
            _borrar(ruta, base, borrados, errores)
    _quitar_llaves_puestas(base, borrados, errores)
    for carpeta, subcarpetas, _ in os.walk(base):
        for nombre in list(subcarpetas):
            if nombre in NO_RECORRER:
                subcarpetas.remove(nombre)
            elif nombre == "__pycache__":
                subcarpetas.remove(nombre)
                _borrar(Path(carpeta) / nombre, base, borrados, errores)
    return borrados, errores


def ejecutar_si_pedida(raiz=None):
    """Lo llama el cierre de MILLER. Si se pidió la purga, la hace ahora y lo dice en la consola.
    Devuelve (borrados, errores), o None si no se pidió."""
    if not _pedida.is_set():
        return None
    _pedida.clear()
    borrados, errores = purgar(raiz)
    print(f"MILLER: Purga hecha: {len(borrados)} {'elemento borrado' if len(borrados) == 1 else 'elementos borrados'}.")
    for texto in errores:
        print(f"[PURGA] No se pudo borrar {texto}")
    print("MILLER: Reabra MILLER para empezar de nuevo, señor.")
    return borrados, errores
