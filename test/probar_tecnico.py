"""MILLER · Prueba de batería, ecualizador, ventanas (cerrar / minimizar), archivos, hora 12 h, contexto y seguridad."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
from utilidades import acceso as _acceso   # estas pruebas usan funciones de pago: modo PRO
_acceso._puestas.add("pro")
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from utilidades import seguridad
fallos = []


def comprobar(condicion, mensaje):
    print(("  OK    " if condicion else "  FALLO ") + mensaje)
    if not condicion:
        fallos.append(mensaje)


base = Path(tempfile.mkdtemp())
seguridad.DIR_SEGURIDAD = base / "seguridad"
seguridad._clave = None

print("1. Batería")
from utilidades import bateria
comprobar("Batería al 76 %, cargando" in bateria.describir({"hay_bateria": True, "porcentaje": 76, "cargando": True,
                                                              "enchufado": True, "minutos": None}), "describe la carga")
comprobar("Quedan unas 2 h 05 min" in bateria.describir({"hay_bateria": True, "porcentaje": 60, "cargando": False,
                                                           "enchufado": False, "minutos": 125}), "dice el tiempo que queda")
comprobar("cargador" in bateria.describir({"hay_bateria": True, "porcentaje": 9, "enchufado": False}), "avisa si queda poca")
comprobar("no tiene batería" in bateria.describir({"hay_bateria": False}), "equipos de escritorio sin batería")
comprobar(isinstance(bateria.describir(), str), "lee la batería real sin fallar")

print("2. Hora de 1 a 12 con a. m. / p. m.")
from utilidades.reloj import frase_hora, hora_12, hora_12_de
casos = {(0, 5): "Son las 12:05 a. m.", (1, 20): "Es la 1:20 a. m.", (12, 0): "Son las 12:00 p. m.",
         (13, 30): "Es la 1:30 p. m.", (15, 5): "Son las 3:05 p. m.", (23, 59): "Son las 11:59 p. m."}
comprobar(all(frase_hora(datetime(2026, 1, 1, h, m)) == e for (h, m), e in casos.items()), "nunca dice 13 a 23 ni 00")
comprobar(hora_12_de(20) == "8 p. m." and hora_12_de(0) == "12 a. m.", "horas de actividad en formato 12 h")
from utilidades import alarmas
_, desc = alarmas.interpretar_momento("pon una alarma a las 9 y 20")
comprobar(":" in desc and ("a. m." in desc or "p. m." in desc), f"las alarmas también: «{desc}»")

print("3. Ventanas: cerrar, minimizar y proteger el sistema")
from utilidades import ventanas as vt
comprobar(vt.limpiar_nombre("el navegador brave") == "brave", "«cerrar el navegador brave» -> brave")
comprobar(vt.limpiar_nombre("la ventana de spotify") == "spotify", "«la ventana de spotify» -> spotify")
comprobar(vt.limpiar_nombre("el navegador") == "navegador", "«el navegador» -> todos los navegadores")
falsas = [{"hwnd": 1, "titulo": "YouTube - Brave", "exe": "brave", "pid": 10, "clase": "Chrome_WidgetWin_1"},
          {"hwnd": 2, "titulo": "Nueva pestaña - Brave", "exe": "brave", "pid": 10, "clase": "Chrome_WidgetWin_1"},
          {"hwnd": 3, "titulo": "informe.pdf - Adobe Acrobat", "exe": "acrobat", "pid": 11, "clase": "AcrobatSDIWindow"},
          {"hwnd": 4, "titulo": "Descargas", "exe": "explorer", "pid": 12, "clase": "CabinetWClass"},
          {"hwnd": 5, "titulo": "Program Manager", "exe": "explorer", "pid": 12, "clase": "Progman"},
          {"hwnd": 6, "titulo": "Spotify Premium", "exe": "spotify", "pid": 13, "clase": "Chrome_WidgetWin_0"},
          {"hwnd": 7, "titulo": "Google Chrome", "exe": "chrome", "pid": 14, "clase": "Chrome_WidgetWin_1"}]
comprobar([v["hwnd"] for v in vt.buscar("brave", falsas)] == [1, 2], "encuentra TODAS las ventanas de Brave")
comprobar({v["hwnd"] for v in vt.buscar("navegador", falsas)} == {1, 2, 7}, "«el navegador» = todos los navegadores abiertos")
comprobar([v["hwnd"] for v in vt.buscar("informe.pdf", falsas)] == [3], "un archivo abierto se encuentra por su título")
comprobar([v["hwnd"] for v in vt.buscar("spotify", falsas)] == [6], "programa por su ejecutable")
seguras = vt._seguras(vt.buscar("explorador", falsas))
comprobar([v["hwnd"] for v in seguras] == [4], "del Explorador solo toca carpetas, nunca el escritorio")
comprobar("explorer" in vt.PROTEGIDOS and "csrss" in vt.PROTEGIDOS, "procesos del sistema protegidos")
comprobar(isinstance(vt.ventanas(), list), "lista las ventanas reales sin fallar")

print("4. Órdenes")
from cerebro.cerebro import Cerebro
cer = Cerebro.__new__(Cerebro)
ordenes = {"miller bateria": "BATERIA", "nivel de la bateria": "BATERIA",
           "minimiza brave": "VENTANA", "minimiza la ventana": "VENTANA", "minimiza todo": "VENTANA",
           "minimizate": "VENTANA", "maximiza spotify": "VENTANA", "restaura la ventana de brave": "VENTANA",
           "abre el archivo informe.pdf": "ABRIR_ARCHIVO", "abre informe punto pdf": "ABRIR_ARCHIVO",
           "cierra el documento informe.docx": "CERRAR_ARCHIVO", "cierra informe.pdf": "CERRAR_ARCHIVO",
           "abre netflix.com": None, "sube los graves": "ECUALIZADOR_AJUSTE", "pon el ecualizador en rock": "ECUALIZADOR",
           "cierra el navegador brave": None, "restaura despacito": None}
mal = [(o, cer.detectar_intencion_tecnica(o), e) for o, e in ordenes.items() if cer.detectar_intencion_tecnica(o) != e]
comprobar(not mal, "reconoce ventanas, archivos, batería y ecualizador" + (f" (fallan: {mal})" if mal else ""))
comprobar(cer.es_orden_cerrar_aplicacion("cierra el navegador brave"), "«cierra el navegador brave» = cerrar programa")
comprobar(not hasattr(cer, "detectar_valoracion") or Cerebro.detectar_valoracion(cer, "pon musica") is None, "sin falsos elogios")
comprobar(not (RAIZ / "utilidades" / "programacion.py").exists() and not (RAIZ / "conocimiento").exists(),
          "el aprendizaje de programación y el análisis de código ya no están")

print("5. Abrir archivos con seguridad")
import cerebro.comandos as cm
falso = cm.Comandos.__new__(cm.Comandos)
falso.ultimo_objetivo = None
exe = base / "virus.exe"
exe.write_bytes(b"MZ")
original = cm.navegacion.buscar_archivo
cm.navegacion.buscar_archivo = lambda nombre, maximo=3: [exe]
respuesta = cm.Comandos.abrir_archivo(falso, "abre el archivo virus.exe")
cm.navegacion.buscar_archivo = original
comprobar("seguridad" in respuesta, f"nunca ejecuta programas o scripts como «archivo»: {respuesta}")

print("6. Contexto")
from cerebro.contexto_ordenes import ContextoOrdenes
ctx = ContextoOrdenes()
ctx.registrar("ABRIR_APLICACION", "abre brave", objetivo="brave")
comprobar(ctx.resolver("cierralo") == "cierra brave", "«ciérralo» = el último programa abierto")
comprobar(ctx.resolver("minimizalo") == "minimiza brave", "«minimízalo»")
ctx.registrar("ABRIR_ARCHIVO", "abre el archivo informe.pdf", objetivo="informe.pdf")
comprobar(ctx.resolver("cierralo") == "cierra informe.pdf", "«ciérralo» = el último archivo abierto")
ctx.registrar("SUBIR_VOLUMEN", "sube el volumen")
comprobar(ctx.resolver("un poco mas") == "sube el volumen" and ctx.resolver("menos") == "baja el volumen", "«más» / «menos»")
ctx.registrar("ECUALIZADOR_AJUSTE", "sube los graves")
comprobar(ctx.resolver("y los agudos") == "sube los agudos", "«y los agudos»")
ctx.registrar("BUSCAR_NAVEGADOR", "busca netflix en el navegador")
comprobar(ctx.resolver("y en brave") == "busca netflix en brave", "«y en brave»")
comprobar(ctx.resolver("otra vez") == "busca netflix en el navegador", "«otra vez»")
ctx.registrar("CERRAR_APLICACION", "cierra brave")
comprobar(ctx.resolver("otra vez") is None, "no repite cierres ni borrados")

print("7. Ecualizador inteligente")
from utilidades.ecualizador import Ecualizador
ffmpeg = shutil.which("ffmpeg") or next((str(p) for p in [RAIZ / "modelos" / "ffmpeg-master-gpl" / "bin" / "ffmpeg.exe"] if p.is_file()), None)
eq = Ecualizador(base / "ecualizador.json", base / "cache_eq", ffmpeg=ffmpeg)
comprobar(eq.filtro({"graves": 0, "medios": 0, "agudos": 0}) == "", "plano: sin filtro")
f = eq.filtro({"graves": 4, "medios": 0, "agudos": -2})
comprobar("bass=g=4" in f and "treble=g=-2" in f and "alimiter" in f, "graves arriba, agudos abajo y sin saturar")
eq.poner_perfil("rock")
cancion = base / "Artista - Tema.mp3"
comprobar(eq.ganancias(cancion) == {"graves": 4.0, "medios": -1.0, "agudos": 3.0}, "perfil rock")
eq.ajustar("bajos", +1, cancion)
comprobar(eq.ganancias(cancion)["graves"] == 6.0, "«sube los bajos» lo aprende para el artista")
if ffmpeg:
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=80:duration=70",
                    str(cancion)], check=True)
    eq.poner_automatico()
    listo = []
    eq.al_listo = lambda o, d: listo.append(d)
    eq.preparar(cancion)
    for _ in range(120):
        if listo:
            break
        time.sleep(0.5)
    comprobar(listo and listo[0].is_file(), "prepara la copia ecualizada en segundo plano")

print("8. Seguridad del propio código y registros")
raiz_falsa = base / "programa"
(raiz_falsa / "cerebro").mkdir(parents=True)
(raiz_falsa / "cerebro" / "a.py").write_text("x = 1\n", encoding="utf-8")
comprobar(seguridad.integridad_codigo(raiz_falsa) is None, "la primera vez sella el código")
comprobar(seguridad.integridad_codigo(raiz_falsa) == [], "sin cambios: intacto")
(raiz_falsa / "cerebro" / "a.py").write_text("x = 2  # cambiado\n", encoding="utf-8")
comprobar(seguridad.integridad_codigo(raiz_falsa) == ["cerebro/a.py"], "detecta un archivo de código cambiado")
seguridad.sellar_codigo(raiz_falsa)
comprobar(seguridad.integridad_codigo(raiz_falsa) == [], "«sella tu código» acepta los cambios")
log = base / "x.log"
for _ in range(300):
    seguridad.anexar_log(log, "x" * 100, maximo=10_000)
comprobar(log.stat().st_size <= 10_200 and log.with_suffix(".log.1").exists(), "los registros nunca crecen sin límite")
seguridad.escribir_json(base / "c.json", {"a": [1, 2], "b": {"c": 3}})
comprobar("\n" not in (base / "c.json").read_text(encoding="utf-8"), "los datos se guardan compactos")

print("\nRESULTADO:", "TODO CORRECTO" if not fallos else f"{len(fallos)} FALLO(S)")
shutil.rmtree(base, ignore_errors=True)
_sys.exit(1 if fallos else 0)
