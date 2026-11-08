"""MILLER · test.probar_modelo_vosk: PRUEBA DEL MODELO DE VOZ LOCAL DE MILLER"""
import sys as _sys
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent      # carpeta raíz de MILLER
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
from pathlib import Path
from vosk import Model
from configuracion import RUTA_MODELO_VOZ
print("=" * 60)
print("        PRUEBA DEL MODELO DE VOZ LOCAL")
print("=" * 60)
print()
print("Ruta del modelo:")
print(RUTA_MODELO_VOZ)
print()
if not RUTA_MODELO_VOZ.exists():
    print("ERROR: No se encontró el modelo.")
    print()
    print("Comprueba que exista:")
    print(RUTA_MODELO_VOZ)
    raise SystemExit(1)
print("Cargando modelo...")
print("Esto puede tardar unos segundos.")
print()
try:
    modelo = Model(str(RUTA_MODELO_VOZ))
except Exception as error:
    print("ERROR cargando el modelo:")
    print(error)
    raise SystemExit(1)
print("Modelo cargado correctamente.")
print()
print("MILLER ya puede utilizar reconocimiento")
print("de voz completamente local.")
print()
print("=" * 60)
