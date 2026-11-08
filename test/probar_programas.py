"""MILLER · test.probar_programas: PRUEBA DEL CATÁLOGO DE PROGRAMAS Comprueba que MILLER encuentra programas por su nombre hablado."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent      # carpeta raíz de MILLER
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
import os
import tempfile
from utilidades.sistema import CatalogoAplicaciones, _norma
fallos = []

def comprobar(condicion, mensaje):
    print(("  OK    " if condicion else "  FALLO ") + mensaje)
    if not condicion:
        fallos.append(mensaje)
print("=" * 60)
print("PRUEBA DEL CATÁLOGO DE PROGRAMAS")
print("=" * 60)
cat = CatalogoAplicaciones(ruta_cache=_Path(tempfile.gettempdir()) / "miller_test_programas.json")
simulados = [("Calculadora", "Microsoft.WindowsCalculator!App", "appid"), ("Word", r"C:\x\Word.lnk", "acceso"),
             ("Google Chrome", r"C:\x\Google Chrome.lnk", "acceso"), ("Spotify", "SpotifyAB.Spotify!Spotify", "appid"),
             ("Visual Studio Code", r"C:\x\Code.lnk", "acceso"), ("Desinstalar Spotify", r"C:\x\u.lnk", "acceso"),
             ("Steam", r"C:\x\Steam.lnk", "acceso"), ("WhatsApp", "5319275A.WhatsAppDesktop!App", "appid")]
cat.entradas = [{"nombre": n, "clave": _norma(n), "objetivo": o, "tipo": t} for n, o, t in simulados]
casos = {"calculadora": "Calculadora", "word": "Word", "chrome": "Google Chrome", "google chrome": "Google Chrome",
         "spotify": "Spotify", "vs code": "Visual Studio Code", "steam": "Steam", "whatsapp": "WhatsApp",
         "wasap": "WhatsApp", "programa inventado xyz": None}
for dicho, esperado in casos.items():
    e = cat.buscar(dicho)
    obtenido = e["nombre"] if e and e["tipo"] != "comando" else None
    comprobar(obtenido == esperado, f"{dicho!r} -> {obtenido}")
e = CatalogoAplicaciones(ruta_cache=_Path(tempfile.gettempdir()) / "vacio.json")
e.entradas = []
r = e.buscar("bloc de notas")
comprobar(r is not None and r["objetivo"] == "notepad.exe", "sin índice usa los programas básicos de Windows")
if os.name == "nt":
    n = cat.indexar()
    print(f"\nPrograma(s) encontrados en este equipo: {n}")
    comprobar(n > 0, "el equipo tiene programas indexados")
    comprobar(cat.buscar("bloc de notas") is not None, "encuentra el Bloc de notas real")
print()
print("=" * 60)
if fallos:
    print(f"PRUEBA FALLIDA: {len(fallos)} comprobaciones fallaron")
    raise SystemExit(1)
print("PRUEBA SUPERADA: el catálogo de programas funciona correctamente")
