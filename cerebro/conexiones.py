"""MILLER · Conexiones: qué recuerdos se relacionan entre sí (comparten palabras con sentido).

Es una red ligera: cada recuerdo es un nodo y dos recuerdos se unen si comparten suficientes palabras.
Se calcula con un índice por palabra (no compara todos contra todos) y solo se recalcula cuando cambian los recuerdos.
Es información para MILLER y para usted: no cambia cómo se buscan los recuerdos.
"""
import threading
from collections import defaultdict

MINIMO_LETRAS = 4          # palabras más cortas no cuentan (de, la, que…)
UMBRAL = 0.2               # proporción de palabras compartidas (Jaccard) para unir dos recuerdos
MAXIMO_RECUERDOS = 400     # solo los más recientes
MAXIMA_FRECUENCIA = 0.2    # una palabra que aparece en más de este porcentaje de recuerdos no une nada


class Conexiones:
    def __init__(self, memoria):
        self.memoria = memoria
        self._cerrojo = threading.Lock()
        self._firma = None
        self._textos = []
        self._refs = []
        self._palabras = []
        self._aristas = {}

    def _palabras_de(self, texto):
        return {p for p in self.memoria.obtener_palabras(texto) if len(p) >= MINIMO_LETRAS}

    def _actualizar(self):
        refs = self.memoria.obtener_recuerdos()[-MAXIMO_RECUERDOS:]
        textos = [str(r.get("contenido", "")) for r in refs]
        firma = (len(textos), hash(tuple(textos)))
        with self._cerrojo:
            if firma == self._firma:
                return
            palabras = [self._palabras_de(t) for t in textos]
            indice = defaultdict(list)
            for i, ps in enumerate(palabras):
                for p in ps:
                    indice[p].append(i)
            tope = max(6, int(len(textos) * MAXIMA_FRECUENCIA))
            aristas = {}
            for ids in indice.values():
                if len(ids) < 2 or len(ids) > tope:
                    continue
                for a in range(len(ids)):
                    for b in range(a + 1, len(ids)):
                        i, j = ids[a], ids[b]
                        if (i, j) in aristas:
                            continue
                        union = palabras[i] | palabras[j]
                        if not union:
                            continue
                        similitud = len(palabras[i] & palabras[j]) / len(union)
                        if similitud >= UMBRAL:
                            aristas[(i, j)] = round(similitud, 2)
            self._textos, self._refs, self._palabras, self._aristas, self._firma = textos, refs, palabras, aristas, firma

    def cantidad(self):
        """Cuántas conexiones hay entre los recuerdos."""
        self._actualizar()
        return len(self._aristas)

    def pares(self):
        """Pares de recuerdos (los mismos dicts de la memoria) que comparten palabras con sentido.
        Es solo una pista: quien quiera olvidar tiene que comprobar la similitud de cada par."""
        self._actualizar()
        return [(self._refs[i], self._refs[j]) for (i, j) in self._aristas]

    def recuerdos_conectados(self):
        self._actualizar()
        return len({i for par in self._aristas for i in par})

    def asociados(self, texto, limite=3):
        """Recuerdos que comparten al menos dos palabras con el texto, del más parecido al menos."""
        self._actualizar()
        buscadas = self._palabras_de(texto)
        if not buscadas:
            return []
        puntuados = []
        for i, ps in enumerate(self._palabras):
            comunes = buscadas & ps
            if len(comunes) >= 2:
                puntuados.append((len(comunes) / len(buscadas | ps), self._textos[i]))
        puntuados.sort(key=lambda par: -par[0])
        return [texto_recuerdo for _, texto_recuerdo in puntuados[:limite]]

    def resumen(self):
        self._actualizar()
        n, e = len(self._textos), len(self._aristas)
        if not n:
            return "Todavía no tengo recuerdos que relacionar."
        if not e:
            return f"Entre mis {n} recuerdos todavía no veo conexiones."
        return (f"Veo {e} {'conexión' if e == 1 else 'conexiones'} entre mis {n} recuerdos; "
                f"{self.recuerdos_conectados()} de ellos están relacionados.")
