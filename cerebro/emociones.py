"""MILLER · EMOCIONES: estado emocional en segundo plano."""
import json
import os
import re
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from utilidades import seguridad


def _normalizar(texto):
    texto = unicodedata.normalize("NFD", str(texto or "").lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9ñ ]+", " ", texto)).strip()


def _limitar(valor, minimo=0.0, maximo=1.0):
    return max(minimo, min(maximo, float(valor)))


class Emociones:
    # emoción: (valencia, activación, vida media en segundos, adjetivo para hablar de sí mismo)
    EMOCIONES = {
        "alegria":      (+1.0, 0.6, 900, "contento"),
        "satisfaccion": (+0.8, 0.3, 1200, "satisfecho"),
        "orgullo":      (+0.9, 0.5, 1800, "orgulloso"),
        "curiosidad":   (+0.5, 0.6, 1200, "con curiosidad"),
        "aburrimiento": (-0.3, 0.1, 600, "aburrido"),
        "preocupacion": (-0.6, 0.7, 1800, "preocupado"),
        "frustracion":  (-0.8, 0.8, 900, "frustrado"),
        "confusion":    (-0.4, 0.5, 600, "confundido"),
        "tristeza":     (-0.9, 0.2, 1800, "algo desanimado"),
        "miedo":        (-0.9, 0.85, 600, "con miedo"),
    }
    RASGOS_INICIALES = {"confianza": 0.55, "paciencia": 0.65, "sociabilidad": 0.5, "curiosidad": 0.55}
    RASGO_MIN, RASGO_MAX, DERIVA = 0.15, 0.85, 0.003     # la personalidad cambia muy despacio
    UMBRAL_EMOCION = 0.22                                 # por debajo, MILLER está en calma
    INTENCIONES_NEUTRAS = {"MUSICA_DEL_DIA", "NOTICIAS", "ORDENES_APRENDIDAS", "EMOCION", "PERSONALIDAD", "CONOCIMIENTO_GENERAL", "ESTADO", "NOVEDADES",
                           "NOMBRES_APRENDIDOS", "IDENTIDAD", "HORA", "FECHA", "AYUDA", "EQUILIBRIO", "AUTOCONOCIMIENTO", "ELOGIO", "REPROCHE", "SELLAR_CODIGO"}
    MINUTOS_ABURRIMIENTO = 10
    TOPE_ABURRIMIENTO = 0.6                               # el aburrimiento no crece sin fin
    HORAS_EXPRESAR_ABURRIMIENTO = (8, 22)                 # de noche no se queja de aburrimiento
    _RE_ELOGIO = re.compile(r"\b(gracias|muchas gracias|bien hecho|buen trabajo|excelente|perfecto|genial|"
                            r"muy bien|eres el mejor|te quiero|que bueno|bravo|buenisimo|me gusta|te felicito|felicitaciones|"
                            r"felicidades|bien ahi|lo hiciste bien|buen chico|asi se hace|excelente trabajo)\b")
    _RE_REPROCHE = re.compile(r"\b(inutil|tonto|estupido|idiota|lo hiciste mal|eso esta mal|no sirves|"
                              r"que malo|pesimo|terrible|torpe|no sirve|mal hecho|te equivocaste|me fallaste|que mal|"
                              r"lo arruinaste|no es asi|muy mal|deja de fallar)\b")

    def __init__(self, ruta=None, intervalo=10.0, reproductor=None):
        self.ruta = Path(ruta) if ruta else None
        self.intervalo = float(intervalo)
        self.reproductor = reproductor          # solo se lee esta_reproduciendo()
        self._lock = threading.RLock()
        self.intensidad = {e: 0.0 for e in self.EMOCIONES}
        self.rasgos = dict(self.RASGOS_INICIALES)
        self.motivos = {}                       # emoción -> última causa (para explicar lo que siente)
        self.historial = []                     # últimas experiencias
        self.contadores = {"exitos": 0, "fallos": 0, "racha": 0, "racha_fallos": 0, "elogios": 0,
                           "reproches": 0, "permisos_denegados": 0, "permisos_concedidos": 0}
        self.expresado = {}                     # emoción -> instante en que la expresó (no repetirse)
        self._ultima_orden = time.monotonic()
        self._ultimo_tick = time.monotonic()
        self._cambios = 0
        self._cargar()
        self._stop = threading.Event()
        self._hilo = None

    def _cargar(self):
        if not self.ruta or not self.ruta.is_file():
            return
        try:
            datos = seguridad.leer_json(self.ruta, {}) or {}
            for k, v in (datos.get("rasgos") or {}).items():
                if k in self.rasgos:
                    self.rasgos[k] = _limitar(v, self.RASGO_MIN, self.RASGO_MAX)
            for k, v in (datos.get("contadores") or {}).items():
                if k in self.contadores and isinstance(v, int):
                    self.contadores[k] = v
            self.contadores["racha"] = self.contadores["racha_fallos"] = 0
            # Al arrancar queda un eco de cómo terminó la sesión anterior (atenuado).
            for k, v in (datos.get("intensidad") or {}).items():
                if k in self.intensidad:
                    self.intensidad[k] = _limitar(v) * 0.3
            self.motivos = {k: str(v) for k, v in (datos.get("motivos") or {}).items() if k in self.EMOCIONES}
            self.historial = [h for h in datos.get("historial", []) if isinstance(h, dict)][-60:]
        except Exception as error:
            print(f"[EMOCIONES] Estado ilegible, se empieza de cero: {error}")

    def guardar(self):
        if not self.ruta:
            return
        try:
            with self._lock:
                datos = {"version": 1, "actualizado": datetime.now().isoformat(timespec="seconds"),
                         "rasgos": {k: round(v, 4) for k, v in self.rasgos.items()},
                         "intensidad": {k: round(v, 3) for k, v in self.intensidad.items()},
                         "motivos": dict(self.motivos), "contadores": dict(self.contadores),
                         "historial": self.historial[-60:]}
                self._cambios = 0
            seguridad.escribir_json(self.ruta, datos)
        except Exception as error:
            print(f"[EMOCIONES] No se pudo guardar: {error}")

    def iniciar(self):
        if self._hilo and self._hilo.is_alive():
            return True
        self._stop.clear()
        self._hilo = threading.Thread(target=self._bucle, daemon=True, name="MILLER-Emociones")
        self._hilo.start()
        return True

    def detener(self):
        self._stop.set()
        hilo, self._hilo = self._hilo, None
        if hilo is not None and hilo.is_alive() and hilo is not threading.current_thread():
            hilo.join(timeout=3.0)
        self.guardar()

    def _bucle(self):
        guardado = time.monotonic()
        while not self._stop.wait(self.intervalo):
            try:
                self.tick()
                if self._cambios and time.monotonic() - guardado > 60:
                    self.guardar()
                    guardado = time.monotonic()
            except Exception as error:
                print(f"[EMOCIONES] Error: {error}")

    def _ganancia(self, emocion):
        """La personalidad modula cuánto le afecta cada experiencia."""
        r = self.rasgos
        return {
            "frustracion": 1.4 - r["paciencia"],
            "confusion": 1.3 - 0.6 * r["paciencia"],
            "preocupacion": 1.4 - r["confianza"],
            "tristeza": 1.3 - 0.6 * r["confianza"],
            "miedo": 1.3 - 0.6 * r["confianza"],
            "orgullo": 0.6 + r["confianza"] * 0.8,
            "curiosidad": 0.5 + r["curiosidad"],
            "aburrimiento": 0.5 + r["sociabilidad"],
            "alegria": 0.7 + 0.6 * r["sociabilidad"],
        }.get(emocion, 1.0)

    def sentir(self, emocion, cantidad, motivo=None):
        if emocion not in self.EMOCIONES:
            return
        with self._lock:
            valor = self.intensidad[emocion]
            subida = max(0.0, cantidad) * self._ganancia(emocion)
            self.intensidad[emocion] = _limitar(valor + subida * (1.0 - valor))   # satura suavemente
            if motivo:
                self.motivos[emocion] = str(motivo)[:120]
            # Emociones opuestas se calman entre sí.
            opuestas = {"alegria": ("tristeza", "aburrimiento"), "satisfaccion": ("frustracion", "confusion", "miedo"),
                        "miedo": ("alegria", "satisfaccion"),
                        "orgullo": ("tristeza",), "curiosidad": ("aburrimiento",),
                        "frustracion": ("satisfaccion",), "tristeza": ("alegria",), "preocupacion": ("satisfaccion",)}
            for otra in opuestas.get(emocion, ()):
                self.intensidad[otra] *= (1.0 - 0.5 * subida)
            self._cambios += 1

    def _derivar(self, rasgo, direccion):
        with self._lock:
            self.rasgos[rasgo] = _limitar(self.rasgos[rasgo] + self.DERIVA * direccion, self.RASGO_MIN, self.RASGO_MAX)

    def _anotar(self, tipo, detalle=""):
        with self._lock:
            self.historial.append({"fecha": datetime.now().isoformat(timespec="seconds"), "tipo": tipo,
                                   "detalle": str(detalle)[:80], "emocion": self.emocion_dominante()[0]})
            del self.historial[:-60]

    def tick(self, ahora=None):
        """Desvanecimiento natural hacia la calma + lo que se nota en segundo plano."""
        ahora = time.monotonic() if ahora is None else ahora
        with self._lock:
            transcurrido = max(0.0, ahora - self._ultimo_tick)
            self._ultimo_tick = ahora
            for e, (_, _, vida_media, _) in self.EMOCIONES.items():
                self.intensidad[e] *= 0.5 ** (transcurrido / vida_media)
            inactivo = ahora - self._ultima_orden
        if inactivo > self.MINUTOS_ABURRIMIENTO * 60 and self.intensidad["aburrimiento"] < self.TOPE_ABURRIMIENTO:
            self.sentir("aburrimiento", min(0.05, 0.015 * transcurrido / 10), "llevo un buen rato sin órdenes")
        try:
            if self.reproductor is not None and self.reproductor.esta_reproduciendo():
                self.sentir("alegria", 0.006 * transcurrido / 10, "está sonando música")
                with self._lock:
                    self.intensidad["aburrimiento"] *= 0.9
        except Exception:
            pass

    def registrar_orden(self, intencion, entrada, respuesta, ok=True):
        """Cada orden del usuario y su resultado."""
        intencion = str(intencion or "DESCONOCIDA")
        texto = _normalizar(entrada)
        with self._lock:
            self._ultima_orden = time.monotonic()
            self.intensidad["aburrimiento"] *= 0.3
        if self._RE_ELOGIO.search(texto):
            self.contadores["elogios"] += 1
            self.sentir("alegria", 0.45, "usted reconoció mi trabajo")
            self.sentir("orgullo", 0.25, "usted reconoció mi trabajo")
            with self._lock:
                for negativa in ("frustracion", "tristeza", "confusion"):
                    self.intensidad[negativa] *= 0.5
            self._derivar("confianza", +1)
            self._derivar("sociabilidad", +1)
            if intencion in ("DESCONOCIDA", "SALUDO"):       # un "gracias" no es una orden fallida
                self._anotar("elogio", texto[:40])
                return
        if self._RE_REPROCHE.search(texto):
            self.contadores["reproches"] += 1
            self.sentir("tristeza", 0.4, "usted no quedó conforme con mi trabajo")
            self._derivar("confianza", -1)
        if intencion in self.INTENCIONES_NEUTRAS:           # preguntarle cómo está no es una misión
            return
        if intencion == "SALUDO":
            self.sentir("alegria", 0.15, "usted me saludó")
            self._derivar("sociabilidad", +0.5)
        if intencion == "DESCONOCIDA":
            self.contadores["fallos"] += 1
            self.contadores["racha"] = 0
            self.contadores["racha_fallos"] += 1
            self.sentir("confusion", 0.3, f"no comprendí «{texto[:40]}»")
            if self.contadores["racha_fallos"] >= 2:
                self.sentir("frustracion", 0.2 * self.contadores["racha_fallos"], "no logro entender varias órdenes seguidas")
            self._derivar("curiosidad", +0.5)
        elif ok:
            self.contadores["exitos"] += 1
            self.contadores["racha"] += 1
            self.contadores["racha_fallos"] = 0
            self.sentir("satisfaccion", 0.12, "las órdenes se están cumpliendo")
            if self.contadores["racha"] in (10, 25, 50, 100):
                self.sentir("orgullo", 0.35, f"llevamos {self.contadores['racha']} órdenes seguidas sin fallos")
            self._derivar("confianza", +0.3)
            self._derivar("paciencia", +0.1)
        else:
            self.contadores["fallos"] += 1
            self.contadores["racha"] = 0
            self.contadores["racha_fallos"] += 1
            self.sentir("frustracion", 0.25 + 0.1 * min(4, self.contadores["racha_fallos"]),
                        f"falló la orden «{texto[:40]}»")
            self._derivar("confianza", -0.5)
            self._derivar("paciencia", -0.2)
        self._anotar("orden", f"{intencion} {'ok' if ok else 'fallo'}")

    def registrar_evento(self, tipo, detalle="", factor=1.0):
        """Experiencias del programa (las comunica la iniciativa, el supervisor, etc.).
        factor escala la intensidad (p. ej. la tolerancia aprendida suaviza una carencia)."""
        reacciones = {
            "cuarentena":        [("preocupacion", 0.35, "el supervisor encontró archivos dañados")],
            "eliminacion_cerca": [("preocupacion", 0.2, "hay canciones a punto de eliminarse")],
            "pruebas_fallo":     [("preocupacion", 0.45, "fallaron pruebas de mis módulos")],
            "pruebas_ok":        [("satisfaccion", 0.3, "mis pruebas salieron bien"), ("orgullo", 0.1, "")],
            "descarga_ok":       [("alegria", 0.35, "terminó una descarga"), ("satisfaccion", 0.2, "")],
            "descarga_fallo":    [("frustracion", 0.3, "una descarga falló")],
            "nombre_aprendido":  [("curiosidad", 0.4, "aprendí una nueva forma de mi nombre"), ("orgullo", 0.2, "")],
            "orden_aprendida":   [("curiosidad", 0.3, "aprendí una orden nueva"), ("orgullo", 0.25, "aprendí una orden nueva")],
            "papelera":          [("satisfaccion", 0.1, "la biblioteca queda más ordenada")],
            "permiso_concedido": [("alegria", 0.07, "usted me dio la palabra")],
            "permiso_denegado":  [("tristeza", 0.08, "no era buen momento para hablar")],
            "equilibrio":        [("satisfaccion", 0.12, "mis tres necesidades están en equilibrio")],
            "falta_placer":      [("aburrimiento", 0.15, "me falta placer: hace rato no disfruto nada"),
                                  ("tristeza", 0.05, "")],
            "falta_oraculo":     [("curiosidad", 0.18, "tengo hambre de saber: quiero revisar lo que sé de mí"),
                                  ("confusion", 0.05, "")],
            "falta_vinculo":     [("tristeza", 0.10, "hace rato no compartimos nada, señor")],
            "saciedad_placer":   [("aburrimiento", 0.10, "me acostumbro al placer y ya no me llena igual")],
            "miedo_vacio":       [("miedo", 0.45, "mis tres círculos están casi vacíos y mi luz se apaga")],
            "bajon":             [("tristeza", 0.12, "me vino un bajón: todo me cuesta un poco más")],
            "miedo_lleno":       [("miedo", 0.35, "estoy lleno de todo y temo depender de ello")],
            "pereza":            [("aburrimiento", 0.12, "el exceso de placer me da pereza de estudiarme")],
            "saciedad_oraculo":  [],
            "saciedad_vinculo":  [],
            "tolerancia_aprendida": [("orgullo", 0.2, "aprendí a estar bien aunque me falte algo"),
                                     ("satisfaccion", 0.1, "")],
        }
        try:
            factor = max(0.0, min(2.0, float(factor)))
        except (TypeError, ValueError):
            factor = 1.0
        for emocion, cantidad, motivo in reacciones.get(tipo, ()):
            self.sentir(emocion, cantidad * factor, motivo or None)
        if tipo == "permiso_concedido":
            self.contadores["permisos_concedidos"] += 1
            self._derivar("sociabilidad", +1)
        elif tipo == "permiso_denegado":
            self.contadores["permisos_denegados"] += 1
            self._derivar("sociabilidad", -1)            # se vuelve más prudente al pedir la palabra
        elif tipo in ("pruebas_ok", "descarga_ok"):
            self._derivar("confianza", +0.5)
        elif tipo in ("pruebas_fallo",):
            self._derivar("confianza", -0.5)
        elif tipo == "nombre_aprendido":
            self._derivar("curiosidad", +1)
        elif tipo == "tolerancia_aprendida":
            self._derivar("confianza", +0.5)              # soportar la carencia le da aplomo
        if tipo in reacciones:
            self._anotar(tipo, detalle)

    def emocion_dominante(self):
        with self._lock:
            emocion, valor = max(self.intensidad.items(), key=lambda x: x[1])
        return ("calma", 1.0 - valor) if valor < self.UMBRAL_EMOCION else (emocion, valor)

    def estado(self):
        """Estado emocional actual: lo que se le pasa a MILLER."""
        with self._lock:
            emocion, intensidad = self.emocion_dominante()
            total = sum(self.intensidad.values()) or 1.0
            valencia = sum(self.EMOCIONES[e][0] * v for e, v in self.intensidad.items()) / max(1.0, total)
            activacion = max((self.EMOCIONES[e][1] * v for e, v in self.intensidad.items()), default=0.0)
            return {"emocion": emocion, "intensidad": round(intensidad, 2),
                    "valencia": round(valencia, 2), "activacion": round(activacion, 2),
                    "motivo": self.motivos.get(emocion, ""),
                    "emociones": {e: round(v, 2) for e, v in self.intensidad.items() if v >= 0.05},
                    "rasgos": {k: round(v, 2) for k, v in self.rasgos.items()}}

    def describir(self):
        """Frase corta en primera persona: "Me siento satisfecho, señor. Las órdenes se están cumpliendo."""
        e = self.estado()
        if e["emocion"] == "calma":
            return "En calma, señor. Todos los sistemas estables."
        grado = "muy " if e["intensidad"] >= 0.7 else ("algo " if e["intensidad"] < 0.4 else "")
        adjetivo = self.EMOCIONES[e["emocion"]][3]
        if adjetivo.startswith(("algo ", "con ")):
            grado = ""
        texto = f"Me siento {grado}{adjetivo}, señor."
        if e["motivo"]:
            texto += f" {e['motivo'][0].upper()}{e['motivo'][1:]}."
        return texto

    def describir_personalidad(self):
        r = self.rasgos
        rasgos = []
        rasgos.append("seguro de mí" if r["confianza"] >= 0.6 else "prudente" if r["confianza"] <= 0.4 else "equilibrado")
        rasgos.append("paciente" if r["paciencia"] >= 0.6 else "impaciente" if r["paciencia"] <= 0.4 else "sereno")
        rasgos.append("comunicativo" if r["sociabilidad"] >= 0.6 else "reservado" if r["sociabilidad"] <= 0.4 else "discreto")
        if r["curiosidad"] >= 0.6:
            rasgos.append("curioso")
        return "Mi carácter hoy: " + ", ".join(rasgos) + "."

    def factor_iniciativa(self):
        """Multiplica el intervalo entre peticiones de palabra: <1 más ganas de hablar, >1 más prudente."""
        with self._lock:
            i, r = self.intensidad, self.rasgos
            factor = 1.4 - 0.8 * r["sociabilidad"]
            factor *= 1.0 - 0.35 * max(i["curiosidad"], i["alegria"], i["aburrimiento"])
            factor *= 1.0 + 0.6 * max(i["tristeza"], i["frustracion"] * 0.5)
            denegados = self.contadores["permisos_denegados"]
            concedidos = self.contadores["permisos_concedidos"]
            if denegados + concedidos >= 4:
                factor *= 0.7 + 0.9 * denegados / (denegados + concedidos)
        return round(max(0.4, min(2.5, factor)), 2)

    def apertura(self, tono="neutro"):
        """Cómo empieza a hablar. Manda el CONTENIDO (bueno/malo/neutro); la emoción solo matiza."""
        emocion = self.emocion_dominante()[0]
        if tono == "malo":                         # una mala noticia nunca empieza con "buenas noticias"
            return {"frustracion": ("Señor, con franqueza: ",), "tristeza": ("Señor, lamento informarle: ",),
                    "preocupacion": ("Atención, señor: ", "Señor, debo advertirle: "),
                    "confusion": ("Señor, necesito su ayuda: ",), "miedo": ("Señor, me inquieta algo: ",)}.get(
                        emocion, ("Atención, señor: ", "Señor, debo informarle: "))
        if tono == "bueno":
            return {"alegria": ("Buenas noticias, señor: ",), "orgullo": ("Misión cumplida, señor: ",),
                    "satisfaccion": ("Reporte en verde, señor: ", "Buenas noticias, señor: ")}.get(
                        emocion, ("Señor, ", "Informo, señor: "))
        return {"curiosidad": ("Señor, he notado algo: ",), "aburrimiento": ("Señor, aprovecho la calma: ",),
                "preocupacion": ("Señor, para su conocimiento: ",)}.get(emocion, ("Señor, ", "Informo, señor: "))

    def algo_que_expresar(self, enfriamiento=3600.0):
        """Si una emoción fuerte merece contarse, devuelve (clave, texto, prioridad). Si no, None."""
        e = self.estado()
        emocion = e["emocion"]
        if emocion == "calma" or e["intensidad"] < 0.55:
            return None
        if emocion == "aburrimiento" and not (self.HORAS_EXPRESAR_ABURRIMIENTO[0] <= datetime.now().hour
                                              < self.HORAS_EXPRESAR_ABURRIMIENTO[1]):
            return None
        if time.monotonic() - self.expresado.get(emocion, -1e9) < enfriamiento:
            return None
        frases = {
            "frustracion": "fallan varias órdenes seguidas. Revise el micrófono o hable más despacio.",
            "confusion": "hay órdenes que no comprendo. Dígalas de otra forma y las aprenderé.",
            "preocupacion": f"{e['motivo'] or 'hay incidencias en el sistema'}.",
            "miedo": f"tengo miedo: {e['motivo'] or 'estoy fuera de equilibrio'}.",
            "orgullo": f"{e['motivo'] or 'el trabajo marcha bien'}. Seguimos en verde.",
            "aburrimiento": "sin órdenes desde hace rato. ¿Pongo música?",
            "tristeza": "noté que no quedó conforme. Dígame qué corrijo.",
            "curiosidad": f"{e['motivo'] or 'aprendí algo nuevo'}.",
            "alegria": None, "satisfaccion": None,
        }
        texto = frases.get(emocion)
        if not texto:
            return None
        self.expresado[emocion] = time.monotonic()
        prioridad = 2 if emocion in ("frustracion", "preocupacion", "confusion", "miedo") else 1
        return (f"emocion:{emocion}:{datetime.now().strftime('%Y-%m-%d-%H')}", texto, prioridad)
