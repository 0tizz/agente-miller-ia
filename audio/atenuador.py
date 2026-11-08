"""MILLER · Atenuador de voz (ducking)."""
import threading

class AtenuadorVoz:
    def __init__(self, reproductor, factor=0.40, factor_voz=1.2, minimo_voz=0.06, maximo_voz=1.0,
                 duracion_bajada=0.30, duracion_subida=1.0, margen=None, db_sobre_musica=1.0, nivel_voz=0.21):
        self.db_sobre_musica = db_sobre_musica   # con música: la voz suena estos dB por encima de la canción
        self.nivel_voz = nivel_voz               # RMS de la voz neural (voz_neural.NIVEL_VOZ_RMS)
        self.reproductor = reproductor
        self.factor = factor                # la música baja a volumen * factor mientras habla
        self.factor_voz = factor_voz        # la voz suena a volumen_música * factor_voz
        self.minimo_voz, self.maximo_voz = minimo_voz, maximo_voz
        self.duracion_bajada, self.duracion_subida = duracion_bajada, duracion_subida
        self._lock = threading.Lock()
        self._profundidad = 0               # admite llamadas anidadas
        self._atenuado = False
    def _volumen_musica(self):
        try:
            return max(0.0, min(1.0, float(getattr(self.reproductor, "volumen", 0.0))))
        except (TypeError, ValueError):
            return 0.0
    def _sonando(self):
        rep = self.reproductor
        try:
            return bool(rep and not getattr(rep, "cerrado", False) and getattr(rep, "inicializado", True)
                        and getattr(rep, "reproduciendo", False) and not getattr(rep, "pausado", False))
        except Exception:
            return False
    def volumen_voz(self):
        """Con música: la voz suena como la canción a su volumen normal (+1 dB) mientras la música baja al 40 %:
        la voz queda claramente delante. Sin música: un 20 % más que el volumen actual."""
        volumen = self._volumen_musica()
        if self._sonando():
            nivel = None
            try:
                nivel = self.reproductor.nivel_cancion_actual()
            except Exception:
                pass
            nivel = nivel or getattr(self.reproductor, "NIVEL_POR_DEFECTO", 0.15)
            musica_oida = volumen * nivel                          # la canción a su volumen normal (sin atenuar)
            voz = musica_oida * 10 ** (self.db_sobre_musica / 20) / max(0.01, self.nivel_voz)
        else:
            voz = volumen * self.factor_voz
        return round(max(self.minimo_voz, min(self.maximo_voz, voz)), 3)
    def _transicion(self, objetivo, duracion):
        fade = getattr(self.reproductor, "fade_controller", None)
        if fade is None:
            return False
        try:
            return bool(fade.transicionar(max(0.0, min(1.0, objetivo)), duracion))
        except Exception as error:
            print(f"[ VOZ ] Atenuación no disponible: {error}")
            return False
    def atenuar(self):
        with self._lock:
            self._profundidad += 1
            if self._profundidad > 1 or not self._sonando():
                return
            volumen = self._volumen_musica()
            if volumen <= 0:
                return
            self._atenuado = self._transicion(volumen * self.factor, self.duracion_bajada)
    def restaurar(self):
        with self._lock:
            self._profundidad = max(0, self._profundidad - 1)
            if self._profundidad or not self._atenuado:
                return
            self._atenuado = False
            if self._sonando():                 # vuelve al volumen ACTUAL (por si cambió mientras hablaba)
                self._transicion(self._volumen_musica(), self.duracion_subida)
    def __enter__(self):
        self.atenuar()
        return self
    def __exit__(self, *_):
        self.restaurar()
