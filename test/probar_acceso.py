"""MILLER · Prueba de llaves, modos, cuotas y espacio en disco. Trabaja en una carpeta temporal: no toca los datos reales."""
import sys as _sys
import os
import shutil
import tempfile
import time
from pathlib import Path as _Path

RAIZ = _Path(__file__).resolve().parent.parent
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
TEMPORAL = _Path(tempfile.mkdtemp(prefix="miller_acceso_"))
(TEMPORAL / "seguridad").mkdir()
os.environ["MILLER_DIR_SEGURIDAD"] = str(TEMPORAL / "seguridad")
fallos = []


def comprobar(condicion, mensaje):
    print(("  OK    " if condicion else "  FALLO ") + mensaje)
    if not condicion:
        fallos.append(mensaje)


import configuracion
import importlib
from utilidades import acceso, cuota

MB = 1024 * 1024
GB = 1024 * MB
import ayuda_llave_boy as ayuda_boy  # noqa: E402
import ayuda_llave_pro as ayuda_pro  # noqa: E402
from utilidades import llave_boy  # noqa: E402
llave_boy.RUTA = TEMPORAL / "llave_boy.json"
acceso.RUTA = TEMPORAL / "acceso.json"
base = TEMPORAL / "miller"
for carpeta in ("audios", "cerebro", "modelos", "dist"):
    (base / carpeta).mkdir(parents=True)
configuracion.RUTA_BASE = base
libre_original = cuota._libre


def reiniciar_intentos():
    datos = acceso._cargar()
    datos["fallos"], datos["bloqueado_hasta"] = 0, 0
    acceso._guardar(datos)


print("1. Llaves: PRO de prueba y guardado")
claros = {"pro": ayuda_pro.preparar()}        # llave PRO de prueba (la real no va en el repositorio)
claros["boy"] = ayuda_boy.preparar()          # llave BOY de prueba (huella y fragmentos)
comprobar(acceso.poner("pro", "PRO-AAAA-BBBB-CCCC").startswith("Negativo"),
          "una PRO que no es la de la huella se rechaza")
comprobar(claros["boy"].startswith("BOY-") and len(claros["boy"].replace("-", "")) == 15,
          "la llave BOY de prueba tiene el formato BOY-XXXX-XXXX-XXXX")
comprobar(len(claros["pro"].replace("-", "")) == 15, "la llave PRO de prueba tiene 12 caracteres tras el prefijo")
texto_fichero = acceso.RUTA.read_text(encoding="utf-8")
comprobar(claros["boy"].replace("-", "") not in texto_fichero and claros["pro"].replace("-", "") not in texto_fichero,
          "el fichero de acceso no contiene las llaves en claro")

print("2. Arranque en FREE y control por modo")
comprobar(acceso.modo() == "free", "arranca en FREE sin llaves puestas")
comprobar(acceso.activas() == frozenset(), "ninguna llave puesta al arrancar")
comprobar(acceso.bloqueo("ECUALIZADOR") is None, "el ecualizador es FREE")
comprobar(acceso.bloqueo("ALARMA") is None and acceso.bloqueo("CALCULAR") is None
          and acceso.bloqueo("EMOCION") is None, "alarma, cálculo y emoción son FREE")
comprobar(acceso.bloqueo("ENSENAR_SINONIMO") is not None, "enseñar sinónimos pide NIÑOS")
comprobar(acceso.bloqueo("DESCARGAR_MUSICA") is not None, "descargar música pide PRO")
comprobar(acceso.bloqueo("BLOQUEAR_ACCESO") is None and acceso.bloqueo("LLAVE_VOZ") is None
          and acceso.bloqueo("ESTADO_ACCESO") is None, "las órdenes de acceso están siempre permitidas")
comprobar(acceso.bloqueo("INTENCION_NO_CATALOGADA") is None, "lo no catalogado es FREE")

print("3. Poner y retirar llaves")
acceso.poner("boy", claros["boy"])
comprobar(acceso.modo() == "boy" and acceso.activas() == {"boy"}, "con la llave BOY el modo es NIÑOS")
comprobar("NIÑOS" in acceso.ultimo_aviso(), "el aviso dice que el modo NIÑOS está activo")
comprobar(acceso.bloqueo("ENSENAR_SINONIMO") is None, "con BOY se desbloquean las funciones de NIÑOS")
comprobar(acceso.bloqueo("DESCARGAR_MUSICA") is not None, "con BOY no se desbloquea PRO")
acceso.poner("pro", claros["pro"].lower().replace("-", " "))
comprobar(acceso.modo() == "pro" and acceso.activas() == {"boy", "pro"}, "con las dos llaves manda PRO")
comprobar(acceso.bloqueo("DESCARGAR_MUSICA") is None, "con PRO puesta se desbloquea la función PRO")
acceso.quitar("pro")
comprobar(acceso.modo() == "boy", "al retirar PRO vuelve el modo NIÑOS")
acceso.quitar("boy")
comprobar(acceso.modo() == "free", "al retirar BOY vuelve FREE")
comprobar("No hay llave" in acceso.quitar("pro"), "retirar una llave que no está puesta avisa")
acceso.poner("pro", claros["boy"])
comprobar("pro" not in acceso.activas() and "no va en esta casilla" in acceso.ultimo_aviso(),
          "una llave BOY no entra en la casilla PRO")
acceso.poner("boy", "BOY-MAL0-MAL0-MAL0")
comprobar(acceso.activas() == frozenset() and "no válida" in acceso.ultimo_aviso(), "una llave inventada no se acepta")
acceso.poner("boy", "   ")
comprobar(acceso.activas() == frozenset(), "una casilla vacía no pone nada")
acceso.introducir(claros["pro"])
comprobar(acceso.modo() == "pro", "la llave escrita en la terminal también funciona")
acceso.bloquear()
comprobar(acceso.modo() == "free" and acceso.activas() == frozenset(), "bloquear() retira todas las llaves")

print("4. Orden de terminal")
comprobar(acceso.orden_llave("acceso " + claros["boy"]) == claros["boy"], "'acceso <llave>' se reconoce")
comprobar(acceso.orden_llave("Llave pro-ab") == "pro-ab", "'llave' también se reconoce, sin distinguir mayúsculas")
comprobar(acceso.orden_llave("hola miller") is None, "una frase normal no es una llave")
comprobar(acceso.orden_llave("acceso") is None, "'acceso' sin llave no es una orden de llave")

print("5. Intentos fallidos y bloqueo")
reiniciar_intentos()
for _ in range(configuracion.ACCESO_INTENTOS_MAX - 1):
    acceso.poner("pro", "PRO-MAL0-MAL0-MAL0")
comprobar(acceso._cargar()["fallos"] == configuracion.ACCESO_INTENTOS_MAX - 1,
          "los fallos quedan contados en el fichero firmado")
acceso.poner("pro", "PRO-MAL0-MAL0-MAL0")
comprobar(acceso._cargar()["bloqueado_hasta"] > time.time(), "al llegar al tope el acceso se bloquea")
acceso.poner("pro", claros["pro"])
comprobar("pro" not in acceso.activas(), "bloqueado, ni la llave buena entra")
reiniciar_intentos()
acceso.poner("pro", claros["pro"])
comprobar("pro" in acceso.activas(), "pasado el bloqueo, la llave vuelve a funcionar")
acceso.bloquear()

print("6. Voz y estado")
comprobar("no se dicen en voz alta" in acceso.aviso_llave_voz(), "las llaves no se aceptan por voz")
comprobar(acceso.estado_texto().startswith("Modo actual: FREE"), "el estado dice el modo actual")
comprobar("Disco:" in acceso.estado_texto(), "el estado incluye el espacio en disco")

print("7. Cuotas por sección")
(base / "cerebro" / "codigo.py").write_bytes(b"x" * 1000)
(base / "modelos" / "modelo.bin").write_bytes(b"x" * 500)
(base / "dist" / "programa.bin").write_bytes(b"x" * 999999)
(base / "audios" / "cancion.mp3").write_bytes(b"x" * 2000)
u = cuota.uso()
comprobar(u["asistente"] == 1500, "el asistente cuenta código y modelos, sin audios ni dist")
comprobar(u["archivos"] == 2000, "los archivos cuentan solo la carpeta audios")
comprobar(cuota.limites("free") == {"asistente": 1024 * MB, "archivos": 1024 * MB}, "FREE: 1024 MB por sección")
comprobar(cuota.limites("boy") == {"asistente": 2048 * MB, "archivos": 8192 * MB}, "NIÑOS: 2048 y 8192 MB")
cuota._libre = lambda: 10 * GB
l_pro = cuota.limites("pro")
total_pro = u["asistente"] + u["archivos"] + configuracion.CUOTA_PRO_DISCO * 10 * GB
comprobar(abs(l_pro["asistente"] - total_pro * 0.30) < 1 and abs(l_pro["archivos"] - total_pro * 0.70) < 1,
          "PRO reparte su parte del disco libre: 30 % asistente y 70 % archivos")
cuota._libre = lambda: 50 * GB
configuracion.CUOTA_FREE_ARCHIVOS_MB = 1
ok, aviso = cuota.puede_crecer("archivos", 2 * MB)
comprobar(not ok and "está llena" in aviso and "archivos" in aviso, "FREE no deja crecer una sección por encima de su tope")
comprobar(cuota.puede_crecer("archivos", 1000)[0], "FREE sí deja crecer dentro del tope")
configuracion.CUOTA_FREE_ARCHIVOS_MB = 1024
cuota._libre = lambda: 1000 * MB
ok, aviso = cuota.puede_crecer("asistente", 1)
comprobar(not ok and "al límite" in aviso, "se respeta la reserva de disco aunque la cuota tenga sitio")
cuota._libre = libre_original

print("7b. Medición única para la ventana")
espacio_original = cuota.espacio_disco
cuota.espacio_disco = lambda: (50 * GB, 100 * GB)
cuota._libre = lambda: 50 * GB
snap = cuota.instantanea()
cuota.espacio_disco = espacio_original
cuota._libre = libre_original
comprobar(set(snap["limites"]) == {"free", "boy", "pro"} and snap["uso"]["archivos"] == 2000,
          "la medición única trae los topes de cada modo y lo usado")
comprobar(snap["limites"]["pro"]["archivos"] > snap["limites"]["boy"]["archivos"],
          "PRO tiene más espacio que NIÑOS")

print("8. Espacio en disco")
libre, total = cuota.espacio_disco()
comprobar(0 < libre <= total, "se lee el espacio libre y total del disco")
resumen = cuota.resumen()
comprobar("Disco:" in resumen and "GB libres de" in resumen, "el resumen informa del disco libre")
comprobar("Asistente:" in resumen and "archivos:" in resumen, "el resumen mantiene las cuotas de ambas secciones")

def reabrir():
    """Simula cerrar y volver a abrir MILLER. Los ayudantes de prueba cambian la huella PRO en memoria:
    se conserva al recargar el módulo."""
    sal, huella = acceso.SAL_PRO, acceso.HUELLA_PRO
    importlib.reload(acceso)
    acceso.SAL_PRO, acceso.HUELLA_PRO = sal, huella


print("N. Las llaves puestas persisten al reabrir MILLER")
acceso.quitar(None)
acceso.poner(None, claros["boy"])
comprobar(acceso.modo() == "boy", "con la llave BOY puesta el modo es NIÑOS")
reabrir()
comprobar(acceso.activas() == frozenset({"boy"}) and acceso.modo() == "boy", "al reabrir, la llave BOY sigue puesta")
acceso.poner(None, claros["pro"])
reabrir()
comprobar(acceso.activas() == frozenset({"boy", "pro"}) and acceso.modo() == "pro", "al reabrir, las dos llaves siguen puestas")
acceso.quitar("pro")
reabrir()
comprobar(acceso.activas() == frozenset({"boy"}), "una llave retirada no vuelve al reabrir")
acceso.quitar(None)
reabrir()
comprobar(acceso.activas() == frozenset() and acceso.modo() == "free", "sin llaves retiradas, al reabrir sigue FREE")
texto_puestas = (TEMPORAL / "seguridad" / "llaves_puestas.json").read_text(encoding="utf-8")
comprobar(claros["boy"].replace("-", "") not in texto_puestas and claros["pro"].replace("-", "") not in texto_puestas,
          "el fichero de llaves puestas no guarda ninguna llave en claro")

shutil.rmtree(TEMPORAL, ignore_errors=True)
print()
if fallos:
    print(f"FALLARON {len(fallos)} comprobaciones:")
    for f in fallos:
        print("  -", f)
    raise SystemExit(1)
print("Todas las comprobaciones de llaves, modos, cuotas y disco pasaron.")
