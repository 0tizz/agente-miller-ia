"""Ayuda de las pruebas: pone una llave BOY de prueba (con sus tres fragmentos) en lugar de la real.
Así las pruebas no dependen de la llave del código abierto ni de lo que MILLER haya descubierto."""
import hashlib
import secrets

from utilidades import llave_boy as lb

ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def preparar():
    """Pone una llave BOY de prueba y la devuelve con guiones (BOY-XXXX-XXXX-XXXX). Sin fragmentos descubiertos."""
    cuerpo = "".join(secrets.choice(ALFABETO) for _ in range(12))
    canonica = lb.PREFIJO + cuerpo
    sal = secrets.token_bytes(16)
    lb.SAL = sal
    lb.HUELLA = hashlib.pbkdf2_hmac("sha256", canonica.encode("utf-8"), sal, lb.ITERACIONES, dklen=32).hex()
    lb.FRAGMENTOS_CIFRADOS = tuple(lb.codificar(i, cuerpo[4 * i:4 * i + 4]) for i in range(3))
    lb._fragmentos_cache = None
    lb._piezas_cache = None
    lb._guardar({})
    return lb.formato(canonica)
