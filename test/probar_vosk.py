"""MILLER · test.probar_vosk: PRUEBA DE VOSK"""
import sys as _sys
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent      # carpeta raíz de MILLER
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
import vosk
print("=" * 50)
print("PRUEBA DE VOSK")
print("=" * 50)
print()
print("Vosk se importó correctamente.")
print()
print("Módulo cargado:")
print(vosk)
print()
print("Prueba de reconocimiento local preparada.")
print("=" * 50)
