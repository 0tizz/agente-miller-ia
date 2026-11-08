"""MILLER · test.probar_sellar: SELLAR se puede decir en voz alta. Sin llave PRO se niega también por voz; con llave
PRO sella. No toca los datos reales: las llaves y el sellado van a una carpeta temporal."""
import os
import shutil
import sys as _sys
import tempfile
from pathlib import Path as _Path

RAIZ = _Path(__file__).resolve().parent.parent      # carpeta raíz de MILLER
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
TEMPORAL = _Path(tempfile.mkdtemp(prefix="miller_sellar_"))
(TEMPORAL / "seguridad").mkdir()
os.environ["MILLER_DIR_SEGURIDAD"] = str(TEMPORAL / "seguridad")
fallos = []


def comprobar(condicion, mensaje):
    print(("  OK    " if condicion else "  FALLO ") + mensaje)
    if not condicion:
        fallos.append(mensaje)


from utilidades import acceso, seguridad  # noqa: E402
from cerebro.cerebro import Cerebro  # noqa: E402

acceso.RUTA = TEMPORAL / "acceso.json"
llaves = acceso.generar_llaves()
c = Cerebro.__new__(Cerebro)
c.iniciativa = None
c.activador = None

SI = ["sella el codigo", "sellar el codigo", "sella tu codigo", "sellar codigo", "sella el programa",
      "sella el sistema", "sellame el codigo", "cellar el programa", "sellalo", "miller sella el codigo",
      "miller, sella este codigo", "sella mi programa", "acepta los cambios del codigo"]
NO = ["sella la carta", "sellar la ventana", "cierra el programa", "celular abre calculadora", "pon musica",
      "abre el programa de notas"]

print("1. Se reconoce SELLAR en las formas de voz")
for frase in SI:
    comprobar(c.detectar_intencion(frase) == "SELLAR_CODIGO", f"«{frase}» es SELLAR")
print("2. Lo que no es SELLAR no se confunde con él")
for frase in NO:
    comprobar(c.detectar_intencion(frase) != "SELLAR_CODIGO", f"«{frase}» no es SELLAR")

print("3. Sin llave PRO, SELLAR por voz se niega y no sella nada")
sellos = []
sellar_original = seguridad.sellar_codigo
seguridad.sellar_codigo = lambda raiz=None: sellos.append(1) or 3
acceso.bloquear()
respuesta = c.generar_respuesta("sella el codigo", "SELLAR_CODIGO")
comprobar("modo PRO" in respuesta, "la respuesta dice que SELLAR es del modo PRO")
comprobar(not sellos, "no se sella nada")

print("4. Con llave PRO, SELLAR por voz sella el código y dice cuántos archivos")
acceso.poner("pro", llaves["pro"])
comprobar("pro" in acceso.activas(), "la llave PRO queda puesta")
respuesta = c.generar_respuesta("sella el codigo", "SELLAR_CODIGO")
comprobar(sellos == [1] and "Código sellado: 3 archivos" in respuesta, "con PRO, la voz sella y lo dice")

seguridad.sellar_codigo = sellar_original
acceso.bloquear()
shutil.rmtree(TEMPORAL, ignore_errors=True)
print()
print("RESULTADO:", "OK" if not fallos else f"FALLO ({len(fallos)})")
if fallos:
    raise SystemExit(1)
