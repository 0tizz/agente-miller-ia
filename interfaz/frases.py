"""MILLER · Juego de ordenar palabras: con las palabras de su pensamiento arma frases para la cascada.

Aprende qué palabra suele seguir a cuál (pares seguidos en lo que oye, dice y piensa) y juega a
ordenarlas: unas veces repite un trozo de un pensamiento real, otras compone una frase nueva
siguiendo los pares que aprendió. Las frases salen en columnas vecinas de la cascada."""
import random
from collections import Counter, defaultdict, deque


class JuegoFrases:
    MAX_PALABRAS, MIN_PALABRAS = 6, 3
    MAX_PARES = 600

    def __init__(self, azar=None):
        self.azar = azar or random.Random()
        self.pares = defaultdict(Counter)            # palabra -> palabras que la siguieron
        self.pensamientos = deque(maxlen=24)         # frases completas recientes (ya filtradas)
        self.jugadas = self.compuestas = 0

    def aprender(self, palabras):
        """Recibe las palabras de un pensamiento, en orden."""
        palabras = [p for p in palabras if p]
        if len(palabras) >= 2:
            for a, b in zip(palabras, palabras[1:]):
                if a != b:
                    self.pares[a][b] += 1
            if len(self.pares) > self.MAX_PARES:      # olvida lo menos repetido
                for clave in sorted(self.pares, key=lambda k: sum(self.pares[k].values()))[:self.MAX_PARES // 4]:
                    del self.pares[clave]
        if len(palabras) >= self.MIN_PALABRAS:
            self.pensamientos.append(tuple(palabras))

    def _trozo_real(self):
        if not self.pensamientos:
            return None
        frase = self.azar.choice(self.pensamientos)
        largo = min(len(frase), self.azar.randint(self.MIN_PALABRAS, self.MAX_PALABRAS))
        inicio = self.azar.randint(0, len(frase) - largo)
        return list(frase[inicio:inicio + largo])

    def _componer(self):
        """Encadena palabras por los pares aprendidos (los más frecuentes pesan más, sin repetir)."""
        inicios = [p for p, siguientes in self.pares.items() if siguientes]
        if not inicios:
            return None
        frase = [self.azar.choice(inicios)]
        objetivo = self.azar.randint(self.MIN_PALABRAS, self.MAX_PALABRAS)
        while len(frase) < objetivo:
            opciones = [(p, n) for p, n in self.pares.get(frase[-1], {}).items() if p not in frase]
            if not opciones:
                break
            total = sum(n for _, n in opciones)
            tirada, acumulado = self.azar.uniform(0, total), 0.0
            for palabra, n in opciones:
                acumulado += n
                if acumulado >= tirada:
                    frase.append(palabra)
                    break
        return frase if len(frase) >= self.MIN_PALABRAS else None

    def jugar(self, maximo=None):
        """Una frase para la cascada (lista de palabras) o None si aún no sabe suficientes."""
        maximo = maximo or self.MAX_PALABRAS
        frase = self._componer() if self.azar.random() < 0.5 else None
        if frase:
            self.compuestas += 1
        else:
            frase = self._trozo_real() or self._componer()
        if not frase:
            return None
        self.jugadas += 1
        return frase[:maximo]
