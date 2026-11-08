"""MILLER · test.probar_voz."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent      # carpeta raíz de MILLER
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
from voz.hablador import Hablador
hablador = Hablador()
hablador.hablar("Hola. Soy MILLER. " "El sistema de voz funciona correctamente.")
