"""MILLER · Pensamiento de la cascada: lo que el orbe ve caer, en qué orden lo piensa y si quiere jugar.

Módulo puro (sin Tk, así se prueba sin pantalla). La ventana le pasa las columnas de la cascada y la
posición del orbe; aquí se decide:
  - PERCIBIR: qué palabras pasan cerca del orbe (o, si son pocas, las que están en pantalla) y a
    qué velocidad caen la cascada;
  - ORDENAR: pone esas palabras en el orden que aprendió (qué palabra suele seguir a cuál);
  - SOLTAR: con la velocidad de la cascada, para que la frase no desentone;
  - JUGAR: decide si ahora quiere jugar a ordenar palabras. Solo cuando no está ocupado, no jugó hace
    poco y tiene ganas (poco placer o mucho rato sin pensar nada). Nunca interrumpe.
"""
import random
from collections import deque


class Percepcion:
    RADIO = 70                  # px: palabras que pasan a esta distancia del orbe
    MUESTRAS = 40               # velocidades recientes que recuerda

    def __init__(self):
        self._velocidades = deque(maxlen=self.MUESTRAS)

    @staticmethod
    def _libre(col):
        """Columna que cae con una palabra suelta (no reservada para una frase ni esperando)."""
        return bool(col.get("palabra")) and not (col.get("frase") or col.get("reservada") or col.get("espera"))

    def observar(self, columnas):
        """Anota a qué velocidad caen las palabras libres."""
        libres = [c["vel"] for c in columnas if self._libre(c) and "vel" in c]
        if libres:
            self._velocidades.append(sum(libres) / len(libres))

    def velocidad(self):
        """Velocidad media reciente de la cascada (0 si todavía no ha mirado)."""
        if not self._velocidades:
            return 0.0
        return sum(self._velocidades) / len(self._velocidades)

    def ritmo(self):
        v = self.velocidad()
        if v <= 0:
            return "desconocido"
        return "rápido" if v >= 3.0 else "lento" if v <= 1.8 else "normal"

    def velocidad_para_frase(self):
        """Velocidad con la que suelta una frase: la de la cascada, acotada para que se lea bien."""
        return min(3.4, max(1.6, (self.velocidad() or 2.2) * 1.05))

    def cercanas(self, columnas, orbe, radio=None):
        """Palabras que caen cerca del orbe, la más próxima primero. orbe = (x, y)."""
        radio = radio or self.RADIO
        ox, oy = orbe
        cerca = []
        for c in columnas:
            if not self._libre(c):
                continue
            dx, dy = c["x"] - ox, c["y"] - oy
            distancia = (dx * dx + dy * dy) ** 0.5
            if distancia <= radio:
                cerca.append((distancia, c["palabra"]))
        cerca.sort()
        return [p for _, p in cerca]

    def visibles(self, columnas, alto):
        """Palabras libres que están dentro de la ventana, de arriba abajo."""
        cuadro = sorted((c for c in columnas if self._libre(c) and 0 <= c["y"] <= alto), key=lambda c: c["y"])
        return [c["palabra"] for c in cuadro]

    def percibir(self, columnas, orbe, alto=None, minimo=3):
        """Lo que el orbe tiene a mano para pensar: lo que pasa cerca o, si es poco, lo que está en pantalla."""
        cerca = self.cercanas(columnas, orbe)
        if len(dict.fromkeys(cerca)) >= minimo:
            return cerca
        return self.visibles(columnas, float("inf") if alto is None else alto)


class Pensador:
    MIN_PALABRAS = 3
    MAX_PALABRAS = 6
    ESPERA_JUEGO = 25.0         # s entre dos juegos
    SILENCIO_PARA_JUGAR = 90.0  # s sin pensar nada: a partir de aquí tiene ganas de entretenerse

    def __init__(self, juego, azar=None):
        self.juego = juego                       # interfaz.frases.JuegoFrases: aprende qué palabra sigue a cuál
        self.azar = azar or random.Random()
        self.ultimo_juego = -1e9
        self.ordenadas = 0

    def ordenar(self, palabras):
        """Pone las palabras en el orden que aprendió: empieza por la que más sigue a las demás y, tras cada
        una, sigue la que más suele venir detrás. Sin datos, mantiene el orden en que llegaron."""
        restantes = list(dict.fromkeys(palabras))
        if len(restantes) < 2:
            return restantes
        pares = self.juego.pares
        inicio = max(restantes, key=lambda p: (sum(pares.get(p, {}).get(q, 0) for q in restantes),
                                               -restantes.index(p)))
        orden = [inicio]
        restantes.remove(inicio)
        while restantes:
            actual = orden[-1]
            siguiente = max(restantes, key=lambda q: (pares.get(actual, {}).get(q, 0), -restantes.index(q)))
            orden.append(siguiente)
            restantes.remove(siguiente)
        return orden

    def elegir(self, percibidas):
        """Lo que dirá en la cascada: si ha visto caer palabras, las ordena; si no, saca una frase de lo que sabe."""
        distintas = list(dict.fromkeys(percibidas))
        if len(distintas) >= self.MIN_PALABRAS:
            self.ordenadas += 1
            return self.ordenar(distintas[:self.MAX_PALABRAS])
        return self.juego.jugar(maximo=self.MAX_PALABRAS)

    def decidir_jugar(self, ahora, ocupado, placer=0.5, silencio=0.0):
        """¿Juega a ordenar palabras ahora? Nunca si está ocupado ni si jugó hace poco."""
        if ocupado or ahora - self.ultimo_juego < self.ESPERA_JUEGO:
            return False
        ganas = placer < 0.45 or silencio > self.SILENCIO_PARA_JUGAR
        return ganas and self.azar.random() < 0.7

    def marcar_juego(self, ahora):
        self.ultimo_juego = ahora
