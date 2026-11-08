"""MILLER · Catálogo de comandos por versión (FREE, NIÑOS = BOY, PRO).

Cada ejemplo es una frase que MILLER entiende. «listado(modo)» dice los comandos de la versión que tiene puesta
y nombra algunos de la versión superior, para que el usuario sepa qué desbloquea cada llave.
La validez de los ejemplos la comprueba test/probar_catalogo.py contra la detección de intenciones.
"""

FREE = (
    ("pon música", "reproduce la biblioteca"),
    ("siguiente canción", "pasa a la siguiente"),
    ("sube el volumen", "cambia el volumen con fundido"),
    ("qué hora es", "hora en formato de 12 horas"),
    ("calcula 25 por 4", "operaciones sencillas"),
    ("pon una alarma para las 7", "alarmas"),
    ("estado de la batería", "batería del equipo"),
    ("quita de la cola la canción 2", "quita de la cola por número o por nombre"),
    ("limpia la cola", "vacía la cola de reproducción"),
    ("limpiar terminal", "borra el texto y la conversación reciente de la terminal"),
    ("qué sabes de ti", "lo que MILLER sabe de sí mismo"),
    ("conexiones de gatos", "qué recuerdos se relacionan con un tema"),
    ("qué modo tengo", "versión y espacio disponible"),
)

BOY = (
    ("qué has olvidado", "recuerdos archivados"),
    ("resume la memoria a largo plazo", "cuántos recuerdos guarda"),
    ("busca en internet cómo hacer pan", "consulta a internet"),
    ("abre la carpeta descargas", "carpetas del equipo"),
    ("qué hay en la papelera", "lo que está en la papelera"),
    ("novedades", "lo que MILLER tiene que contarle"),
)

PRO = (
    ("pon música y sube el volumen", "varios comandos en una frase"),
    ("estado del supervisor", "el supervisor de la biblioteca"),
    ("revisa la biblioteca", "revisión de la biblioteca"),
    ("repara la biblioteca", "reparación de la biblioteca"),
    ("sella el código", "sellado del código"),
)

NOMBRE = {"free": "FREE", "boy": "NIÑOS", "pro": "PRO"}


def _frases(lista):
    return " · ".join(frase for frase, _ in lista)


class Respuesta(str):
    """Texto para la terminal que además trae lo que MILLER dice en voz alta (atributo «voz»)."""

    def __new__(cls, texto, voz=None):
        obj = super().__new__(cls, texto)
        obj.voz = voz
        return obj


VOZ_COMANDOS = "Comandos disponibles en terminal."


def listado_completo(modo):
    """Todos los comandos, agrupados por versión; la versión que tiene puesta va primero y marcada.
    En voz solo se dice que están en la terminal."""
    modo = modo if modo in NOMBRE else "free"
    grupos = [("free", "FREE", FREE), ("boy", "NIÑOS", BOY), ("pro", "PRO", PRO)]
    orden = sorted(grupos, key=lambda g: g[0] != modo)            # la versión actual primero
    lineas = [f"Comandos de MILLER. Versión actual: {NOMBRE[modo]}."]
    for clave, nombre, lista in orden:
        if clave == modo:
            estado = "activa"
        elif clave in ("boy", "pro") and ["free", "boy", "pro"].index(clave) > ["free", "boy", "pro"].index(modo):
            estado = f"con la llave {nombre}"
        else:
            estado = "incluida"
        lineas.append(f"{nombre} ({estado}):")
        lineas.extend(f"  · {frase} — {descripcion}" for frase, descripcion in lista)
    lineas.append("Diga «comandos» de nuevo para verlos; con las flechas ↑ y ↓ repite órdenes anteriores.")
    return Respuesta("\n".join(lineas), voz=VOZ_COMANDOS)


def listado(modo):
    """Texto con los comandos de la versión «modo» y algunos de las superiores."""
    modo = modo if modo in NOMBRE else "free"
    if modo == "pro":
        return (f"Versión PRO, la completa. Comandos de FREE: {_frases(FREE)}. "
                f"De NIÑOS: {_frases(BOY)}. Exclusivos de PRO: {_frases(PRO)}.")
    if modo == "boy":
        return (f"Versión NIÑOS. Comandos: {_frases(FREE)} · {_frases(BOY)}. "
                f"Con la llave PRO se suman, por ejemplo: {_frases(PRO[:3])}.")
    return (f"Versión FREE. Comandos: {_frases(FREE)}. "
            f"Con la llave NIÑOS se suman, por ejemplo: {_frases(BOY[:3])}. "
            f"Con la llave PRO, además: {_frases(PRO[:3])}.")
