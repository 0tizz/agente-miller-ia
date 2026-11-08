"""MILLER · Llave BOY (plan niños).

Es de código abierto, así que nada de aquí da acceso por sí solo. Se puede poner en la tarjeta BOY en cualquier
momento: la comprobación es la huella (PBKDF2 con sal), no el descubrimiento.

MILLER además la va encontrando en la cascada de palabras. La llave está partida en tres fragmentos de cuatro
caracteres que caen de vez en cuando entre las palabras. Cada vez que cae uno nuevo, MILLER lo guarda; cuando
tiene los tres, avisa («clave BOY encontrada») y la escribe en la terminal.

Los fragmentos van enmascarados con XOR: es ofuscación, no un secreto (quien lea el código puede deshacerla).
La llave PRO sí es secreta: solo se guarda su huella en acceso.py.

El progreso se guarda firmado en datos/seguridad/llave_boy.json.
"""
import hashlib
import hmac
import random
import re
import threading
import unicodedata

import configuracion
from utilidades import seguridad

RUTA = configuracion.RUTA_DATOS / "seguridad" / "llave_boy.json"
ITERACIONES = 100_000
PREFIJO = "BOY"

# Huella de la llave completa en canónico («BOYF9VFXL848RDZ»): sal y PBKDF2-HMAC-SHA256.
SAL = bytes.fromhex("923aa26f1bd0aeec212a6f75e3045a41")
HUELLA = "bd92f88592bc526f3b7256d73776b82e1615869706a8c5e53dfb43a186258d72"
# Fragmentos de cuatro caracteres, enmascarados (ver codificar/_fragmento).
FRAGMENTOS_CIFRADOS = ("cf317947", "04cf4c6d", "92cf3470")

_RE_BOY = re.compile(r"^BOY")
_cerrojo = threading.Lock()
_fragmentos_cache = None
_piezas_cache = None


def _sin_tildes(texto):
    return "".join(c for c in unicodedata.normalize("NFD", str(texto or "").lower())
                   if unicodedata.category(c) != "Mn").strip()


def _canonica_llave(texto):
    return "".join(c for c in str(texto or "") if c.isalnum() and c.isascii()).upper()


def _mascara(indice):
    return hashlib.sha256(f"MILLER-BOY-{indice}".encode("utf-8")).digest()[:4]


def codificar(indice, fragmento):
    """Enmascara un fragmento (hex). Lo usan las pruebas; el código guarda FRAGMENTOS_CIFRADOS."""
    return bytes(a ^ b for a, b in zip(fragmento.encode("ascii"), _mascara(indice))).hex()


def _fragmentos():
    """Los tres fragmentos en claro, descifrados una sola vez."""
    global _fragmentos_cache
    if _fragmentos_cache is None:
        _fragmentos_cache = tuple(
            bytes(a ^ b for a, b in zip(bytes.fromhex(cifrado), _mascara(i))).decode("ascii")
            for i, cifrado in enumerate(FRAGMENTOS_CIFRADOS))
    return _fragmentos_cache


def formato(canonica):
    """«BOYF9VFXL848RDZ» → «BOY-F9VF-XL84-8RDZ»."""
    return f"{PREFIJO}-{canonica[3:7]}-{canonica[7:11]}-{canonica[11:15]}"


def _huella(canonica):
    return hashlib.pbkdf2_hmac("sha256", canonica.encode("utf-8"), SAL, ITERACIONES, dklen=32).hex()


def _piezas():
    """Fragmentos ya guardados: {índice: texto}. Solo se aceptan los fragmentos auténticos."""
    global _piezas_cache
    with _cerrojo:
        if _piezas_cache is None:
            datos = seguridad.leer_json(RUTA, None) or {}
            guardadas = datos.get("piezas", {}) if isinstance(datos, dict) else {}
            validas = {}
            for clave, texto in (guardadas.items() if isinstance(guardadas, dict) else []):
                if str(clave).isdigit() and int(clave) < len(FRAGMENTOS_CIFRADOS):
                    indice = int(clave)
                    if texto == _fragmentos()[indice]:
                        validas[indice] = texto
            _piezas_cache = validas
        return dict(_piezas_cache)


def _guardar(piezas):
    global _piezas_cache
    with _cerrojo:
        _piezas_cache = dict(piezas)
    seguridad.escribir_json(RUTA, {"piezas": {str(i): t for i, t in sorted(piezas.items())}},
                            indent=2, sincronizar=True)


def progreso():
    """Cuántos fragmentos ha encontrado MILLER (0 a {total})."""
    return len(_piezas())


def total():
    return len(FRAGMENTOS_CIFRADOS)


def completado():
    """True si MILLER ya tiene los tres fragmentos (lo ha descubierto o se metió en la tarjeta)."""
    return progreso() == total()


def verificar(texto):
    """True si el texto es la llave BOY completa, con o sin guiones, en mayúsculas o no. No depende de lo descubierto."""
    canonica = _canonica_llave(texto)
    return canonica.startswith(PREFIJO) and len(canonica) == 15 and hmac.compare_digest(_huella(canonica), HUELLA)


def marcar_conocida():
    """La llave se puso en la tarjeta: se da por conocida. No hay aviso de descubrimiento."""
    _guardar({i: texto for i, texto in enumerate(_fragmentos())})


def fragmento_pendiente():
    """Un fragmento que MILLER aún no tiene, para que caiga en la cascada. None si ya los tiene todos."""
    faltan = [i for i in range(total()) if i not in _piezas()]
    if not faltan:
        return None
    return _fragmentos()[random.choice(faltan)]


_ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def senuelo():
    """Un fragmento de OTRA llave BOY (falsa): cae en la cascada para que MILLER aprenda a distinguirlo.
    Nunca coincide con los fragmentos reales; observar() lo descarta."""
    reales = set(_fragmentos())
    while True:
        cuerpo = "".join(random.choice(_ALFABETO) for _ in range(4))
        if cuerpo not in reales:
            return f"BOY-{cuerpo}" if random.random() < 0.5 else cuerpo


def observar(palabra):
    """Compara una palabra de la cascada con la llave BOY.

    Devuelve (estado, texto):
      («pieza», fragmento)     un fragmento nuevo: queda guardado;
      («encontrada», llave)    eran los tres: la llave completa en formato BOY-XXXX-XXXX-XXXX;
      («repetida», fragmento)  un fragmento que ya tenía;
      (None, None)             la palabra no es de la llave.
    """
    limpia = _canonica_llave(palabra)
    limpia = _RE_BOY.sub("", limpia, count=1)
    if not limpia or limpia not in _fragmentos():
        return None, None
    indice = _fragmentos().index(limpia)
    piezas = _piezas()
    if indice in piezas:
        return "repetida", limpia
    piezas[indice] = limpia
    _guardar(piezas)
    if len(piezas) == total():
        return "encontrada", formato(PREFIJO + "".join(_fragmentos()))
    return "pieza", limpia
