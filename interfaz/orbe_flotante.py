"""MILLER · El orbe: uno solo, el mismo núcleo que se ve en la cascada y encima de cualquier página.

El cerebro de la esencia decide dónde está, cómo luce y cuándo está llenando un círculo (guiar): entonces el
orbe desaparece de la ventana. Este módulo lo pinta, se arrastra (y el cerebro lo sigue), percibe el puntero
(se aparta un poco) y aprende de su entorno con utilidades/orbe_entorno.py. Sin cerebro que lo guíe se mueve
solo, con su propia deriva. Solo se toca desde el hilo de la interfaz.
"""
import math
import random
import time
from datetime import datetime

LADO = 68                # caja del orbe: cabe el núcleo y sus anillos
INTERVALO_MS = 60
DISTANCIA_HUIDA = 70
RADIO_MAXIMO = 20.0      # el núcleo no crece más que esto (los anillos quedan dentro de la caja)
COLORES = {"contento": "#e6fff0", "atento": "#2ee86a", "dormido": "#5fd38c"}


def _acotar(valor, minimo, maximo):
    return max(minimo, min(maximo, valor))


class OrbeFlotante:
    def __init__(self, tk, contenedor, ancho, alto, aprendiz, musica_fn=None, inactividad_fn=None,
                 fondo_fn=None, al_arrastrar=None):
        self.contenedor, self.ancho, self.alto = contenedor, ancho, alto
        self.aprendiz = aprendiz
        self.musica_fn = musica_fn or (lambda: False)
        self.inactividad_fn = inactividad_fn or (lambda: 0.0)
        self.fondo_fn = fondo_fn or (lambda: "black")
        self.al_arrastrar = al_arrastrar
        self.lienzo = tk.Canvas(contenedor, width=LADO, height=LADO, bg="black", highlightthickness=0, bd=0,
                                cursor="fleur")
        x0, y0 = aprendiz.posicion_de_reposo(ancho, alto, LADO)
        self.x, self.y = float(x0), float(y0)
        self.vx = self.vy = 0.0
        self.guiado = False          # True cuando el cerebro de la esencia dice dónde está
        self.arrastrando = False
        self._oculto = False
        self._mostrado = False
        self._vista = None           # (radio, relleno, borde, anillos) que pide el cerebro
        self._fase = 0.0
        self._ultimo = time.monotonic()
        self.lienzo.bind("<ButtonPress-1>", self._pulsar)
        self.lienzo.bind("<B1-Motion>", self._arrastrar)
        self.lienzo.bind("<ButtonRelease-1>", self._soltar)
        self._colocar()
        contenedor.after(INTERVALO_MS, self._latir)

    def elevar(self):
        """Lo pone por encima de la página abierta (se llama al abrir cada página)."""
        self.lienzo.lift()

    def centro(self):
        return self.x + LADO / 2, self.y + LADO / 2

    # ------------------------------------------------------------ lo que dice el cerebro
    def guiar(self, cx, cy, radio, relleno, borde, anillos, oculto=False):
        """El cerebro dice dónde está el orbe, su tamaño, sus colores y si debe verse. Lo pinta en el momento;
        no lo mueve (el cerebro ya lo ha movido)."""
        self.guiado = True
        if not self.arrastrando:
            self.x = _acotar(cx - LADO / 2, 0, self.ancho - LADO)
            self.y = _acotar(cy - LADO / 2, 0, self.alto - LADO)
        self._oculto = bool(oculto)
        self._colocar()
        if self._oculto:
            return
        self._vista = (_acotar(radio, 4.0, RADIO_MAXIMO), relleno, borde, anillos)
        self._dibujar_vista()

    def empuje(self):
        """Lo que percibe del puntero: un empujón suave para apartarse si el puntero se acerca."""
        px, py = self._puntero()
        if px is None or self._oculto:
            return 0.0, 0.0
        cx, cy = self.centro()
        distancia = math.hypot(cx - px, cy - py)
        if 0 < distancia < DISTANCIA_HUIDA:
            empuje = (DISTANCIA_HUIDA - distancia) / DISTANCIA_HUIDA * 1.2
            return (cx - px) / distancia * empuje, (cy - py) / distancia * empuje
        return 0.0, 0.0

    # ------------------------------------------------------------ arrastre
    def _pulsar(self, _evento):
        self.arrastrando = True
        self.vx = self.vy = 0.0

    def _arrastrar(self, evento):
        if not self.arrastrando:
            return
        self.x = _acotar(evento.x_root - self.contenedor.winfo_rootx() - LADO / 2, 0, self.ancho - LADO)
        self.y = _acotar(evento.y_root - self.contenedor.winfo_rooty() - LADO / 2, 0, self.alto - LADO)
        self._colocar()
        if callable(self.al_arrastrar):
            self.al_arrastrar(*self.centro())

    def _soltar(self, _evento):
        if not self.arrastrando:
            return
        self.arrastrando = False
        self.aprendiz.registrar_reposo(self.x / max(self.ancho - LADO, 1), self.y / max(self.alto - LADO, 1))
        self.aprendiz.guardar(forzar=True)

    def _colocar(self):
        if self._oculto:
            if self._mostrado:
                self.lienzo.place_forget()
                self._mostrado = False
            return
        self.lienzo.place(x=round(self.x), y=round(self.y))
        self._mostrado = True

    # ------------------------------------------------------------ vida propia
    def _latir(self):
        try:
            if not self.lienzo.winfo_exists():
                return
            ahora = time.monotonic()
            segundos = min(ahora - self._ultimo, 2.0)
            self._ultimo = ahora
            inactivo = float(self.inactividad_fn() or 0.0)
            musica = bool(self.musica_fn())
            self.lienzo.configure(bg=self.fondo_fn())
            activo = inactivo <= 60.0
            self.aprendiz.registrar_tiempo(segundos, activo, musica, datetime.now().hour)
            self._fase = (self._fase + 0.12) % (2 * math.pi)
            if not self.guiado and not self.arrastrando:            # sin cerebro: se mueve solo
                self._andar(activo)
                self._colocar()
                self._dibujar(COLORES[self.aprendiz.estado(inactivo, musica)])
            self.aprendiz.guardar()
        except Exception:
            pass
        finally:
            try:
                self.contenedor.after(INTERVALO_MS, self._latir)
            except Exception:
                pass

    def _andar(self, activo):
        tx, ty = self.aprendiz.posicion_de_reposo(self.ancho, self.alto, LADO)
        ex, ey = self.empuje()
        self.vx += ex
        self.vy += ey
        vagar = 0.35 if activo else 0.08                      # dormido: casi quieto
        self.vx += (tx - self.x) * 0.0006 + random.uniform(-vagar, vagar) * 0.25
        self.vy += (ty - self.y) * 0.0006 + random.uniform(-vagar, vagar) * 0.25
        tope = 1.1 if activo else 0.35
        velocidad = math.hypot(self.vx, self.vy)
        if velocidad > tope:
            self.vx, self.vy = self.vx * tope / velocidad, self.vy * tope / velocidad
        self.vx *= 0.97
        self.vy *= 0.97
        self.x = _acotar(self.x + self.vx, 0, self.ancho - LADO)
        self.y = _acotar(self.y + self.vy, 0, self.alto - LADO)

    def _puntero(self):
        try:
            x, y = self.contenedor.winfo_pointerxy()
            return x - self.contenedor.winfo_rootx(), y - self.contenedor.winfo_rooty()
        except Exception:
            return None, None

    def _dibujar_vista(self):
        radio, relleno, borde, anillos = self._vista
        c = LADO / 2
        pulso = 1 + 0.08 * math.sin(self._fase)
        self.lienzo.delete("all")
        for k, anillo in enumerate(anillos):
            r = (radio + 6 + 5 * k) * pulso
            self.lienzo.create_oval(c - r, c - r, c + r, c + r, outline=anillo, width=2 if k == 0 else 1)
        r = radio * pulso
        self.lienzo.create_oval(c - r, c - r, c + r, c + r, fill=relleno, outline=borde, width=2)

    def _dibujar(self, color):
        """Sin cerebro: el orbe sencillo, con su halo que late."""
        self.lienzo.delete("all")
        c = LADO / 2
        halo = 9 + 2 * math.sin(self._fase)
        self.lienzo.create_oval(c - halo - 4, c - halo - 4, c + halo + 4, c + halo + 4, outline="", fill="#1b6b33")
        self.lienzo.create_oval(c - 8, c - 8, c + 8, c + 8, fill="#0a2e16", outline=color, width=3)
        self.lienzo.create_oval(c - 3, c - 3, c + 3, c + 3, fill=color, outline="")
