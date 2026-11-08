"""MILLER · test.probar_voz_multiple."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent      # carpeta raíz de MILLER
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
from voz.hablador import Hablador
hablador = Hablador()
hablador.hablar("Hola. Soy MILLER.")
hablador.hablar("Esta es la segunda respuesta.")
hablador.hablar("Esta es la tercera respuesta.")
hablador.hablar("La síntesis de voz funciona correctamente.")
print()
print("Prueba de voz finalizada.")
