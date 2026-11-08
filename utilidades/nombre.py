"""MILLER · Nombre del asistente.

El nombre se pone al iniciar el programa: la primera vez, en la página INSTALACIÓN de la ventana (o en la consola
si no hay ventana). Solo se puede poner una vez. PURGAR lo borra.
Es la palabra con la que se le llama (la de activación) y el nombre con el que se presenta. Ya no aprende formas
nuevas de oírlo: vale el nombre que se escribió al iniciar. Se guarda firmado en datos/nombre_asistente.json.
"""
import re
import sys
import threading

import configuracion
from utilidades import seguridad

# Nombre de esta sesión. None hasta que se lee o se pone.
_actual = None
# Solo letras (con acentos y ñ): sin espacios, cifras ni signos.
_SOLO_LETRAS = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+")
# Se activa cuando el nombre queda fijado (guardado o recién puesto): el arranque espera este aviso.
_fijado = threading.Event()
_cerrojo = threading.Lock()                    # ENVIAR y Enter pueden llegar a la vez: solo uno lo guarda


def valido(texto):
    """(True, nombre) si sirve como nombre; (False, motivo) si no."""
    texto = str(texto or "").strip()
    if not texto:
        return False, "Escriba un nombre, señor."
    if not _SOLO_LETRAS.fullmatch(texto):
        return False, "Use una sola palabra, solo con letras, señor."
    minimo, maximo = configuracion.NOMBRE_LONGITUD_MINIMA, configuracion.NOMBRE_LONGITUD_MAXIMA
    if not minimo <= len(texto) <= maximo:
        return False, f"El nombre debe tener entre {minimo} y {maximo} letras, señor."
    return True, texto


def _guardado():
    """El nombre que quedó guardado (con su firma comprobada), o None."""
    datos = seguridad.leer_json(configuracion.RUTA_NOMBRE_ASISTENTE, None)
    if isinstance(datos, dict):
        ok, nombre = valido(datos.get("nombre"))
        if ok:
            return nombre
    return None


def fijado():
    """True si ya hay un nombre guardado."""
    return _guardado() is not None


def esperar_fijado(tiempo=None):
    """Espera a que el nombre quede fijado (guardado o recién puesto). Devuelve True si ya lo está."""
    return _fijado.wait(tiempo)


def clave():
    """El nombre con el que se llama al asistente en esta sesión."""
    global _actual
    if _actual is None:
        guardado = _guardado()
        _actual = guardado or configuracion.NOMBRE_PREDETERMINADO
        if guardado is not None:
            _fijado.set()
    return _actual


def fijar(texto):
    """Guarda el nombre. Solo una vez: si ya hay uno guardado, no cambia. Devuelve (ok, nombre o motivo)."""
    global _actual
    with _cerrojo:                             # ENVIAR y Enter pueden llegar a la vez: solo uno lo guarda
        guardado = _guardado()
        if guardado is not None:
            _fijado.set()
            return False, f"Ya tengo nombre, señor: {guardado}. Solo se puede poner una vez."
        ok, resultado = valido(texto)
        if not ok:
            return False, resultado
        seguridad.escribir_json(configuracion.RUTA_NOMBRE_ASISTENTE, {"nombre": resultado}, sincronizar=True)
        _actual = resultado
        _fijado.set()
        return True, resultado


def configurar_al_iniciar(entrada=input, salida=print, interactivo=None):
    """Al iniciar el programa. Si ya hay nombre, lo usa. Si no, lo pregunta en la consola (Enter = el predeterminado).
    Sin consola (p. ej. el .exe sin ventana de texto) usa el predeterminado solo en esta sesión, sin guardarlo.
    Devuelve el nombre de esta sesión."""
    global _actual
    guardado = _guardado()
    if guardado is not None:
        _actual = guardado
        _fijado.set()
        return _actual
    if interactivo is None:
        interactivo = bool(sys.stdin) and sys.stdin.isatty()
    if not interactivo:
        _actual = configuracion.NOMBRE_PREDETERMINADO
        return _actual
    salida("MILLER: Antes de empezar, ¿cómo quiere llamarme, señor?")
    salida("MILLER: Escriba un nombre de una sola palabra. Solo se puede poner una vez.")
    while True:
        try:
            respuesta = entrada(f"Nombre (Enter = {configuracion.NOMBRE_PREDETERMINADO}): ")
        except (EOFError, KeyboardInterrupt):
            salida("")
            _actual = configuracion.NOMBRE_PREDETERMINADO
            return _actual
        respuesta = str(respuesta or "").strip() or configuracion.NOMBRE_PREDETERMINADO
        try:
            ok, resultado = fijar(respuesta)
        except Exception as error:
            salida(f"MILLER: No pude guardar el nombre ({error}). Lo uso solo en esta sesión, señor.")
            _actual = respuesta if valido(respuesta)[0] else configuracion.NOMBRE_PREDETERMINADO
            return _actual
        if ok:
            salida(f"MILLER: Entendido, señor. Desde ahora me llamo {resultado}.")
            return resultado
        salida(f"MILLER: Negativo. {resultado}")
