"""Prueba de la barra del reproductor: formato de tiempos, progreso, título, controles y duración con ffmpeg.
No necesita Tkinter ni audio: los controles se comprueban con objetos falsos. Termina en OK o con FALLO."""
import shutil
import subprocess
import sys as _sys
import tempfile
import time
from pathlib import Path as _Path

RAIZ = _Path(__file__).resolve().parent.parent
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))

from utilidades import duracion as d  # noqa: E402
from interfaz import barra_reproductor as b  # noqa: E402

fallos = 0


def comprobar(nombre, condicion):
    global fallos
    if condicion:
        print(f"OK     {nombre}")
    else:
        fallos += 1
        print(f"FALLO  {nombre}")


class Falso:
    def __init__(self, **atributos):
        self.__dict__.update(atributos)


class ComandosFalsos:
    """Hace de comandos.ejecutar: guarda cada orden y responde como lo haría MILLER."""
    def __init__(self, lanza=False):
        self.llamadas, self.lanza = [], lanza

    def ejecutar(self, intencion, texto=""):
        self.llamadas.append((intencion, texto))
        if self.lanza:
            raise RuntimeError("fallo de prueba")
        return f"hecho {intencion}"


def reproductor_falso(**extra):
    base = dict(cancion_actual=None, pausado=False, volumen=0.6, modo_aleatorio=False)
    base.update(extra)
    return Falso(**base)


def barra_de_prueba(reproductor, comandos, informar=None):
    barra = b.BarraReproductor.__new__(b.BarraReproductor)     # sin ventana: solo la lógica de los controles
    barra.reproductor, barra.comandos, barra.informar = reproductor, comandos, informar
    return barra


# ---------------------------------------------------------------- formato, progreso y título
comprobar("duración leída de la salida de ffmpeg",
          abs(d.analizar_salida("  Duration: 00:03:45.12, start: 0.0") - 225.12) < 0.01)
comprobar("sin línea de duración no hay dato", d.analizar_salida("nada que ver") is None)
comprobar("duración N/A no cuenta", d.analizar_salida("Duration: N/A, bitrate: N/A") is None)
comprobar("duración cero no cuenta", d.analizar_salida("Duration: 00:00:00.00") is None)
comprobar("formato m:ss", d.formatear(65) == "1:05")
comprobar("formato h:mm:ss", d.formatear(3725) == "1:02:05")
comprobar("formato cero", d.formatear(0) == "0:00")
comprobar("formato sin dato", d.formatear(None) == "--:--")
comprobar("progreso a la mitad", d.fraccion(10, 20) == 0.5)
comprobar("progreso topado en 1", d.fraccion(30, 20) == 1.0)
comprobar("progreso sin duración es 0", d.fraccion(5, None) == 0.0)
comprobar("progreso negativo es 0", d.fraccion(-1, 10) == 0.0)
comprobar("título sin canción", b.texto_titulo(None) == "Sin reproducción")
comprobar("título recortado", len(b.texto_titulo("x" * 80)) == 2 + b.LARGO_TITULO)
comprobar("título con pausa", b.texto_titulo("tema", True) == "pausa: tema")
comprobar("título normal", b.texto_titulo("tema") == "> tema")
comprobar("la barra no tiene línea de texto propio", not hasattr(b.BarraReproductor, "mostrar_respuesta"))
comprobar("controles compactos: nueve botones en una fila", len(b.BOTONES) == 9)

# ---------------------------------------------------------------- cada control = la orden de voz
c = ComandosFalsos()
barra_de_prueba(reproductor_falso(), c)._orden("pausa")
comprobar("pausa sin canción reproduce", c.llamadas[-1] == ("REPRODUCIR_MUSICA", ""))
c = ComandosFalsos()
barra_de_prueba(reproductor_falso(cancion_actual=Falso(name="a.mp3")), c)._orden("pausa")
comprobar("pausa con canción sonando pausa", c.llamadas[-1] == ("PAUSAR_AUDIO", ""))
c = ComandosFalsos()
barra_de_prueba(reproductor_falso(cancion_actual=Falso(name="a.mp3"), pausado=True), c)._orden("pausa")
comprobar("pausa con canción pausada continúa", c.llamadas[-1] == ("CONTINUAR_AUDIO", ""))
for clave, esperada in (("anterior", "ANTERIOR_AUDIO"), ("siguiente", "SIGUIENTE_AUDIO"),
                        ("detener", "DETENER_AUDIO"), ("aleatorio", "ALEATORIO_AUDIO"), ("repetir", "REPETIR_AUDIO")):
    c = ComandosFalsos()
    barra_de_prueba(reproductor_falso(), c)._orden(clave)
    comprobar(f"{clave} envía {esperada}", c.llamadas[-1] == (esperada, ""))
c = ComandosFalsos()
barra_de_prueba(reproductor_falso(), c)._orden("bajar")
comprobar("bajar vuelve a la frase de volumen", c.llamadas[-1] == ("VOLUMEN_AUDIO", "bajar volumen"))
c = ComandosFalsos()
barra_de_prueba(reproductor_falso(), c)._orden("subir")
comprobar("subir vuelve a la frase de volumen", c.llamadas[-1] == ("VOLUMEN_AUDIO", "subir volumen"))

rf = reproductor_falso(silenciar=lambda: True, restaurar_volumen=lambda: True)
comprobar("silenciar responde como MILLER",
          barra_de_prueba(rf, ComandosFalsos())._orden("silencio") == "Afirmativo. Silencio, señor.")
rf = reproductor_falso(volumen=0.0, silenciar=lambda: True, restaurar_volumen=lambda: True)
comprobar("reactivar con volumen en cero",
          barra_de_prueba(rf, ComandosFalsos())._orden("silencio") == "Afirmativo. Sonido recuperado, señor.")
comprobar("sin reproductor responde negativo",
          barra_de_prueba(None, ComandosFalsos())._orden("pausa").startswith("Negativo"))
comprobar("control desconocido responde negativo",
          barra_de_prueba(reproductor_falso(), ComandosFalsos())._orden("nada").startswith("Negativo"))

# la respuesta llega a quien informa (la terminal), y un error se informa en vez de romper
recibidas = []
barra_de_prueba(reproductor_falso(), ComandosFalsos(), recibidas.append)._accion("detener")
comprobar("la respuesta se informa", recibidas == ["hecho DETENER_AUDIO"])
recibidas = []
barra_de_prueba(reproductor_falso(), ComandosFalsos(lanza=True), recibidas.append)._accion("detener")
comprobar("un error se informa como negativo",
          len(recibidas) == 1 and recibidas[0].startswith("Negativo. No pude completar el control"))

# ---------------------------------------------------------------- lo que muestra la barra
rf = reproductor_falso(cancion_actual=Falso(name="a.mp3"), posicion_segundos=lambda: 30.0,
                       duracion_segundos=lambda: 120.0)
estado = barra_de_prueba(rf, ComandosFalsos())._estado_reproductor()
comprobar("tiempo transcurrido / total", estado["tiempo"] == "0:30 / 2:00")
comprobar("progreso de la barra", abs(estado["frac"] - 0.25) < 1e-9)
comprobar("volumen en porcentaje", estado["volumen"] == 60)
comprobar("título con el nombre", estado["titulo"] == "> a.mp3")

# ---------------------------------------------------------------- duración medida con ffmpeg
ffmpeg = shutil.which("ffmpeg")
if ffmpeg is None:
    print("OMITIDO ffmpeg no está instalado: no se mide una pista real")
else:
    tmp = _Path(tempfile.mkdtemp(prefix="prueba_barra_"))
    try:
        pista = tmp / "tono.wav"
        subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                        "sine=frequency=440:duration=2", "-y", str(pista)], check=True)
        comprobar("la primera vez se mide en segundo plano", d.duracion_de(pista, ffmpeg) is None)
        total, limite = None, time.time() + 30
        while total is None and time.time() < limite:
            total = d.duracion_de(pista, ffmpeg)
            time.sleep(0.2)
        comprobar("duración medida cerca de 2 s", total is not None and abs(total - 2.0) < 0.1)
        comprobar("la segunda vez sale de la caché", d.duracion_de(pista, ffmpeg) == total)
        comprobar("sin ffmpeg no se mide nada", d.duracion_de(tmp / "otro.wav", None) is None)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

print("OK" if fallos == 0 else f"FALLO: {fallos} comprobaciones")
if fallos:
    raise SystemExit(1)
