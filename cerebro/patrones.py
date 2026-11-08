"""MILLER · Reconocimiento de patrones: corrige palabras mal oídas y descubre rutinas del usuario."""
import re
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from difflib import get_close_matches
from functools import lru_cache
from pathlib import Path

_PYTHON = {"self", "def", "return", "none", "true", "false", "elif", "else", "import", "from", "class", "try",
           "except", "lambda", "while", "for", "not", "and", "with", "print", "str", "int", "len", "dict", "list",
           "getattr", "hasattr", "isinstance", "texto", "intencion", "respuesta", "normalizado", "fullmatch", "search"}
# Intenciones que no son una rutina (preguntarle cómo está no es un hábito que automatizar).
NO_RUTINA = {"DESCONOCIDA", "SALIR", "SALUDO", "EMOCION", "PERSONALIDAD", "IDENTIDAD", "HORA", "FECHA", "AYUDA",
             "NOVEDADES", "EQUILIBRIO", "AUTOCONOCIMIENTO", "ELOGIO", "REPROCHE", "CANCELAR_LIMPIEZA", "CONFIRMAR_LIMPIEZA", "BORRAR_CANCION", "VACIAR_PAPELERA",
             "VACIAR_CUARENTENA", "OLVIDAR_NOMBRE", "ENSENAR_ORDEN", "CALCULAR", "ALARMA"}


@lru_cache(maxsize=4096)
def _plano(texto):
    texto = unicodedata.normalize("NFD", str(texto).lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")     # igual que el cerebro (ñ -> n)


class Corrector:
    """Vocabulario de órdenes: las palabras de las reglas del cerebro y las frases que ya funcionaron.
    Una palabra desconocida se cambia por la más parecida del vocabulario (p. ej. «reprodusir» -> «reproducir»)."""
    MINIMO_LETRAS, PARECIDO = 4, 0.78

    def __init__(self, fuentes=(), frases=()):
        self._fuentes = [Path(f) for f in fuentes]
        self._extra = set()
        self._vocabulario = None
        self.agregar_frases(frases)

    def _cargar(self):
        palabras = set()
        for fuente in self._fuentes:
            try:
                palabras.update(re.findall(r"[a-z]{3,}", _plano(fuente.read_text(encoding="utf-8"))))
            except OSError:
                pass
        self._vocabulario = frozenset((palabras | self._extra) - _PYTHON)
        self._ordenado = sorted(self._vocabulario)
        self.corregir_palabra.cache_clear()

    def agregar_frases(self, frases):
        nuevas = {p for f in frases for p in re.findall(r"[a-z]{3,}", _plano(f))} - self._extra
        if nuevas:
            self._extra |= nuevas
            if self._vocabulario is not None:
                self._vocabulario = None                  # se reconstruye en la próxima corrección

    @property
    def vocabulario(self):
        if self._vocabulario is None:
            self._cargar()
        return self._vocabulario

    @lru_cache(maxsize=2048)
    def corregir_palabra(self, palabra):
        if len(palabra) < self.MINIMO_LETRAS or palabra.isdigit() or palabra in self.vocabulario:
            return palabra
        candidatas = [p for p in self._ordenado if abs(len(p) - len(palabra)) <= 2 and p[0] == palabra[0]]
        mejor = get_close_matches(palabra, candidatas, n=1, cutoff=self.PARECIDO)
        return mejor[0] if mejor else palabra

    def corregir(self, frase):
        """Devuelve la frase con las palabras mal oídas corregidas (o la misma si no hay nada que corregir)."""
        palabras = _plano(frase).split()
        vocabulario = self.vocabulario
        return " ".join(self.corregir_palabra(p) if p not in vocabulario else p for p in palabras)

    def __hash__(self):
        return id(self)


class Rutinas:
    """Descubre hábitos en el historial: la misma orden, a la misma hora, en 3 o más días distintos.
    El cálculo se cachea una hora: el historial solo crece de a poco."""
    MINIMO_DIAS, VIGENCIA = 3, 3600.0

    def __init__(self):
        self._cache, self._calculado, self._tamano = [], 0.0, -1

    def detectar(self, historial, ahora=None):
        ahora_mono = time.monotonic()
        if (self._tamano == len(historial) or ahora_mono - self._calculado < self.VIGENCIA) and self._tamano >= 0:
            return self._cache
        dias, frases = defaultdict(set), defaultdict(Counter)
        for e in historial or ():
            intencion = e.get("intencion")
            if not e.get("ok", True) or intencion in NO_RUTINA:
                continue
            try:
                fecha = datetime.fromisoformat(str(e.get("fecha")))
            except ValueError:
                continue
            clave = (intencion, fecha.hour)
            dias[clave].add(fecha.date())
            frases[clave][str(e.get("entrada", ""))] += 1
        patrones = [{"intencion": i, "hora": h, "dias": len(d), "frase": frases[(i, h)].most_common(1)[0][0]}
                    for (i, h), d in dias.items() if len(d) >= self.MINIMO_DIAS]
        patrones.sort(key=lambda p: (-p["dias"], p["hora"]))
        self._cache, self._calculado, self._tamano = patrones, ahora_mono, len(historial or ())
        return patrones

    def para_ahora(self, historial, ahora=None):
        """Rutinas de esta hora que hoy todavía no se han hecho."""
        ahora = ahora or datetime.now()
        hoy = ahora.date()
        hechas = set()
        for e in historial or ():
            try:
                fecha = datetime.fromisoformat(str(e.get("fecha")))
            except ValueError:
                continue
            if fecha.date() == hoy:
                hechas.add(e.get("intencion"))
        return [p for p in self.detectar(historial) if p["hora"] == ahora.hour and p["intencion"] not in hechas]
