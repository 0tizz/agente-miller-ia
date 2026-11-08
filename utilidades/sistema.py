"""MILLER · Capa de interacción con Windows."""
import os
import platform
import subprocess
import webbrowser
from utilidades import seguridad


def _ruta_datos():
    try:
        from configuracion import RUTA_DATOS
        return RUTA_DATOS
    except Exception:
        return Path(__file__).resolve().parent.parent / "datos"
from pathlib import Path
import json
import re
import threading
import time
import unicodedata
from difflib import SequenceMatcher
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# Nombre hablado -> lo que se busca en el catálogo (o un ejecutable / URI directo).
ALIAS_PROGRAMAS = {
    "calculadora": "calc.exe", "bloc de notas": "notepad.exe", "bloc": "notepad.exe", "notas": "notepad.exe",
    "explorador de archivos": "explorer.exe", "explorador": "explorer.exe", "archivos": "explorer.exe",
    "paint": "mspaint.exe", "simbolo del sistema": "cmd.exe", "consola": "cmd.exe", "terminal": "wt.exe",
    "powershell": "powershell.exe", "administrador de tareas": "taskmgr.exe", "panel de control": "control.exe",
    "configuracion": "ms-settings:", "ajustes": "ms-settings:", "tienda": "ms-windows-store:",
    "recortes": "snippingtool.exe", "herramienta de recortes": "snippingtool.exe", "editor del registro": "regedit.exe",
    "word": "Word", "excel": "Excel", "powerpoint": "PowerPoint", "outlook": "Outlook", "teams": "Teams",
    "navegador": "msedge.exe", "edge": "msedge.exe", "chrome": "Google Chrome", "google chrome": "Google Chrome",
    "firefox": "Firefox", "visual studio code": "Visual Studio Code", "vs code": "Visual Studio Code",
    "wasap": "WhatsApp", "guasap": "WhatsApp", "whats": "WhatsApp", "spoti": "Spotify",
    "camara": "Cámara", "reloj": "Reloj", "calendario": "Calendario", "fotos": "Fotos", "correo": "Correo",
}
_EXCLUIR = re.compile(r"uninstall|desinstal|readme|leeme|help|ayuda|manual|license|licencia|website|sitio web|"
                      r"documentation|documentacion|release notes|changelog", re.I)

def _norma(texto):
    texto = unicodedata.normalize("NFD", str(texto or "").lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+#. ]+", " ", texto)).strip()

class CatalogoAplicaciones:
    """Índice de TODOS los programas del equipo Windows: menú Inicio, escritorio, apps de la Tienda y App Paths."""
    VIGENCIA = 12 * 3600
    def __init__(self, ruta_cache=None):
        self.ruta_cache = Path(ruta_cache) if ruta_cache else _ruta_datos() / "aplicaciones.json"
        self.entradas, self._fecha, self._lock = [], 0.0, threading.Lock()
        self._hilo = None
        self._cargar_cache()
    def _cargar_cache(self):
        try:
            datos = seguridad.leer_json(self.ruta_cache, {}) or {}
            entradas = [e for e in datos.get("entradas", []) if isinstance(e, dict)
                        and e.get("tipo") in ("appid", "acceso", "exe") and isinstance(e.get("objetivo"), str)]
            self.entradas, self._fecha = entradas, float(datos.get("fecha", 0))
        except (OSError, ValueError, TypeError, AttributeError):
            self.entradas, self._fecha = [], 0.0
    def indexar_en_segundo_plano(self):
        if os.name != "nt" or (self._hilo and self._hilo.is_alive()):
            return
        if self.entradas and time.time() - self._fecha < self.VIGENCIA:
            return
        self._hilo = threading.Thread(target=self.indexar, daemon=True, name="MILLER-IndiceProgramas")
        self._hilo.start()
    def indexar(self):
        if os.name != "nt":
            return 0
        entradas, vistos = [], set()
        def agregar(nombre, objetivo, tipo):
            clave = _norma(nombre)
            if clave and not _EXCLUIR.search(nombre) and (clave, tipo) not in vistos:
                vistos.add((clave, tipo))
                entradas.append({"nombre": nombre, "clave": clave, "objetivo": str(objetivo), "tipo": tipo})
        for app in self._apps_inicio():                       # apps de la Tienda y del sistema (incluye Win32)
            agregar(app.get("Name", ""), app.get("AppID", ""), "appid")
        carpetas = [Path(os.environ.get("ProgramData", r"C:\ProgramData")) / r"Microsoft\Windows\Start Menu\Programs",
                    Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs",
                    Path(os.environ.get("USERPROFILE", "")) / "Desktop", Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop"]
        for carpeta in carpetas:
            try:
                for acceso in carpeta.rglob("*.lnk"):
                    agregar(acceso.stem, acceso, "acceso")
            except OSError:
                continue
        for nombre, ruta in self._app_paths():
            agregar(Path(nombre).stem, ruta, "exe")
        with self._lock:
            self.entradas, self._fecha = entradas, time.time()
        try:
            seguridad.escribir_json(self.ruta_cache, {"fecha": self._fecha, "entradas": entradas}, indent=None)
        except (OSError, ValueError):
            pass
        print(f"[SISTEMA] Índice de programas: {len(entradas)} encontrados.")
        return len(entradas)
    @staticmethod
    def _apps_inicio():
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                                "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json -Compress"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25, creationflags=_NO_WINDOW)
            datos = json.loads(r.stdout or "[]")
            return datos if isinstance(datos, list) else [datos]
        except (OSError, ValueError, subprocess.SubprocessError):
            return []
    @staticmethod
    def _app_paths():
        try:
            import winreg
        except ImportError:
            return []
        salida = []
        for raiz in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(raiz, r"Software\Microsoft\Windows\CurrentVersion\App Paths") as clave:
                    for i in range(winreg.QueryInfoKey(clave)[0]):
                        nombre = winreg.EnumKey(clave, i)
                        try:
                            with winreg.OpenKey(clave, nombre) as sub:
                                ruta = winreg.QueryValue(sub, None)
                            if ruta:
                                salida.append((nombre, ruta.strip('"')))
                        except OSError:
                            continue
            except OSError:
                continue
        return salida
    def buscar(self, nombre):
        """Mejor coincidencia para el nombre dicho. Devuelve la entrada o None."""
        consulta = _norma(nombre)
        if not consulta:
            return None
        alias = ALIAS_PROGRAMAS.get(consulta)
        objetivo = _norma(alias) if alias else consulta
        with self._lock:
            entradas = list(self.entradas)
        prioridad = {"appid": 0, "acceso": 1, "exe": 2}
        def puntuar(e):
            clave = e["clave"]
            if clave == objetivo or clave == consulta:
                return 1.0
            palabras = clave.split()
            if objetivo in palabras or consulta in palabras or clave.startswith(objetivo + " "):
                return 0.93 - 0.01 * len(palabras)
            if len(objetivo) >= 4 and objetivo in clave:
                return 0.85 - 0.005 * len(clave)
            return SequenceMatcher(None, objetivo, clave).ratio() * 0.9
        mejores = sorted(((puntuar(e), -prioridad.get(e["tipo"], 3), e) for e in entradas), key=lambda x: (x[0], x[1]), reverse=True)
        if mejores and mejores[0][0] >= 0.72:
            return mejores[0][2]
        if alias and (alias.endswith((".exe", ":")) or ":" in alias):   # ejecutable o URI del sistema conocido
            return {"nombre": nombre, "clave": consulta, "objetivo": alias, "tipo": "comando"}
        return None
    @staticmethod
    def lanzar(entrada):
        objetivo, tipo = entrada["objetivo"], entrada["tipo"]
        if tipo == "appid":
            subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{objetivo}"], creationflags=_NO_WINDOW)
        elif tipo == "comando" and objetivo.endswith(".exe"):
            subprocess.Popen([objetivo], creationflags=_NO_WINDOW)      # sin shell: nada de inyección de comandos
        else:
            if seguridad.es_peligroso(objetivo):
                seguridad.alerta(f"Lanzamiento bloqueado de un objetivo sospechoso: {objetivo[:80]}")
                return False
            os.startfile(objetivo)                              # .lnk, .exe, ms-settings:, ...
        return True
    def abrir(self, nombre):
        """(True, nombre_mostrado) si lo abrió; (False, motivo)."""
        if os.name != "nt":
            return False, "solo disponible en Windows"
        entrada = self.buscar(nombre)
        if entrada is None and (not self.entradas or time.time() - self._fecha > 600):
            self.indexar()                                      # programa recién instalado: reindexa una vez
            entrada = self.buscar(nombre)
        if entrada is None:
            return False, "no encontrado"
        try:
            self.lanzar(entrada)
            return True, entrada["nombre"]
        except Exception as error:
            print(f"[SISTEMA] Error abriendo {entrada['nombre']}: {error}")
            return False, "error al abrir"

class Sistema:
    """Controlador de las funciones del sistema operativo."""
    def __init__(self):
        self.sistema_operativo = platform.system()
        self.nombre_sistema = platform.platform()
        self.procesador = platform.processor()
        self.programas = CatalogoAplicaciones()
        self.programas.indexar_en_segundo_plano()
    def abrir_url(self, url):
        if not url:
            return False
        if not seguridad.url_segura(url):
            seguridad.alerta(f"URL bloqueada: {str(url)[:80]}")
            return False
        try:
            webbrowser.open_new(url)
            return True
        except Exception as error:
            print(f"[SISTEMA] Error al abrir URL: {error}")
            return False
    def abrir_aplicacion(self, aplicacion):
        """Abre CUALQUIER programa instalado por su nombre. Devuelve (ok, nombre_o_motivo)."""
        if not aplicacion:
            return False, "sin nombre"
        return self.programas.abrir(aplicacion)
    # CERRAR APLICACIÓN (cierre normal: la aplicación puede pedir guardar)
    def cerrar_aplicacion(self, aplicacion):
        """Cierra un programa abierto por su nombre. Devuelve (ok, nombre_o_motivo)."""
        consulta = _norma(aplicacion)
        if not consulta or os.name != "nt":
            return False, "no disponible"
        objetivo = ALIAS_PROGRAMAS.get(consulta, consulta)
        proceso = Path(objetivo).stem if objetivo.endswith(".exe") else _norma(objetivo).replace(" ", "")
        proceso = {"calc": "CalculatorApp", "mspaint": "mspaint", "explorer": "__ninguno__"}.get(proceso, proceso)
        titulo = seguridad.texto_para_comando(consulta)
        proceso = seguridad.texto_para_comando(proceso)
        if not titulo or not proceso:
            return False, "no disponible"
        script = (f"$p = Get-Process | Where-Object {{ $_.Id -ne {os.getpid()} -and $_.MainWindowHandle -ne 0 -and "
                  f"($_.ProcessName -like '{proceso}*' -or $_.MainWindowTitle -like '*{titulo}*') }}; "
                  "if (-not $p) { exit 3 }; $p | ForEach-Object { [void]$_.CloseMainWindow() }; "
                  "($p | Select-Object -First 1).ProcessName")
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True,
                               text=True, timeout=15, creationflags=_NO_WINDOW)
        except (OSError, subprocess.SubprocessError) as error:
            print(f"[SISTEMA] Error cerrando aplicación: {error}")
            return False, "error"
        return (True, r.stdout.strip() or aplicacion) if r.returncode == 0 else (False, "no está abierto")
    def crear_carpeta(self, nombre):
        if not nombre:
            return False
        try:
            ruta = seguridad.ruta_dentro(Path.cwd(), nombre)
            if ruta is None:
                return False
            ruta.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as error:
            print(f"[SISTEMA] Error creando carpeta: " f"{error}")
            return False
    def abrir_carpeta(self, nombre):
        if not nombre:
            return False
        try:
            ruta = seguridad.ruta_dentro(Path.cwd(), nombre)
            if ruta is None or not ruta.exists():
                return False
            if not ruta.is_dir():
                return False
            os.startfile(str(ruta))
            return True
        except Exception as error:
            print(f"[SISTEMA] Error abriendo carpeta: " f"{error}")
            return False
    def abrir_ruta(self, ruta):
        if not ruta:
            return False
        try:
            ruta = Path(ruta).expanduser()
            if not ruta.exists():
                return False
            if seguridad.archivo_peligroso(ruta):
                seguridad.alerta(f"Apertura bloqueada de un programa o script: {ruta.name}")
                return False
            os.startfile(str(ruta))
            return True
        except Exception as error:
            print(f"[SISTEMA] Error abriendo ruta: " f"{error}")
            return False
    def obtener_estado(self):
        try:
            return {
                "sistema_operativo":
                    self.nombre_sistema,
                "procesador":
                    self.procesador
                    or "No disponible",
                "arquitectura":
                    platform.machine(),
                "version_python":
                    platform.python_version(),
                "memoria":
                    self.obtener_memoria()
            }
        except Exception as error:
            print(f"[SISTEMA] Error obteniendo estado: " f"{error}")
            return {}
    def obtener_memoria(self):
        try:
            resultado = subprocess.run(
                [
                    "powershell",
                    "-Command",
                    "(Get-CimInstance "
                    "Win32_OperatingSystem)"
                    ".FreePhysicalMemory"
                ],
                capture_output=True,
                text=True,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW
                )
            )
            if resultado.returncode != 0:
                return "No disponible"
            valor = (resultado.stdout.strip())
            if not valor:
                return "No disponible"
            memoria_kb = float(valor)
            memoria_gb = (memoria_kb / (1024 * 1024))
            return (f"{memoria_gb:.2f} GB disponibles")
        except Exception:
            return "No disponible"
    def obtener_nombre_equipo(self):
        try:
            return platform.node()
        except Exception:
            return "Equipo desconocido"
    def obtener_directorio_actual(self):
        try:
            return str(Path.cwd())
        except Exception:
            return ""
    def es_windows(self):
        return (self.sistema_operativo == "Windows")
