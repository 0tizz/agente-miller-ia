"""MILLER · Conversación fluida: seguimiento sin repetir el nombre y modo llamada."""
import re
import threading
import time
import unicodedata


def _normalizar(texto):
    texto = unicodedata.normalize("NFD", str(texto or "").lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9ñ ]+", " ", texto)).strip()


class Conversacion:
    """Tras cada respuesta deja unos segundos para seguir hablando sin decir "Miller"."""
    _RE_INICIO = re.compile(r"^(?:miller )?(?:modo (?:llamada|conversacion)|hablemos|conversemos|vamos a (?:hablar|conversar)|"
                            r"iniciar llamada|inicia (?:la )?llamada|abre (?:la )?llamada|llamada)$")
    _RE_FIN = re.compile(r"^(?:miller )?(?:fin de la (?:llamada|conversacion)|cuelga|colgar|cuelga la llamada|"
                         r"termina(?:r)? (?:la )?(?:llamada|conversacion)|cierra (?:la )?llamada|eso es todo|"
                         r"gracias eso es todo|hasta luego miller|corto)$")

    def __init__(self, ventana=8.0, fin_inactividad=90.0, activa=True):
        self.ventana = float(ventana)
        self.fin_inactividad = float(fin_inactividad)
        self.activa = bool(activa)
        self._lock = threading.Lock()
        self._seguimiento_hasta = 0.0
        self._llamada = False
        self._ultima_voz = time.monotonic()

    def es_inicio(self, texto):
        return bool(self._RE_INICIO.match(_normalizar(texto)))

    def es_fin(self, texto):
        return bool(self._RE_FIN.match(_normalizar(texto)))

    def iniciar_llamada(self):
        with self._lock:
            self._llamada, self._ultima_voz = True, time.monotonic()

    def terminar_llamada(self):
        with self._lock:
            self._llamada, self._seguimiento_hasta = False, 0.0

    def en_llamada(self):
        return self._llamada

    def abrir_seguimiento(self):
        """Llamar justo después de que MILLER termina de responder."""
        if self.activa:
            with self._lock:
                self._seguimiento_hasta = time.monotonic() + self.ventana

    def cerrar_seguimiento(self):
        with self._lock:
            self._seguimiento_hasta = 0.0

    def oido(self):
        """Se oyó una frase: mantiene viva la llamada."""
        with self._lock:
            self._ultima_voz = time.monotonic()

    def acepta_sin_nombre(self):
        with self._lock:
            return self.activa and (self._llamada or time.monotonic() < self._seguimiento_hasta)

    def en_seguimiento(self):
        with self._lock:
            return self.activa and not self._llamada and time.monotonic() < self._seguimiento_hasta

    def debe_caducar(self):
        return self._llamada and time.monotonic() - self._ultima_voz > self.fin_inactividad

    def llamada_caducada(self):
        """True (una sola vez) si la llamada lleva demasiado tiempo en silencio."""
        with self._lock:
            if self._llamada and time.monotonic() - self._ultima_voz > self.fin_inactividad:
                self._llamada = False
                return True
            return False
