"""Prueba no interactiva: niveles de disco, mensajes de cuota y poda de memoria con poco espacio.
Trabaja en carpetas temporales con el disco simulado; nunca toca datos, audios ni la memoria reales."""
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
TEMPORAL = Path(tempfile.mkdtemp(prefix="miller_disco_"))
os.environ["MILLER_DIR_SEGURIDAD"] = str(TEMPORAL / "seguridad")
import configuracion  # noqa: E402
configuracion.RUTA_BASE = TEMPORAL / "miller"
configuracion.RUTA_DATOS = TEMPORAL / "miller" / "datos"
(TEMPORAL / "miller" / "audios").mkdir(parents=True)
from utilidades import cuota, acceso  # noqa: E402
from cerebro.memoria import Memoria  # noqa: E402
from cerebro.conexiones import Conexiones  # noqa: E402

MB, GB = cuota.MB, cuota.GB
TOTAL = 100 * GB
fallos = 0


def comprobar(nombre, condicion, detalle=""):
    global fallos
    if condicion:
        print(f"  OK    {nombre}")
    else:
        fallos += 1
        print(f"  FALLO {nombre} {detalle}")


def disco(libre):
    cuota._libre = lambda: libre
    cuota.espacio_disco = lambda: (libre, TOTAL)


print("0. Precondiciones")
comprobar("modo FREE por defecto en la prueba", acceso.modo() == "free", f"-> {acceso.modo()}")

print("1. Niveles de presión del disco")
for libre, esperado, nombre in [(50 * GB, "normal", "50 % libre"),
                                (3 * GB, "baja", "3 % libre"),
                                (1.5 * GB, "critica", "1,5 % libre (menos del 2 %)"),
                                (int(0.5 * GB), "critica", "0,5 GB libres (bajo la reserva)")]:
    disco(libre)
    comprobar(f"{nombre} -> {esperado}", cuota.presion() == esperado, f"-> {cuota.presion()}")

print("2. Mensajes al crecer")
disco(50 * GB)
ok, aviso = cuota.puede_crecer("archivos", 1 * MB)
comprobar("con disco normal se permite", ok and aviso == "")
configuracion.CUOTA_FREE_ARCHIVOS_MB = 0
ok, aviso = cuota.puede_crecer("archivos", 1 * MB)
comprobar("cuota de archivos llena: se niega y lo dice", not ok and "llena" in aviso and "archivos" in aviso, aviso)
configuracion.CUOTA_FREE_ARCHIVOS_MB = 1024
disco(int(1.2 * GB))
ok, aviso = cuota.puede_crecer("archivos", 50 * MB)
comprobar("disco al límite: se niega y lo dice", not ok and "al límite" in aviso, aviso)
comprobar("aviso de presión crítica con texto", "casi no tiene espacio" in cuota.aviso_presion(cuota.estado_disco()))
disco(50 * GB)
comprobar("sin presión no hay aviso", cuota.aviso_presion(cuota.estado_disco()) == "")

print("3. Escritura de recuerdos con margen mínimo")
cuota._libre = lambda: 10 * MB
comprobar("con 10 MB libres no se guarda", cuota.puede_guardar(4096) is False)
cuota._libre = lambda: 5 * GB
comprobar("con 5 GB libres sí se guarda", cuota.puede_guardar(4096) is True)


AHORA = datetime.now()


def hace(dias):
    return (AHORA - timedelta(days=dias)).isoformat()


def recuerdo(id_, texto, importancia=1.0, frecuencia=0, dias=0):
    return {"id": id_, "contenido": texto, "categoria": "general", "fecha": hace(dias),
            "importancia": importancia, "frecuencia": frecuencia, "ultimo_acceso": hace(dias)}


CASOS = {
    "A": recuerdo(1, "mi cumpleanos es el cinco de marzo en bogota", importancia=1.8, frecuencia=4, dias=200),
    "B": recuerdo(2, "mi cumpleanos es el cinco de marzo en bogota ciudad", dias=200),
    "C": recuerdo(3, "nota suelta sobre un libro de cocina antiguo", dias=200),
    "D": recuerdo(4, "el informe trimestral de ventas quedo listo ayer por la tarde", dias=0),
    "E": recuerdo(5, "el informe trimestral de ventas quedo listo ayer por la tarde temprano", dias=0),
    "F": recuerdo(6, "la clave del proyecto miller se guarda en la carpeta segura", dias=0),
}


def memoria_nueva(nombre):
    m = Memoria(TEMPORAL / f"memoria_{nombre}.json")
    m.memoria = [dict(r) for r in CASOS.values()]
    return m


def textos(m):
    return {r["contenido"] for r in m.memoria}


print("4. Clasificación y poda con disco normal")
m = memoria_nueva("normal")
comprobar("A se clasifica como importante", m.valor_recuerdo(CASOS["A"], AHORA) == "importante")
comprobar("C se clasifica como débil", m.valor_recuerdo(CASOS["C"], AHORA) == "debil")
comprobar("similitud A-B ≥ 0.9 (precondición)", m.calcular_similitud(CASOS["A"]["contenido"], CASOS["B"]["contenido"]) >= 0.9)
disco(50 * GB)
resumen = m.plan_de_olvido(AHORA)
quedan = textos(m)
comprobar("disco normal: el débil viejo C se archiva", CASOS["C"]["contenido"] not in quedan)
comprobar("disco normal: lo importante A nunca se olvida por el tiempo", CASOS["A"]["contenido"] in quedan)
comprobar("disco normal: B (débil, viejo) también se archiva", CASOS["B"]["contenido"] not in quedan)
comprobar("el resumen dice presión normal", resumen.get("presion") == "normal", str(resumen.get("presion")))

print("5. Poda con poco espacio: solo lo casi idéntico")
m = memoria_nueva("critica")
pares = Conexiones(m).pares()
comprobar("la red de conexiones propone el par del informe",
          any({a["contenido"], b["contenido"]} == {CASOS["D"]["contenido"], CASOS["E"]["contenido"]} for a, b in pares))
cuota.presion = lambda: "critica"
disco(1.5 * GB)
resumen = m.plan_de_olvido(AHORA)
quedan = textos(m)
comprobar("con poco espacio: C (débil único) se conserva", CASOS["C"]["contenido"] in quedan)
comprobar("con poco espacio: A (importante) se conserva", CASOS["A"]["contenido"] in quedan)
comprobar("con poco espacio: B, casi idéntico a A, se olvida", CASOS["B"]["contenido"] not in quedan)
comprobar("con poco espacio: de D y E queda uno solo",
          (CASOS["D"]["contenido"] in quedan) != (CASOS["E"]["contenido"] in quedan))
comprobar("con poco espacio: F se conserva", CASOS["F"]["contenido"] in quedan)
comprobar("olvidado no se borra: queda archivado y se puede recuperar",
          any(r.get("contenido") == CASOS["B"]["contenido"] for r in m.aprendizaje["olvidados"]))
comprobar("el resumen dice presión crítica", resumen.get("presion") == "critica", str(resumen.get("presion")))

print("6. Recuerdo nuevo rechazado sin margen en el disco")
m = memoria_nueva("sin_margen")
antes = len(m.memoria)
cuota.puede_guardar = lambda *a, **k: False
guardado = m.guardar_recuerdo("un dato nuevo que no debería entrar sin margen")
comprobar("no se guarda y lo indica", guardado is False and m.ultimo_error == "disco" and len(m.memoria) == antes)

print()
print("Todas las comprobaciones de disco y memoria pasaron." if not fallos else f"{fallos} comprobación(es) fallaron.")
raise SystemExit(1 if fallos else 0)
