"""MILLER · Prueba de órdenes nuevas: varias órdenes juntas, navegador, explorador, cálculo y alarmas."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
import tempfile
from datetime import datetime
from pathlib import Path
try:
    import pygame  # noqa: F401
except ImportError:
    import types
    class _M:
        def __getattr__(self, n):
            return lambda *a, **k: None
    pygame = types.ModuleType("pygame"); pygame.mixer = _M(); pygame.mixer.music = _M(); pygame.init = lambda *a, **k: None
    _sys.modules["pygame"] = pygame
from cerebro.cerebro import Cerebro
from utilidades import navegacion
from utilidades.alarmas import GestorAlarmas, interpretar_momento
from utilidades.calculadora import calcular
fallos = []


def comprobar(condicion, mensaje):
    print(("  OK    " if condicion else "  FALLO ") + mensaje)
    if not condicion:
        fallos.append(mensaje)


c = object.__new__(Cerebro)
print("1. Reconoce las órdenes")
for frase, esperada in (("busca netflix en el navegador", "BUSCAR_NAVEGADOR"),
                        ("miller abre netflix en el navegador brave", "ABRIR_SITIO_WEB"),
                        ("abre netflix en google chrome", "ABRIR_SITIO_WEB"),
                        ("busca recetas en youtube", "BUSCAR_NAVEGADOR"),
                        ("busca en el explorador archivoprueba.txt", "BUSCAR_ARCHIVO"),
                        ("busca el archivo informe punto pdf", "BUSCAR_ARCHIVO"),
                        ("suma cinco mas tres", "CALCULAR"), ("cuanto es doce por cuatro", "CALCULAR"),
                        ("divide diez entre dos", "CALCULAR"), ("pon alarma a las nueve y veinte", "ALARMA"),
                        ("pon alarma en media hora", "ALARMA"), ("que alarmas tengo", "ALARMA"),
                        ("sube el volumen", "SUBIR_VOLUMEN"), ("pon mas volumen", "SUBIR_VOLUMEN")):
    obtenida = c.detectar_intencion(frase)
    comprobar(obtenida == esperada, f"'{frase}' -> {obtenida}")
print("2. Varias órdenes en una frase")
for frase, n in (("busca netflix en el navegador y luego sube el volumen", 2),
                 ("pon alarma en media hora y sube el volumen", 2),
                 ("suma 2 y 3", 1), ("pon alarma a las 9 y 20", 1), ("pon rock y blues", 1)):
    partes = c.dividir_ordenes(frase)
    comprobar(len(partes) == n, f"'{frase}' -> {partes}")
print("3. Cálculo")
for frase, esperado in (("suma cinco mas tres", "8"), ("cuanto es 10 entre 4", "2,5"), ("raiz cuadrada de 81", "9"),
                        ("cuanto es el 20 por ciento de 150", "30"), ("divide 7 entre 0", "cero")):
    r = calcular(frase)
    comprobar(esperado in r, f"'{frase}' -> {r}")
print("4. Alarmas")
ahora = datetime(2026, 11, 7, 9, 16)
for frase, hora in (("pon alarma a las 9 y 20", "09:20"), ("pon alarma en media hora", "09:46"),
                    ("pon alarma en una hora y treinta y seis minutos", "10:52"), ("pon alarma a las 7 de la manana", "07:00")):
    r = interpretar_momento(frase, ahora)
    comprobar(r and r[0].strftime("%H:%M") == hora, f"'{frase}' -> {r and r[0].strftime('%H:%M')}")
g = GestorAlarmas(None)
g.crear("pon alarma en 1 segundo")
import time
time.sleep(0.1)
g._alarmas[0]["cuando"] = datetime.now()
g.iniciar()
time.sleep(1.6)
comprobar(g.hay_vencidas() and "Alarma, señor" in g.anunciar(g.tomar_vencidas()[0]), "la alarma vence y se anuncia")
g.detener()
print("5. Explorador")
carpeta = Path(tempfile.mkdtemp())
(carpeta / "sub" / "otra").mkdir(parents=True)
(carpeta / "sub" / "otra" / "ArchivoPrueba.txt").write_text("x")
encontrados = navegacion.buscar_archivo("archivoprueba.txt", raices=[carpeta])
comprobar(encontrados and encontrados[0].name == "ArchivoPrueba.txt", f"encuentra el archivo en subcarpetas: {encontrados}")
comprobar(navegacion.buscar_archivo("archivoprueba punto txt", raices=[carpeta]), "entiende 'punto txt' dicho por voz")
comprobar(navegacion.detectar_navegador("abre netflix en el navegador brave") == "brave", "detecta Brave")
comprobar(navegacion.quitar_navegador("netflix en el navegador brave") == "netflix", "limpia el destino")
print()
print("RESULTADO:", "OK" if not fallos else f"FALLO ({len(fallos)})")
if fallos:
    raise SystemExit(1)
