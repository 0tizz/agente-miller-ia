"""MILLER · Plan de instalación: busca en este equipo los modelos que ya existen, copia exactamente
lo encontrado a modelos/ y descarga solo lo que de verdad falta. Informa del progreso paso a paso.

Lo que se busca por nombre exacto:
  - vosk-model-small-es-0.42  (con am/final.mdl dentro)
  - es_ES-davefx-medium       (con es_ES-davefx-medium.onnx dentro)
  - ffmpeg.exe                (dentro de una carpeta bin/; la raíz de esa carpeta es el modelo)
"""
import os
import shutil
import time
from collections import deque
from pathlib import Path

import configuracion
from utilidades import entorno, instalador

PROFUNDIDAD_MAXIMA = 7
TIEMPO_BUSQUEDA_S = 40.0
# Carpetas que no tienen sentido buscar dentro (ruido y cachés enormes).
CARPETAS_OMITIDAS = {"appdata", "node_modules", ".git", "venv", ".venv", "site-packages", "__pycache__",
                     "$recycle.bin", "system volume information", "windows", "program files", "program files (x86)",
                     "programdata", "dist", "build", "graphify-out"}
NOMBRE_VOSK = "vosk-model-small-es-0.42"
NOMBRE_VOZ = "es_ES-davefx-medium"
ARCHIVO_FFMPEG = "ffmpeg.exe"


def _raices_de_busqueda():
    """Carpetas donde suele estar un modelo: la que contiene a MILLER, el perfil del usuario y sus carpetas comunes."""
    casa = Path.home()
    candidatas = [configuracion.RUTA_BASE.parent, casa / "Desktop", casa / "Documents", casa / "Downloads",
                  casa / "OneDrive", casa]
    raices, vistas = [], set()
    for c in candidatas:
        try:
            real = c.resolve()
        except OSError:
            continue
        if c.is_dir() and real not in vistas:
            vistas.add(real)
            raices.append(c)
    return raices


def buscar_en_equipo(claves=None, progreso=None, tiempo_max=TIEMPO_BUSQUEDA_S):
    """Busca en este equipo los modelos pedidos. Devuelve {clave: carpeta raíz encontrada o None}.
    progreso(fraccion_o_None, texto) se llama al entrar en cada carpeta para que la ventana muestre actividad."""
    pendientes = set(claves or instalador.MODELOS)
    hallados = {c: None for c in instalador.MODELOS}
    propia = configuracion.RUTA_MODELOS.resolve() if configuracion.RUTA_MODELOS.exists() else None
    limite = time.monotonic() + tiempo_max
    cola = deque((raiz, 0) for raiz in _raices_de_busqueda())
    visitadas = set()
    while cola and pendientes and time.monotonic() < limite:
        carpeta, nivel = cola.popleft()
        try:
            real = carpeta.resolve()
        except OSError:
            continue
        if real in visitadas or (propia is not None and real == propia):
            continue                                      # nunca se busca dentro de la propia copia de modelos
        visitadas.add(real)
        if progreso:
            progreso(None, f"Buscando en {carpeta}…")
        try:
            with os.scandir(carpeta) as iterador:
                entradas = list(iterador)
        except OSError:
            continue
        for entrada in entradas:
            try:
                es_carpeta = entrada.is_dir(follow_symlinks=False)
                es_archivo = entrada.is_file(follow_symlinks=False)
            except OSError:
                continue
            ruta = Path(entrada.path)
            if es_archivo:
                if entrada.name == ARCHIVO_FFMPEG and "ffmpeg" in pendientes and ruta.parent.name.lower() == "bin":
                    hallados["ffmpeg"] = ruta.parent.parent
                    pendientes.discard("ffmpeg")
                continue
            if not es_carpeta:
                continue
            if entrada.name == NOMBRE_VOSK and "vosk" in pendientes and (ruta / "am" / "final.mdl").is_file():
                hallados["vosk"] = ruta
                pendientes.discard("vosk")
            elif entrada.name == NOMBRE_VOZ and "voz" in pendientes and (ruta / f"{NOMBRE_VOZ}.onnx").is_file():
                hallados["voz"] = ruta
                pendientes.discard("voz")
            elif (nivel + 1 < PROFUNDIDAD_MAXIMA and not entrada.name.startswith(".")
                  and entrada.name.lower() not in CARPETAS_OMITIDAS):
                cola.append((ruta, nivel + 1))
    return hallados


def encontrados_en_carpeta(carpeta):
    """Modelos que ya están dentro de otra copia de MILLER (su carpeta modelos/, o la propia carpeta)."""
    origen = Path(carpeta)
    base = origen / "modelos" if (origen / "modelos").is_dir() else origen
    hallados = {}
    for clave, ruta_relativa in instalador.UBICACION_EN_COPIA.items():
        ruta = base.joinpath(*ruta_relativa)
        hallados[clave] = ruta if ruta.is_dir() else None
    return hallados


def copiar_arbol(origen, destino, progreso=None):
    """Copia archivo a archivo y avisa del avance en bytes (así la barra se mueve de verdad)."""
    origen, destino = Path(origen), Path(destino)
    if destino.resolve().is_relative_to(origen.resolve()):
        raise ValueError("el destino está dentro del origen")
    archivos = [p for p in origen.rglob("*") if p.is_file()]
    total = sum(p.stat().st_size for p in archivos) or 1
    hecho = 0
    for archivo in archivos:
        relativo = archivo.relative_to(origen)
        (destino / relativo).parent.mkdir(parents=True, exist_ok=True)
        tamano = archivo.stat().st_size
        shutil.copy2(archivo, destino / relativo)
        hecho += tamano
        if progreso:
            progreso(hecho / total, f"Copiando {relativo.name}… {hecho >> 20} de {total >> 20} MB")


def copiar_encontrado(clave, origen, avisar=print, progreso=None):
    """Copia el modelo encontrado en este equipo a su sitio dentro de modelos/ y lo verifica."""
    m = instalador.MODELOS[clave]
    if not instalador._ocupado.acquire(blocking=False):
        avisar("Ya hay una instalación en curso.")
        return False
    try:
        avisar(f"Copiando {m['nombre']} desde {origen}")
        copiar_arbol(origen, m["destino"], progreso)
        ok = bool(m["prueba"]())
        avisar(f"{m['nombre']}: {'copiado.' if ok else 'copiado, pero no se pudo verificar.'}")
        return ok
    except Exception as error:
        avisar(f"Error copiando {m['nombre']}: {error}")
        return False
    finally:
        instalador._ocupado.release()


def plan_instalacion(encontrados=None, solo_copiar=False):
    """Pasos necesarios, en orden: librerías (si faltan), copias de lo encontrado y descargas de lo demás."""
    encontrados = encontrados or {}
    pasos = []
    if instalador.puede_instalar_librerias() and entorno.faltantes():
        pasos.append({"tipo": "pip", "nombre": "Librerías de Python"})
    for clave, m in instalador.MODELOS.items():
        if m["prueba"]():
            continue
        if encontrados.get(clave) is not None:
            pasos.append({"tipo": "copia", "clave": clave, "origen": encontrados[clave], "nombre": m["nombre"]})
        elif not solo_copiar:
            pasos.append({"tipo": "descarga", "clave": clave, "nombre": m["nombre"]})
    return pasos


def _nada(*_):
    pass


def ejecutar_plan(pasos, avisar=print, progreso_paso=None, progreso_total=None):
    """Ejecuta el plan. progreso_paso: avance del paso actual. progreso_total: avance de todo el plan."""
    paso_cb, total_cb = progreso_paso or _nada, progreso_total or _nada
    n = len(pasos)
    if n == 0:
        total_cb(1.0, "Nada que instalar.")
        avisar("Nada que instalar.")
        return instalador.todo_listo()
    ok = True
    for i, paso in enumerate(pasos):
        total_cb(i / n, f"Paso {i + 1} de {n}: {paso['nombre']}")

        def fase(fraccion, texto, _i=i):
            paso_cb(fraccion, texto)
            if fraccion is not None:
                total_cb((_i + fraccion) / n, texto)
        try:
            if paso["tipo"] == "pip":
                listo = instalador.instalar_librerias(avisar, fase)
            elif paso["tipo"] == "copia":
                listo = copiar_encontrado(paso["clave"], paso["origen"], avisar, fase)
            else:
                listo = instalador.descargar_modelo(paso["clave"], avisar, fase)
        except Exception as error:
            avisar(f"{paso['nombre']}: {error}")
            listo = False
        ok = ok and bool(listo)
        paso_cb(1.0 if listo else 0.0, f"{paso['nombre']}: {'listo' if listo else 'con error'}")
    completo = instalador.todo_listo()
    texto_final = "Todo listo." if completo else "Quedan componentes pendientes."
    total_cb(1.0 if completo else (n - 1) / n, texto_final)
    avisar(texto_final)
    return ok and completo
