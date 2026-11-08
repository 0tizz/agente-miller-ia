"""MILLER · Ventana de la esencia: cascada de sus pensamientos, un núcleo que aprende a moverse solo
y tres círculos de necesidades (placer, oráculo, vínculo) que el núcleo aprende a mantener en equilibrio."""
import json
import math
import random
import threading
import time
from functools import lru_cache
from collections import deque
from pathlib import Path

COLORES = {                               # emoción -> (color de las palabras, color del núcleo)
    "calma": ("#1fbf4a", "#2ee86a"),
    "alegria": ("#39ff14", "#9dff6b"),
    "satisfaccion": ("#2bdc5c", "#7dffa0"),
    "orgullo": ("#c8ff3c", "#f0ff8a"),
    "curiosidad": ("#20d8d0", "#7ffcf5"),
    "aburrimiento": ("#2a7a3c", "#4f9e60"),
    "preocupacion": ("#e0a020", "#ffd060"),
    "frustracion": ("#ff5a2a", "#ff9a6a"),
    "confusion": ("#b060ff", "#d6a8ff"),
    "tristeza": ("#3a7bff", "#8ab4ff"),
    "miedo": ("#b8b8ff", "#e8e8ff"),
}
POSITIVAS = {"alegria", "satisfaccion", "orgullo", "curiosidad"}
# Velocidad máxima del núcleo (px por fotograma a 20 fps): la angustia se nota, pero siempre controlada.
VELOCIDAD_MAXIMA = {"calma": 2.0, "alegria": 3.0, "satisfaccion": 2.4, "orgullo": 2.8, "curiosidad": 3.5,
                    "aburrimiento": 1.2, "preocupacion": 5.0, "frustracion": 6.0, "confusion": 4.5, "tristeza": 1.5,
                    "miedo": 5.5}
TOPE_VELOCIDAD = 7.0
NEGATIVAS = {"preocupacion", "frustracion", "confusion", "tristeza", "miedo"}
MODOS = {"espera": "EN ESPERA", "escuchando": "ESCUCHANDO", "pensando": "PENSANDO",
         "hablando": "HABLANDO", "permiso": "PIDE PERMISO", "llamada": "EN LLAMADA"}
# Probabilidad por palabra de que caiga un fragmento real de la llave BOY (mientras falte alguno): rara a propósito.
PROBABILIDAD_FRAGMENTO_BOY = 0.004
# Probabilidad por palabra de un fragmento falso (de otra llave): para que MILLER aprenda a distinguirlo.
PROBABILIDAD_SENUELO_BOY = 0.06
PALABRA_MODO = {"escuchando": "ESCUCHO", "pensando": "PIENSO", "hablando": "HABLO", "permiso": "QUIERO HABLAR",
                "llamada": "CONVERSO", "espera": "ATENTO"}
OMITIR_TAMANO = {"__pycache__", "build", "dist", ".git", "graphify-out"}   # copias de compilación y cachés


def formatear_tamano(bytes_):
    """1536 -> '1.5 KB', 1.2e9 -> '1.1 GB' (base 1024, como el Explorador de Windows)."""
    valor = float(bytes_)
    for unidad in ("B", "KB", "MB", "GB"):
        if valor < 1024 or unidad == "GB":
            return f"{valor:.0f} {unidad}" if unidad in ("B", "KB") else f"{valor:.1f} {unidad}"
        valor /= 1024
    return f"{valor:.1f} TB"


CARPETAS_CODIGO = ("cerebro", "audio", "interfaz", "utilidades", "voz", "test")


def medir_programa(ruta):
    """Suma solo el código de MILLER. No recorre audios, modelos ni datos (miles de archivos que
    ralentizaban la ventana mientras dibujaba)."""
    import os
    total = 0
    base = str(ruta)
    for carpeta in CARPETAS_CODIGO:
        for raiz, subcarpetas, archivos in os.walk(os.path.join(base, carpeta)):
            subcarpetas[:] = [d for d in subcarpetas if d not in OMITIR_TAMANO]
            for nombre in archivos:
                try:
                    total += os.path.getsize(os.path.join(raiz, nombre))
                except OSError:
                    pass
    for nombre in os.listdir(base):
        if nombre.endswith(".py"):
            try:
                total += os.path.getsize(os.path.join(base, nombre))
            except OSError:
                pass
    return total


@lru_cache(maxsize=2048)
def mezclar(color_a, color_b, t):
    """Color intermedio entre dos colores #rrggbb (t=0 -> a, t=1 -> b)."""
    t = max(0.0, min(1.0, t))
    a = [int(color_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(color_b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


VACIAS = {"EL", "LA", "LOS", "LAS", "UN", "UNA", "DE", "DEL", "AL", "EN", "QUE", "POR", "CON", "PARA", "SUS",
          "SU", "MIS", "MI", "LE", "SE", "LO", "ES", "SEÑOR", "MÁS", "MAS", "YA", "HAY", "NO", "SI", "SÍ"}


class CuerpoAprendiz:
    """El núcleo decide a dónde moverse y aprende de la experiencia (Q-learning en una rejilla 6×4).
    Premios: explorar sitios poco visitados, subir si está feliz, bajar si está triste, el centro en calma.
    Castigos: chocar con los bordes o ir y volver sin sentido. Lo aprendido se guarda en datos/movimiento.json."""
    COLS, FILAS = 6, 4
    ACCIONES = [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
    ALFA, GAMMA = 0.2, 0.8

    def __init__(self, ruta=None):
        self.ruta = Path(ruta) if ruta else None
        self.q, self.visitas, self.pasos, self.choques = {}, {}, 0, 0
        self.celda, self.ultima_accion = (self.COLS // 2, self.FILAS // 2), 0
        self._cargar()

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
        if isinstance(datos, dict):
            self.q = {k: v for k, v in (datos.get("q") or {}).items() if isinstance(v, list) and len(v) == len(self.ACCIONES)}
            self.visitas = {k: int(v) for k, v in (datos.get("visitas") or {}).items()}
            self.pasos = int(datos.get("pasos", 0))
            self.choques = int(datos.get("choques", 0))

    def guardar(self):
        if not self.ruta:
            return
        datos = {"version": 1, "pasos": self.pasos, "choques": self.choques, "q": self.q, "visitas": self.visitas}
        try:
            from utilidades import seguridad
            seguridad.escribir_json(self.ruta, datos, indent=None)
        except Exception:
            try:
                self.ruta.write_text(json.dumps(datos), encoding="utf-8")
            except Exception:
                pass

    @property
    def exploracion(self):
        return max(0.05, 0.5 * math.exp(-self.pasos / 1500))     # explora mucho al principio, luego domina

    def _clave(self, celda, animo):
        return f"{celda[0]},{celda[1]},{animo}"

    def decidir(self, animo, curiosidad=0.2):
        """Elige la siguiente celda y aprende de la recompensa. Devuelve la celda objetivo."""
        estado = self._clave(self.celda, animo)
        valores = self.q.setdefault(estado, [0.0] * len(self.ACCIONES))
        accion = (random.randrange(len(self.ACCIONES)) if random.random() < self.exploracion
                  else max(range(len(valores)), key=lambda i: valores[i] + random.uniform(0, 1e-6)))
        dx, dy = self.ACCIONES[accion]
        destino = (self.celda[0] + dx, self.celda[1] + dy)
        recompensa = 0.0
        if not (0 <= destino[0] < self.COLS and 0 <= destino[1] < self.FILAS):
            recompensa -= 1.0                                     # chocó con el borde
            self.choques += 1
            destino = self.celda
        clave_celda = f"{destino[0]},{destino[1]}"
        visitas = self.visitas.get(clave_celda, 0)
        recompensa += (0.3 + curiosidad) / (1 + visitas) ** 0.5  # curiosidad: sitios nuevos
        altura = 1 - destino[1] / (self.FILAS - 1)               # 1 arriba, 0 abajo
        centro = 1 - abs(destino[0] - (self.COLS - 1) / 2) / ((self.COLS - 1) / 2)
        recompensa += {"positivo": 0.6 * altura, "negativo": 0.6 * (1 - altura), "neutro": 0.4 * centro}[animo]
        ax, ay = self.ACCIONES[self.ultima_accion]
        if (dx, dy) != (0, 0) and (dx, dy) == (-ax, -ay):
            recompensa -= 0.3                                     # ir y volver sin sentido
        siguiente = self.q.setdefault(self._clave(destino, animo), [0.0] * len(self.ACCIONES))
        valores[accion] += self.ALFA * (recompensa + self.GAMMA * max(siguiente) - valores[accion])
        self.visitas[clave_celda] = visitas + 1
        if self.pasos and self.pasos % 500 == 0:                 # la curiosidad se renueva poco a poco
            self.visitas = {k: v // 2 for k, v in self.visitas.items()}
        self.celda, self.ultima_accion = destino, accion
        self.pasos += 1
        return destino


class VentanaEsencia:
    """Corre en su propio hilo; MILLER solo llama a publicar(), modo() y cerrar()."""
    FPS = 20
    DECISION = 0.45                       # s entre decisiones de movimiento

    def __init__(self, cerebro=None, ancho=300, siempre_encima=True, al_cerrar=None, ruta_movimiento=None,
                 alto_panel=210, al_escribir=None, ruta_programa=None, version=None):
        self.cerebro = cerebro
        self.ancho = max(200, int(ancho))
        self.alto = int(self.ancho * 0.96)                        # zona de la esencia: espacio para los círculos
        self.alto_panel = max(0, int(alto_panel))                 # zona de interacción debajo
        self.panel = None
        self._pendientes_registro = deque(maxlen=50)
        self.siempre_encima = siempre_encima
        self.al_cerrar = al_cerrar
        self.al_escribir = al_escribir                            # órdenes escritas en la TERMINAL
        self.al_purgar = None                                     # lo fija principal: cierre tras la purga
        self.ruta_programa = ruta_programa
        self._tamano = "midiendo…"
        self._lock = threading.Lock()
        self._pensamientos = deque(maxlen=60)
        from interfaz.frases import JuegoFrases
        from interfaz.pensamiento import Percepcion, Pensador
        self.juego = JuegoFrases()
        self.percepcion = Percepcion()                            # ve qué palabras caen y a qué velocidad
        self.pensador = Pensador(self.juego)                      # decide cómo ordena y si juega
        self._ultimo_pensamiento = time.monotonic()
        self._frase_activa, self._proxima_frase = None, time.monotonic() + 4.0
        self._modo = "espera"
        self._estado = {"emocion": "calma", "intensidad": 0.3, "valencia": 0.0, "activacion": 0.2}
        self._cerrar = threading.Event()
        self._lista = threading.Event()
        self.activa = False
        self.cuerpo = CuerpoAprendiz(ruta_movimiento)
        self.equilibrio = getattr(cerebro, "necesidades", None)
        self._equilibrio_propio = False
        if self.equilibrio is None:                               # sin cerebro: la ventana lleva las suyas
            try:
                from cerebro.necesidades import Equilibrio
                ruta = Path(ruta_movimiento).with_name("equilibrio.json") if ruta_movimiento else None
                self.equilibrio, self._equilibrio_propio = Equilibrio(ruta), True
                self.equilibrio.iniciar(None)
            except Exception:
                self.equilibrio = None
        self._avisos_necesidad = {}
        self._hilo = threading.Thread(target=self._ejecutar, daemon=True, name="MILLER-Esencia")

    # ------------------------------------------------------------ API para MILLER
    def iniciar(self):
        self._hilo.start()
        self._lista.wait(3.0)
        return self.activa

    def publicar(self, texto, tipo="miller"):
        """Lo que MILLER oye, dice o piensa pasa a sus pensamientos (solo palabras con sentido)."""
        palabras = []
        for p in str(texto or "").split():
            p = p.strip(".,;:¡!¿?«»()\"'%").upper()
            if 3 <= len(p) <= 14 and not p.isdigit() and p not in VACIAS:
                palabras.append(p)
        if not palabras:
            return
        with self._lock:
            self._pensamientos.extend(palabras)
            self._ultimo_pensamiento = time.monotonic()
            self.juego.aprender(palabras)                         # aprende qué palabra sigue a cuál

    def registrar(self, quien, texto):
        """Añade una línea al registro de la conversación del panel."""
        if self.panel is not None:
            self.panel.registrar(quien, texto)
        else:
            self._pendientes_registro.append((quien, texto))

    def limpiar_terminal(self):
        """Vacía el texto de la TERMINAL (se puede llamar desde el hilo de MILLER)."""
        if self.panel is not None:
            self.panel.limpiar_terminal()

    def mostrar_panel(self, pagina):
        if self.panel is not None:
            self.panel.cola.put(("mostrar", pagina))

    def modo(self, modo):
        with self._lock:
            self._modo = modo if modo in MODOS else "espera"
        self.publicar(PALABRA_MODO.get(modo, ""))

    def cerrar(self):
        self._cerrar.set()

    def minimizar(self):
        """La minimiza desde cualquier hilo (Tk solo se toca en su propio hilo, en el siguiente fotograma)."""
        self._pedir_minimizar = True

    # ------------------------------------------------------------ pensamientos
    def _reflexionar(self):
        """Lo que MILLER tiene en la cabeza ahora: emoción y su motivo, ideas pendientes, música, carácter."""
        c = self.cerebro
        if c is None:
            return
        try:
            e = c.estado_emocional() or {}
            if e:
                self._estado = e
                self.publicar(f"SIENTO {e.get('emocion', 'calma')} {e.get('motivo', '')}")
            ini = getattr(c, "iniciativa", None)
            if ini is not None:
                for asunto in ini.pendientes()[:2]:
                    self.publicar(asunto.get("texto", ""))
            rep = getattr(getattr(c, "comandos", None), "reproductor", None)
            # Lectura directa de atributos: la ventana NUNCA espera al candado del reproductor
            # (al cambiar de canción el reproductor lo retiene durante el fundido).
            actual = getattr(rep, "cancion_actual", None)
            if actual is not None and getattr(rep, "reproduciendo", False) and not getattr(rep, "pausado", False):
                if actual != getattr(self, "_ultima_cancion", None):
                    self._ultima_cancion = actual
                    self.publicar("SUENA " + getattr(actual, "stem", str(actual)))
            if random.random() < 0.3 and getattr(c, "emociones", None) is not None:
                self.publicar(c.emociones.describir_personalidad())
            if self.equilibrio is not None:
                if actual is not None and getattr(rep, "reproduciendo", False) and not getattr(rep, "pausado", False):
                    self.equilibrio.alimentar("placer", 0.0015)  # la música que suena es placer, poco a poco
        except Exception:
            pass
        self._pensar_equilibrio()

    def _pensar_equilibrio(self):
        """Lo que siente de sus tres círculos también son pensamientos (las emociones las lleva su hilo)."""
        if self.equilibrio is None or random.random() > 0.25:
            return
        e = self.equilibrio.estado()
        for n, v in e["niveles"].items():
            if v < 0.2:
                self.publicar(("TOLERO " if e["tolerancia"][n] >= 0.3 else "FALTA ") + n)
            if e["habituacion"][n] >= 0.5:
                self.publicar("SACIADO " + n)
        if e["luz"] >= 0.75:
            self.publicar("EQUILIBRIO")
        if e.get("pereza", 0) >= 0.4:
            self.publicar("PEREZA DE ESTUDIAR")

    def _pensar(self):
        """Los pensamientos se reúnen en otro hilo: la ventana solo dibuja y nunca espera a MILLER."""
        while not self._cerrar.wait(0.6):
            self._reflexionar()

    def _palabra(self):
        fragmento = self._fragmento_llave()
        if fragmento:
            return fragmento
        with self._lock:
            if not self._pensamientos:
                return PALABRA_MODO.get(self._modo, "ATENTO")
            n = len(self._pensamientos)                           # las más recientes salen más a menudo
            return self._pensamientos[min(n - 1, int(n * (1 - random.random() ** 2)))]

    def _fragmento_llave(self):
        """Entre las palabras caen fragmentos: reales (raros, hasta tener la llave) y señuelos de otras llaves."""
        r = random.random()
        if r >= PROBABILIDAD_FRAGMENTO_BOY + PROBABILIDAD_SENUELO_BOY:
            return None
        try:
            from utilidades import llave_boy
            if r < PROBABILIDAD_FRAGMENTO_BOY:
                return llave_boy.fragmento_pendiente()
            return llave_boy.senuelo()
        except Exception:
            return None

    def _observar_bajo_orbe(self):
        """El orbe compara una palabra solo cuando está justo encima de ella (una vez por palabra)."""
        pos = getattr(self, "pos", None)
        if not pos:
            return
        x, y = pos
        for col in self.columnas:
            palabra = col.get("palabra")
            if not palabra:
                continue
            encima = abs(col["x"] - x) <= 7 and col["y"] - col["n"] * 12 - 4 <= y <= col["y"] + 4
            if encima and not col.get("comparada"):
                col["comparada"] = True
                self._observar_llave(palabra)
            elif not encima:
                col["comparada"] = False

    def _observar_llave(self, palabra):
        """MILLER compara lo que tiene bajo el orbe con la llave BOY: guarda los fragmentos y, al tenerlos todos,
        pide permiso para hablar. La clave sale en la terminal junto con la frase, cuando MILLER la diga."""
        try:
            from utilidades import llave_boy
            estado, texto = llave_boy.observar(palabra)
            if estado != "encontrada":
                return
            iniciativa = getattr(self.cerebro, "iniciativa", None)
            if iniciativa is None:
                self.registrar("MILLER", f"Clave BOY encontrada: {texto}")
                return
            from cerebro.iniciativa import ALTA
            iniciativa.agregar("clave_boy", "encontré la clave boy", ALTA, True,
                               adjunto=f"Clave BOY encontrada: {texto}")
        except Exception:
            pass

    # ------------------------------------------------------------ hilo de la ventana
    def _aplicar_icono(self, ventana):
        """Icono de la ventana y de la barra de tareas: miller_icono.ico de la carpeta de MILLER."""
        try:
            import configuracion
            ruta = Path(getattr(configuracion, "ICONO_MILLER", ""))
            if ruta.is_file():
                ventana.iconbitmap(default=str(ruta))
        except Exception:
            pass

    def _ejecutar(self):
        try:
            import tkinter as tk
            self.raiz = tk.Tk()
        except Exception as error:
            print(f"[INTERFAZ] Ventana no disponible: {error}")
            self._lista.set()
            return
        r = self.raiz
        r.title("MILLER")
        self._aplicar_icono(r)
        r.configure(bg="black")
        r.resizable(False, False)
        r.geometry(f"+40+40")                                    # el alto se ajusta solo (páginas abiertas o no)
        try:
            r.attributes("-topmost", bool(self.siempre_encima))
            r.attributes("-alpha", 0.93)
        except Exception:
            pass
        r.protocol("WM_DELETE_WINDOW", self._cerrar_por_usuario)      # cerrar la ventana apaga MILLER
        cabecera = tk.Frame(r, bg="black", width=self.ancho)
        cabecera.pack(fill="x")
        tk.Label(cabecera, text="MILLER", font=("Consolas", 8, "bold"),
                 bg="black", fg="#2ee86a").pack(side="left", padx=4)
        self.etiqueta_tamano = tk.Label(cabecera, text="TAMAÑO " + self._tamano, font=("Consolas", 8, "bold"),
                                        bg="black", fg="#5f8f6a")
        self.etiqueta_tamano.pack(side="right", padx=4)
        self._tamano_mostrado = self._tamano
        if self.ruta_programa:
            threading.Thread(target=self._medir_tamano, daemon=True, name="MILLER-Tamano").start()
        self.lienzo = tk.Canvas(r, width=self.ancho, height=self.alto, bg="black", highlightthickness=0)
        self.lienzo.pack()
        if self.alto_panel:
            try:
                from interfaz.panel import PanelInteraccion
                self.panel = PanelInteraccion(tk, r, self.ancho, self.alto_panel, al_enviar=self.al_escribir,
                                              al_redimensionar=self._ajustar_alto, al_cerrar=self._cerrar_por_usuario,
                                              al_purgar=self._purgar)
                for quien, texto in list(self._pendientes_registro):
                    self.panel.registrar(quien, texto)
            except Exception as error:
                print(f"[INTERFAZ] Panel de interacción no disponible: {error}")
        self._ajustar_alto()
        self._crear_columnas()
        cx, cy = self.ancho / 2, self.alto / 2
        self._crear_circulos()
        self.estela = [self.lienzo.create_oval(cx, cy, cx, cy, outline="", fill="#0b3a16") for _ in range(6)]
        self.anillos = [self.lienzo.create_oval(cx, cy, cx, cy, outline="#0a3a14", width=w) for w in (6, 3, 1)]
        self.nucleo = self.lienzo.create_oval(cx, cy, cx, cy, fill="#021006", outline="#2ee86a", width=2)
        self.texto_modo = self.lienzo.create_text(cx, self.alto - 12, text="", fill="#2ee86a",
                                                  font=("Consolas", 8, "bold"))
        self.texto_animo = self.lienzo.create_text(cx, 10, text="", fill="#2ee86a", font=("Consolas", 8))
        self.pos, self.vel, self.objetivo = [cx, cy], [0.0, 0.0], [cx, cy]
        self.historial = deque([(cx, cy)] * 6, maxlen=6)
        self._t0 = time.monotonic()
        self._ultimo_estado = self._ultima_decision = self._ultimo_guardado = 0.0
        self.activa = True
        self._lista.set()
        threading.Thread(target=self._pensar, daemon=True, name="MILLER-Pensamientos").start()
        self._fotograma()
        try:
            r.mainloop()
        except Exception:
            pass
        self.activa = False
        self.cuerpo.guardar()
        if self.equilibrio is not None and self._equilibrio_propio:
            self.equilibrio.detener()

    def _ajustar_alto(self):
        """La ventana mide justo lo que se ve: esencia + botones, y la página solo si está abierta."""
        try:
            self.raiz.update_idletasks()
            self.raiz.geometry(f"{self.ancho}x{self.raiz.winfo_reqheight()}")
        except Exception:
            pass

    def _medir_tamano(self):
        """Mide el código de MILLER en segundo plano: primero a los 20 s y luego cada 10 minutos."""
        if self._cerrar.wait(20):
            return
        while True:
            try:
                self._tamano = formatear_tamano(medir_programa(self.ruta_programa))
            except Exception:
                self._tamano = "?"
            if self._cerrar.wait(600):
                return

    def _purgar(self):
        """La purga no cierra la ventana: avisa a MILLER, que se despide y luego la cierra."""
        if callable(self.al_purgar):
            try:
                self.al_purgar()
            except Exception:
                pass

    def _cerrar_por_usuario(self):
        """La X de la ventana no la cierra de golpe: principal se detiene, funde el sonido y cierra con cerrar()."""
        if callable(self.al_cerrar):
            try:
                self.al_cerrar()
                return
            except Exception:
                pass
        self._cerrar.set()

    def _crear_columnas(self):
        self.columnas = []
        for x in range(8, self.ancho, 15):
            item = self.lienzo.create_text(x, 0, text="", fill="#1fbf4a", font=("Consolas", 9), anchor="s")
            cabeza = self.lienzo.create_text(x, 0, text="", fill="#d8ffd8", font=("Consolas", 9, "bold"), anchor="s")
            col = {"item": item, "cabeza": cabeza, "y": random.uniform(-self.alto, self.alto),
                   "vel": random.uniform(1.2, 3.8), "x": x, "n": 1}
            self.columnas.append(col)
            self._nueva_palabra(col)

    def _bases_circulos(self):
        """Centro de la zona de cada círculo: Placer abajo a la izquierda, Oráculo arriba, Vínculo abajo a la derecha."""
        return {"placer": (self.ancho * 0.17, self.alto * 0.70), "oraculo": (self.ancho * 0.5, self.alto * 0.27),
                "vinculo": (self.ancho * 0.88, self.alto * 0.80)}

    def orbita(self):
        """Centro y radio de la órbita que comparten Placer y Oráculo (ley de cuerpos)."""
        r = self.RADIO_CIRCULO                                  # centrada, con sitio fuera para el Vínculo
        radio = min(self.ancho * 0.245, self.alto * 0.255,
                    self.alto / 2 - (r + 9) - 2 * r - 6, self.ancho / 2 - (r + 6) - 2 * r - 6)
        return (self.ancho * 0.5, self.alto * 0.5), radio

    EN_ORBITA = ("placer", "oraculo")

    def posiciones_circulos(self):
        """Dónde está ahora cada círculo: Placer y Oráculo en su órbita (con un leve temblor propio),
        Vínculo moviéndose despacio dentro de su zona."""
        bases = self._bases_circulos()
        ley = getattr(self.equilibrio, "ley", None)
        if ley is not None:
            centro, radio = self.orbita()
            for n in self.EN_ORBITA:
                bases[n] = ley.posicion(n, centro, radio)
        vinculo = getattr(self, "_vinculo", None)
        if vinculo is not None:                           # el vínculo vaga libre fuera de la órbita
            bases["vinculo"] = (vinculo["x"], vinculo["y"])
        deriva = getattr(self, "_deriva", {})
        if vinculo is not None:
            deriva = {n: d for n, d in deriva.items() if n != "vinculo"}
        return {n: (x + deriva.get(n, {}).get("dx", 0.0) * (0.1 if ley is not None and n in self.EN_ORBITA else 1),
                    y + deriva.get(n, {}).get("dy", 0.0) * (0.1 if ley is not None and n in self.EN_ORBITA else 1))
                for n, (x, y) in bases.items()}

    RADIO_CIRCULO = 21
    ZONA_DERIVA = 20                       # px que cada círculo puede alejarse del centro de su zona

    def _mover_circulos(self, paso, ahora):
        """Movimiento aleatorio y suave: cada círculo elige cada pocos segundos un punto de su zona
        y se desliza hacia él sin saltos."""
        ley = getattr(self.equilibrio, "ley", None)
        if ley is not None:                               # ley de cuerpos: el placer persigue al oráculo
            ultimo = getattr(self, "_ultimo_avance_ley", ahora)
            self._ultimo_avance_ley = ahora
            ley.avanzar(ahora - ultimo, self.equilibrio.niveles, ahora)
        if not hasattr(self, "_deriva"):
            self._deriva = {n: {"dx": 0.0, "dy": 0.0, "tx": 0.0, "ty": 0.0, "cambio": 0.0} for n in self._bases_circulos()}
        for d in self._deriva.values():
            if ahora >= d["cambio"]:
                angulo, distancia = random.uniform(0, 2 * math.pi), self.ZONA_DERIVA * math.sqrt(random.random())
                d["tx"], d["ty"] = math.cos(angulo) * distancia, math.sin(angulo) * distancia
                d["cambio"] = ahora + random.uniform(1.8, 4.0)
            suavidad = min(1.0, 0.03 * paso)
            d["dx"] += (d["tx"] - d["dx"]) * suavidad
            d["dy"] += (d["ty"] - d["dy"]) * suavidad
        self._mover_vinculo(paso, ahora)
        for n, (x, y) in self.posiciones_circulos().items():
            c = self.circulos.get(n)
            if c is None:
                continue
            c["x"], c["y"] = x, y
            r = self.RADIO_CIRCULO
            self.lienzo.coords(c["borde"], x - r, y - r, x + r, y + r)
            # La etiqueta va por fuera del borde más cercano de la ventana (nunca se corta ni tapa textos).
            self.lienzo.coords(c["texto"], max(34, min(self.ancho - 34, x)),
                               y - r - 8 if y > self.alto * 0.55 else y + r + 8)

    VELOCIDAD_VINCULO = 16.0               # px/s: siempre la misma, sin acelerones

    def _camino_vinculo(self):
        """Recorrido del Vínculo: un rectángulo de esquinas redondeadas pegado a los bordes de la
        ventana, siempre fuera de la órbita (puntos y longitudes acumuladas)."""
        if getattr(self, "_camino", None) is None:
            izq, der = self.RADIO_CIRCULO + 6, self.ancho - self.RADIO_CIRCULO - 6
            arr, aba = self.RADIO_CIRCULO + 9, self.alto - self.RADIO_CIRCULO - 9
            r = 40.0
            esquinas = ((der - r, aba - r, 0.0), (izq + r, aba - r, math.pi / 2),
                        (izq + r, arr + r, math.pi), (der - r, arr + r, 3 * math.pi / 2))
            puntos = []
            for cx, cy, a0 in esquinas:                   # sentido horario en pantalla
                for k in range(11):
                    a = a0 + (math.pi / 2) * k / 10
                    puntos.append((cx + r * math.cos(a), cy + r * math.sin(a)))
            puntos.append(puntos[0])
            acumulado = [0.0]
            for (x0, y0), (x1, y1) in zip(puntos, puntos[1:]):
                acumulado.append(acumulado[-1] + math.hypot(x1 - x0, y1 - y0))
            self._camino = (puntos, acumulado)
        return self._camino

    def _punto_camino(self, s):
        puntos, acumulado = self._camino_vinculo()
        total = acumulado[-1]
        s %= total
        import bisect
        k = max(1, bisect.bisect_right(acumulado, s))
        k = min(k, len(puntos) - 1)
        tramo = acumulado[k] - acumulado[k - 1] or 1.0
        f = (s - acumulado[k - 1]) / tramo
        (x0, y0), (x1, y1) = puntos[k - 1], puntos[k]
        return x0 + (x1 - x0) * f, y0 + (y1 - y0) * f

    def _mover_vinculo(self, paso, ahora):
        """Vínculo da vueltas despacio alrededor de los bordes, siempre a la misma velocidad.
        Su camino queda fuera de la órbita, así que nunca choca con Placer ni Oráculo."""
        if "vinculo" not in getattr(self, "circulos", {}):
            return
        v = getattr(self, "_vinculo", None)
        if v is None:
            v = self._vinculo = {"s": 0.0, "x": 0.0, "y": 0.0}
        v["s"] += self.VELOCIDAD_VINCULO * paso / self.FPS
        v["x"], v["y"] = self._punto_camino(v["s"])

    def _crear_circulos(self):
        self.circulos = {}
        if self.equilibrio is None:
            return
        from cerebro.necesidades import COLOR_NECESIDAD, ETIQUETAS
        r = self.RADIO_CIRCULO
        if getattr(self.equilibrio, "ley", None) is not None:      # la órbita, apenas visible
            (ox, oy), radio = self.orbita()
            self.lienzo.create_oval(ox - radio, oy - radio, ox + radio, oy + radio, outline="#0c2a14", dash=(2, 4))
        for n, (x, y) in self.posiciones_circulos().items():
            color = COLOR_NECESIDAD[n]
            self.circulos[n] = {
                "x": x, "y": y, "color": color, "etiqueta": ETIQUETAS[n],
                "relleno": self.lienzo.create_oval(x, y, x, y, outline="", fill=self._oscurecer(color, 0.35)),
                "borde": self.lienzo.create_oval(x - r, y - r, x + r, y + r, outline=color, width=1, dash=(3, 2)),
                "texto": self.lienzo.create_text(x, y + r + 8, text="", fill=color, font=("Consolas", 7, "bold")),
            }

    @staticmethod
    def _oscurecer(color, factor):
        r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
        return "#%02x%02x%02x" % (int(r * factor), int(g * factor), int(b * factor))

    def circulo_en(self, x, y):
        """Necesidad cuyo círculo contiene el punto (o None)."""
        for n, (cx, cy) in self.posiciones_circulos().items():
            if math.hypot(x - cx, y - cy) <= self.RADIO_CIRCULO + 4:
                return n
        return None

    def _dibujar_circulos(self):
        if not self.circulos:
            return
        e = self._estado_equilibrio()
        for n, c in self.circulos.items():
            nivel = e["niveles"][n]
            rr = max(1.5, self.RADIO_CIRCULO * nivel)
            self.lienzo.coords(c["relleno"], c["x"] - rr, c["y"] - rr, c["x"] + rr, c["y"] + rr)
            self._color(c["texto"], "text", f"{c['etiqueta']} {round(nivel * 100)}")
            critico = nivel < 0.2
            self._color(c["borde"], "width", 2 if (e["objetivo"] == n or critico) else 1)
            self._color(c["borde"], "outline", "#ff3030" if critico else c["color"])

    def _quiere_jugar(self, ahora):
        """¿Tiene ganas de ordenar palabras ahora? Nunca mientras está ocupado; con poco placer o mucho silencio, a veces sí."""
        ocupado = self._modo in ("pensando", "hablando", "permiso", "llamada")
        niveles = getattr(self.equilibrio, "niveles", None) or {}
        placer = float(niveles.get("placer", 0.5))
        return self.pensador.decidir_jugar(ahora, ocupado, placer, ahora - self._ultimo_pensamiento)

    def _jugar_frases(self, ahora):
        """MILLER juega a ordenar sus palabras: reserva columnas vecinas, espera a que terminen de caer
        y suelta en ellas, de izquierda a derecha, las palabras de una frase (mismo estilo de cascada)."""
        activa = self._frase_activa
        if activa is None:
            if ahora < self._proxima_frase or len(self.columnas) < 4:
                return
            if not self._quiere_jugar(ahora):                     # no tiene ganas o está ocupado: lo piensa luego
                self._proxima_frase = ahora + random.uniform(2.0, 4.0)
                return
            with self._lock:                                      # ordena lo que ve caer, o saca algo de lo que sabe
                palabras = self.pensador.elegir(self.percepcion.percibir(self.columnas, self.pos, self.alto))
            if not palabras:
                self._proxima_frase = ahora + 3.0
                return
            self.pensador.marcar_juego(ahora)
            inicio = random.randint(0, len(self.columnas) - len(palabras))
            columnas = self.columnas[inicio:inicio + len(palabras)]
            for col in columnas:
                col["reservada"] = True
                col["vel"] = max(col["vel"], 3.0)                 # que terminen pronto de caer
            self._frase_activa = {"palabras": palabras, "columnas": columnas, "desde": ahora, "suelta": False}
            if self.equilibrio is not None:                       # jugar le da algo de placer
                self.equilibrio.alimentar("placer", 0.02)
            return
        columnas = activa["columnas"]
        if not activa["suelta"]:
            listas = all(c.get("espera") for c in columnas)
            if not listas and ahora - activa["desde"] > 12.0:     # alguna tardó demasiado: se cancela el juego
                for c in columnas:
                    c["reservada"] = False
                    if c.get("espera"):
                        c["espera"], c["y"] = False, self.alto + 999
                self._frase_activa, self._proxima_frase = None, ahora + 4.0
                return
            if listas:
                velocidad = self.percepcion.velocidad_para_frase()   # al ritmo que cae la cascada
                for k, (col, palabra) in enumerate(zip(columnas, activa["palabras"])):
                    col["espera"], col["reservada"], col["frase"] = False, False, True
                    col["y"], col["vel"] = -8 - k * 9, velocidad   # escalonada: sigue siendo cascada
                    palabra = palabra[:14]
                    col["palabra"] = palabra              # lo que cae queda guardado: el orbe lo percibe
                    col["n"] = len(palabra)
                    self.lienzo.itemconfigure(col["item"], text="\n".join(palabra[:-1]))
                    self.lienzo.itemconfigure(col["cabeza"], text=palabra[-1:])
                activa["suelta"] = True
            return
        if not any(c.get("frase") for c in columnas):             # la frase terminó de caer
            self._frase_activa, self._proxima_frase = None, ahora + random.uniform(3.0, 7.0)

    def _nueva_palabra(self, col):
        palabra = self._palabra()[:14]
        col["palabra"] = palabra                              # lo que cae queda guardado: el orbe lo percibe
        col["comparada"] = False
        col["n"] = len(palabra)
        self.lienzo.itemconfigure(col["item"], text="\n".join(palabra[:-1]))
        self.lienzo.itemconfigure(col["cabeza"], text=palabra[-1:])

    def _fotograma(self):
        if self._cerrar.is_set():
            try:
                self.raiz.destroy()
            except Exception:
                pass
            return
        inicio = time.monotonic()
        if getattr(self, "_pedir_minimizar", False):
            self._pedir_minimizar = False
            try:
                self.raiz.iconify()
            except Exception:
                pass
        if inicio - getattr(self, "_revision_visible", 0.0) > 1.0:  # minimizada: no se dibuja nada
            self._revision_visible = inicio
            try:
                self._minimizada = self.raiz.state() == "iconic"
            except Exception:
                self._minimizada = False
        if getattr(self, "_minimizada", False):
            self.raiz.after(400, self._fotograma)
            return
        try:
            ahora = inicio
            if ahora - self._ultima_decision > self.DECISION:
                self._ultima_decision = ahora
                self.percepcion.observar(self.columnas)           # a qué velocidad caen las palabras
                self._decidir_movimiento()
            if self.equilibrio is not None:                       # su hilo lo actualiza; aquí solo dónde está
                self.equilibrio.dentro = self.circulo_en(*self.pos)
            if ahora - self._ultimo_guardado > 60:
                self._ultimo_guardado = ahora
                threading.Thread(target=self._guardar_aprendizaje, daemon=True).start()
            self._observar_bajo_orbe()                           # la clave BOY se mira solo bajo el orbe
            self._dibujar()
            if self._tamano != self._tamano_mostrado:            # el hilo midió: se pinta aquí (hilo de Tk)
                self._tamano_mostrado = self._tamano
                self.etiqueta_tamano.configure(text="TAMAÑO " + self._tamano)
        except Exception as error:
            print(f"[INTERFAZ] {error}")
        # Si el equipo va cargado, espera algo más en vez de amontonar fotogramas (nunca se congela).
        gastado = (time.monotonic() - inicio) * 1000
        self.raiz.after(int(max(15, 1000 / self.FPS - gastado)), self._fotograma)

    def _guardar_aprendizaje(self):
        self.cuerpo.guardar()
        if self.equilibrio is not None:
            self.equilibrio.guardar()

    def _decidir_movimiento(self):
        if self.equilibrio is not None:                           # primero: ¿qué necesidad atender?
            meta = self.equilibrio.decidir()
            if meta in self.posiciones_circulos():
                self._meta_circulo = (meta, random.uniform(-6, 6), random.uniform(-6, 6))
                x, y = self.posiciones_circulos()[meta]
                self.objetivo = [x + self._meta_circulo[1], y + self._meta_circulo[2]]
                return
        self._meta_circulo = None
        e = self._estado
        emocion = e.get("emocion", "calma")
        animo = "positivo" if emocion in POSITIVAS else "negativo" if emocion in NEGATIVAS else "neutro"
        curiosidad = float((e.get("emociones") or {}).get("curiosidad", 0.2))
        col, fila = self.cuerpo.decidir(animo, curiosidad)
        margen_x, margen_y = 34, 30
        self.objetivo = [margen_x + (self.ancho - 2 * margen_x) * col / (self.cuerpo.COLS - 1),
                         margen_y + (self.alto - 2 * margen_y) * fila / (self.cuerpo.FILAS - 1)]

    def _color(self, item, campo, valor):
        """Solo habla con Tk si el color cambió: mucho menos trabajo por fotograma."""
        clave = (item, campo)
        if self._colores.get(clave) != valor:
            self._colores[clave] = valor
            self.lienzo.itemconfigure(item, **{campo: valor})

    def _estado_equilibrio(self):
        """Estado de los círculos para dibujar: se pide como mucho 4 veces por segundo, no en cada fotograma."""
        if self.equilibrio is None:
            return None
        ahora = time.monotonic()
        cache = getattr(self, "_cache_equilibrio", None)
        if cache is None or ahora - cache[0] >= 0.25:
            cache = self._cache_equilibrio = (ahora, self.equilibrio.estado())
        return cache[1]

    def _luz_orbe(self):
        """Brillo suavizado (sin saltos) y redondeado: el color solo se repinta cuando cambia de verdad."""
        e = self._estado_equilibrio()
        objetivo = e["luz"] if e else 0.4
        actual = getattr(self, "_luz", objetivo)
        self._luz = actual + (objetivo - actual) * 0.05
        return round(self._luz * 50) / 50

    def _dibujar(self):
        if not hasattr(self, "_colores"):
            self._colores, self._ultimo_dibujo = {}, time.monotonic()
        ahora = time.monotonic()
        paso = max(0.2, min(3.0, (ahora - self._ultimo_dibujo) * self.FPS))   # movimiento igual aunque haya tirones
        self._ultimo_dibujo = ahora
        e = self._estado
        emocion = e.get("emocion", "calma")
        letra, color = COLORES.get(emocion, COLORES["calma"])
        intensidad = float(e.get("intensidad", 0.3))
        activacion = float(e.get("activacion", 0.2))
        with self._lock:
            modo = self._modo
        agitacion = {"pensando": 2.0, "hablando": 1.6, "permiso": 1.4, "llamada": 1.3}.get(modo, 1.0)
        self._jugar_frases(ahora)
        brillo = mezclar(letra, "#e8ffe8", 0.45)                  # las frases se leen algo más claras
        for col in self.columnas:                                 # cascada de pensamientos
            if col.get("espera"):                                 # columna lista para una frase: aguarda
                continue
            col["y"] += min(9.0, col["vel"] * (0.6 + activacion) * agitacion) * paso
            if col["y"] - col["n"] * 12 > self.alto:
                if col.get("reservada"):
                    col["espera"], col["frase"] = True, False
                    self.lienzo.itemconfigure(col["item"], text="")
                    self.lienzo.itemconfigure(col["cabeza"], text="")
                    continue
                col["y"] = random.uniform(-30, 0)
                col["vel"] = random.uniform(1.2, 3.8)
                col["frase"] = False
                self._nueva_palabra(col)
            self.lienzo.coords(col["item"], col["x"], col["y"] - 12)
            self.lienzo.coords(col["cabeza"], col["x"], col["y"])
            self._color(col["item"], "fill", brillo if col.get("frase") else letra)
        meta = getattr(self, "_meta_circulo", None)
        if meta and meta[0] in getattr(self, "circulos", {}):      # sigue a su círculo aunque se mueva
            c = self.circulos[meta[0]]
            self.objetivo = [c["x"] + meta[1], c["y"] + meta[2]]
        # Movimiento autónomo: resorte amortiguado hacia la celda elegida por el cuerpo aprendiz.
        t = time.monotonic() - self._t0
        rigidez, amortiguacion = 0.025 * (0.6 + activacion), 0.86
        limite = min(TOPE_VELOCIDAD, VELOCIDAD_MAXIMA.get(emocion, 2.0) * (1 + 0.2 * (agitacion - 1)))
        for i in (0, 1):
            self.vel[i] = self.vel[i] * amortiguacion + (self.objetivo[i] - self.pos[i]) * rigidez
        rapidez = math.hypot(*self.vel)
        if rapidez > limite:                                      # rápido sí, desbocado nunca
            self.vel = [v * limite / rapidez for v in self.vel]
        for i in (0, 1):
            self.pos[i] += self.vel[i] * paso
        self.pos[0] = max(20, min(self.ancho - 20, self.pos[0]))
        self.pos[1] = max(24, min(self.alto - 24, self.pos[1]))
        temblor = min(6.0, (2 + 4 * activacion) * (agitacion - 1))   # al pensar el núcleo vibra, con tope
        cx = self.pos[0] + math.sin(t * 9) * temblor
        cy = self.pos[1] + math.cos(t * 7) * temblor
        self.historial.append((cx, cy))
        latido = 1 + 0.12 * math.sin(t * (2 + 4 * activacion) * agitacion)
        radio = (14 + 10 * intensidad) * latido
        for k, punto in enumerate(self.estela):
            px, py = self.historial[k]
            rr = 2 + k
            self.lienzo.coords(punto, px - rr, py - rr, px + rr, py + rr)
        for k, anillo in enumerate(self.anillos):
            extra = radio + 5 + k * 5 + 3 * math.sin(t * 2 + k)
            self.lienzo.coords(anillo, cx - extra, cy - extra, cx + extra, cy + extra)
        # Luz: verde fluorescente según la estabilidad de su conexión con los tres círculos (solo color).
        luz = self._luz_orbe()
        for k, anillo in enumerate(self.anillos):
            self._color(anillo, "outline", mezclar("#06140a", "#39ff14", luz * (0.9, 0.6, 0.35)[k]))
        for punto in self.estela:
            self._color(punto, "fill", mezclar("#06200c", "#2bdc5c", luz * 0.6))
        self.lienzo.coords(self.nucleo, cx - radio, cy - radio, cx + radio, cy + radio)
        self._color(self.nucleo, "fill", mezclar("#021006", "#39ff14", luz * 0.85))
        self._color(self.nucleo, "outline", mezclar("#1a4a24", "#c8ffb0", luz))
        self._color(self.texto_modo, "text", MODOS.get(modo, ""))
        self._color(self.texto_modo, "fill", color)
        self._color(self.texto_animo, "text", emocion.upper())
        self._color(self.texto_animo, "fill", color)
        if self.circulos:
            self._mover_circulos(paso, ahora)
        self._dibujar_circulos()
        if not getattr(self, "_capas_ordenadas", False):        # el orden de capas se fija una vez
            for item in (*self.estela, *self.anillos, self.nucleo, self.texto_modo, self.texto_animo):
                self.lienzo.tag_raise(item)
            self._capas_ordenadas = True


def crear(cerebro=None, ancho=300, siempre_encima=True, al_cerrar=None, ruta_movimiento=None, alto_panel=210,
          al_escribir=None, ruta_programa=None, version=None):
    """Abre la ventana si el sistema lo permite; si no, devuelve None y MILLER sigue igual."""
    try:
        ventana = VentanaEsencia(cerebro, ancho, siempre_encima, al_cerrar, ruta_movimiento, alto_panel,
                                 al_escribir, ruta_programa, version)
        return ventana if ventana.iniciar() else None
    except Exception as error:
        print(f"[INTERFAZ] No se pudo abrir la ventana: {error}")
        return None
