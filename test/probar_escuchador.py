"""MILLER · test.probar_escuchador: PRUEBA DEL ESCUCHADOR LOCAL"""
import sys as _sys
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent      # carpeta raíz de MILLER
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
from voz.escuchador import Escuchador
print("=" * 60)
print("       PRUEBA DEL RECONOCIMIENTO DE VOZ LOCAL")
print("=" * 60)
print()
escuchador = Escuchador()
print()
print("Modelo disponible:", escuchador.modelo_disponible)
print("Micrófono disponible:", escuchador.microfono_disponible)
print("Sistema inicializado:", escuchador.inicializado)
print()
if not escuchador.esta_disponible():
    print("ERROR: El escuchador no está disponible.")
    if escuchador.error:
        print("Motivo:", escuchador.error)
    escuchador.detener()
    raise SystemExit(1)
print("Habla una frase.")
print("Por ejemplo:")
print("Miller abre calculadora")
print()
try:
    texto = escuchador.escuchar()
    print()
    print("RESULTADO:")
    print(texto)
except KeyboardInterrupt:
    print()
    print("Prueba interrumpida.")
finally:
    escuchador.detener()
print()
print("=" * 60)
print("PRUEBA FINALIZADA")
print("=" * 60)
