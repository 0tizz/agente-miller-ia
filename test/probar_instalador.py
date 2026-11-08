"""MILLER · Prueba de la instalación inicial: estado de componentes y descarga segura de modelos (sin internet)."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
import shutil
import tempfile
import zipfile
from pathlib import Path
from utilidades import instalador, seguridad
fallos = []


def comprobar(condicion, mensaje):
    print(("  OK    " if condicion else "  FALLO ") + mensaje)
    if not condicion:
        fallos.append(mensaje)


base = Path(tempfile.mkdtemp())
seguridad.DIR_SEGURIDAD = base / "seguridad"
seguridad._clave = None
print("1. Estado de los componentes")
filas = instalador.estado()
comprobar(len(filas) >= 8, f"{len(filas)} componentes revisados")
for _, nombre, listo, tipo in filas:
    print(f"        {'✓' if listo else '✗'} {nombre} [{tipo}]")
print("2. Descarga de un modelo (simulada, en carpeta temporal)")
zip_bueno = base / "vosk.zip"
with zipfile.ZipFile(zip_bueno, "w") as z:
    z.writestr("vosk-model-small-es-0.42/am/final.mdl", "modelo")
destino = base / "modelos" / "voz" / "vosk-model-small-es-0.42"
original = dict(instalador.MODELOS["vosk"])
instalador.MODELOS["vosk"].update(destino=destino, prueba=lambda: (destino / "am" / "final.mdl").is_file())
instalador._descargar = lambda url, archivo, avisar: shutil.copy(zip_bueno, archivo)
mensajes = []
comprobar(instalador.descargar_modelo("vosk", mensajes.append), "modelo descargado, descomprimido y colocado")
comprobar((destino / "am" / "final.mdl").is_file(), "queda en modelos/voz/")
print("3. Seguridad")
zip_malo = base / "malo.zip"
with zipfile.ZipFile(zip_malo, "w") as z:
    z.writestr("../../fuera.txt", "ataque")
shutil.rmtree(destino)
instalador._descargar = lambda url, archivo, avisar: shutil.copy(zip_malo, archivo)
mensajes.clear()
comprobar(not instalador.descargar_modelo("vosk", mensajes.append), "rechaza un comprimido con rutas fuera de la carpeta")
comprobar(not (base / "fuera.txt").exists() and not (base.parent / "fuera.txt").exists(), "no escribe fuera")
instalador.MODELOS["vosk"]["url"] = "https://sitio-malicioso.com/modelo.zip"
mensajes.clear()
comprobar(not instalador.descargar_modelo("vosk", mensajes.append) and "bloqueada" in " ".join(mensajes),
          "solo descarga de los sitios permitidos")
instalador.MODELOS["vosk"].update(original)
print()
print("RESULTADO:", "OK" if not fallos else f"FALLO ({len(fallos)})")
if fallos:
    raise SystemExit(1)
