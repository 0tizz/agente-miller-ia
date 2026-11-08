"""MILLER · voz.escuchador."""
import json, os, struct, math, re, time, unicodedata
from array import array
import pyaudio
from vosk import Model, KaldiRecognizer
import configuracion
from configuracion import RUTA_MODELO_VOZ
try:
    from vosk import SetLogLevel
    SetLogLevel(-1)                       # sin trazas internas de Kaldi: menos consola y CPU
except Exception:
    pass

class Escuchador:
    FRECUENCIA_VOSK = 16000
    TAMANO_BLOQUE = 1600
    CANALES = 1
    DURACION_BLOQUE_MS = 100
    NIVEL_AUDIO_MINIMO = 120
    USAR_REMUESTREO = True
    VARIANTES_MILLER = {
        "miler": "miller", "mille": "miller",
        "mil ler": "miller", "mil er": "miller",
        "miller": "miller",
    }
    def __init__(self):
        self.microfono_disponible = False
        self.modelo_disponible = False
        self.inicializado = False
        self.error = None
        self.frecuencia_muestreo = self.FRECUENCIA_VOSK
        self.tamano_bloque = self.TAMANO_BLOQUE
        self.tamano_bloque_captura = self.tamano_bloque
        self.canales = self.CANALES
        self.remuestreo_activo = False
        self.ultima_frecuencia_captura = self.FRECUENCIA_VOSK
        self._ultima_muestra_remuestreo = 0
        self.indice_microfono = None
        self.nombre_microfono = None
        self.frecuencia_dispositivo = None
        self.audio = None
        self.flujo = None
        self.modelo = None
        self.reconocedor = None
        self.audio_detectado = False
        self.ultimo_nivel_audio = 0
        self._inicializar()
    def _inicializar(self):
        try:
            ruta_modelo = str(RUTA_MODELO_VOZ)
            if not os.path.isdir(ruta_modelo):
                self.error = "No se encontró el modelo de voz local."
                print(f"[VOZ] {self.error}")
                return
            print("[VOZ] Cargando modelo local...")
            self.modelo = Model(ruta_modelo)
            self.modelo_disponible = True
            print("[VOZ] Modelo local cargado.")
        except Exception as error:
            self.error = f"Error cargando modelo: {error}"
            print(f"[VOZ] {self.error}")
            return
        try:
            self.audio = pyaudio.PyAudio()
            cantidad_dispositivos = self.audio.get_device_count()
            print(f"[VOZ] Dispositivos de audio detectados: {cantidad_dispositivos}")
            if not self._buscar_microfono():
                self.error = "No se encontró ningún micrófono de entrada disponible."
                print(f"[VOZ] {self.error}")
                return
            self.microfono_disponible = True
        except Exception as error:
            self.error = f"Error inicializando audio: {error}"
            print(f"[VOZ] {self.error}")
            return
        if not self._crear_reconocedor():
            return
        self.inicializado = True
        print("[VOZ] Reconocimiento de voz LOCAL activado.")
        print(f"[VOZ] Micrófono seleccionado: {self.nombre_microfono}")
        print(f"[VOZ] Índice del micrófono: {self.indice_microfono}")
        print(f"[VOZ] Frecuencia objetivo de Vosk: {self.FRECUENCIA_VOSK} Hz")
        print(f"[VOZ] Frecuencia del dispositivo: {self.frecuencia_dispositivo} Hz")
    def _buscar_microfono(self):
        """Busca exclusivamente dispositivos con entrada de audio."""
        if self.audio is None:
            return False
        print("[VOZ] Buscando micrófonos de entrada...")
        dispositivos_entrada = []
        try:
            cantidad = self.audio.get_device_count()
            for indice in range(cantidad):
                try:
                    informacion = self.audio.get_device_info_by_index(indice)
                except Exception as error:
                    print(f"[VOZ] No se pudo consultar el dispositivo {indice}: {error}")
                    continue
                nombre = informacion.get("name", "Dispositivo desconocido")
                canales_entrada = int(informacion.get("maxInputChannels", 0))
                frecuencia = informacion.get("defaultSampleRate", 0)
                print(f"[VOZ] [{indice}] {nombre} | entradas={canales_entrada} | frecuencia={frecuencia}")
                if canales_entrada > 0:
                    dispositivos_entrada.append((indice, nombre, frecuencia, canales_entrada))
            if not dispositivos_entrada:
                return False
            try:
                predeterminado = self.audio.get_default_input_device_info()
                indice_predeterminado = int(predeterminado.get("index"))
                for dispositivo in dispositivos_entrada:
                    if dispositivo[0] == indice_predeterminado:
                        self._seleccionar_microfono(dispositivo)
                        print("[VOZ] Se utilizará el micrófono predeterminado de Windows.")
                        return True
            except Exception as error:
                print(f"[VOZ] No se pudo obtener el micrófono predeterminado: {error}")
            # PRIMER MICRÓFONO DISPONIBLE
            self._seleccionar_microfono(dispositivos_entrada[0])
            print("[VOZ] Se utilizará el primer dispositivo de entrada disponible.")
            return True
        except Exception as error:
            self.error = f"Error buscando micrófonos: {error}"
            print(f"[VOZ] {self.error}")
            return False
    def _seleccionar_microfono(self, dispositivo):
        self.indice_microfono = dispositivo[0]
        self.nombre_microfono = str(dispositivo[1])
        try:
            frecuencia = int(float(dispositivo[2]))
        except Exception:
            frecuencia = 44100
        if frecuencia <= 0:
            frecuencia = 44100
        self.frecuencia_dispositivo = frecuencia
        self.frecuencia_muestreo = self.FRECUENCIA_VOSK
    def _crear_reconocedor(self):
        try:
            if self.modelo is None:
                return False
            self.reconocedor = KaldiRecognizer(self.modelo, self.frecuencia_muestreo)
            for metodo, valor in (("SetWords", False), ("SetPartialWords", False)):   # solo se usa el texto
                try:
                    getattr(self.reconocedor, metodo)(valor)
                except Exception:
                    pass
            # Fin de frase más rápido: conversación fluida, como una llamada.
            silencio = float(getattr(configuracion, "VOZ_SILENCIO_FIN_FRASE", 0.6))
            try:
                self.reconocedor.SetEndpointerDelays(5.0, max(0.3, silencio), 15.0)
            except Exception:
                pass
            return True
        except Exception as error:
            self.error = f"Error creando reconocedor: {error}"
            print(f"[VOZ] {self.error}")
            return False
    def _frecuencia_soportada(self, frecuencia):
        if self.audio is None or self.indice_microfono is None:
            return False
        try:
            return bool(self.audio.is_format_supported(
                frecuencia,
                input_device=self.indice_microfono,
                input_channels=self.canales,
                input_format=pyaudio.paInt16
            ))
        except Exception:
            return False
    def _calcular_bloque_captura(self, frecuencia):
        try:
            frecuencia = int(frecuencia)
        except Exception:
            frecuencia = self.FRECUENCIA_VOSK
        if frecuencia <= 0:
            frecuencia = self.FRECUENCIA_VOSK
        muestras = int(round(frecuencia * self.DURACION_BLOQUE_MS / 1000.0))
        return muestras if muestras > 0 else self.tamano_bloque
    def _configurar_frecuencia_captura(self, frecuencia):
        try:
            frecuencia = int(frecuencia)
        except Exception:
            frecuencia = self.FRECUENCIA_VOSK
        if frecuencia <= 0:
            frecuencia = self.FRECUENCIA_VOSK
        self.ultima_frecuencia_captura = frecuencia
        self.tamano_bloque_captura = self._calcular_bloque_captura(frecuencia)
        self.remuestreo_activo = bool(self.USAR_REMUESTREO and frecuencia != self.FRECUENCIA_VOSK)
        self.frecuencia_muestreo = self.FRECUENCIA_VOSK
    def _abrir_flujo(self, frecuencia):
        self._configurar_frecuencia_captura(frecuencia)
        self.flujo = self.audio.open(
            format=pyaudio.paInt16,
            channels=self.canales,
            rate=frecuencia,
            input=True,
            input_device_index=self.indice_microfono,
            frames_per_buffer=self.tamano_bloque_captura,
            start=True
        )
        return True
    def _abrir_microfono(self):
        if self.audio is None:
            print("[VOZ] PyAudio no está inicializado.")
            return False
        if not self.microfono_disponible:
            print("[VOZ] No hay micrófono disponible.")
            return False
        if self.flujo is not None:
            try:
                if self.flujo.is_active():
                    return True
            except Exception:
                pass
            self._cerrar_microfono()
        # OPCIÓN 1: 16000 HZ
        if self._frecuencia_soportada(self.FRECUENCIA_VOSK):
            try:
                print("[VOZ] Intentando abrir micrófono a 16000 Hz...")
                self._abrir_flujo(self.FRECUENCIA_VOSK)
                print("[VOZ] Micrófono abierto correctamente.")
                print(f"[VOZ] Captura configurada a {self.FRECUENCIA_VOSK} Hz.")
                print(f"[VOZ] Vosk recibirá audio a {self.FRECUENCIA_VOSK} Hz.")
                return True
            except Exception as error:
                print(f"[VOZ] No fue posible abrir el micrófono a 16000 Hz: {error}")
                self._cerrar_microfono()
        # OPCIÓN 2: FRECUENCIA NATIVA + REMUESTREO
        frecuencia_nativa = self.frecuencia_dispositivo
        if frecuencia_nativa is not None and frecuencia_nativa > 0:
            try:
                print("[VOZ] 16000 Hz no está disponible.")
                print(f"[VOZ] Intentando frecuencia nativa: {frecuencia_nativa} Hz...")
                self._abrir_flujo(frecuencia_nativa)
                if self.remuestreo_activo:
                    print(
                        f"[VOZ] Remuestreo local activado: "
                        f"{frecuencia_nativa} Hz → {self.FRECUENCIA_VOSK} Hz."
                    )
                print("[VOZ] Micrófono abierto correctamente.")
                print(f"[VOZ] Captura física: {frecuencia_nativa} Hz.")
                print(f"[VOZ] Frecuencia entregada a Vosk: {self.FRECUENCIA_VOSK} Hz.")
                return True
            except Exception as error:
                print(f"[VOZ] No fue posible abrir la frecuencia nativa: {error}")
                self._cerrar_microfono()
        self.error = "No fue posible abrir el micrófono con ninguna frecuencia compatible."
        print(f"[VOZ] {self.error}")
        return False
    def _medir_nivel_audio(self, datos):
        if not datos:
            return 0
        try:
            muestras = array("h")
            muestras.frombytes(datos[:len(datos) // 2 * 2])
            if not muestras:
                return 0
            suma = math.sumprod(muestras, muestras) if hasattr(math, "sumprod") else sum(m * m for m in muestras)
            nivel = int(math.sqrt(suma / len(muestras)))
            return max(0, nivel)
        except Exception:
            return 0
    def _remuestrear_pcm16(self, datos, frecuencia_origen):
        if not datos:
            return b""
        try:
            frecuencia_origen = int(frecuencia_origen)
        except Exception:
            return datos
        if frecuencia_origen <= 0 or frecuencia_origen == self.FRECUENCIA_VOSK:
            return datos
        if not self.USAR_REMUESTREO:
            return datos
        try:
            cantidad_muestras = len(datos) // 2
            if cantidad_muestras <= 0:
                return b""
            muestras = array("h")
            muestras.frombytes(datos[:cantidad_muestras * 2])
            import sys
            if sys.byteorder != "little":
                muestras.byteswap()
            cantidad_salida = int(round(cantidad_muestras * self.FRECUENCIA_VOSK / frecuencia_origen))
            if cantidad_salida <= 0:
                return b""
            salida = array("h")
            paso = frecuencia_origen / float(self.FRECUENCIA_VOSK)
            ultima_muestra = self._ultima_muestra_remuestreo
            for indice in range(cantidad_salida):
                posicion = indice * paso
                indice_base = int(posicion)
                fraccion = posicion - indice_base
                if indice_base >= cantidad_muestras:
                    muestra = int(muestras[-1])
                else:
                    actual = int(muestras[indice_base])
                    siguiente = (
                        int(muestras[indice_base + 1])
                        if indice_base + 1 < cantidad_muestras
                        else actual
                    )
                    muestra = int(round(actual + (siguiente - actual) * fraccion))
                muestra = max(-32768, min(32767, muestra))
                salida.append(muestra)
            if salida:
                ultima_muestra = int(salida[-1])
            self._ultima_muestra_remuestreo = ultima_muestra
            if sys.byteorder != "little":
                salida.byteswap()
            return salida.tobytes()
        except Exception as error:
            print(f"[VOZ] Error remuestreando audio: {error}")
            return b""
    def _preparar_audio_para_vosk(self, datos):
        if not datos:
            return b""
        if self.ultima_frecuencia_captura == self.FRECUENCIA_VOSK:
            return datos
        return self._remuestrear_pcm16(datos, self.ultima_frecuencia_captura)
    def _normalizar_texto(self, texto):
        if texto is None:
            return ""
        texto = str(texto).strip().lower()
        if not texto:
            return ""
        texto = unicodedata.normalize("NFD", texto)
        texto = "".join(caracter for caracter in texto if unicodedata.category(caracter) != "Mn")
        texto = texto.replace("’", "'").replace("´", "'").replace("`", "'")
        texto = re.sub(r"[^a-z0-9áéíóúüñ' ]+", " ", texto)
        return re.sub(r"\s+", " ", texto).strip()
    def _corregir_variantes_miller(self, texto):
        if not texto:
            return ""
        palabras = texto.split()
        resultado = []
        indice = 0
        while indice < len(palabras):
            palabra = palabras[indice]
            if palabra in self.VARIANTES_MILLER:
                resultado.append("miller")
                indice += 1
                continue
            if palabra == "mil" and indice + 1 < len(palabras):
                if palabras[indice + 1] in ("ler", "er", "le", "lerr"):
                    resultado.append("miller")
                    indice += 2
                    continue
            resultado.append(palabra)
            indice += 1
        return " ".join(resultado)
    def _procesar_texto_reconocido(self, texto):
        texto = self._normalizar_texto(texto)
        if not texto:
            return ""
        return self._corregir_variantes_miller(texto).strip()
    def _cerrar_microfono(self):
        if self.flujo is None:
            return
        try:
            self.flujo.stop_stream()
        except Exception:
            pass
        try:
            self.flujo.close()
        except Exception:
            pass
        self.flujo = None
        self.remuestreo_activo = False
        self.ultima_frecuencia_captura = self.FRECUENCIA_VOSK
        self.tamano_bloque_captura = self.tamano_bloque
        self._ultima_muestra_remuestreo = 0
    def _reiniciar_reconocedor(self):
        """Crea un reconocedor nuevo."""
        if self.modelo is None:
            return False
        return self._crear_reconocedor()
    def descartar_eco(self):
        """Tras hablar MILLER: vacía lo grabado mientras hablaba para no oírse a sí mismo."""
        try:
            if self.flujo is not None:
                pendiente = self.flujo.get_read_available()
                while pendiente > 0:
                    self.flujo.read(min(pendiente, 8192), exception_on_overflow=False)
                    pendiente = self.flujo.get_read_available()
        except Exception:
            self._cerrar_microfono()
        self._limpiar_reconocedor()
    def _limpiar_reconocedor(self):
        try:
            self.reconocedor.Reset()                 # mucho más barato que crear otro reconocedor
        except Exception:
            self._reiniciar_reconocedor()
    def escuchar(self, interrumpir=None):
        """Espera una frase. interrumpir:"""
        proxima_consulta = time.monotonic() + 1.0
        if not self.inicializado:
            print("[VOZ] El escuchador no está inicializado.")
            return ""
        if not self.modelo_disponible or not self.microfono_disponible:
            return ""
        if not self._abrir_microfono():
            return ""
        print("")
        print("🎙️ MILLER está escuchando...")
        print("[VOZ] Habla ahora...")
        print("[VOZ] Esperando una frase...")
        while True:
            try:
                datos = self.flujo.read(self.tamano_bloque_captura, exception_on_overflow=False)
            except Exception as error:
                print(f"[VOZ] Error leyendo audio: {error}")
                self._cerrar_microfono()
                return ""
            if not datos:
                continue
            if interrumpir is not None and time.monotonic() >= proxima_consulta:
                proxima_consulta = time.monotonic() + 1.0
                try:
                    if interrumpir() and not self.escuchar_parcial():
                        return ""
                except Exception:
                    pass
            nivel = self._medir_nivel_audio(datos)
            self.ultimo_nivel_audio = nivel
            if nivel >= self.NIVEL_AUDIO_MINIMO and not self.audio_detectado:
                self.audio_detectado = True
                print("[VOZ] 🔊 Audio del micrófono detectado.")
                print(f"[VOZ] Nivel de audio: {nivel}")
            audio_vosk = self._preparar_audio_para_vosk(datos)
            if not audio_vosk:
                continue
            try:
                aceptado = self.reconocedor.AcceptWaveform(audio_vosk)
            except Exception as error:
                print(f"[VOZ] Error procesando audio: {error}")
                self._reiniciar_reconocedor()
                continue
            if not aceptado:
                continue
            try:
                resultado = self.reconocedor.Result()
            except Exception as error:
                print(f"[VOZ] Error obteniendo resultado: {error}")
                self._reiniciar_reconocedor()
                continue
            texto = self._extraer_texto(resultado)
            self._limpiar_reconocedor()
            self.audio_detectado = False
            if not texto:
                continue
            print(f"🎙️ Detectado: {texto}")
            return texto
    def _extraer_texto(self, resultado):
        if not resultado:
            return ""
        try:
            datos = json.loads(resultado)
        except Exception:
            return ""
        texto = datos.get("text", "")
        if texto is None:
            return ""
        return self._procesar_texto_reconocido(texto)
    def escuchar_parcial(self):
        if self.reconocedor is None:
            return ""
        try:
            resultado = self.reconocedor.PartialResult()
            datos = json.loads(resultado)
            parcial = datos.get("partial", "")
            if parcial:
                return self._procesar_texto_reconocido(parcial)
        except Exception:
            pass
        return ""
    def esta_disponible(self):
        return bool(
            self.inicializado
            and self.microfono_disponible
            and self.modelo_disponible
            and self.audio is not None
            and self.modelo is not None
            and self.reconocedor is not None
            and self.indice_microfono is not None
        )
    def estado(self):
        return {
            "inicializado": self.inicializado,
            "microfono_disponible": self.microfono_disponible,
            "modelo_disponible": self.modelo_disponible,
            "flujo_abierto": self.flujo is not None,
            "indice_microfono": self.indice_microfono,
            "nombre_microfono": self.nombre_microfono,
            "frecuencia_muestreo": self.frecuencia_muestreo,
            "frecuencia_dispositivo": self.frecuencia_dispositivo,
            "frecuencia_captura": self.ultima_frecuencia_captura,
            "tamano_bloque": self.tamano_bloque,
            "tamano_bloque_captura": self.tamano_bloque_captura,
            "remuestreo_activo": self.remuestreo_activo,
            "audio_detectado": self.audio_detectado,
            "ultimo_nivel_audio": self.ultimo_nivel_audio,
            "error": self.error,
        }
    def detener(self):
        self._cerrar_microfono()
        if self.audio is not None:
            try:
                self.audio.terminate()
            except Exception:
                pass
            self.audio = None
        self.reconocedor = None
        self.inicializado = False
        self.audio_detectado = False
        self.ultimo_nivel_audio = 0
        print("[VOZ] Escuchador detenido.")
