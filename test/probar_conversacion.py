"""MILLER · Prueba de la conversación fluida (seguimiento sin nombre y modo llamada)."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
import time
from voz.conversacion import Conversacion
fallos = []


def comprobar(condicion, mensaje):
    print(("  OK    " if condicion else "  FALLO ") + mensaje)
    if not condicion:
        fallos.append(mensaje)


c = Conversacion(ventana=0.5, fin_inactividad=0.6)
print("1. Seguimiento tras una respuesta")
comprobar(not c.acepta_sin_nombre(), "sin respuesta previa exige el nombre")
c.abrir_seguimiento()
comprobar(c.acepta_sin_nombre() and c.en_seguimiento(), "justo después acepta sin nombre")
time.sleep(0.6)
comprobar(not c.acepta_sin_nombre(), "pasada la ventana vuelve a exigir el nombre")
print("2. Modo llamada")
for t in ("modo llamada", "Miller, hablemos", "conversemos"):
    comprobar(c.es_inicio(t), f"'{t}' inicia llamada")
for t in ("fin de la llamada", "cuelga", "eso es todo"):
    comprobar(c.es_fin(t), f"'{t}' cuelga")
comprobar(not c.es_inicio("pon musica") and not c.es_fin("pon musica"), "una orden normal no inicia ni cuelga")
c.iniciar_llamada()
time.sleep(0.4)
c.oido()
time.sleep(0.4)
comprobar(c.en_llamada() and c.acepta_sin_nombre(), "la voz mantiene viva la llamada")
time.sleep(0.4)
comprobar(c.debe_caducar() and c.llamada_caducada() and not c.en_llamada(), "silencio largo: cuelga sola")
comprobar(not c.llamada_caducada(), "avisa una sola vez")
print()
print("RESULTADO:", "OK" if not fallos else f"FALLO ({len(fallos)})")
if fallos:
    raise SystemExit(1)
