"""MILLER · Navegadores y explorador: abrir o buscar en Brave, Chrome, Edge, Firefox u Opera, y encontrar archivos."""
import os
import re
import shutil
import subprocess
import time
import unicodedata
import webbrowser
from pathlib import Path
from urllib.parse import quote_plus

from utilidades import seguridad

_SIN_VENTANA = 0x08000000 if os.name == "nt" else 0
_PF = os.environ.get("ProgramFiles", r"C:\Program Files")
_PF86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
_LOCAL = os.environ.get("LOCALAPPDATA", "")
NAVEGADORES = {   # clave: (nombre para decir, ejecutables posibles)
    "brave": ("Brave", [rf"{_PF}\BraveSoftware\Brave-Browser\Application\brave.exe",
                        rf"{_PF86}\BraveSoftware\Brave-Browser\Application\brave.exe",
                        rf"{_LOCAL}\BraveSoftware\Brave-Browser\Application\brave.exe", "brave"]),
    "chrome": ("Google Chrome", [rf"{_PF}\Google\Chrome\Application\chrome.exe",
                                 rf"{_PF86}\Google\Chrome\Application\chrome.exe",
                                 rf"{_LOCAL}\Google\Chrome\Application\chrome.exe", "chrome", "google-chrome"]),
    "edge": ("Microsoft Edge", [rf"{_PF86}\Microsoft\Edge\Application\msedge.exe",
                                rf"{_PF}\Microsoft\Edge\Application\msedge.exe", "msedge"]),
    "firefox": ("Firefox", [rf"{_PF}\Mozilla Firefox\firefox.exe", rf"{_PF86}\Mozilla Firefox\firefox.exe", "firefox"]),
    "opera": ("Opera", [rf"{_LOCAL}\Programs\Opera\opera.exe", rf"{_LOCAL}\Programs\Opera GX\opera.exe", "opera"]),
}
_RE_NAVEGADOR = [
    ("brave", r"\bbrave\b"),
    ("chrome", r"\b(?:google )?chrome\b|\bnavegador (?:de )?google\b|\b(?:con|en) google navegador\b"),
    ("edge", r"\b(?:microsoft )?edge\b"),
    ("firefox", r"\b(?:mozilla )?firefox\b|\bmozilla\b"),
    ("opera", r"\bopera(?: gx)?\b"),
]
MOTORES = {
    "youtube": "https://www.youtube.com/results?search_query={}",
    "bing": "https://www.bing.com/search?q={}",
    "duckduckgo": "https://duckduckgo.com/?q={}",
    "google": "https://www.google.com/search?q={}",
}


def plano(texto):
    texto = unicodedata.normalize("NFD", str(texto or "").lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", texto).strip()


def detectar_navegador(texto):
    t = plano(texto)
    return next((clave for clave, patron in _RE_NAVEGADOR if re.search(patron, t)), None)


def quitar_navegador(texto):
    """Quita "en el navegador brave", "con chrome", "en el navegador"... del texto."""
    t = plano(texto)
    t = re.sub(r"\s+(?:en|con|desde|usando|por)\s+(?:el\s+)?(?:navegador\s*)?(?:de\s+)?"
               r"(?:brave|google chrome|chrome|microsoft edge|edge|mozilla firefox|firefox|mozilla|opera gx|opera|google)?\s*$",
               "", t)
    return re.sub(r"\s+(?:en|con)\s+(?:el\s+)?navegador\b.*$", "", t).strip()


_cache_rutas = {}


def ruta_navegador(clave, catalogo=None):
    """Ruta del ejecutable del navegador (se busca una vez y se recuerda)."""
    if clave in _cache_rutas:
        return _cache_rutas[clave]
    ruta = None
    for candidato in NAVEGADORES.get(clave, ("", []))[1]:
        if os.path.isabs(candidato):
            if os.path.isfile(candidato):
                ruta = candidato
                break
        elif shutil.which(candidato):
            ruta = shutil.which(candidato)
            break
    if ruta is None and catalogo is not None:                   # índice de programas del sistema
        try:
            entrada = catalogo.buscar(NAVEGADORES[clave][0])
            if entrada and entrada.get("tipo") in ("exe", "acceso"):
                ruta = entrada["objetivo"]
        except Exception:
            pass
    _cache_rutas[clave] = ruta
    return ruta


def abrir(url, navegador=None, catalogo=None):
    """Abre la URL en el navegador pedido (o el predeterminado). Devuelve (ok, nombre_del_navegador)."""
    if not seguridad.url_segura(url):
        seguridad.alerta(f"URL bloqueada: {str(url)[:80]}")
        return False, "URL no permitida"
    if navegador:
        ruta = ruta_navegador(navegador, catalogo)
        nombre = NAVEGADORES[navegador][0]
        if not ruta:
            return False, f"{nombre} no está instalado"
        try:
            if ruta.lower().endswith(".lnk") and os.name == "nt":
                os.startfile(ruta)                               # acceso directo: abre el navegador
                time.sleep(1.5)
                webbrowser.open_new_tab(url)
            else:
                subprocess.Popen([ruta, url], creationflags=_SIN_VENTANA)
            return True, nombre
        except OSError as error:
            print(f"[NAVEGADOR] No se pudo abrir {nombre}: {error}")
            return False, f"no pude abrir {nombre}"
    try:
        webbrowser.open_new_tab(url)
        return True, "el navegador"
    except Exception as error:
        print(f"[NAVEGADOR] {error}")
        return False, "no pude abrir el navegador"


def url_busqueda(consulta, motor="google"):
    return MOTORES.get(motor, MOTORES["google"]).format(quote_plus(consulta))


# ------------------------------------------------------------------ explorador de archivos
_EXCLUIR = {"appdata", "windows", "program files", "program files (x86)", "programdata", "$recycle.bin",
            "system volume information", "node_modules", ".git", "__pycache__", "venv", ".venv", "site-packages"}


def raices_busqueda():
    casa = Path(os.environ.get("USERPROFILE") or Path.home())
    raices = [casa / n for n in ("Desktop", "Escritorio", "Documents", "Documentos", "Downloads", "Descargas",
                                 "Music", "Música", "Pictures", "Imágenes", "Videos", "Vídeos", "OneDrive")]
    raices.append(casa)
    if os.name == "nt":
        for letra in "DEFG":
            if os.path.isdir(f"{letra}:\\"):
                raices.append(Path(f"{letra}:\\"))
    vistas, salida = set(), []
    for r in raices:
        try:
            clave = str(r.resolve()).lower()
        except OSError:
            continue
        if r.is_dir() and clave not in vistas:
            vistas.add(clave)
            salida.append(r)
    return salida


_CACHE_BUSQUEDAS, VIGENCIA_BUSQUEDA = {}, 120.0


def buscar_archivo(nombre, raices=None, limite_segundos=8.0, maximo=5, profundidad=7):
    """Igual que _buscar_archivo, pero repetir la búsqueda en 2 minutos es instantáneo
    (se comprueba que los archivos sigan existiendo)."""
    clave = (plano(nombre), tuple(str(r) for r in raices) if raices else None, maximo, profundidad)
    guardado = _CACHE_BUSQUEDAS.get(clave)
    if guardado and time.monotonic() - guardado[0] < VIGENCIA_BUSQUEDA:
        vivos = [r for r in guardado[1] if r.exists()]
        if vivos:
            return vivos
    resultado = _buscar_archivo(nombre, raices, limite_segundos, maximo, profundidad)
    if len(_CACHE_BUSQUEDAS) > 64:
        _CACHE_BUSQUEDAS.clear()
    if resultado:                                  # lo no encontrado se vuelve a buscar (pudo crearse)
        _CACHE_BUSQUEDAS[clave] = (time.monotonic(), resultado)
    return resultado


def _buscar_archivo(nombre, raices=None, limite_segundos=8.0, maximo=5, profundidad=7):
    """Busca por nombre (exacto primero, luego parcial), sin entrar en carpetas del sistema y con tiempo límite."""
    objetivo = plano(nombre).replace(" punto ", ".").strip(" .")
    if not objetivo:
        return []
    sin_espacios = objetivo.replace(" ", "")
    exactos, parciales = [], []
    fin = time.monotonic() + limite_segundos
    pendientes = [(Path(r), 0) for r in (raices or raices_busqueda())]
    vistos = set()
    while pendientes and time.monotonic() < fin and len(exactos) < maximo:
        carpeta, nivel = pendientes.pop(0)
        try:
            clave = str(carpeta).lower()
            if clave in vistos:
                continue
            vistos.add(clave)
            with os.scandir(carpeta) as it:
                for e in it:
                    nombre_e = e.name.lower()
                    if e.is_dir(follow_symlinks=False):
                        if nivel < profundidad and nombre_e not in _EXCLUIR and not nombre_e.startswith("."):
                            pendientes.append((Path(e.path), nivel + 1))
                        continue
                    simple = plano(e.name)
                    if simple == objetivo or simple.replace(" ", "") == sin_espacios:
                        exactos.append(Path(e.path))
                    elif objetivo in simple or (len(sin_espacios) > 3 and sin_espacios in simple.replace(" ", "")):
                        parciales.append(Path(e.path))
        except (PermissionError, FileNotFoundError, NotADirectoryError, OSError):
            continue
    return (exactos + parciales)[:maximo]


def mostrar_en_explorador(ruta):
    """Abre el Explorador de Windows con el archivo seleccionado."""
    ruta = Path(ruta)
    try:
        if os.name == "nt":
            subprocess.Popen(["explorer.exe", f"/select,{ruta}"], creationflags=_SIN_VENTANA)
        else:
            subprocess.Popen(["xdg-open", str(ruta.parent)])
        return True
    except OSError as error:
        print(f"[EXPLORADOR] {error}")
        return False
