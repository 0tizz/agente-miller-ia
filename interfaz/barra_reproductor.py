"""Barra del reproductor de la ventana MILLER: canción, tiempo, progreso y los controles.

Va empaquetada abajo, dentro del contenedor de páginas: se ve en todas las páginas de MILLER.
Cada control ejecuta la misma orden que la voz (comandos.ejecutar), en un hilo aparte. Su respuesta se
escribe en la terminal («MILLER: ...»), igual que una orden de voz; la barra no muestra texto propio.
Los datos se leen sin tomar el candado del reproductor.
"""
import threading
from pathlib import Path

from utilidades import duracion as _duracion

VERDE, VERDE_OSCURO, GRIS, FONDO = "#2ee86a", "#0b2a12", "#5f8f6a", "#000000"
FUENTE = ("Consolas", 9)
FUENTE_BOTON = ("Consolas", 8, "bold")

REFRESCO_MS = 250
ALTO = 64
LARGO_TITULO = 40
BOTONES = (
    ("anterior", "<<"), ("pausa", "Pausa"), ("siguiente", ">>"), ("detener", "Parar"),
    ("bajar", "Vol-"), ("subir", "Vol+"), ("aleatorio", "Aleat."), ("repetir", "Repetir"), ("silencio", "Mudo"),
)
INTENCION = {"anterior": "ANTERIOR_AUDIO", "siguiente": "SIGUIENTE_AUDIO", "detener": "DETENER_AUDIO",
             "aleatorio": "ALEATORIO_AUDIO", "repetir": "REPETIR_AUDIO"}


def texto_titulo(nombre, pausado=False):
    """Nombre de la canción recortado, con 'pausa:' o '>' delante. Sin canción: Sin reproducción."""
    if not nombre:
        return "Sin reproducción"
    texto = nombre if len(nombre) <= LARGO_TITULO else nombre[:LARGO_TITULO - 3] + "..."
    return ("pausa: " if pausado else "> ") + texto


class BarraReproductor:
    """Barra fija abajo: título y tiempo, progreso y una fila de controles. Se refresca cada REFRESCO_MS."""

    def __init__(self, tk, padre, comandos, raiz, informar=None, acciones=None):
        self.tk, self.comandos, self.raiz = tk, comandos, raiz
        self.acciones = acciones                  # AccionesAudio: pausa, siguiente, anterior y parar se ven al instante
        self.reproductor = getattr(comandos, "reproductor", None)
        self.informar = informar                  # recibe el texto de la respuesta (se llama desde otro hilo)
        self.marco = tk.Frame(padre, bg=FONDO, height=ALTO, highlightthickness=0)
        self.marco.pack_propagate(False)
        self.marco.pack(side="bottom", fill="x")
        fila = tk.Frame(self.marco, bg=FONDO)
        fila.pack(side="top", fill="x", padx=4, pady=(2, 0))
        self.titulo = tk.Label(fila, text="Sin reproducción", font=FUENTE, bg=FONDO, fg=GRIS, anchor="w")
        self.titulo.pack(side="left", fill="x", expand=True)
        self.tiempo = tk.Label(fila, text="", font=FUENTE, bg=FONDO, fg=GRIS, anchor="e")
        self.tiempo.pack(side="right")
        self.progreso = tk.Canvas(self.marco, height=5, bg=VERDE_OSCURO, highlightthickness=0)
        self.progreso.pack(side="top", fill="x", padx=4, pady=(1, 2))
        fila_botones = tk.Frame(self.marco, bg=FONDO)
        fila_botones.pack(side="top", fill="x", padx=2, pady=(0, 2))
        self.botones = {}
        for clave, texto in BOTONES:
            boton = tk.Button(fila_botones, text=texto, font=FUENTE_BOTON, bg=FONDO, fg=VERDE,
                              activebackground=VERDE_OSCURO, activeforeground=VERDE, relief="flat", bd=0,
                              padx=0, pady=1, cursor="hand2", command=lambda c=clave: self.pulsar(c))
            boton.pack(side="left", fill="x", expand=True, padx=1)
            self.botones[clave] = boton
        self._ultimo = None
        self._tick()

    # ---------------------------------------------------------------- lectura del estado
    def _estado_reproductor(self):
        """Lo que se pinta ahora. Solo lectura: no toma el candado del reproductor."""
        r = self.reproductor
        if r is None:
            return {"titulo": "Reproductor no disponible", "tiempo": "", "frac": 0.0, "pausado": False,
                    "sonando": False, "aleatorio": False, "repetir": False, "mudo": False, "volumen": 0}
        actual = getattr(r, "cancion_actual", None)
        volumen = float(getattr(r, "volumen", 0.0) or 0.0)
        # cancion_actual sigue puesta al parar: "suena" mira si de verdad se reproduce.
        datos = {"pausado": bool(getattr(r, "pausado", False)),
                 "sonando": actual is not None and bool(getattr(r, "reproduciendo", False)),
                 "aleatorio": bool(getattr(r, "modo_aleatorio", False)),
                 "repetir": bool(getattr(r, "modo_repetir", False)),
                 "mudo": volumen <= 0.001, "volumen": round(volumen * 100)}
        if actual is None:
            datos.update(titulo=texto_titulo(None), tiempo="", frac=0.0)
        else:
            pos, dur = r.posicion_segundos(), r.duracion_segundos()
            nombre = getattr(actual, "name", None) or Path(str(actual)).name   # ruta o texto: ambos sirven
            datos.update(titulo=texto_titulo(nombre, datos["pausado"]),
                         tiempo=f"{_duracion.formatear(pos)} / {_duracion.formatear(dur)}",
                         frac=_duracion.fraccion(pos, dur))
        return datos

    def _tick(self):
        try:
            if self.marco.winfo_ismapped():
                self.refrescar()
        except Exception:
            pass                                   # un fallo de pintado no debe parar el refresco
        try:
            self.raiz.after(REFRESCO_MS, self._tick)
        except Exception:
            pass                                   # la ventana se cerró: se deja de refrescar

    def refrescar(self):
        """Repinta los textos y los botones solo si el estado cambió."""
        d = self._estado_reproductor()
        clave = (d["titulo"], d["tiempo"], d["volumen"], round(d["frac"], 3), d["pausado"], d["sonando"],
                 d["aleatorio"], d["repetir"], d["mudo"], self.progreso.winfo_width())
        if clave == self._ultimo:
            return
        self._ultimo = clave
        self.titulo.configure(text=d["titulo"])
        self.tiempo.configure(text="  ·  ".join(p for p in (d["tiempo"], f"vol {d['volumen']} %") if p))
        if not d["sonando"]:
            pausa = "Play"
        else:
            pausa = "Seguir" if d["pausado"] else "Pausa"
        self.botones["pausa"].configure(text=pausa)
        self.botones["aleatorio"].configure(fg=VERDE if d["aleatorio"] else GRIS)
        self.botones["repetir"].configure(fg=VERDE if d["repetir"] else GRIS)
        self.botones["silencio"].configure(text="Reactivar" if d["mudo"] else "Mudo")
        self._dibujar(d["frac"])

    def _dibujar(self, frac):
        ancho = max(1, self.progreso.winfo_width())
        alto = max(1, self.progreso.winfo_height())
        self.progreso.delete("all")
        self.progreso.create_rectangle(0, 0, int(ancho * frac), alto, fill=VERDE, outline="")

    # ---------------------------------------------------------------- controles
    def pulsar(self, clave):
        """Ejecuta el control sin bloquear la ventana. Desde la ventana (hilo de Tk) los controles de reproducción
        pasan por AccionesAudio, que los refleja al instante en las tarjetas y en la cola."""
        if self.acciones is not None and clave in ("pausa", "siguiente", "anterior", "detener"):
            self.acciones.controlar(clave)
            return
        threading.Thread(target=self._accion, args=(clave,), daemon=True).start()

    def _accion(self, clave):
        try:
            respuesta = self._orden(clave)
        except Exception as error:
            respuesta = f"Negativo. No pude completar el control: {error}"
        if respuesta and self.informar is not None:
            self.informar(str(respuesta))

    def _orden(self, clave):
        """Ejecuta el control con la misma orden que usa la voz y devuelve la respuesta de MILLER."""
        r = self.reproductor
        if self.comandos is None or r is None:
            return "Negativo. El reproductor no está disponible, señor."
        if clave == "silencio":
            return self._silencio(r)
        if clave == "pausa":
            if getattr(r, "cancion_actual", None) is None:
                return self.comandos.ejecutar("REPRODUCIR_MUSICA")
            return self.comandos.ejecutar("CONTINUAR_AUDIO" if getattr(r, "pausado", False) else "PAUSAR_AUDIO")
        if clave in ("bajar", "subir"):
            return self.comandos.ejecutar("VOLUMEN_AUDIO", "bajar volumen" if clave == "bajar" else "subir volumen")
        intencion = INTENCION.get(clave)
        if intencion is None:
            return "Negativo. Control desconocido, señor."
        return self.comandos.ejecutar(intencion)

    def _silencio(self, r):
        if float(getattr(r, "volumen", 0.0) or 0.0) <= 0.001:
            return "Afirmativo. Sonido recuperado, señor." if r.restaurar_volumen() \
                else "Negativo. No pude recuperar el sonido, señor."
        return "Afirmativo. Silencio, señor." if r.silenciar() else "Negativo. No pude silenciar, señor."
