"""Prueba no interactiva: conexiones entre recuerdos (red de palabras compartidas) y su intención.
Trabaja en una carpeta temporal; nunca toca datos ni audios reales."""
import os
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

TEMPORAL = Path(tempfile.mkdtemp(prefix="miller_conexiones_"))
os.environ["MILLER_DIR_SEGURIDAD"] = str(TEMPORAL / "seguridad")
import configuracion  # noqa: E402
configuracion.RUTA_DATOS = TEMPORAL / "datos"
configuracion.RUTA_BASE = TEMPORAL / "miller"
from cerebro.conexiones import Conexiones  # noqa: E402
from cerebro.memoria import Memoria  # noqa: E402

fallos = 0


def comprobar(nombre, condicion, detalle=""):
    global fallos
    if condicion:
        print(f"  OK    {nombre}")
    else:
        fallos += 1
        print(f"  FALLO {nombre} {detalle}")


print("1. Red de conexiones")
memoria = Memoria(TEMPORAL / "memoria.json")
red = Conexiones(memoria)
comprobar("sin recuerdos no hay conexiones", red.cantidad() == 0 and "Todavía" in red.resumen())
memoria.guardar_recuerdo("el gato negro duerme en el sofá de la sala", "general")
memoria.guardar_recuerdo("el gato negro come pescado cada noche", "general")
memoria.guardar_recuerdo("pescado fresco para el gato negro del vecino", "general")
memoria.guardar_recuerdo("la lluvia cayó sobre la ciudad todo el día", "general")
comprobar("los recuerdos que comparten palabras se conectan", red.cantidad() >= 3, str(red.cantidad()))
comprobar("un recuerdo sin nada en común no se conecta", red.recuerdos_conectados() == 3 and red.cantidad() == 3,
          str(red.recuerdos_conectados()))
asociados = red.asociados("gato negro pescado")
comprobar("'gato negro pescado' encuentra los recuerdos del gato", len(asociados) >= 2
          and all("gato" in a for a in asociados), str(asociados))
comprobar("un tema ajeno no encuentra nada", red.asociados("volcán islandia") == [])
comprobar("el resumen cuenta conexiones", "conexiones" in red.resumen() and "4 recuerdos" in red.resumen() or
          "entre mis 4" in red.resumen(), red.resumen())
print("2. Intención «conexiones» en Cerebro")
from cerebro.cerebro import Cerebro  # noqa: E402
c = Cerebro.__new__(Cerebro)
c.memoria = memoria
comprobar("'conexiones' se detecta como CONEXIONES", c.detectar_intencion("miller conexiones") == "CONEXIONES")
comprobar("'que se relaciona con gato' se detecta", c.detectar_intencion("que se relaciona con gato") == "CONEXIONES")
comprobar("'conexiones de gato' responde con los recuerdos",
          "gato" in c.describir_conexiones("conexiones de gato"))
comprobar("'conexiones' a secas da el resumen", "conexiones" in c.describir_conexiones("conexiones")
          or "Todavía" in c.describir_conexiones("conexiones"))
print("3. Iniciativa: aviso de conexiones nuevas")
from cerebro.iniciativa import Iniciativa  # noqa: E402
ini = Iniciativa.__new__(Iniciativa)
ini.cerebro = c
c.__dict__["_red_conexiones"] = red
ini._estado = {}
ini.agregados = []
ini.agregar = lambda clave, texto, prioridad=2, una_vez=True, tono=None: ini.agregados.append((clave, texto))
ini._observar_conexiones(True)
comprobar("la primera vez solo fija la base", ini._estado.get("conexiones") == red.cantidad() and not ini.agregados)
for texto in ["el río pasa por la granja de mi abuelo", "mi abuelo tenía una granja con vacas lecheras",
              "las vacas de la granja dan leche fresca cada mañana", "la granja del abuelo vende leche y queso"]:
    memoria.guardar_recuerdo(texto, "general")
ini._observar_conexiones(False)
comprobar("tres conexiones nuevas o más se cuentan", len(ini.agregados) == 1 and "conexiones nuevas" in ini.agregados[0][1],
          str(ini.agregados))

print()
print("Todas las comprobaciones de las conexiones pasaron." if not fallos else f"{fallos} comprobación(es) fallaron.")
raise SystemExit(1 if fallos else 0)
