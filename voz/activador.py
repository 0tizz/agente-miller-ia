"""MILLER · Activador de voz"""
import difflib
from functools import lru_cache
import json
import os
import re
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path
try:
    from utilidades import seguridad
except Exception:
    seguridad = None

@lru_cache(maxsize=2048)
def _normalizar_activacion(texto):
    return Activador._normalizar_sin_cache(texto)

class Activador:
    SIMILITUD_MINIMA = 0.84
    SIMILITUD_SEPARADA = 0.78
    # Máximo de palabras que puede ocupar la activación.
    MAX_PALABRAS_ACTIVACION = 3
    # Solo analizamos las primeras palabras de la frase.
    MAX_PALABRAS_FUZZY_INICIAL = 3
    # Longitud mínima razonable para una activación unida.
    LONGITUD_MINIMA_UNIDA = 4
    SIMILITUD_CANDIDATA = 0.55          # por debajo: ni siquiera se considera
    CONFIRMACIONES_NECESARIAS = 3       # apariciones para aprender por repetición
    VENTANA_REPETICION = 25.0           # s: "frase ignorada -> la repite con miller"
    SIMILITUD_ORDEN_REPETIDA = 0.60
    MAX_APRENDIDAS = 40
    # Palabras corrientes que jamás se aprenden como nombre.
    PALABRAS_PROHIBIDAS = {
        "mi", "mis", "me", "mil", "miles de", "mire", "mira", "miren", "mirar", "milla", "millas", "mejor",
        "mientras", "miel", "mitad", "mio", "mia", "millon", "millones", "militar", "mismo", "misma", "mire usted",
        "mi el", "mi le", "mi la", "el", "la", "le", "lee", "leer", "ella", "ellos", "ella le", "dile", "dime",
        "mil veces", "mil gracias", "milo", "mila", "mili", "mal", "muy", "mucho", "miercoles",
    }
    def __init__(self, palabra="miller", ruta_aprendizaje=None, aprender=True,
                 confirmaciones=None, al_aprender=None):
        self.palabra = self._normalizar(palabra)
        self.aprender_activo = bool(aprender)
        if confirmaciones:
            self.CONFIRMACIONES_NECESARIAS = max(1, int(confirmaciones))
        self.ruta_aprendizaje = Path(ruta_aprendizaje) if ruta_aprendizaje else None
        self.al_aprender = al_aprender          # callback(variante): p. ej. la iniciativa lo comunica
        self._lock_aprendizaje = threading.Lock()
        self._ultimo_rechazo = None             # (candidata, orden, instante)
        self.nuevas_aprendidas = []             # aprendidas en esta sesión (para informar)
        self.conocimiento = self._cargar_aprendizaje()
        # Las formas de fábrica son solo del nombre «miller»: con otro nombre, solo vale ese nombre.
        variaciones = set() if self.palabra != "miller" else {
            "miller",
            "miler",
            "miles",
            "mi les",
            "mil er",
            "mil ler",
            "mil leer",
            "mil le",
            "mil el",
            "mi ller",
            "mi ler",
            "mi leer",
            # OTRAS FORMAS FRECUENTES
            "miler",
            "miller",
            "miles",
            "mil ler",
            "mil leer",
            "mi ler",
            "mi leer",
            "mi ller",
        }
        # Normalizar variaciones.
        self.variaciones = {self._normalizar(variante) for variante in variaciones}
        self.variaciones.add(self.palabra)
        self.variaciones_base = set(self.variaciones)
        for variante in self.conocimiento["aprendidas"]:
            self.variaciones.add(self._normalizar(variante))
        self.variaciones_unidas = {self._unir_palabras(variante) for variante in self.variaciones}
        # Estado informativo.
        self.activado = False
    def _normalizar(self, texto):
        return _normalizar_activacion(texto) if texto is not None else ""
    @staticmethod
    def _normalizar_sin_cache(texto):
        if texto is None:
            return ""
        texto = str(texto).lower().strip()
        # Eliminar acentos.
        texto = unicodedata.normalize("NFD", texto)
        texto = "".join(caracter for caracter in texto if unicodedata.category(caracter) != "Mn")
        # Eliminar puntuación.
        texto = re.sub(r"[^\w\s]", " ", texto)
        # Normalizar espacios.
        texto = " ".join(texto.split())
        return texto
    def _unir_palabras(self, texto):
        texto = self._normalizar(texto)
        return texto.replace(" ", "")
    def obtener_palabra(self):
        return self.palabra
    def _similitud_palabra(self, palabra):
        """Calcula similitud entre una palabra reconocida y MILLER."""
        palabra = self._normalizar(palabra)
        if not palabra:
            return 0.0
        return difflib.SequenceMatcher(None, palabra, self.palabra).ratio()
    def _similitud_unida(self, texto):
        texto_unido = self._unir_palabras(texto)
        palabra_unida = self._unir_palabras(self.palabra)
        if not texto_unido:
            return 0.0
        if len(texto_unido) < self.LONGITUD_MINIMA_UNIDA:
            return 0.0
        return difflib.SequenceMatcher(None, texto_unido, palabra_unida).ratio()
    def _es_variacion_exacta(self, texto):
        """Comprueba si el texto corresponde exactamente a una variante conocida."""
        texto = self._normalizar(texto)
        if not texto:
            return False
        return (texto in self.variaciones)
    def _es_variacion_unida(self, texto):
        texto = self._normalizar(texto)
        if not texto:
            return False
        unido = self._unir_palabras(texto)
        return (unido in self.variaciones_unidas)
    def _es_variacion_aproximada(self, texto):
        texto = self._normalizar(texto)
        if not texto:
            return False
        # Variante exacta.
        if self._es_variacion_exacta(texto):
            return True
        # Variante unida.
        if self._es_variacion_unida(texto):
            return True
        if " " in texto:
            similitud_unida = (self._similitud_unida(texto))
            return (similitud_unida >= self.SIMILITUD_SEPARADA)
        # Comparación de una sola palabra.
        similitud = (self._similitud_palabra(texto))
        return (similitud >= self.SIMILITUD_MINIMA)
    def _obtener_candidatos_iniciales(self, palabras):
        candidatos = []
        limite = min(len(palabras), self.MAX_PALABRAS_ACTIVACION)
        for longitud in range(1, limite + 1):
            candidato = " ".join(palabras[:longitud])
            candidatos.append(candidato)
        return candidatos
    def _buscar_activacion(self, texto):
        texto = self._normalizar(texto)
        if not texto:
            return (False, -1, -1)
        palabras = texto.split()
        if not palabras:
            return (False, -1, -1)
        candidatos = (self._obtener_candidatos_iniciales(palabras))
        for longitud in range(min(self.MAX_PALABRAS_ACTIVACION, len(palabras)), 0, -1):
            candidato = " ".join(palabras[:longitud])
            if self._es_variacion_exacta(candidato):
                return (True, 0, longitud)
            if self._es_variacion_unida(candidato):
                return (True, 0, longitud)
        # 2. FUZZY CONTROLADO
        limite = min(len(candidatos), self.MAX_PALABRAS_FUZZY_INICIAL)
        for indice in range(limite - 1, -1, -1):
            candidato = candidatos[indice]
            if " " not in candidato:
                continue
            similitud = (self._similitud_unida(candidato))
            if (similitud >= self.SIMILITUD_SEPARADA):
                return (True, 0, indice + 1)
        primera = palabras[0]
        if self._es_variacion_aproximada(primera):
            return (True, 0, 1)
        return (False, -1, -1)
    def esta_activado(self, texto):
        """Devuelve True si MILLER está presente al comienzo de la frase."""
        encontrada, _, _ = (self._buscar_activacion(texto))
        return encontrada
    def extraer_orden(self, texto):
        texto = self._normalizar(texto)
        if not texto:
            return ""
        encontrada, _, fin = (self._buscar_activacion(texto))
        if not encontrada:
            return ""
        palabras = texto.split()
        orden = palabras[fin:]
        return " ".join(orden).strip()

    @staticmethod
    def _conocimiento_vacio():
        return {"version": 1, "aprendidas": {}, "candidatas": {}, "olvidadas": [], "usos": {}}
    def _cargar_aprendizaje(self):
        datos = self._conocimiento_vacio()
        if self.ruta_aprendizaje and self.ruta_aprendizaje.is_file():
            try:
                leido = (seguridad.leer_json(self.ruta_aprendizaje, {}) if seguridad is not None
                         else json.loads(self.ruta_aprendizaje.read_text(encoding="utf-8"))) or {}
                for clave, valor in datos.items():
                    if isinstance(leido.get(clave), type(valor)):
                        datos[clave] = leido[clave]
            except Exception as error:
                print(f"[ACTIVADOR] Aprendizaje del nombre ilegible, se empieza de cero: {error}")
        return datos
    def _guardar_aprendizaje(self):
        if not self.ruta_aprendizaje:
            return
        try:
            if seguridad is not None:
                seguridad.escribir_json(self.ruta_aprendizaje, self.conocimiento)
                return
            self.ruta_aprendizaje.parent.mkdir(parents=True, exist_ok=True)
            temporal = self.ruta_aprendizaje.with_suffix(".tmp")
            temporal.write_text(json.dumps(self.conocimiento, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporal, self.ruta_aprendizaje)
        except Exception as error:
            print(f"[ACTIVADOR] No se pudo guardar el aprendizaje del nombre: {error}")
    def _parecido(self, candidato):
        """Similitud de 0 a 1 entre un trozo de frase y el nombre."""
        candidato = self._normalizar(candidato)
        if " " in candidato:
            return self._similitud_unida(candidato)
        return self._similitud_palabra(candidato)
    def _es_aprendible(self, candidato):
        candidato = self._normalizar(candidato)
        unido = self._unir_palabras(candidato)
        if (not candidato or candidato in self.PALABRAS_PROHIBIDAS or unido in self.PALABRAS_PROHIBIDAS
                or candidato in self.conocimiento["olvidadas"] or len(unido) < self.LONGITUD_MINIMA_UNIDA):
            return False
        return unido[0] == self._unir_palabras(self.palabra)[0]       # empieza por la misma letra ("m")
    def _mejor_candidata(self, palabras):
        """Trozo inicial (1-2 palabras) más parecido al nombre, dentro de la zona gris."""
        mejor = None
        for longitud in (2, 1):
            if len(palabras) <= longitud:          # debe quedar una orden detrás
                continue
            trozo = " ".join(palabras[:longitud])
            if not self._es_aprendible(trozo):
                continue
            similitud = self._parecido(trozo)
            if self.SIMILITUD_CANDIDATA <= similitud and (mejor is None or similitud > mejor[1]):
                mejor = (trozo, similitud, " ".join(palabras[longitud:]))
        return mejor
    def aprender_variante(self, variante, motivo="aprendida"):
        """Añade una forma nueva de reconocer el nombre. Devuelve True si es nueva.
        Con el aprendizaje apagado (el nombre se pone al iniciar) no aprende nada."""
        if not self.aprender_activo:
            return False
        variante = self._normalizar(variante)
        if not variante or variante in self.variaciones or not self._es_aprendible(variante):
            return False
        with self._lock_aprendizaje:
            if len(self.conocimiento["aprendidas"]) >= self.MAX_APRENDIDAS:
                antigua = min(self.conocimiento["aprendidas"].items(), key=lambda x: x[1].get("usos", 0))[0]
                self.olvidar_variante(antigua, _bloqueado=True)
            self.conocimiento["aprendidas"][variante] = {
                "desde": datetime.now().isoformat(timespec="seconds"), "motivo": motivo, "usos": 0}
            self.conocimiento["candidatas"].pop(variante, None)
            self.variaciones.add(variante)
            self.variaciones_unidas.add(self._unir_palabras(variante))
            self.nuevas_aprendidas.append(variante)
            self._guardar_aprendizaje()
        print(f"[ACTIVADOR] 🧠 Nueva forma de mi nombre aprendida: '{variante}' ({motivo}).")
        if callable(self.al_aprender):
            try:
                self.al_aprender(variante)
            except Exception as error:
                print(f"[ACTIVADOR] Aviso de aprendizaje fallido: {error}")
        return True
    def olvidar_variante(self, variante, _bloqueado=False):
        """Quita una variante aprendida (las de fábrica no se tocan) y no la vuelve a aprender."""
        variante = self._normalizar(variante)
        if variante not in self.conocimiento["aprendidas"]:
            return False
        self.conocimiento["aprendidas"].pop(variante, None)
        if variante not in self.conocimiento["olvidadas"]:
            self.conocimiento["olvidadas"].append(variante)
        if variante not in self.variaciones_base:
            self.variaciones.discard(variante)
            self.variaciones_unidas = {self._unir_palabras(v) for v in self.variaciones}
        if not _bloqueado:
            self._guardar_aprendizaje()
        return True
    def variantes_aprendidas(self):
        return sorted(self.conocimiento["aprendidas"])
    def _registrar_rechazo(self, palabras):
        """Frase ignorada: si empieza parecido al nombre, se anota como candidata."""
        if not self.aprender_activo:
            return
        mejor = self._mejor_candidata(palabras)
        if not mejor:
            self._ultimo_rechazo = None
            return
        trozo, similitud, orden = mejor
        self._ultimo_rechazo = (trozo, orden, time.monotonic())
        with self._lock_aprendizaje:
            c = self.conocimiento["candidatas"].setdefault(trozo, {"vistas": 0, "similitud": round(similitud, 2)})
            c["vistas"] += 1
            c["ultima"] = datetime.now().isoformat(timespec="seconds")
            vistas = c["vistas"]
            if len(self.conocimiento["candidatas"]) > 100:        # conserva las más vistas
                for k, _ in sorted(self.conocimiento["candidatas"].items(), key=lambda x: x[1].get("vistas", 0))[:20]:
                    self.conocimiento["candidatas"].pop(k, None)
            self._guardar_aprendizaje()
        if vistas >= self.CONFIRMACIONES_NECESARIAS:
            self.aprender_variante(trozo, f"oída {vistas} veces antes de una orden")
    def _registrar_activacion(self, palabras, fin):
        """Frase aceptada: refuerza la variante usada y comprueba si la frase anterior era una repetición."""
        if not self.aprender_activo:
            return
        usada = " ".join(palabras[:fin])
        if usada in self.conocimiento["aprendidas"]:
            self.conocimiento["aprendidas"][usada]["usos"] = self.conocimiento["aprendidas"][usada].get("usos", 0) + 1
            self._guardar_aprendizaje()
        rechazo, self._ultimo_rechazo = self._ultimo_rechazo, None
        if not rechazo:
            return
        trozo, orden_rechazada, instante = rechazo
        orden = " ".join(palabras[fin:])
        if time.monotonic() - instante > self.VENTANA_REPETICION or not orden:
            return
        if difflib.SequenceMatcher(None, orden, orden_rechazada).ratio() >= self.SIMILITUD_ORDEN_REPETIDA:
            self.aprender_variante(trozo, "el usuario repitió la orden con mi nombre")
    def activar(self):
        self.activado = True
    def desactivar(self):
        self.activado = False
    def esta_en_modo_activo(self):
        return self.activado
    def procesar(self, texto):
        texto = self._normalizar(texto)
        if not texto:
            self.desactivar()
            return {"activado": False, "orden": "", "estado": False}
        encontrada, inicio, fin = (self._buscar_activacion(texto))
        if not encontrada:
            self.desactivar()
            try:
                self._registrar_rechazo(texto.split())
            except Exception as error:
                print(f"[ACTIVADOR] Error aprendiendo el nombre: {error}")
            return {"activado": False, "orden": "", "estado": False}
        palabras = texto.split()
        try:
            self._registrar_activacion(palabras, fin)
        except Exception as error:
            print(f"[ACTIVADOR] Error aprendiendo el nombre: {error}")
        orden = palabras[fin:]
        orden = " ".join(orden).strip()
        self.activar()
        resultado = {"activado": True, "orden": orden, "estado": True}
        self.desactivar()
        return resultado
    def informacion(self):
        return {"palabra": self.palabra, "variaciones": sorted(self.variaciones), "activado": self.activado,
                "aprendidas": self.variantes_aprendidas(),
                "candidatas": dict(self.conocimiento["candidatas"])}
