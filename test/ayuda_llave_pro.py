"""Ayuda de las pruebas: pone una llave PRO de prueba en lugar de la real.
La llave PRO real no va en el repositorio público: las pruebas usan una generada al momento y solo cambian la huella
del módulo acceso mientras dura la prueba."""
import hashlib
import secrets

from utilidades import acceso

ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def preparar():
    """Pone una llave PRO de prueba (sal y huella propias) y la devuelve con guiones: PRO-XXXX-XXXX-XXXX."""
    cuerpo = "".join(secrets.choice(ALFABETO) for _ in range(12))
    canonica = "PRO" + cuerpo
    sal = secrets.token_bytes(16)
    acceso.SAL_PRO = sal
    acceso.HUELLA_PRO = hashlib.pbkdf2_hmac("sha256", canonica.encode("utf-8"), sal, acceso.ITERACIONES).hex()
    return f"PRO-{cuerpo[:4]}-{cuerpo[4:8]}-{cuerpo[8:]}"
