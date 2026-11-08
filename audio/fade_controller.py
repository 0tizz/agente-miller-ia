"""MILLER · Controlador central de fade"""
import threading
import time

class FadeController:
    """Controlador centralizado de transiciones de volumen."""
    VOLUMEN_MINIMO = 0.0
    VOLUMEN_MAXIMO = 1.0
    DURACION_FADE_IN = 2.0
    DURACION_FADE_OUT = 1.2
    PASOS = 40
    INTERVALO = 0.05
    def __init__(self, obtener_volumen, establecer_volumen):
        """obtener_volumen: Función que devuelve el volumen actual."""
        self._obtener_volumen = (obtener_volumen)
        self._establecer_volumen = (establecer_volumen)
        self._lock = threading.RLock()
        self._hilo = None
        # Evento para cancelar una transición
        self._cancelar_evento = (threading.Event())
        self._activo = False
        self._cerrado = False
    def _limitar_volumen(self, volumen):
        """Limita el volumen entre 0.0 y 1.0."""
        try:
            volumen = float(volumen)
        except (TypeError, ValueError):
            volumen = 0.0
        return max(self.VOLUMEN_MINIMO, min(self.VOLUMEN_MAXIMO, volumen))
    def cancelar(self):
        """Cancela inmediatamente cualquier fade activo."""
        with self._lock:
            self._cancelar_evento.set()
            self._activo = False
            hilo = self._hilo
            self._hilo = None
        # Esperar al hilo anterior.
        if (hilo is not None and hilo.is_alive() and hilo is not threading.current_thread()):
            hilo.join(timeout=1.0)
    def esta_activo(self):
        """Devuelve True si existe una transición activa."""
        with self._lock:
            return self._activo
    def transicionar(self, volumen_objetivo, duracion=None):
        """Realiza una transición suave desde el volumen actual hasta el volumen objetivo."""
        with self._lock:
            if self._cerrado:
                return False
            # Cancelar cualquier transición anterior.
            self._cancelar_evento.set()
            hilo_anterior = self._hilo
            self._cancelar_evento = (threading.Event())
            evento_cancelacion = (self._cancelar_evento)
            self._activo = True
        # Esperar al hilo anterior.
        if (
            hilo_anterior is not None
            and hilo_anterior.is_alive()
            and hilo_anterior is not threading.current_thread()
        ):
            hilo_anterior.join(timeout=1.0)
        if duracion is None:
            duracion = (self.DURACION_FADE_IN)
        try:
            duracion = float(duracion)
        except (TypeError, ValueError):
            duracion = (self.DURACION_FADE_IN)
        duracion = max(0.0, duracion)
        objetivo = (self._limitar_volumen(volumen_objetivo))
        try:
            inicial = (self._limitar_volumen(self._obtener_volumen()))
        except Exception:
            inicial = 0.0
        # Sin transición.
        if (duracion <= 0.0 or abs(inicial - objetivo) < 0.0001):
            try:
                if not evento_cancelacion.is_set():
                    self._establecer_volumen(objetivo)
                    resultado = True
                else:
                    resultado = False
            except Exception:
                resultado = False
            with self._lock:
                self._activo = False
                if self._hilo is threading.current_thread():
                    self._hilo = None
            return resultado
        hilo = threading.Thread(
            target=self._ejecutar_transicion,
            args=(
                inicial,
                objetivo,
                duracion,
                evento_cancelacion,
            ),
            daemon=True,
            name="MILLER-FadeController"
        )
        with self._lock:
            self._hilo = hilo
        hilo.start()
        # Esperar finalización.
        hilo.join()
        with self._lock:
            if self._hilo is hilo:
                self._hilo = None
            self._activo = False
        return not evento_cancelacion.is_set()
    def _ejecutar_transicion(self, inicial, objetivo, duracion, evento_cancelacion):
        """Motor interno de la transición."""
        try:
            pasos = max(1, int(self.PASOS * max(duracion, 0.01) / (self.PASOS * self.INTERVALO)))
            intervalo = (duracion / pasos)
            for paso in range(1, pasos + 1):
                if (evento_cancelacion.is_set() or self._cerrado):
                    return
                lineal = (paso / pasos)
                # Curva suave (ease in-out): arranca y termina sin saltos audibles.
                progreso = lineal * lineal * (3.0 - 2.0 * lineal)
                volumen = (inicial + (objetivo - inicial) * progreso)
                volumen = (self._limitar_volumen(volumen))
                try:
                    self._establecer_volumen(volumen)
                except Exception:
                    return
                if paso < pasos:
                    if evento_cancelacion.wait(intervalo):
                        return
            # Asegurar valor final exacto.
            if not evento_cancelacion.is_set():
                try:
                    self._establecer_volumen(objetivo)
                except Exception:
                    return
        finally:
            with self._lock:
                self._activo = False
    def fade_in(self, volumen_objetivo, duracion=None):
        """Realiza un fade-in hasta el volumen indicado."""
        if duracion is None:
            duracion = (self.DURACION_FADE_IN)
        return self.transicionar(volumen_objetivo, duracion)
    def fade_out(self, duracion=None):
        """Realiza un fade-out hasta 0%."""
        if duracion is None:
            duracion = (self.DURACION_FADE_OUT)
        return self.transicionar(0.0, duracion)
    def establecer_directo(self, volumen):
        """Cancela cualquier fade y establece el volumen inmediatamente."""
        self.cancelar()
        volumen = (self._limitar_volumen(volumen))
        try:
            self._establecer_volumen(volumen)
            return True
        except Exception:
            return False
    def cerrar(self):
        """Cierra el controlador de fades."""
        with self._lock:
            if self._cerrado:
                return
            self._cerrado = True
        self.cancelar()
        print("[ FADE ] FadeController cerrado.")
    def obtener_estado(self):
        with self._lock:
            return {
                "activo":
                    self._activo,
                "cerrado":
                    self._cerrado,
                "hilo_activo":
                    (
                        self._hilo is not None
                        and self._hilo.is_alive()
                    ),
            }
