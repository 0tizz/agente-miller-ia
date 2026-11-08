"""MILLER · test.probar_nombre: el nombre del asistente se pone al iniciar, una sola vez, y es la palabra de activación.
No aprende formas nuevas de oírlo. Trabaja en una carpeta temporal: no toca los datos reales ni el código."""
import os
import shutil
import sys as _sys
import tempfile
from pathlib import Path as _Path

RAIZ = _Path(__file__).resolve().parent.parent      # carpeta raíz de MILLER
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
TEMPORAL = _Path(tempfile.mkdtemp(prefix="miller_nombre_"))
(TEMPORAL / "seguridad").mkdir()
os.environ["MILLER_DIR_SEGURIDAD"] = str(TEMPORAL / "seguridad")
fallos = []


def comprobar(condicion, mensaje):
    print(("  OK    " if condicion else "  FALLO ") + mensaje)
    if not condicion:
        fallos.append(mensaje)


import configuracion  # noqa: E402
from utilidades import nombre  # noqa: E402
from voz.activador import Activador  # noqa: E402

RUTA = TEMPORAL / "datos" / "nombre_asistente.json"
RUTA.parent.mkdir(parents=True)
configuracion.RUTA_NOMBRE_ASISTENTE = RUTA


def borrar_guardado():
    """Quita el nombre guardado (con su copia y su firma), como si nunca se hubiera puesto."""
    for ruta in RUTA.parent.glob(RUTA.name + "*"):
        ruta.unlink()
    nombre._actual = None


def entradas(*respuestas):
    """Una consola falsa: devuelve las respuestas en orden y después se acaba (EOF)."""
    pendientes = list(respuestas)

    def leer(_mensaje=""):
        if not pendientes:
            raise EOFError
        return pendientes.pop(0)
    return leer


print("1. Un nombre válido: una sola palabra, solo letras, de 3 a 20")
comprobar(nombre.valido("Jarvis") == (True, "Jarvis"), "Jarvis es válido")
comprobar(nombre.valido("  Ñandú ")[0], "Ñandú (con acento y espacios alrededor) es válido")
comprobar(not nombre.valido("")[0], "vacío no vale")
comprobar(not nombre.valido("Ab")[0], "dos letras no valen")
comprobar(not nombre.valido("Jar vis")[0], "dos palabras no valen")
comprobar(not nombre.valido("J4rvis")[0], "las cifras no valen")
comprobar(not nombre.valido("Jarvis!")[0], "los signos no valen")
comprobar(not nombre.valido("x" * 21)[0], "más de 20 letras no vale")

print("2. Sin consola (p. ej. el .exe sin ventana de texto): Miller para esta sesión, sin guardar nada")
borrar_guardado()
comprobar(nombre.configurar_al_iniciar(interactivo=False, salida=lambda _t: None) == "Miller",
          "sin consola, el nombre de esta sesión es Miller")
comprobar(not RUTA.exists(), "y no se guarda nada")

print("3. En consola: se pregunta y el nombre se guarda")
borrar_guardado()
salida = []
comprobar(nombre.configurar_al_iniciar(entrada=entradas("Jarvis"), salida=salida.append, interactivo=True) == "Jarvis",
          "la respuesta Jarvis es el nombre de esta sesión")
comprobar(RUTA.exists() and nombre.fijado(), "queda guardado en datos")
comprobar(any("Jarvis" in linea for linea in salida), "MILLER lo confirma")

print("4. Solo se puede poner una vez")
ok, mensaje = nombre.fijar("Otro")
comprobar(not ok and "Solo se puede poner una vez" in mensaje, "poner otro nombre se rechaza")
nombre._actual = None
salida = []
comprobar(nombre.configurar_al_iniciar(entrada=entradas("Otro"), salida=salida.append, interactivo=True) == "Jarvis",
          "al volver a abrir sigue Jarvis")
comprobar(not any("cómo quiere llamarme" in linea for linea in salida), "y no vuelve a preguntar")

print("5. Enter da el predeterminado; un nombre malo se vuelve a pedir")
borrar_guardado()
comprobar(nombre.configurar_al_iniciar(entrada=entradas(""), salida=lambda _t: None, interactivo=True) == "Miller",
          "Enter pone Miller")
comprobar(nombre.fijado() and nombre.clave() == "Miller", "y Miller queda guardado")
borrar_guardado()
salida = []
comprobar(nombre.configurar_al_iniciar(entrada=entradas("a", "Luna"), salida=salida.append, interactivo=True) == "Luna",
          "con «a» (muy corto) vuelve a preguntar; luego vale Luna")
comprobar(any(linea.startswith("MILLER: Negativo") for linea in salida), "y dice por qué no sirvió")

print("6. La palabra de activación es el nombre: sin las formas de fábrica de «miller» y sin aprender")
a = Activador("Jarvis", aprender=False)
comprobar(a.esta_activado("jarvis abre calculadora"), "Jarvis activa la escucha")
comprobar(a.extraer_orden("Jarvis, abre calculadora") == "abre calculadora", "la orden llega sin el nombre")
comprobar(not a.esta_activado("miller abre calculadora"), "miller ya no activa a Jarvis")
comprobar(not a.esta_activado("miler abre calculadora"), "ni sus deformaciones de fábrica")
for _ in range(4):
    a.procesar("jarbis pon musica")
comprobar(a.variantes_aprendidas() == [], "con el aprendizaje apagado no aprende formas nuevas")
comprobar(a.esta_activado("jarvis pon musica"), "sigue activando con su nombre")
b = Activador("miller", aprender=False)
comprobar(b.esta_activado("miler pon musica"), "con el nombre Miller siguen sus formas de fábrica")

print("7. Las órdenes con el nombre elegido se entienden como si dijeran «miller»")
nombre._actual = "Jarvis"
from cerebro.cerebro import Cerebro  # noqa: E402
c = Cerebro.__new__(Cerebro)
comprobar(c.normalizar_texto("Jarvis, abre calculadora") == "miller abre calculadora",
          "«Jarvis, abre calculadora» se lee «miller abre calculadora»")
comprobar(c.normalizar_texto("JARVIS") == "miller", "«JARVIS» a secas se lee «miller» (saludo)")
comprobar(c.normalizar_texto("javier abre algo") == "javier abre algo", "una palabra parecida no se cambia")
comprobar(c.normalizar_texto("pon musica de jarvis") == "pon musica de jarvis",
          "el nombre en medio de la frase no se cambia")
nombre._actual = "Miller"
comprobar(c.normalizar_texto("Miller, abre calculadora") == "miller, abre calculadora",
          "con el nombre predeterminado no cambia nada")

nombre._actual = None
shutil.rmtree(TEMPORAL, ignore_errors=True)
print()
print("RESULTADO:", "OK" if not fallos else f"FALLO ({len(fallos)})")
if fallos:
    raise SystemExit(1)
