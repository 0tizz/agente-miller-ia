"""MILLER · Voz neural local (Piper): voces masculinas de modelos/voces, sin internet."""
import io
import threading
import time
import wave
from collections import OrderedDict
from pathlib import Path

try:
    from piper import PiperVoice
except Exception as _error_piper:          # sin piper-tts: Hablador usa SAPI5
    PiperVoice = None
    ERROR_PIPER = str(_error_piper)
else:
    ERROR_PIPER = ""
try:
    from piper import SynthesisConfig
except Exception:
    SynthesisConfig = None

try:
    import numpy as np                     # llega con piper-tts (onnxruntime)
except Exception:
    np = None

VOCES = {
    "es_MX-ald-medium": "latina (México)",
    "es_ES-davefx-medium": "española (España)",
}


def voces_instaladas(carpeta):
    """Nombres de las voces con .onnx y .onnx.json presentes."""
    carpeta = Path(carpeta)
    return [n for n in VOCES if (carpeta / n / f"{n}.onnx").is_file() and (carpeta / n / f"{n}.onnx.json").is_file()]


class VozNeural:
    MAX_CACHE = 64                         # frases ya sintetizadas: se reutilizan sin gastar CPU

    def __init__(self, carpeta, nombre, velocidad=185, suavizar=True):
        self.suavizar = bool(suavizar)
        if PiperVoice is None:
            raise RuntimeError(f"piper-tts no disponible: {ERROR_PIPER}")
        self.carpeta = Path(carpeta)
        self.velocidad = max(80, min(350, int(velocidad)))
        self._lock = threading.Lock()
        self._cache = OrderedDict()
        self.nombre = None
        self.voz = None
        self.cargar(nombre)

    def cargar(self, nombre):
        ruta = self.carpeta / nombre / f"{nombre}.onnx"
        if not ruta.is_file():
            raise FileNotFoundError(f"No está la voz {nombre} en {self.carpeta}")
        voz = PiperVoice.load(str(ruta), config_path=str(ruta) + ".json")
        with self._lock:
            self.voz, self.nombre = voz, nombre
            self._cache.clear()
        return nombre

    def descripcion(self):
        return VOCES.get(self.nombre, self.nombre)

    def sintetizar(self, texto):
        """Texto -> WAV en memoria (bytes)."""
        clave = (self.nombre, texto)
        with self._lock:
            if clave in self._cache:
                self._cache.move_to_end(clave)
                return self._cache[clave]
            voz = self.voz
        escala = round(185 / self.velocidad, 2)       # 185 ppm = ritmo natural del modelo
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            if hasattr(voz, "synthesize_wav"):
                ajustes = SynthesisConfig(length_scale=escala) if SynthesisConfig else None
                voz.synthesize_wav(texto, wav, syn_config=ajustes) if ajustes else voz.synthesize_wav(texto, wav)
            else:                                     # API antigua de piper-tts
                voz.synthesize(texto, wav, length_scale=escala)
        datos = buffer.getvalue()
        if self.suavizar:
            datos = suavizar_wav(datos, frecuencia_mezclador())
        with self._lock:
            self._cache[clave] = datos
            while len(self._cache) > self.MAX_CACHE:
                self._cache.popitem(last=False)
        return datos

    @staticmethod
    def reproducir(datos, volumen=1.0):
        """Reproduce el WAV y espera a que termine. Usa pygame (se mezcla con la música)."""
        return _reproducir(datos, volumen)


def frecuencia_mezclador():
    try:
        import pygame
        info = pygame.mixer.get_init()
        return int(info[0]) if info else 44100
    except Exception:
        return 44100


NIVEL_VOZ_RMS = 0.22                       # ≈ -13 dBFS: el nivel típico de la música


def suavizar_wav(datos, frecuencia_salida=44100):
    """Iguala la voz al nivel de la música (unos -13 dBFS como una canción masterizada), con presencia,
    sin picos ásperos, fundidos cortos y remuestreo limpio. Así, al mismo volumen, voz y música suenan parejas."""
    if np is None:
        return datos
    try:
        with wave.open(io.BytesIO(datos)) as w:
            frecuencia, canales, ancho = w.getframerate(), w.getnchannels(), w.getsampwidth()
            crudo = w.readframes(w.getnframes())
        if ancho != 2 or not crudo:
            return datos
        x = np.frombuffer(crudo, dtype="<i2").astype(np.float32) / 32768.0
        if canales > 1:
            x = x.reshape(-1, canales).mean(axis=1)
        x -= float(x.mean())                                          # sin componente continua
        x = np.convolve(x, np.array([0.25, 0.5, 0.25], dtype=np.float32), mode="same")   # quita solo el siseo
        for _ in range(2):                                            # nivel de canción, con compresión suave
            rms = float(np.sqrt(np.mean(x * x))) or 1.0
            x *= min(8.0, NIVEL_VOZ_RMS / rms)
            x = 0.95 * np.tanh(x / 0.95)
        n_in, n_out = int(frecuencia * 0.012), int(frecuencia * 0.04)
        if len(x) > n_in + n_out:
            x[:n_in] *= np.linspace(0.0, 1.0, n_in, dtype=np.float32)
            x[-n_out:] *= np.linspace(1.0, 0.0, n_out, dtype=np.float32)
        if frecuencia_salida and frecuencia_salida != frecuencia:     # remuestreo lineal, sin escalones
            t = np.arange(int(len(x) * frecuencia_salida / frecuencia)) * (frecuencia / frecuencia_salida)
            x = np.interp(t, np.arange(len(x)), x).astype(np.float32)
            frecuencia = frecuencia_salida
        salida = io.BytesIO()
        with wave.open(salida, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(frecuencia)
            w.writeframes((np.clip(x, -1.0, 1.0) * 32767).astype("<i2").tobytes())
        return salida.getvalue()
    except Exception as error:
        print(f"[VOZ] Suavizado no aplicado: {error}")
        return datos


def _reproducir(datos, volumen=1.0):
    """Reproduce el WAV y espera a que termine. Usa pygame (se mezcla con la música)."""
    try:
        import pygame
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        sonido = pygame.mixer.Sound(file=io.BytesIO(datos))
        sonido.set_volume(max(0.0, min(1.0, float(volumen))))
        canal = sonido.play()
        limite = time.monotonic() + sonido.get_length() + 2.0
        while canal is not None and canal.get_busy() and time.monotonic() < limite:
            time.sleep(0.02)
        return True
    except Exception as error:
        print(f"[VOZ] pygame no pudo reproducir la voz neural ({error}); se usa winsound.")
    try:
        import winsound
        winsound.PlaySound(datos, winsound.SND_MEMORY)
        return True
    except Exception as error:
        print(f"[VOZ] No se pudo reproducir la voz neural: {error}")
        return False
