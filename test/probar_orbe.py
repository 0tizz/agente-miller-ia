"""Prueba no interactiva: lo que aprende el orbe (sin ventana). Usa una carpeta temporal."""
import os
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
TEMPORAL = Path(tempfile.mkdtemp(prefix="miller_orbe_"))
os.environ["MILLER_DIR_SEGURIDAD"] = str(TEMPORAL / "seguridad")
from utilidades import orbe_entorno as oe  # noqa: E402

fallos = 0


def comprobar(nombre, condicion, detalle=""):
    global fallos
    if condicion:
        print(f"  OK    {nombre}")
    else:
        fallos += 1
        print(f"  FALLO {nombre} {detalle}")


ruta = TEMPORAL / "orbe.json"
print("1. Percepción")
o = oe.EntornoOrbe(ruta)
comprobar("sin datos previos, nada aprendido", o.pagina_favorita() is None and o.hora_habitual() is None)
o.registrar_pagina("terminal")
o.registrar_pagina("terminal")
o.registrar_pagina("explorador")
o.registrar_pagina("inventada")
comprobar("la página favorita es la más abierta", o.pagina_favorita() == "terminal", str(o.paginas))
comprobar("una página desconocida se ignora", "inventada" not in o.paginas)
o.registrar_tiempo(60, True, False, 9)
comprobar("el tiempo activo suma minutos a la hora", abs(o.horas[9] - 1.0) < 1e-9, str(o.horas[9]))
o.registrar_tiempo(30, False, True, 9)
comprobar("con la ventana inactiva no suma a la hora", abs(o.horas[9] - 1.0) < 1e-9)
comprobar("la música suma aparte", abs(o.segundos_musica - 30) < 1e-9)
comprobar("la hora habitual es la de más actividad", o.hora_habitual() == 9)
o.registrar_tiempo(0, True, True, 3)
comprobar("un intervalo de cero no cuenta", o.horas[3] == 0.0)

print("2. Estado percibido")
comprobar("ventana tocada y sin música: atento", o.estado(5, False) == "atento")
comprobar("ventana sin tocar: dormido", o.estado(500, False) == "dormido")
comprobar("con música sonando: contento", o.estado(500, True) == "contento")

print("3. Posición de reposo")
o.registrar_reposo(2.0, -1.0)
comprobar("la posición se limita a la zona", o.reposo == [1.0, 0.0], str(o.reposo))
x, y = o.posicion_de_reposo(480, 340, 34)
comprobar("la posición de reposo cae dentro de la zona", 0 <= x <= 480 - 34 and 0 <= y <= 340 - 34, f"{x},{y}")
comprobar("la posición de reposo se calcula desde la fracción", abs(x - 446) < 1e-9 and abs(y) < 1e-9)
o.registrar_reposo(0.25, 0.75)

print("4. Guardado y lectura")
comprobar("forzar guarda aunque no haya pasado la pausa", o.guardar(forzar=True) is True)
o2 = oe.EntornoOrbe(ruta)
comprobar("las páginas se recuperan", o2.paginas["terminal"] == 2 and o2.paginas["explorador"] == 1)
comprobar("el reposo se recupera", o2.reposo == [0.25, 0.75], str(o2.reposo))
comprobar("las horas se recuperan", abs(o2.horas[9] - 1.0) < 1e-6)
comprobar("el tiempo de música se recupera", abs(o2.segundos_musica - 30) < 1e-6)
ruta.write_text("esto no es json {", encoding="utf-8")
o3 = oe.EntornoOrbe(ruta)
comprobar("un archivo dañado no rompe el orbe", o3.reposo == [0.5, 0.85] and o3.pagina_favorita() is None)

print()
print("Todas las comprobaciones del orbe pasaron." if not fallos else f"{fallos} comprobación(es) fallaron.")
raise SystemExit(1 if fallos else 0)
