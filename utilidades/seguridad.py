"""MILLER · Seguridad: integridad del conocimiento, saneo de entradas y límites de acceso."""
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import shutil
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

try:
    from configuracion import RUTA_BASE as RAIZ          # funciona también en el .exe
except Exception:
    RAIZ = Path(__file__).resolve().parent.parent
DIR_SEGURIDAD = Path(os.environ.get("MILLER_DIR_SEGURIDAD") or RAIZ / "datos" / "seguridad")
MAX_JSON_BYTES = 25 * 1024 * 1024
MAX_ENTRADA = 300
MAX_CONOCIMIENTO = 600
MAX_PROFUNDIDAD = 12
INTERVALO_RESPALDO = 600
DOMINIOS_DESCARGA = ("youtube.com", "youtu.be", "music.youtube.com", "soundcloud.com")

_lock = threading.RLock()
_clave = None
_ultimo_respaldo = {}
_estado = {"verificados": 0, "adoptados": 0, "alertas": 0, "restaurados": 0}

# Caracteres invisibles o de control que se usan para engañar (bidi, ancho cero...).
_RE_INVISIBLES = re.compile("[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f​-‏‪-‮⁠-⁤﻿]")
_RE_ETIQUETAS = re.compile(r"<[^>]{0,500}>")
_RE_ESQUEMAS = re.compile(r"\b(?:javascript|vbscript|data|file)\s*:", re.I)
_RE_URL = re.compile(r"\bhttps?://\S+|\bwww\.\S+", re.I)
_RE_PELIGROSO = re.compile(r"(?:powershell|cmd(?:\.exe)?\s*/c|rm\s+-rf|del\s+/[fsq]|format\s+[a-z]:|curl\s+|wget\s+|"
                           r"invoke-expression|iex\s*\(|base64\s+-d|reg\s+add|schtasks)", re.I)
_RE_NOMBRE_INVALIDO = re.compile(r'[<>:"|?*\\/\x00-\x1f]')
_NOMBRES_RESERVADOS = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


# Archivos que al abrirlos ejecutarían código (programas, scripts, macros de Office, imágenes de disco).
EXTENSIONES_PELIGROSAS = frozenset({
    ".exe", ".bat", ".cmd", ".com", ".ps1", ".psm1", ".psc1", ".psc2", ".ps1xml", ".vbs", ".vbe", ".vb", ".js",
    ".jse", ".wsf", ".wsh", ".msi", ".msp", ".mst", ".scr", ".hta", ".reg", ".cpl", ".msc", ".jar", ".pif", ".lnk",
    ".url", ".sct", ".wsc", ".inf", ".scf", ".dll", ".ocx", ".gadget", ".application", ".appref-ms", ".xbap",
    ".chm", ".library-ms", ".search-ms", ".diagcab", ".msh", ".msh1", ".msh2", ".mshxml", ".msh1xml", ".msh2xml",
    ".iso", ".img", ".vhd", ".vhdx", ".docm", ".dotm", ".xlsm", ".xltm", ".xlam", ".pptm", ".potm", ".ppam"})


def archivo_peligroso(ruta):
    """True si abrir ese archivo ejecutaría código (programa, script, macro o imagen de disco)."""
    return Path(str(ruta)).suffix.lower() in EXTENSIONES_PELIGROSAS


def alerta(mensaje):
    """Registra un incidente de seguridad (consola + datos/seguridad/alertas.log)."""
    _estado["alertas"] += 1
    linea = f"{datetime.now().isoformat(timespec='seconds')} {mensaje}"
    print(f"[SEGURIDAD] ⚠ {mensaje}")
    try:
        DIR_SEGURIDAD.mkdir(parents=True, exist_ok=True)
        registro = DIR_SEGURIDAD / "alertas.log"
        if registro.exists() and registro.stat().st_size > 200_000:
            registro.replace(registro.with_suffix(".log.1"))
        with registro.open("a", encoding="utf-8") as f:
            f.write(linea + "\n")
    except OSError:
        pass


def resumen():
    """Estado de las capas de seguridad para "Miller, estado de seguridad"."""
    alertas = 0
    try:
        registro = DIR_SEGURIDAD / "alertas.log"
        if registro.exists():
            alertas = sum(1 for _ in registro.open(encoding="utf-8"))
    except OSError:
        pass
    texto = (f"Seguridad activa. {_estado['verificados']} archivos de conocimiento verificados en esta sesión. ")
    if _estado["restaurados"]:
        texto += f"{_estado['restaurados']} restaurados desde respaldo. "
    texto += f"{alertas} alertas registradas." if alertas else "Sin alertas."
    try:
        cambiados = integridad_codigo()
        if cambiados is None:
            texto += " Código sellado ahora por primera vez."
        elif cambiados:
            nombres = ", ".join(sorted(cambiados)[:3]) + ("…" if len(cambiados) > 3 else "")
            texto += (f" Atención: {len(cambiados)} archivos de mi código cambiaron desde que se sellaron ({nombres})."
                      " Si fue usted, diga «Miller, sella tu código».")
        else:
            texto += " Mi código está intacto."
    except Exception:
        pass
    return texto


# ------------------------------------------------------------ integridad del propio programa
_EXCLUIR_CODIGO = {"__pycache__", "dist", "build", ".git", "datos", "audios", "modelos", "graphify-out", "test"}


def _huellas_codigo(raiz=None):
    """sha256 de cada .py de MILLER (sin pruebas ni datos)."""
    raiz = Path(raiz or RAIZ)
    huellas = {}
    for ruta in raiz.rglob("*.py"):
        if any(p in _EXCLUIR_CODIGO for p in ruta.relative_to(raiz).parts):
            continue
        try:
            huellas[str(ruta.relative_to(raiz)).replace("\\", "/")] = hashlib.sha256(ruta.read_bytes()).hexdigest()
        except OSError:
            pass
    return huellas


def sellar_codigo(raiz=None):
    """Guarda (firmadas) las huellas del código actual: a partir de aquí se detecta cualquier cambio."""
    huellas = _huellas_codigo(raiz)
    escribir_json(DIR_SEGURIDAD / "integridad.json", {"sellado": datetime.now().isoformat(timespec="seconds"),
                                                    "huellas": huellas}, respaldo=False)
    return len(huellas)


def integridad_codigo(raiz=None):
    """Archivos de código cambiados, nuevos o borrados desde el sello (lista). None si aún no había sello."""
    sello = leer_json(DIR_SEGURIDAD / "integridad.json", None)
    if not isinstance(sello, dict) or not isinstance(sello.get("huellas"), dict):
        sellar_codigo(raiz)
        return None
    actuales, guardadas = _huellas_codigo(raiz), sello["huellas"]
    return [n for n in set(actuales) | set(guardadas) if actuales.get(n) != guardadas.get(n)]


def anexar_log(ruta, linea, maximo=512_000):
    """Añade una línea a un registro que nunca crece sin límite (se rota a .1)."""
    ruta = Path(ruta)
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        if ruta.exists() and ruta.stat().st_size > maximo:
            ruta.replace(ruta.with_suffix(ruta.suffix + ".1"))
        with ruta.open("a", encoding="utf-8") as f:
            f.write(linea.rstrip("\n") + "\n")
    except OSError:
        pass


def limpiar_antiguos(dias=30):
    """Borra copias aisladas y respaldos de más de 'dias' días: la carpeta de datos no crece sin fin."""
    limite = time.time() - dias * 86400
    borrados = 0
    for carpeta in (DIR_SEGURIDAD / "sospechosos", RAIZ / "datos" / "respaldos_interfaz"):
        try:
            for archivo in carpeta.iterdir():
                if archivo.is_file() and archivo.stat().st_mtime < limite:
                    archivo.unlink()
                    borrados += 1
        except OSError:
            continue
    return borrados


def _obtener_clave():
    global _clave
    with _lock:
        if _clave is not None:
            return _clave
        DIR_SEGURIDAD.mkdir(parents=True, exist_ok=True)
        archivo = DIR_SEGURIDAD / "clave.bin"
        try:
            datos = archivo.read_bytes()
            if len(datos) == 32:
                _clave = datos
                return _clave
        except OSError:
            pass
        _clave = secrets.token_bytes(32)
        archivo.write_bytes(_clave)
        _ocultar(archivo)
        return _clave


def _ocultar(ruta):
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(str(ruta), 0x02)   # oculto
        except Exception:
            pass


def firmar(datos: bytes) -> str:
    return hmac.new(_obtener_clave(), datos, hashlib.sha256).hexdigest()


def _ruta_firma(ruta):
    return ruta.with_name(ruta.name + ".firma")


def _ruta_respaldo(ruta):
    return ruta.with_name(ruta.name + ".bak")


def _firma_valida(ruta, datos):
    try:
        guardada = _ruta_firma(ruta).read_text(encoding="ascii").strip()
    except OSError:
        return None                                  # sin firma (archivo antiguo o nuevo)
    return hmac.compare_digest(guardada, firmar(datos))


def _aislar(ruta):
    """Copia el archivo sospechoso a datos/seguridad/sospechosos/ para revisarlo."""
    try:
        destino = DIR_SEGURIDAD / "sospechosos"
        destino.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ruta, destino / f"{time.strftime('%Y%m%d-%H%M%S')}_{ruta.name}")
    except OSError:
        pass


def leer_json(ruta, defecto=None):
    """Lee un archivo de conocimiento verificando su firma."""
    ruta = Path(ruta)
    if not ruta.is_file():
        return defecto
    try:
        if ruta.stat().st_size > MAX_JSON_BYTES:
            alerta(f"{ruta.name} demasiado grande ({ruta.stat().st_size} bytes): posible ataque de saturación.")
            _aislar(ruta)
            return _desde_respaldo(ruta, defecto)
        datos = ruta.read_bytes()
    except OSError as error:
        print(f"[SEGURIDAD] No se pudo leer {ruta.name}: {error}")
        return defecto
    valida = _firma_valida(ruta, datos)
    if valida is False:
        alerta(f"{ruta.name} fue modificado fuera de MILLER. Copia aislada en datos/seguridad/sospechosos.")
        _aislar(ruta)
        respaldo = _desde_respaldo(ruta, None)
        if respaldo is not None:
            return respaldo
    try:
        contenido = json.loads(datos.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        alerta(f"{ruta.name} ilegible ({error}).")
        _aislar(ruta)
        return _desde_respaldo(ruta, defecto)
    if valida is not True:                           # sin firma o alterado sin respaldo: se sanea y se adopta
        contenido = sanear_estructura(contenido)
        _estado["adoptados"] += 1
        escribir_json(ruta, contenido)
    _estado["verificados"] += 1
    return contenido


def _desde_respaldo(ruta, defecto):
    respaldo = _ruta_respaldo(ruta)
    try:
        datos = respaldo.read_bytes()
        if _firma_valida(respaldo, datos) is True:
            contenido = json.loads(datos.decode("utf-8"))
            _estado["restaurados"] += 1
            alerta(f"{ruta.name} restaurado desde su último respaldo válido.")
            escribir_json(ruta, contenido, respaldo=False)
            return contenido
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        pass
    return defecto


def escribir_json(ruta, contenido, indent=None, respaldo=True, sincronizar=False):
    """Escritura atómica + firma. Guarda un respaldo firmado como mucho cada 10 minutos."""
    ruta = Path(ruta)
    datos = json.dumps(contenido, ensure_ascii=False, indent=indent, allow_nan=False).encode("utf-8")
    if len(datos) > MAX_JSON_BYTES:
        alerta(f"{ruta.name}: escritura bloqueada, supera el tamaño máximo.")
        return False
    with _lock:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ahora = time.monotonic()
        if respaldo and ruta.is_file() and ahora - _ultimo_respaldo.get(ruta, -1e9) > INTERVALO_RESPALDO:
            try:
                actual = ruta.read_bytes()
                if _firma_valida(ruta, actual) is True:
                    _ruta_respaldo(ruta).write_bytes(actual)
                    _ruta_firma(_ruta_respaldo(ruta)).write_text(firmar(actual), encoding="ascii")
                    _ultimo_respaldo[ruta] = ahora
            except OSError:
                pass
        temporal = ruta.with_name(ruta.name + ".tmp")
        with temporal.open("wb") as f:
            f.write(datos)
            if sincronizar:
                f.flush()
                os.fsync(f.fileno())
        os.replace(temporal, ruta)
        _ruta_firma(ruta).write_text(firmar(datos), encoding="ascii")
    return True


def sanear_texto(texto, maximo=MAX_ENTRADA):
    texto = unicodedata.normalize("NFC", str(texto or ""))
    texto = _RE_INVISIBLES.sub(" ", texto.replace("\r", " ").replace("\n", " ").replace("\t", " "))
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto[:maximo].rstrip()


def sanear_entrada(texto):
    """Lo que dice o escribe el usuario: sin caracteres de control y con longitud limitada."""
    return sanear_texto(texto, MAX_ENTRADA)


def sanear_conocimiento(texto, maximo=MAX_CONOCIMIENTO):
    """Lo que MILLER aprende (internet, recuerdos): sin HTML, scripts, enlaces ni órdenes de sistema."""
    texto = html.unescape(str(texto or ""))
    texto = _RE_ETIQUETAS.sub(" ", texto)
    texto = _RE_ESQUEMAS.sub(" ", texto)
    texto = _RE_URL.sub(" ", texto)
    texto = _RE_PELIGROSO.sub(" ", texto)
    return sanear_texto(texto, maximo)


def es_peligroso(texto):
    return bool(_RE_PELIGROSO.search(str(texto or "")) or _RE_ESQUEMAS.search(str(texto or "")))


def sanear_estructura(obj, profundidad=0):
    """Recorre un JSON cargado y sanea todas sus cadenas (límite de profundidad)."""
    if profundidad > MAX_PROFUNDIDAD:
        return None
    if isinstance(obj, dict):
        return {sanear_texto(k, 200): sanear_estructura(v, profundidad + 1) for k, v in list(obj.items())[:20000]}
    if isinstance(obj, list):
        return [sanear_estructura(v, profundidad + 1) for v in obj[:20000]]
    if isinstance(obj, str):
        return _RE_INVISIBLES.sub(" ", obj)[:5000]
    return obj


def nombre_seguro(nombre, maximo=80):
    nombre = sanear_texto(nombre, maximo).strip(" .")
    if not nombre or ".." in nombre or _RE_NOMBRE_INVALIDO.search(nombre):
        return None
    if nombre.split(".")[0].lower() in _NOMBRES_RESERVADOS:
        return None
    return nombre


def ruta_dentro(base, nombre):
    """Devuelve base/nombre solo si queda DENTRO de base (evita ../, rutas absolutas y unidades)."""
    nombre = nombre_seguro(nombre)
    if not nombre:
        return None
    base = Path(base).resolve()
    ruta = (base / nombre).resolve()
    try:
        ruta.relative_to(base)
    except ValueError:
        alerta(f"Ruta fuera de la zona permitida bloqueada: {nombre}")
        return None
    return ruta


def url_segura(url, dominios=None):
    try:
        url = str(url or "").strip()
        partes = urlparse(url)
    except (TypeError, ValueError):
        return False
    if len(url) > 2048 or _RE_INVISIBLES.search(url) or " " in url:
        return False
    if partes.scheme.lower() not in ("http", "https") or not partes.hostname or "@" in partes.netloc:
        return False
    if dominios:
        host = partes.hostname.lower()
        return any(host == d or host.endswith("." + d) for d in dominios)
    return True


def texto_para_comando(texto, maximo=60):
    """Texto apto para insertarse en un comando del sistema: solo letras, números, espacio, punto y guion."""
    return re.sub(r"[^\w .\-]", "", str(texto or ""), flags=re.UNICODE)[:maximo].strip()


class LimitadorOrdenes:
    """Frena ráfagas de órdenes (scripts o ruido) para que MILLER no se sature."""
    def __init__(self, maximo=20, ventana=10.0):
        self.maximo, self.ventana, self._marcas, self._lock = maximo, ventana, [], threading.Lock()

    def permitir(self):
        ahora = time.monotonic()
        with self._lock:
            self._marcas = [t for t in self._marcas if ahora - t < self.ventana]
            if len(self._marcas) >= self.maximo:
                return False
            self._marcas.append(ahora)
            return True
