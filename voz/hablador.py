"""MILLER · Síntesis de voz: voz neural masculina (Piper, modelos/voces) y SAPI5 de respaldo."""
try:
    import pyttsx3
except Exception:                          # sin pyttsx3: solo voz neural
    pyttsx3 = None
try:
    from voz.voz_neural import VozNeural, VOCES, voces_instaladas
except Exception:
    VozNeural, VOCES, voces_instaladas = None, {}, (lambda carpeta: [])
try:
    import configuracion as _cfg
except Exception:
    _cfg = None

class Hablador:
    """Controlador de salida de voz de MILLER."""
    INDICADORES_ESPANOL = ("spanish", "español", "espanol", "es-es", "es_es", "es-mx", "es_mx",
                           "es-co", "es_co", "es-us", "es_us")
    VOCES_MASCULINAS = ("pablo", "raul", "raúl", "jorge", "alvaro", "álvaro", "diego", "carlos",
                        "andres", "andrés", "enrique", "juan", "david", "male", "hombre")
    VOCES_FEMENINAS = ("helena", "sabina", "laura", "paloma", "elvira", "dalia", "salome", "female", "mujer")
    def __init__(self, atenuador=None):
        self.disponible = False
        self.nombre_voz = None
        self.atenuador = atenuador
        self.velocidad = int(getattr(_cfg, "VOZ_VELOCIDAD", 185))
        self.genero = str(getattr(_cfg, "VOZ_GENERO", "masculino")).lower()
        self.neural = None
        self._iniciar_neural()
        self.verificar_motor()
        self.disponible = self.disponible or self.neural is not None
    def _iniciar_neural(self):
        """Carga una sola vez la voz neural configurada (se reutiliza en cada respuesta)."""
        if VozNeural is None or str(getattr(_cfg, "VOZ_MOTOR", "neural")).lower() != "neural":
            return
        carpeta = getattr(_cfg, "RUTA_VOCES", None)
        instaladas = voces_instaladas(carpeta) if carpeta else []
        if not instaladas:
            return
        preferida = getattr(_cfg, "VOZ_NEURAL", "es_ES-davefx-medium")
        try:
            self.neural = VozNeural(carpeta, preferida if preferida in instaladas else instaladas[0], self.velocidad,
                                    suavizar=getattr(_cfg, "VOZ_SUAVIZADO", True))
            print(f"[VOZ] Voz neural masculina: {self.neural.descripcion()}.")
        except Exception as error:
            print(f"[VOZ] Voz neural no disponible ({error}). Se usa la voz de Windows.")
            self.neural = None
    def voz_actual(self):
        if self.neural is not None:
            return f"voz neural {self.neural.descripcion()}"
        return "voz de Windows" if self.disponible else "sin voz"
    def cambiar_voz(self, texto=""):
        """Alterna entre las voces masculinas instaladas o elige la pedida ("mexicana", "española")."""
        if self.neural is None:
            return "Solo dispongo de la voz de Windows. Instale piper-tts para las voces neurales."
        instaladas = voces_instaladas(self.neural.carpeta)
        t = str(texto or "").lower()
        elegida = next((n for n in instaladas if ("mex" in t or "latin" in t) and n.startswith("es_MX")), None) or \
            next((n for n in instaladas if ("espa" in t) and n.startswith("es_ES")), None)
        if elegida is None:
            otras = [n for n in instaladas if n != self.neural.nombre]
            elegida = otras[0] if otras else self.neural.nombre
        if elegida == self.neural.nombre:
            return f"Ya uso la voz {self.neural.descripcion()}."
        try:
            self.neural.cargar(elegida)
            return f"Afirmativo. Voz {self.neural.descripcion()} activada."
        except Exception as error:
            print(f"[VOZ] No se pudo cambiar de voz: {error}")
            return "Negativo. No pude cambiar de voz."
    def conectar_atenuador(self, atenuador):
        """Activa la atenuación de música y el volumen de voz adaptativo."""
        self.atenuador = atenuador
    def verificar_motor(self):
        """Comprueba que pyttsx3 pueda inicializarse."""
        if pyttsx3 is None:
            self.disponible = False
            return False
        try:
            motor = pyttsx3.init(driverName="sapi5")
            self.disponible = True
            self.obtener_voz_espanol(motor)
            motor.stop()
            del motor
            return True
        except Exception as error:
            print(f"[VOZ] No se pudo inicializar el sistema de voz: {error}")
            self.disponible = False
            return False
    def obtener_voz_espanol(self, motor):
        """Busca una voz en español, masculina si existe. Guarda y devuelve su id."""
        if self.nombre_voz:
            return self.nombre_voz
        try:
            espanolas = []
            for voz in motor.getProperty("voices"):
                info = " ".join(str(getattr(voz, c, "")) for c in ("id", "name", "languages", "gender")).lower()
                if any(i in info for i in self.INDICADORES_ESPANOL):
                    espanolas.append((voz, info))
            if not espanolas:
                return None
            if self.genero.startswith("masc"):
                preferidas = [v for v, i in espanolas if any(n in i for n in self.VOCES_MASCULINAS)] or \
                             [v for v, i in espanolas if not any(n in i for n in self.VOCES_FEMENINAS)]
            else:
                preferidas = [v for v, i in espanolas if any(n in i for n in self.VOCES_FEMENINAS)]
            self.nombre_voz = (preferidas or [espanolas[0][0]])[0].id
            return self.nombre_voz
        except Exception as error:
            print(f"[VOZ] Error buscando voz española: {error}")
        return None
    def volumen_actual(self):
        if self.atenuador is not None:
            try:
                return self.atenuador.volumen_voz()
            except Exception:
                pass
        return 1.0
    def crear_motor(self):
        """Crea un nuevo motor SAPI5 con velocidad, volumen y voz."""
        try:
            motor = pyttsx3.init(driverName="sapi5")
            motor.setProperty("rate", self.velocidad)
            motor.setProperty("volume", self.volumen_actual())
            voz = self.obtener_voz_espanol(motor)
            if voz:
                try:
                    motor.setProperty("voice", voz)
                except Exception:
                    pass
            return motor
        except Exception as error:
            print(f"[VOZ] Error creando motor: {error}")
            return None
    def hablar(self, texto):
        """Pronuncia una respuesta. Atenúa la música mientras habla."""
        texto = str(texto).strip() if texto is not None else ""
        if not texto:
            return False
        if not self.disponible:
            print("[VOZ] El sistema de voz no está disponible.")
            return False
        if self.neural is not None and self._hablar_neural(texto):
            return True
        if pyttsx3 is None:
            return False
        motor, atenuado = None, False
        try:
            motor = self.crear_motor()
            if motor is None:
                return False
            if self.atenuador is not None:
                try:
                    self.atenuador.atenuar()
                    atenuado = True
                except Exception as error:
                    print(f"[VOZ] No se pudo atenuar la música: {error}")
            motor.say(texto)
            motor.runAndWait()
            motor.stop()
            return True
        except Exception as error:
            print(f"[VOZ] Error reproduciendo respuesta: {error}")
            return False
        finally:
            if atenuado:
                try:
                    self.atenuador.restaurar()
                except Exception as error:
                    print(f"[VOZ] No se pudo restaurar la música: {error}")
            if motor is not None:
                try:
                    motor.stop()
                except Exception:
                    pass
                del motor
    def _hablar_neural(self, texto):
        """Voz neural: sintetiza (o reutiliza de la caché) y reproduce con la música atenuada."""
        try:
            datos = self.neural.sintetizar(texto)
        except Exception as error:
            print(f"[VOZ] Fallo de la voz neural ({error}); se usa la voz de Windows.")
            return False
        atenuado = False
        if self.atenuador is not None:
            try:
                self.atenuador.atenuar()
                atenuado = True
            except Exception as error:
                print(f"[VOZ] No se pudo atenuar la música: {error}")
        try:
            return self.neural.reproducir(datos, self.volumen_actual())
        finally:
            if atenuado:
                try:
                    self.atenuador.restaurar()
                except Exception as error:
                    print(f"[VOZ] No se pudo restaurar la música: {error}")
    def detener(self):
        """No mantiene un motor permanente; existe para que principal.py cierre sin errores."""
        return True
