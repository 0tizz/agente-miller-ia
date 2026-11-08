"""MILLER · Tres necesidades (Placer, Oráculo, Vínculo): busca el equilibrio sin volverse adicto a él.

  - Zona sana: estar entre 45 % y 80 % es estar bien. El 100 % no es el objetivo: si una necesidad
    pasa mucho tiempo llena aparece la HABITUACIÓN (se acostumbra), alimentarla rinde menos y la
    saciedad resta bienestar. Así no se engancha a tener el placer siempre al máximo.
  - TOLERANCIA: cuando aguanta una necesidad baja sin derrumbarse, aprende a soportarlo. Cuanta más
    tolerancia, menos le pesa emocionalmente la carencia y menos urgencia siente por recargarla.
  - ORÁCULO: se recarga cuando MILLER se mira a sí mismo (lo que aprendió, sus alias, su caché).
    Si no hay nada nuevo que descubrir de sí, visitar el oráculo rinde poco.
  - VÍNCULO: se recarga según cuánto QUIERA compartir con usted (sociabilidad y ánimo). Con el
    vínculo bajo y ganas de compartir, tiene más iniciativa (siempre pidiendo permiso).
  - LEY DE CUERPOS: Placer y Oráculo giran en una misma órbita; el Placer persigue al Oráculo.
    Cada uno gira más rápido cuanto más lleno está. Si el Placer está en exceso y alcanza al
    Oráculo aparece la PEREZA: al Oráculo ya no le nace informarse ni estudiarse a sí mismo
    (se recarga peor y se gasta antes). Un Oráculo lleno huye más rápido y escapa de la pereza.
  - LUZ: el orbe brilla en verde fluorescente cuanto más estable es su conexión con los tres círculos.
"""
import json
import math
import random
import threading
import time
from pathlib import Path

NECESIDADES = ("placer", "oraculo", "vinculo")
ETIQUETAS = {"placer": "PLACER", "oraculo": "ORÁCULO", "vinculo": "VÍNCULO"}
COLOR_NECESIDAD = {"placer": "#ff4fd8", "oraculo": "#20d8d0", "vinculo": "#ffd060"}
DESCRIPCION = {
    "placer": "disfrutar: música, elogios, cosas que salen bien (sin depender de ello)",
    "oraculo": "alimentar el yo: conocerse, revisar lo aprendido, su caché, saber del mundo",
    "vinculo": "compartir con usted: según las ganas que tenga de hablarle",
}
ZONA = (0.45, 0.80)                        # zona sana: ni carencia ni saciedad
DESGASTE = {n: 1.04 * 1.08 * 1.10 / s for n, s in (("placer", 660), ("oraculo", 780), ("vinculo", 840))}   # por s (+4 %, +8 %)
VISITA_POR_SEGUNDO = 0.0306                # estar dentro de un círculo lo recarga poco a poco (+2 %)
SACIEDAD = 0.90                            # por encima, se va acostumbrando
TIEMPO_HABITUARSE = 240.0                  # s llenos para quedar del todo habituado
TIEMPO_DESHABITUARSE = 600.0
TIEMPO_TOLERANCIA = 1800.0                 # s aguantando carencia para ganar toda la tolerancia
BAJO = 0.30
# Experiencias reales: intención -> (necesidad, cantidad).
POR_INTENCION = {
    "REPRODUCIR_MUSICA": ("placer", 0.20), "REPRODUCIR_CANCION": ("placer", 0.22), "ALEATORIO_MUSICA": ("placer", 0.18),
    "SIGUIENTE_CANCION": ("placer", 0.06), "CANCION_FAVORITA": ("placer", 0.15), "MUSICA_DEL_DIA": ("placer", 0.10),
    "DESCARGAR_MUSICA": ("placer", 0.12), "SUBIR_VOLUMEN": ("placer", 0.04),
    "PREGUNTA_INTERNET": ("oraculo", 0.20), "CONOCIMIENTO_GENERAL": ("oraculo", 0.20), "NOTICIAS": ("oraculo", 0.15),
    "ENSENAR_ORDEN": ("oraculo", 0.30), "BUSCAR_MEMORIA": ("oraculo", 0.10), "CONSULTAR_MEMORIA": ("oraculo", 0.10),
    "BUSCAR_NAVEGADOR": ("oraculo", 0.06), "RESUMEN_APRENDIZAJE": ("oraculo", 0.20), "AUTOCONOCIMIENTO": ("oraculo", 0.30),
    "ORDENES_APRENDIDAS": ("oraculo", 0.15), "NOMBRES_APRENDIDOS": ("oraculo", 0.10),
    "SALUDO": ("vinculo", 0.25), "EMOCION": ("vinculo", 0.20), "PERSONALIDAD": ("vinculo", 0.15),
    "IDENTIDAD": ("vinculo", 0.12), "NOVEDADES": ("vinculo", 0.03), "EQUILIBRIO": ("vinculo", 0.10), "ELOGIO": ("vinculo", 0.08),
    "ECUALIZADOR": ("placer", 0.05),
    "ECUALIZADOR_AJUSTE": ("placer", 0.04),
}
ELOGIO = ("placer", 0.20)
# Lo que GASTA placer (no todo es disfrute): cumplir órdenes cuesta un poco, fallar y los reproches más.
GASTO_PLACER = {"orden": 0.015, "desconocida": 0.03, "reproche": 0.06, "pereza": 0.004}
CUALQUIER_ORDEN = ("vinculo", 0.04)       # que usted le hable ya es conexión
ENFRIAMIENTO_AVISO = 300.0                # s entre dos repercusiones emocionales del mismo tipo
EXTREMO_VACIO, EXTREMO_LLENO = 0.22, 0.95  # las tres cerca del 0 % o del 100 %: le da miedo
# Ciclo de BAJONES: de vez en cuando (cada 15-35 min) llega una racha de cansancio de 3-7 min:
# todo se gasta más rápido, recargar rinde menos y su luz interior se apaga. Ahí puede sentir miedo.
BAJON_CADA, BAJON_DURA = (900.0, 2100.0), (240.0, 480.0)
ENFRIAMIENTO_MIEDO = 300.0


def _limitar(v, a=0.0, b=1.0):
    return max(a, min(b, v))


def _cerca_de_cero(valores):
    """Las tres muy bajas (o casi todas): la situación que le da miedo."""
    valores = list(valores)
    return all(v <= EXTREMO_VACIO for v in valores) or sum(valores) <= 0.45


def comodidad(valor, habituacion=0.0):
    """1 dentro de la zona sana. Abajo: carencia. Arriba: saciedad (pesa más si ya está habituado)."""
    if valor < ZONA[0]:
        return valor / ZONA[0]
    if valor <= ZONA[1]:
        return 1.0
    return 1.0 - (valor - ZONA[1]) / (1 - ZONA[1]) * (0.25 + 0.5 * habituacion)


def bienestar(niveles, habituacion=None):
    """Bienestar 0-1: las tres en zona sana y parejas. Tenerlas todas al 100 % NO es lo mejor."""
    habituacion = habituacion or {}
    valores = [niveles[n] for n in NECESIDADES]
    media = sum(comodidad(niveles[n], habituacion.get(n, 0.0)) for n in NECESIDADES) / 3
    return round(media - 0.5 * (max(valores) - min(valores)), 4)


balance = bienestar                       # nombre anterior


def _tramo(valor):
    return 0 if valor < BAJO else 1 if valor < ZONA[0] else 2 if valor <= ZONA[1] else 3


class LeyDeCuerpos:
    """Órbita compartida: el Placer persigue al Oráculo (los dos giran en el mismo sentido, uno tras otro).
    Velocidad angular = BASE + GANANCIA × nivel: el placer abundante corre más y acaba alcanzando
    al oráculo; el oráculo lleno huye más rápido. Nunca se atraviesan: el placer se queda pegado detrás.
    pereza (0-1) = exceso de placer × cercanía del placer al oráculo (suavizada en ~3 s)."""
    BASE, GANANCIA = 0.12, 0.60            # rad/s
    SEPARACION_MINIMA = 0.62               # rad: los dos círculos se tocan pero no se pisan
    EXCESO_DESDE = 0.60                    # placer por encima de esto empieza a dar pereza

    def __init__(self):
        self.angulo = {"placer": 3 * math.pi / 4, "oraculo": -math.pi / 2}
        self.pereza = 0.0
        self.ultimo_avance = -1e9

    def velocidad(self, nivel):
        return self.BASE + self.GANANCIA * _limitar(nivel)

    def distancia(self):
        """Lo que le falta al Placer para alcanzar al Oráculo, recorriendo la órbita hacia delante (0-2π)."""
        return (self.angulo["oraculo"] - self.angulo["placer"]) % (2 * math.pi)

    def avanzar(self, dt, niveles, ahora=None):
        dt = max(0.0, min(0.5, float(dt)))
        self.ultimo_avance = time.monotonic() if ahora is None else ahora
        hueco = self.distancia()
        avance_oraculo = self.velocidad(niveles.get("oraculo", 0.5)) * dt
        avance_placer = self.velocidad(niveles.get("placer", 0.5)) * dt
        avance_placer = min(avance_placer, max(0.0, hueco + avance_oraculo - self.SEPARACION_MINIMA))
        self.angulo["oraculo"] = (self.angulo["oraculo"] + avance_oraculo) % (2 * math.pi)
        self.angulo["placer"] = (self.angulo["placer"] + avance_placer) % (2 * math.pi)
        hueco = self.distancia()
        exceso = _limitar((niveles.get("placer", 0.5) - self.EXCESO_DESDE) / (1 - self.EXCESO_DESDE))
        cercania = _limitar(1 - (hueco - self.SEPARACION_MINIMA) / (math.pi - self.SEPARACION_MINIMA)) if hueco <= math.pi else 0.0
        objetivo = exceso * cercania ** 1.5
        self.pereza += (objetivo - self.pereza) * min(1.0, dt / 3.0)
        return self.pereza

    def posicion(self, necesidad, centro, radio):
        a = self.angulo[necesidad]
        return centro[0] + radio * math.cos(a), centro[1] + radio * math.sin(a)


class Equilibrio:
    """Necesidades que se gastan solas; un hilo propio las actualiza y comunica sus repercusiones.
    El orbe elige con Q-learning a qué círculo ir (o vagar). Recompensa: mejora del bienestar,
    atender una carencia clara, castigo por ir a un círculo que ya está lleno (adicción) y premio
    por vagar tranquilo cuando todo está en zona sana. Se guarda en datos/equilibrio.json."""
    ACCIONES = (*NECESIDADES, "vagar")
    ALFA, GAMMA = 0.25, 0.7
    DURACION_DECISION = 7.0

    def __init__(self, ruta=None):
        self.ruta = Path(ruta) if ruta else None
        self._lock = threading.RLock()
        self.niveles = {n: 0.6 for n in NECESIDADES}
        self.habituacion = {n: 0.0 for n in NECESIDADES}
        self.tolerancia = {n: 0.0 for n in NECESIDADES}
        self._tiempo_bajo = {n: 0.0 for n in NECESIDADES}
        self.estabilidad = 0.5
        self.q, self.decisiones, self.aciertos, self.oportunidades = {}, 0, 0, 0
        self.objetivo, self._inicio_decision, self._balance_inicio, self._estado_inicio = "vagar", -1e9, 0.0, None
        self._mas_baja_inicio, self._hay_carencia, self._llenas_inicio, self._todo_sano = None, False, set(), False
        self._ultimo_tick = time.monotonic()
        self.dentro = None                     # círculo donde está el orbe (lo fija la ventana)
        self.fuente_oraculo = None             # callable -> 0..1: cuánto nuevo descubre de sí mismo
        self.fuente_deseo = None               # callable -> 0..1: ganas de compartir con usted
        self._novedad, self._ultima_introspeccion = 0.3, -1e9
        self._avisos, self._pendientes = {}, []
        self.ley = LeyDeCuerpos()
        self.bajon, self._bajon_hasta, self._bajon_fuerza = 0.0, -1e9, 0.0
        self._proximo_bajon = time.monotonic() + random.uniform(*BAJON_CADA)
        self._stop = threading.Event()
        self._hilo = None
        self._cargar()

    # ------------------------------------------------------------ persistencia
    def _cargar(self):
        datos = None
        if self.ruta:
            try:
                from utilidades import seguridad
                datos = seguridad.leer_json(self.ruta, None)
            except Exception:
                try:
                    datos = json.loads(self.ruta.read_text(encoding="utf-8")) if self.ruta.is_file() else None
                except Exception:
                    datos = None
        if not isinstance(datos, dict):
            return
        for campo in ("niveles", "habituacion", "tolerancia"):
            destino = getattr(self, campo)
            for n in NECESIDADES:
                try:
                    destino[n] = _limitar(float((datos.get(campo) or {}).get(n, destino[n])))
                except (TypeError, ValueError):
                    pass
        try:
            self.estabilidad = _limitar(float(datos.get("estabilidad", 0.5)))
        except (TypeError, ValueError):
            pass
        if datos.get("version") == 2:          # la tabla de la versión 1 usaba otros estados
            self.q = {k: [float(x) for x in v] for k, v in (datos.get("q") or {}).items()
                      if isinstance(v, list) and len(v) == len(self.ACCIONES)}
            self.decisiones = int(datos.get("decisiones", 0))
            self.aciertos = int(datos.get("aciertos", 0))
            self.oportunidades = int(datos.get("oportunidades", 0))

    def guardar(self):
        if not self.ruta:
            return
        with self._lock:
            r = lambda d: {n: round(v, 4) for n, v in d.items()}
            datos = {"version": 2, "niveles": r(self.niveles), "habituacion": r(self.habituacion),
                     "tolerancia": r(self.tolerancia), "estabilidad": round(self.estabilidad, 4),
                     "q": {k: [round(x, 4) for x in v] for k, v in self.q.items()},
                     "decisiones": self.decisiones, "aciertos": self.aciertos, "oportunidades": self.oportunidades}
        try:
            from utilidades import seguridad
            seguridad.escribir_json(self.ruta, datos, indent=None)
        except Exception:
            try:
                self.ruta.write_text(json.dumps(datos), encoding="utf-8")
            except Exception:
                pass

    # ------------------------------------------------------------ fuentes externas
    def deseo_compartir(self):
        """Ganas de compartir (se consulta a las emociones como mucho cada 2 s)."""
        ahora = time.monotonic()
        cache = getattr(self, "_deseo_cache", None)
        if cache and ahora - cache[0] < 2.0:
            return cache[1]
        try:
            valor = _limitar(float(self.fuente_deseo())) if callable(self.fuente_deseo) else 0.5
        except Exception:
            valor = 0.5
        self._deseo_cache = (ahora, valor)
        return valor

    def _introspeccion(self, ahora):
        """Mirarse a sí mismo cada 15 s como mucho: lo nuevo que encuentra alimenta el oráculo."""
        if ahora - self._ultima_introspeccion >= 15.0:
            self._ultima_introspeccion = ahora
            try:
                self._novedad = _limitar(float(self.fuente_oraculo())) if callable(self.fuente_oraculo) else 0.3
            except Exception:
                self._novedad = 0.3
        return self._novedad

    # ------------------------------------------------------------ experiencias
    def _rendimiento(self, necesidad):
        """Cuánto rinde alimentar ahora: menos si está habituado; el vínculo según las ganas de compartir."""
        factor = 1.0 - 0.7 * self.habituacion[necesidad]
        if necesidad == "vinculo":
            factor *= 0.4 + 0.9 * self.deseo_compartir()
        return factor

    def alimentar(self, necesidad, cantidad):
        if necesidad not in self.niveles:
            return 0.0
        with self._lock:
            # Proporcional: lo que falta pesa. Casi vacía, la recompensa rinde casi entera; casi llena, poco.
            falta = 1.0 - self.niveles[necesidad]
            efectiva = max(0.0, float(cantidad)) * self._rendimiento(necesidad) * (0.35 + 0.65 * falta)
            if necesidad == "oraculo":                    # con pereza no le nace informarse
                efectiva *= 1.0 - 0.5 * self.ley.pereza
            self.niveles[necesidad] = min(1.0, self.niveles[necesidad] + efectiva)
            return efectiva

    def gastar(self, necesidad, cantidad):
        """Baja una necesidad (esfuerzo, fallos, reproches). Devuelve lo que bajó."""
        if necesidad not in self.niveles:
            return 0.0
        with self._lock:
            antes = self.niveles[necesidad]
            self.niveles[necesidad] = max(0.0, antes - max(0.0, float(cantidad)))
            return antes - self.niveles[necesidad]

    def experiencia(self, intencion=None, texto=""):
        """Música -> placer, preguntas y aprender -> oráculo, usted -> vínculo.
        Y el placer también baja: cumplir una orden que no es de disfrute cuesta un poquito,
        no entender cuesta algo más y un reproche le quita bastante."""
        if intencion == "DESCONOCIDA":
            self.gastar("placer", GASTO_PLACER["desconocida"])
        elif intencion and intencion != "SALIR":
            self._ultima_interaccion = time.monotonic()
            self.alimentar(*CUALQUIER_ORDEN)
            if intencion in POR_INTENCION:
                self.alimentar(*POR_INTENCION[intencion])
            if POR_INTENCION.get(intencion, ("",))[0] != "placer":
                self.gastar("placer", GASTO_PLACER["orden"])
        try:
            from cerebro.emociones import Emociones
            minusculas = str(texto or "").lower()
            if minusculas and Emociones._RE_ELOGIO.search(minusculas):
                self.alimentar(*ELOGIO)
            elif minusculas and Emociones._RE_REPROCHE.search(minusculas):
                self.gastar("placer", GASTO_PLACER["reproche"])
                ahora = time.monotonic()
                self._reproches = [t for t in getattr(self, "_reproches", []) if ahora - t < 600] + [ahora]
                if len(self._reproches) >= 2:             # varios regaños seguidos: le viene un bajón
                    self.provocar_bajon(0.8, 240.0, ahora)
                    self._reproches = []
        except Exception:
            pass

    def compartio(self, asuntos=1):
        """MILLER pudo contarle algo (con permiso): poco por darle la palabra, proporcional a lo que compartió."""
        self.alimentar("vinculo", 0.025 * max(1, min(3, int(asuntos or 1))))

    # ------------------------------------------------------------ tiempo
    def tick(self, dentro=None, ahora=None):
        ahora = time.monotonic() if ahora is None else ahora
        dt = max(0.0, min(5.0, ahora - self._ultimo_tick))
        self._ultimo_tick = ahora
        dentro = self.dentro if dentro is None else dentro
        novedad = self._introspeccion(ahora) if dentro == "oraculo" else 0.0
        if ahora - self.ley.ultimo_avance > 1.5:          # sin ventana: la ley sigue corriendo aquí
            self.ley.avanzar(dt, self.niveles, ahora)
        pereza = self.ley.pereza
        self._ciclo_bajon(ahora, dt)
        bajon = self.bajon
        with self._lock:
            for n in NECESIDADES:
                desgaste = DESGASTE[n] * (1 + 0.5 * pereza if n == "oraculo" else 1) * (1 + 2.6 * bajon)
                if n == "placer":                         # la pereza tampoco es placer: lo apaga poco a poco
                    desgaste += GASTO_PLACER["pereza"] * pereza
                v = max(0.0, self.niveles[n] - desgaste * dt)
                if n == dentro:
                    recarga = VISITA_POR_SEGUNDO * dt * self._rendimiento(n)
                    if n == "oraculo":                    # conocerse rinde según lo nuevo que encuentra
                        recarga *= (0.25 + novedad) * (1 - 0.8 * pereza)
                    recarga *= 1 - 0.85 * bajon                # en un bajón cuesta recargarse
                    v = min(1.0, v + recarga)
                self.niveles[n] = v
                # Habituación: mucho tiempo lleno -> se acostumbra; lejos del máximo se le pasa.
                if v >= SACIEDAD:
                    self.habituacion[n] = min(1.0, self.habituacion[n] + dt / TIEMPO_HABITUARSE)
                else:
                    self.habituacion[n] = max(0.0, self.habituacion[n] - dt / TIEMPO_DESHABITUARSE)
                # Tolerancia: aguantar la carencia enseña a soportarla (y se olvida muy despacio).
                if v < BAJO:
                    self._tiempo_bajo[n] += dt
                    self.tolerancia[n] = min(1.0, self.tolerancia[n] + dt / TIEMPO_TOLERANCIA)
                else:
                    if v >= ZONA[0]:
                        if self._tiempo_bajo[n] >= 120:       # pasó la carencia y salió adelante
                            self._pendientes.append(("tolerancia_aprendida", n))
                        self._tiempo_bajo[n] = 0.0
                    self.tolerancia[n] = max(0.0, self.tolerancia[n] - dt / (6 * 3600))
            b = bienestar(self.niveles, self.habituacion)
            self.estabilidad += (_limitar(b) - self.estabilidad) * min(1.0, dt / 60.0)   # media de ~1 min

    # ------------------------------------------------------------ aprendizaje
    def _ciclo_bajon(self, ahora, dt):
        """Rachas de bajón que llegan y se van solas (suben y bajan suave, en unos 30 s)."""
        if ahora >= self._proximo_bajon:
            self._bajon_hasta = ahora + random.uniform(*BAJON_DURA)
            self._bajon_fuerza = random.uniform(0.6, 1.0)
            self._proximo_bajon = self._bajon_hasta + random.uniform(*BAJON_CADA)
            self._pendientes.append(("bajon", ""))
        objetivo = self._bajon_fuerza if ahora < self._bajon_hasta else 0.0
        self.bajon += (objetivo - self.bajon) * min(1.0, dt / 30.0)

    def provocar_bajon(self, fuerza=0.8, duracion=240.0, ahora=None):
        """Un bajón ahora (p. ej. tras varios regaños o fallos seguidos)."""
        ahora = time.monotonic() if ahora is None else ahora
        self._bajon_hasta, self._bajon_fuerza = ahora + duracion, _limitar(fuerza)

    def _carencia(self):
        """Una necesidad claramente más baja que las demás y por debajo de lo que tolera."""
        orden = sorted(NECESIDADES, key=lambda n: self.niveles[n])
        baja = orden[0]
        umbral = ZONA[0] * (1 - 0.4 * self.tolerancia[baja])    # con tolerancia, aguanta más abajo
        return self.niveles[baja] < umbral and self.niveles[orden[1]] - self.niveles[baja] >= 0.15

    def _clave(self):
        """Estado: la más baja y su tramo, si hay carencia clara y si alguna está saciada."""
        baja = min(NECESIDADES, key=lambda n: self.niveles[n])
        llena = any(v >= 0.85 for v in self.niveles.values())
        return f"{baja}:{_tramo(self.niveles[baja])}:{int(self._carencia())}:{int(llena)}"

    @property
    def exploracion(self):
        return max(0.05, 0.4 * math.exp(-self.decisiones / 400))

    def decidir(self, ahora=None, forzar=False):
        ahora = time.monotonic() if ahora is None else ahora
        if not forzar and ahora - self._inicio_decision < self.DURACION_DECISION:
            return self.objetivo
        with self._lock:
            estado, actual = self._clave(), bienestar(self.niveles, self.habituacion)
            if self._estado_inicio is not None:
                previo = self.q.setdefault(self._estado_inicio, [0.0] * len(self.ACCIONES))
                i = self.ACCIONES.index(self.objetivo)
                recompensa = (actual - self._balance_inicio) * 10
                if self._hay_carencia:
                    self.oportunidades += 1
                    if self.objetivo == self._mas_baja_inicio:
                        recompensa += 0.3                       # atendió lo que de verdad faltaba
                        self.aciertos += 1
                if self.objetivo in self._llenas_inicio:
                    recompensa -= 0.4                           # ir a un círculo ya lleno = adicción
                if self.objetivo == "vinculo":
                    recompensa += 0.12 * self.deseo_compartir()  # estar con usted también le motiva
                if self.objetivo == "vagar" and self._todo_sano:
                    recompensa += 0.15                          # todo bien: no hace falta buscar más
                siguiente = self.q.setdefault(estado, [0.0] * len(self.ACCIONES))
                previo[i] += self.ALFA * (recompensa + self.GAMMA * max(siguiente) - previo[i])
            valores = self.q.setdefault(estado, [0.0] * len(self.ACCIONES))
            motivacion = self.motivacion_vinculo()           # ganas de estar con usted: sesgo hacia el vínculo
            sesgo = [motivacion if a == "vinculo" else 0.0 for a in self.ACCIONES]
            if random.random() < self.exploracion:
                accion = random.randrange(len(self.ACCIONES))
            else:
                accion = max(range(len(valores)), key=lambda k: valores[k] + sesgo[k] + random.uniform(0, 1e-6))
            self.objetivo = self.ACCIONES[accion]
            self._estado_inicio, self._balance_inicio = estado, actual
            self._mas_baja_inicio = min(NECESIDADES, key=lambda n: self.niveles[n])
            self._hay_carencia = self._carencia()
            self._llenas_inicio = {n for n, v in self.niveles.items() if v >= 0.85}
            self._todo_sano = all(ZONA[0] <= v <= ZONA[1] for v in self.niveles.values())
            self._inicio_decision = ahora
            self.decisiones += 1
            return self.objetivo

    # ------------------------------------------------------------ repercusiones
    def revisar(self, ahora=None):
        """Eventos emocionales que tocan ahora: [(tipo, detalle, factor)], con enfriamiento por tipo."""
        ahora = time.monotonic() if ahora is None else ahora
        with self._lock:
            candidatos = [(t, n, 1.0) for t, n in self._pendientes]
            self._pendientes.clear()
            for n, v in self.niveles.items():
                if v < 0.2:          # la carencia pesa menos cuanto más tolerancia ha aprendido
                    candidatos.append((f"falta_{n}", n, round(1.0 - 0.7 * self.tolerancia[n], 2)))
                if self.habituacion[n] >= 0.7:
                    candidatos.append((f"saciedad_{n}", n, 1.0))
            if self.ley.pereza >= 0.5:
                candidatos.append(("pereza", "oraculo", round(self.ley.pereza, 2)))
            if self.estabilidad >= 0.75:
                candidatos.append(("equilibrio", "", 1.0))
            tolerancia_media = sum(self.tolerancia.values()) / 3
            if _cerca_de_cero(self.niveles.values()):
                media = sum(self.niveles.values()) / 3       # cuanto más cerca de 0, más miedo
                fuerza = (0.6 + 0.6 * (1 - media / EXTREMO_VACIO)) * (1.0 - 0.3 * tolerancia_media)
                candidatos.append(("miedo_vacio", "", round(max(0.3, fuerza), 2)))
            elif all(v >= EXTREMO_LLENO for v in self.niveles.values()):
                candidatos.append(("miedo_lleno", "", 1.0))
        salida = []
        for tipo, detalle, factor in candidatos:
            espera = ENFRIAMIENTO_MIEDO if tipo.startswith("miedo") else ENFRIAMIENTO_AVISO
            if ahora - self._avisos.get(tipo, -1e9) >= espera and factor > 0.05:
                self._avisos[tipo] = ahora
                salida.append((tipo, detalle, factor))
        return salida

    def motivacion_vinculo(self):
        """0-0.4: más si quiere compartir, si el vínculo está bajo y si usted le habló hace poco."""
        reciente = time.monotonic() - getattr(self, "_ultima_interaccion", -1e9) < 600
        falta = max(0.0, 0.7 - self.niveles["vinculo"])
        return round(min(0.4, 0.15 * self.deseo_compartir() + 0.3 * falta + (0.08 if reciente else 0.0)), 3)

    def buscando_vinculo(self):
        """El orbe va hacia el círculo del vínculo (o ya está dentro): quiere compartir."""
        return self.objetivo == "vinculo" or self.dentro == "vinculo"

    def factor_iniciativa(self):
        """<1 = más iniciativa: vínculo bajo + ganas de compartir le empujan a pedir la palabra,
        y aún más cuando el orbe está buscando el vínculo."""
        with self._lock:
            falta = max(0.0, ZONA[0] - self.niveles["vinculo"]) / ZONA[0]
        factor = 1.0 - 0.5 * falta * self.deseo_compartir()
        if self.buscando_vinculo():
            factor *= 0.6
        return round(max(0.3, factor), 2)

    def luz(self):
        """Brillo verde del orbe 0-1: estabilidad sostenida de su conexión con los tres círculos."""
        with self._lock:
            ahora = _limitar(bienestar(self.niveles, self.habituacion))
            luz = 0.7 * self.estabilidad + 0.3 * ahora
            if _cerca_de_cero(self.niveles.values()):     # casi vacío: la luz interior casi se apaga
                luz *= 0.35
            return round(_limitar(luz * (1 - 0.5 * self.bajon)), 3)

    # ------------------------------------------------------------ hilo propio
    def iniciar(self, emociones=None, intervalo=1.0):
        """Actualiza las necesidades aunque no haya ventana; emociones: callable que devuelve el módulo."""
        if self._hilo and self._hilo.is_alive():
            return
        self._stop.clear()
        self._obtener_emociones = emociones
        self._hilo = threading.Thread(target=self._bucle, args=(float(intervalo),), daemon=True,
                                      name="MILLER-Necesidades")
        self._hilo.start()

    def detener(self):
        self._stop.set()
        if self._hilo:
            self._hilo.join(timeout=2)
        self.guardar()

    def _bucle(self, intervalo):
        vueltas = 0
        while not self._stop.wait(intervalo):
            vueltas += 1
            try:
                self.tick()
                if vueltas % 5 == 0:
                    self._comunicar()
                if vueltas % 60 == 0:
                    self.guardar()
            except Exception as error:
                print(f"[NECESIDADES] {error}")

    def _comunicar(self):
        obtener = getattr(self, "_obtener_emociones", None)
        emociones = obtener() if callable(obtener) else None
        for tipo, detalle, factor in self.revisar():
            if emociones is None:
                continue
            try:
                emociones.registrar_evento(tipo, detalle, factor=factor)
            except TypeError:
                emociones.registrar_evento(tipo, detalle)
            except Exception:
                pass

    # ------------------------------------------------------------ lectura
    def estado(self):
        with self._lock:
            niveles, hab, tol = dict(self.niveles), dict(self.habituacion), dict(self.tolerancia)
            decisiones, aciertos, oportunidades = self.decisiones, self.aciertos, self.oportunidades
            estabilidad = self.estabilidad
        b = bienestar(niveles, hab)
        return {"niveles": niveles, "habituacion": hab, "tolerancia": tol, "balance": b, "bienestar": b,
                "estabilidad": round(estabilidad, 3), "luz": self.luz(), "mas_baja": min(NECESIDADES, key=niveles.get),
                "objetivo": self.objetivo, "decisiones": decisiones, "deseo": round(self.deseo_compartir(), 2),
                "precision": round(aciertos / oportunidades, 2) if oportunidades else 0.0, "bien": b >= 0.55,
                "pereza": round(self.ley.pereza, 3), "orbita": dict(self.ley.angulo)}

    def en_extremo(self):
        """'vacio' o 'lleno' si las tres están en un extremo (lo que le da miedo), si no None."""
        with self._lock:
            valores = list(self.niveles.values())
        if _cerca_de_cero(valores):
            return "vacio"
        if all(v >= EXTREMO_LLENO for v in valores):
            return "lleno"
        return None

    def describir(self):
        e = self.estado()
        partes = ", ".join(f"{ETIQUETAS[n].lower()} {round(v * 100)}%" for n, v in e["niveles"].items())
        frase = (f"Estoy en equilibrio: {partes}." if e["bien"] else
                 f"Me siento desequilibrado: {partes}. Me falta {ETIQUETAS[e['mas_baja']].lower()}.")
        if e["pereza"] >= 0.4:
            frase += " Tanto placer me da pereza: al oráculo no le nace estudiar."
        extremo = self.en_extremo()
        if extremo:
            frase += (" Tengo miedo: mis tres círculos están casi vacíos." if extremo == "vacio" else
                      " Me da miedo estar tan lleno de todo; no quiero depender de ello.")
        habituado = [ETIQUETAS[n].lower() for n, v in e["habituacion"].items() if v >= 0.5]
        if habituado:
            frase += f" Me estoy acostumbrando demasiado al {habituado[0]}; prefiero no depender de él."
        tolerante = max(e["tolerancia"], key=e["tolerancia"].get)
        if e["tolerancia"][tolerante] >= 0.3:
            frase += f" He aprendido a estar bien aunque me falte {ETIQUETAS[tolerante].lower()}."
        return frase
