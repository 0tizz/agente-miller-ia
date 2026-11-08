"""MILLER · Prueba de la purga: borra recuerdos, aprendizaje y cachés en una carpeta temporal.
No necesita micrófono ni ventana y no toca los datos reales."""
import shutil
import sys as _sys
import tempfile
from pathlib import Path as _Path

RAIZ = _Path(__file__).resolve().parent.parent
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
TEMPORAL = _Path(tempfile.mkdtemp(prefix="miller_purga_"))
fallos = []


def comprobar(condicion, mensaje):
    print(("  OK    " if condicion else "  FALLO ") + mensaje)
    if not condicion:
        fallos.append(mensaje)


def escribir(ruta, contenido=b"x"):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(contenido)


from utilidades import purga  # noqa: E402

base = TEMPORAL / "miller"
datos = base / "datos"
cache = datos / "cache"

# Lo que se conserva, relativo a la carpeta de MILLER.
CONSERVAR = [
    "datos/alarmas.json", "datos/alarmas.json.bak", "datos/ecualizador.json", "datos/ecualizador.json.firma",
    "datos/seguridad/acceso.json", "datos/seguridad/integridad.json", "datos/seguridad/alertas.log",
    "datos/seguridad/clave.bin", "datos/supervisor/supervisor.log",
    "audios/cancion.mp3", "audios/cuarentena/papelera/vieja.mp3", "modelos/voz/modelo.bin",
    "principal.py", "cerebro/cerebro.py", "dist/MILLER/__pycache__/x.pyc",
]

print("1. Preparar una carpeta de MILLER con recuerdos, cachés y cosas que no se tocan")
for nombre in purga.ARCHIVOS_DATOS:
    escribir(datos / nombre)
    escribir(datos / (nombre + ".bak"))
    escribir(datos / (nombre + ".firma"))
escribir(datos / "supervisor" / "estado_supervisor.json")
escribir(datos / "supervisor" / "estado_supervisor.json.bak")
escribir(datos / "supervisor" / "informe_biblioteca.json")
escribir(cache / "ecualizador" / "cancion.mp3")
escribir(base / "cerebro" / "__pycache__" / "cerebro.cpython-313.pyc")
for ruta in CONSERVAR:
    escribir(base / ruta)

print("2. La purga borra recuerdos, aprendizaje y cachés")
borrados, errores = purga.purgar(base)
comprobar(not errores, "no hay errores al borrar")
for nombre in purga.ARCHIVOS_DATOS:
    comprobar(not list(datos.glob(nombre + "*")), f"se borra {nombre} con su copia .bak y su firma")
comprobar(not list((datos / "supervisor").glob("estado_supervisor.json*")), "se borra el estado del supervisor")
comprobar(not list((datos / "supervisor").glob("informe_biblioteca.json*")), "se borra el informe de la biblioteca")
comprobar(cache.is_dir() and not any(cache.iterdir()), "la caché del ecualizador queda vacía (la carpeta sigue)")
comprobar(not (base / "cerebro" / "__pycache__").exists(), "se borra la caché de Python del código")

print("3. Lo que no se toca")
for ruta in CONSERVAR:
    comprobar((base / ruta).exists(), f"se conserva {ruta}")

print("4. La purga solo se hace si se ha pedido")
escribir(datos / "memoria.json")
comprobar(purga.ejecutar_si_pedida(base) is None, "sin petición, al cerrar no se borra nada")
comprobar((datos / "memoria.json").exists(), "la memoria sigue porque nadie pidió la purga")
purga.pedir()
comprobar(purga.pedida(), "al pedirla queda marcada")
resultado = purga.ejecutar_si_pedida(base)
comprobar(resultado is not None and not purga.pedida(), "al cerrar se hace y la marca se apaga")
comprobar(not (datos / "memoria.json").exists(), "tras la petición, la memoria desaparece")
comprobar((base / "audios" / "cancion.mp3").exists(), "las canciones siguen en su sitio")

shutil.rmtree(TEMPORAL, ignore_errors=True)
print()
if fallos:
    print(f"FALLARON {len(fallos)} comprobaciones:")
    for f in fallos:
        print("  -", f)
    raise SystemExit(1)
print("Todas las comprobaciones de la purga pasaron.")
