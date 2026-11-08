"""MILLER · Prueba de maximizar y minimizar programas (sin Windows: la API se sustituye por una lista falsa)."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
import os
import tempfile
from pathlib import Path

_base = Path(tempfile.mkdtemp())
os.environ["MILLER_DIR_SEGURIDAD"] = str(_base / "seguridad")
fallos = []


def comprobar(condicion, mensaje):
    print(("  OK    " if condicion else "  FALLO ") + mensaje)
    if not condicion:
        fallos.append(mensaje)


from utilidades import ventanas as _v
from cerebro.comandos import Comandos
from cerebro.cerebro import Cerebro

llamadas = []
_v.disponible = lambda: True
_v.mostrar_como = lambda nombre, modo: (llamadas.append((nombre, modo)) or (1, nombre))
cmd = Comandos.__new__(Comandos)
cmd.minimizar_propia = None
cmd.ultimo_objetivo = None
cer = Cerebro.__new__(Cerebro)

print("1. Verbos completos (antes «minimizar x» se leía mal)")
casos = [
    ("minimiza brave", "brave", "minimizar"), ("minimizar chrome", "chrome", "minimizar"),
    ("minimizame netflix", "netflix", "minimizar"), ("maximizar spotify", "spotify", "maximizar"),
    ("maximizame discord", "discord", "maximizar"), ("maximiza la ventana de word", "word", "maximizar"),
    ("restaurar brave", "brave", "restaurar"), ("restaurame excel", "excel", "restaurar"),
    ("miller maximiza el navegador brave", "brave", "maximizar"), ("esconde steam", "steam", "minimizar"),
]
for texto, nombre, modo in casos:
    llamadas.clear()
    cmd.controlar_ventana(texto)
    comprobar(llamadas == [(nombre, modo)], f"«{texto}» -> {modo} {nombre}: {llamadas}")

print("2. Pantalla completa")
llamadas.clear()
cmd.controlar_ventana("pon spotify en pantalla completa")
comprobar(llamadas == [("spotify", "maximizar")], "«pon spotify en pantalla completa» maximiza spotify")
llamadas.clear()
cmd.controlar_ventana("deja la ventana de netflix en pantalla completa")
comprobar(llamadas == [("netflix", "maximizar")], "acepta «la ventana de» dentro")
comprobar(cer.detectar_intencion("pon spotify en pantalla completa") == "VENTANA", "la detección la entiende como ventana")
comprobar(cer.detectar_intencion("pon musica") == "REPRODUCIR_MUSICA", "«pon música» sigue siendo música")
comprobar(cer.detectar_intencion("maximiza brave") == "VENTANA", "«maximiza brave» sigue siendo ventana")

print("3. Búsqueda de ventanas (pestañas y programas)")
lista = [
    {"exe": "brave", "titulo": "Netflix - Brave", "hwnd": 1, "pid": 10, "clase": "Chrome_WidgetWin_1"},
    {"exe": "brave", "titulo": "YouTube - Brave", "hwnd": 2, "pid": 10, "clase": "Chrome_WidgetWin_1"},
    {"exe": "spotify", "titulo": "Spotify Premium", "hwnd": 3, "pid": 20, "clase": ""},
    {"exe": "winword", "titulo": "informe.docx - Word", "hwnd": 4, "pid": 30, "clase": ""},
]
comprobar([v["hwnd"] for v in _v.buscar("brave", lista)] == [1, 2], "brave: todas sus ventanas")
comprobar([v["hwnd"] for v in _v.buscar("netflix", lista)] == [1], "netflix: la pestaña por el título")
comprobar([v["hwnd"] for v in _v.buscar("spotify", lista)] == [3], "spotify: por el ejecutable")
comprobar([v["hwnd"] for v in _v.buscar("informe", lista)] == [4], "archivo abierto por su nombre en el título")
comprobar(_v.buscar("discord", lista) == [], "un programa cerrado no aparece")
comprobar(_v.limpiar_nombre("la ventana de Spotify") == "spotify", "limpia «la ventana de»")

print()
if fallos:
    print(f"FALLOS: {len(fallos)}")
    raise SystemExit(1)
print("TODO OK")
