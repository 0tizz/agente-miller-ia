"""MILLER · test.probar_activador."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent      # carpeta raíz de MILLER
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
from voz.activador import Activador
activador = Activador("miller")
pruebas = [
    "miller abre calculadora",
    "miler abre calculadora",
    "milord abre calculadora",
    "miller abre google",
    "hola como estas",
    "abre calculadora"
]
print("=" * 60)
print("PRUEBA DEL ACTIVADOR DE MILLER")
print("=" * 60)
print()
for frase in pruebas:
    activado = activador.esta_activado(frase)
    orden = activador.extraer_orden(frase)
    print(f"Frase: {frase}")
    print(f"Activado: {activado}")
    print(f"Orden: {orden}")
    print("-" * 60)
