"""MILLER · Control de ventanas de Windows: cerrar, minimizar, maximizar y restaurar programas y archivos abiertos.

Todo con la API de Windows (ctypes): sin PowerShell ni consola, así no hay texto que se pueda inyectar.
  - Cerrar = pedirle a la ventana que se cierre (WM_CLOSE), como al pulsar la X: el programa puede
    preguntar si guardar. Solo con "forzar" se termina el proceso, y nunca uno del sistema.
  - Un programa se reconoce por su ejecutable (brave.exe) o por el título de su ventana; un archivo
    abierto, por su nombre en el título (informe.pdf - Adobe Acrobat).
"""
import os
import re
import unicodedata
from pathlib import Path

# Procesos que MILLER nunca cierra ni minimiza a la fuerza (sistema y el propio MILLER).
PROTEGIDOS = {"explorer", "csrss", "winlogon", "wininit", "lsass", "services", "smss", "svchost", "dwm", "system",
              "registry", "fontdrvhost", "sihost", "taskhostw", "ctfmon", "searchhost", "startmenuexperiencehost",
              "shellexperiencehost", "textinputhost", "lockapp", "securityhealthsystray", "msmpeng", "conhost",
              "applicationframehost", "runtimebroker"}
# Nombre dicho -> ejecutable(s). Lo demás se busca por parecido con el ejecutable o el título.
PROGRAMAS = {
    "brave": ["brave"], "chrome": ["chrome"], "google chrome": ["chrome"], "edge": ["msedge"], "microsoft edge": ["msedge"],
    "firefox": ["firefox"], "opera": ["opera", "launcher"], "opera gx": ["opera"], "navegador": ["brave", "chrome", "msedge", "firefox", "opera"],
    "spotify": ["spotify"], "discord": ["discord"], "whatsapp": ["whatsapp", "whatsapp.root"], "telegram": ["telegram"],
    "word": ["winword"], "excel": ["excel"], "powerpoint": ["powerpnt"], "outlook": ["outlook", "olk"],
    "bloc de notas": ["notepad"], "notepad": ["notepad"], "calculadora": ["calculatorapp", "calc"],
    "visual studio code": ["code"], "vs code": ["code"], "code": ["code"], "visual studio": ["devenv"],
    "explorador": ["__explorador__"], "explorador de archivos": ["__explorador__"], "carpeta": ["__explorador__"],
    "paint": ["mspaint"], "vlc": ["vlc"], "steam": ["steam", "steamwebhelper"], "obs": ["obs64", "obs"],
    "zoom": ["zoom"], "teams": ["ms-teams", "teams"], "unity": ["unity", "unity hub"], "photoshop": ["photoshop"],
    "acrobat": ["acrobat", "acrord32"], "adobe": ["acrobat", "acrord32"], "netflix": ["netflix"], "youtube": ["__titulo__"],
    "configuracion": ["systemsettings"], "administrador de tareas": ["taskmgr"],
}
_RELLENO = re.compile(r"\b(el|la|los|las|un|una|del|de|al|programa|aplicacion|app|ventana|ventanas|navegador web|todo|toda|"
                      r"todas|todos|por favor|miller)\b")
CLASES_SISTEMA = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "NotifyIconOverflowWindow",
                  "Windows.UI.Core.CoreWindow", "TopLevelWindowForOverflowXamlIsland"}
WM_CLOSE, SW_MINIMIZE, SW_MAXIMIZE, SW_RESTORE = 0x0010, 6, 3, 9


def plano(texto):
    t = unicodedata.normalize("NFD", str(texto or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").strip()


def limpiar_nombre(texto):
    """'el navegador brave' -> 'brave'; 'la ventana de spotify' -> 'spotify'."""
    t = plano(texto)
    t = re.sub(r"\bnavegador\s+(?=\w)", "", t)               # "navegador brave" -> "brave" (pero "navegador" solo, sigue)
    t = _RELLENO.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip(" .")


def disponible():
    return os.name == "nt"


# ------------------------------------------------------------ API de Windows
def _api():
    import ctypes
    from ctypes import wintypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    return ctypes, wintypes, user32, kernel32


def _exe_de(pid, ctypes, wintypes, kernel32):
    h = kernel32.OpenProcess(0x1000, False, pid)          # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(520)
        tam = wintypes.DWORD(520)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(tam)):
            return Path(buf.value).stem.lower()
        return ""
    finally:
        kernel32.CloseHandle(h)


def ventanas():
    """Ventanas visibles con título: [{'hwnd', 'titulo', 'exe', 'pid', 'minimizada'}]."""
    if not disponible():
        return []
    ctypes, wintypes, user32, kernel32 = _api()
    resultado, propio = [], os.getpid()
    PROTO = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def visitar(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4):      # GW_OWNER: ventanas secundarias no
            return True
        largo = user32.GetWindowTextLengthW(hwnd)
        if largo <= 0:
            return True
        clase = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(hwnd, clase, 128)
        if clase.value in CLASES_SISTEMA:                   # escritorio y barra de tareas: intocables
            return True
        buf = ctypes.create_unicode_buffer(largo + 1)
        user32.GetWindowTextW(hwnd, buf, largo + 1)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == propio:
            return True
        resultado.append({"hwnd": hwnd, "titulo": buf.value, "pid": pid.value, "clase": clase.value,
                          "exe": _exe_de(pid.value, ctypes, wintypes, kernel32),
                          "minimizada": bool(user32.IsIconic(hwnd))})
        return True
    user32.EnumWindows(PROTO(visitar), 0)
    return resultado


def buscar(nombre, lista=None):
    """Ventanas de un programa o archivo: primero por ejecutable conocido, luego por título."""
    nombre = limpiar_nombre(nombre)
    if not nombre:
        return []
    lista = ventanas() if lista is None else lista
    objetivos = PROGRAMAS.get(nombre)
    if objetivos == ["__explorador__"]:                        # carpetas abiertas: ventanas del Explorador
        return [v for v in lista if v["exe"] == "explorer"]
    if objetivos and objetivos != ["__titulo__"]:
        encontradas = [v for v in lista if v["exe"] in objetivos]
        if encontradas:
            return encontradas
    compacto = nombre.replace(" ", "")
    por_exe = [v for v in lista if len(compacto) >= 3 and (v["exe"] == compacto or v["exe"].startswith(compacto))]
    if por_exe:
        return por_exe
    stem = plano(Path(nombre).stem) if "." in nombre else nombre
    return [v for v in lista if len(stem) >= 3 and stem in plano(v["titulo"])]


def _seguras(lista):
    """Fuera los procesos del sistema; del Explorador, solo sus ventanas de carpeta."""
    return [v for v in lista if v["exe"] not in PROTEGIDOS or (v["exe"] == "explorer" and v.get("clase") == "CabinetWClass")]


def cerrar(nombre, forzar=False):
    """Cierra todas las ventanas del programa o archivo. (cuántas, nombre_mostrado)."""
    if not disponible():
        return 0, None
    encontradas = _seguras(buscar(nombre))
    if not encontradas:
        return 0, None
    ctypes, wintypes, user32, kernel32 = _api()
    for v in encontradas:
        user32.PostMessageW(v["hwnd"], WM_CLOSE, 0, 0)
    if forzar:                                                 # solo si se pide: termina el proceso
        for pid in {v["pid"] for v in encontradas if v["exe"] not in PROTEGIDOS}:
            h = kernel32.OpenProcess(0x0001, False, pid)        # PROCESS_TERMINATE
            if h:
                kernel32.TerminateProcess(h, 1)
                kernel32.CloseHandle(h)
    return len(encontradas), _mostrar(encontradas[0], nombre)


def mostrar_como(nombre, modo):
    """modo: 'minimizar' | 'maximizar' | 'restaurar'. (cuántas, nombre_mostrado)."""
    if not disponible():
        return 0, None
    encontradas = _seguras(buscar(nombre))
    if not encontradas:
        return 0, None
    _, _, user32, _ = _api()
    orden = {"minimizar": SW_MINIMIZE, "maximizar": SW_MAXIMIZE, "restaurar": SW_RESTORE}[modo]
    for v in encontradas:
        user32.ShowWindow(v["hwnd"], orden)
        if modo != "minimizar":
            user32.SetForegroundWindow(v["hwnd"])
    return len(encontradas), _mostrar(encontradas[0], nombre)


def ventana_activa():
    """La ventana que el usuario tiene delante (si no es la de MILLER)."""
    if not disponible():
        return None
    ctypes, wintypes, user32, kernel32 = _api()
    hwnd = user32.GetForegroundWindow()
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not hwnd or pid.value == os.getpid():
        return None
    largo = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(max(1, largo + 1))
    user32.GetWindowTextW(hwnd, buf, largo + 1)
    exe = _exe_de(pid.value, ctypes, wintypes, kernel32)
    return {"hwnd": hwnd, "titulo": buf.value, "pid": pid.value, "exe": exe}


def minimizar_activa():
    v = ventana_activa()
    if not v or v["exe"] in PROTEGIDOS - {"explorer"}:
        return None
    _api()[2].ShowWindow(v["hwnd"], SW_MINIMIZE)
    return v["titulo"] or v["exe"]


def minimizar_todo():
    """Como Windows + M: minimiza todas las ventanas."""
    if not disponible():
        return False
    _, _, user32, _ = _api()
    for v in _seguras(ventanas()):
        user32.ShowWindow(v["hwnd"], SW_MINIMIZE)
    return True


def _mostrar(v, nombre):
    titulo = v["titulo"].split(" - ")[-1].strip() if " - " in v["titulo"] else v["titulo"]
    return (titulo or v["exe"] or nombre)[:60]
