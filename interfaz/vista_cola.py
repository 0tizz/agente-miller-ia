"""MILLER · Vista COLA dentro de ENTORNO (biblioteca musical).

Muestra las canciones de la cola en su orden. ▲ y ▼ cambian una canción de puesto, ▶ la pone a sonar ahora y
✕ la quita; VACIAR COLA borra toda la cola. Cada orden pasa por AccionesAudio, la misma que usa la voz, y su
respuesta se escribe en la terminal.

Las filas se crean una sola vez y se reutilizan: al cambiar la cola solo se reordenan, se renumeran o se quitan
las que sobran. Así la vista se actualiza en línea sin rehacerse entera ni parpadear.
"""
from pathlib import Path

LARGO_NOMBRE = 56
SUBIR, BAJAR, REPRODUCIR, QUITAR = "subir", "bajar", "reproducir", "quitar"


def _nombre_corto(nombre):
    return nombre if len(nombre) <= LARGO_NOMBRE else nombre[: LARGO_NOMBRE - 1] + "…"


class VistaCola:
    def __init__(self, tk, padre, tema, fuente, acciones, barra_verde):
        self.tk, self.t, self.acciones = tk, tema, acciones
        self.fuente = fuente
        self.fuente_negrita = (fuente[0], fuente[1], "bold")
        F, V, VO, G = tema["FONDO"], tema["VERDE"], tema["VERDE_OSCURO"], tema["GRIS"]
        self.ambar = tema.get("AMBAR", V)
        self.marco = tk.Frame(padre, bg=F)
        cabecera = tk.Frame(self.marco, bg=F)
        cabecera.pack(side="top", fill="x", padx=4, pady=(2, 4))
        tk.Button(cabecera, text="VACIAR COLA", font=self.fuente_negrita, bg=VO, fg=V, activebackground=V,
                  highlightthickness=0, highlightbackground=F,
                  activeforeground=F, relief="flat", bd=0, cursor="hand2",
                  command=acciones.vaciar_cola).pack(side="right")
        self.titulo = tk.Label(cabecera, text="", font=self.fuente_negrita, bg=F, fg=V, anchor="w")
        self.titulo.pack(side="left", fill="x", expand=True, padx=(0, 6))
        cuerpo = tk.Frame(self.marco, bg=F)
        cuerpo.pack(side="top", fill="both", expand=True, padx=2)
        self.lienzo = tk.Canvas(cuerpo, bg=F, highlightthickness=0, bd=0)
        barra = barra_verde(cuerpo, self.lienzo.yview, tema)
        self.lienzo.configure(yscrollcommand=barra.set)
        barra.pack(side="right", fill="y")
        self.lienzo.pack(side="left", fill="both", expand=True)
        self.interior = tk.Frame(self.lienzo, bg=F)
        self._ventana = self.lienzo.create_window(0, 0, window=self.interior, anchor="nw")
        self.interior.bind("<Configure>", lambda e: self.lienzo.configure(scrollregion=self.lienzo.bbox("all")))
        self.lienzo.bind("<Configure>", lambda e: self.lienzo.itemconfigure(self._ventana, width=e.width))
        self._vacia = tk.Label(self.interior, text="La cola está vacía. Ponga canciones desde la biblioteca musical.",
                               font=self.fuente, bg=F, fg=G, anchor="w", justify="left")
        self._filas = {}      # clave -> fila creada; se reutiliza mientras la canción siga en la cola
        self._orden = []      # claves en el orden actual de la cola

    def pintar(self, cola, sonando="", pausada=False):
        """cola: rutas en orden. sonando: nombre de la canción que suena. Actualiza en sitio, sin rehacer las filas."""
        rutas = [str(p) for p in cola]
        texto = f"COLA · {len(rutas)} canción(es)" if len(rutas) != 1 else "COLA · 1 canción"
        if sonando:
            texto += f"   ·   {'PAUSADA' if pausada else 'SONANDO'}: {_nombre_corto(sonando)}"
        self.titulo.configure(text=texto)
        if not rutas:
            for fila in self._filas.values():
                fila["marco"].destroy()
            self._filas, self._orden = {}, []
            self._vacia.pack(fill="x", padx=6, pady=8)
            return
        self._vacia.pack_forget()
        # Una misma canción puede estar dos veces: la clave lleva el número de repetición.
        claves, repetidas = [], {}
        for ruta in rutas:
            n = repetidas.get(ruta, 0)
            repetidas[ruta] = n + 1
            claves.append((ruta, n))
        vivas = set(claves)
        for clave in [c for c in self._filas if c not in vivas]:
            self._filas.pop(clave)["marco"].destroy()
        total = len(claves)
        for pos, clave in enumerate(claves, start=1):
            if clave not in self._filas:
                self._filas[clave] = self._crear_fila(clave)
            self._actualizar_fila(self._filas[clave], clave, pos, total, sonando, pausada)
        if claves != self._orden:                       # solo si cambió el orden o entró/salió alguna canción
            for clave in claves:
                marco = self._filas[clave]["marco"]
                marco.pack_forget()
                marco.pack(fill="x", padx=3, pady=2)
            self._orden = claves

    def _crear_fila(self, clave):
        tk, t = self.tk, self.t
        F, V, VO, G = t["FONDO"], t["VERDE"], t["VERDE_OSCURO"], t["GRIS"]
        marco = tk.Frame(self.interior, bg=F, highlightthickness=1, highlightbackground=VO)
        botones = tk.Frame(marco, bg=F)
        botones.pack(side="right", padx=3, pady=3)          # primero los botones: el nombre no los empuja
        fila = {"marco": marco, "botones": []}
        for texto, orden in (("▲", SUBIR), ("▼", BAJAR), ("▶", REPRODUCIR), ("✕", QUITAR)):
            boton = tk.Button(botones, text=texto, font=self.fuente_negrita, width=2, bg=VO, fg=V,
                              highlightthickness=0, highlightbackground=F,
                              activebackground=V, activeforeground=F, relief="flat", bd=0, cursor="hand2",
                              command=lambda o=orden, c=clave: self._ordenar(o, c))
            boton.pack(side="left", padx=1)
            fila["botones"].append((orden, boton))
        fila["badge"] = tk.Label(marco, text="", font=self.fuente_negrita, bg=F, fg=self.ambar)
        fila["badge"].pack(side="right", padx=(0, 4))
        fila["numero"] = tk.Label(marco, text="", font=self.fuente_negrita, bg=F, fg=G, width=3)
        fila["numero"].pack(side="left")
        fila["nombre"] = tk.Label(marco, text=_nombre_corto(Path(clave[0]).name), font=self.fuente, bg=F, fg=V,
                                  anchor="w")
        fila["nombre"].pack(side="left", fill="x", expand=True, padx=(2, 4))
        return fila

    def _actualizar_fila(self, fila, clave, pos, total, sonando, pausada=False):
        V, VO = self.t["VERDE"], self.t["VERDE_OSCURO"]
        suena = bool(sonando) and Path(clave[0]).name == sonando
        for orden, boton in fila["botones"]:
            apagado = (orden == SUBIR and pos == 1) or (orden == BAJAR and pos == total)
            boton.configure(state="disabled" if apagado else "normal")
        fila["numero"].configure(text=f"{pos:>2}")
        fila["badge"].configure(text=("PAUSADA" if pausada else "SONANDO") if suena else "")
        fila["nombre"].configure(fg=self.ambar if suena else V)
        fila["marco"].configure(highlightbackground=self.ambar if suena else VO)

    def _ordenar(self, orden, clave):
        """La posición se calcula al pulsar, así que siempre es la actual aunque la cola haya cambiado."""
        if clave not in self._orden:
            return
        pos = self._orden.index(clave) + 1
        if orden == SUBIR:
            self.acciones.subir_cola(pos)
        elif orden == BAJAR:
            self.acciones.bajar_cola(pos)
        elif orden == REPRODUCIR:
            self.acciones.reproducir_de_cola(pos)
        else:
            self.acciones.quitar_de_cola(pos)
