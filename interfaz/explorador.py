"""MILLER · Explorador de archivos dentro de la ventana (página EXPLORADOR del panel).

Estilo del Explorador de Windows, en la zona de la ventana:
- Arriba: atrás, adelante, subir, actualizar, la dirección y Buscar. Debajo: Nueva, Cortar, Copiar, Pegar,
  Nombre, Eliminar y Propiedades.
- Izquierda: el árbol (MILLER, Disco local (C:), Archivos de MILLER y sus carpetas).
- Derecha: el contenido (nombre, tipo, tamaño, modificado). Clic en un título = ordenar. Selección múltiple
  con Ctrl y Mayús. Escribir letras salta al elemento que empieza así.
- Clic derecho o teclas: Abrir, Cortar, Copiar, Pegar, Copiar ruta, Nueva carpeta, Cambiar nombre (F2),
  Eliminar (Supr), Propiedades (Alt+Intro), Actualizar (F5).
- Abajo: resumen y estado de la selección.

La lógica está en utilidades/explorador_archivos.py. Lo que puede tardar (copiar, pegar, medir carpetas)
corre en un hilo aparte; la ventana solo se toca desde su propio hilo.
"""
import os
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path

from utilidades import acceso
from utilidades import explorador_archivos as ex

COLUMNAS = (("nombre", "Nombre", 120, True), ("tipo", "Tipo", 74, False),
            ("tamano", "Tamaño", 58, False), ("modificado", "Modificado", 116, False))
RAIZ_MILLER, RAIZ_PROGRAMA, RAIZ_ARCHIVOS = "raiz|miller", "raiz|programa", "raiz|archivos"
ANCHO_IZQUIERDA = 224      # columna izquierda: el árbol arriba y la TERMINAL abajo, cada una la mitad
MARCA_VACIO = "|vacio"


def _ignorar_enlaces(carpeta, nombres):
    """Al copiar una carpeta no se siguen ni se copian enlaces (apuntarían fuera de MILLER)."""
    return [n for n in nombres if os.path.islink(os.path.join(carpeta, n))]


class ExploradorArchivos:
    """Se dibuja dentro de «padre» (el marco de la página EXPLORADOR). No abre ventanas propias."""

    def __init__(self, padre, base, tema, fuente, en_uso=None, audio=None, aprender=None, panel_terminal=None,
                 informar=None):
        self._aprender_fn = aprender                   # avisa de los eventos del entorno (lo aprende el orbe)
        self._panel_terminal = panel_terminal          # monta la TERMINAL en la mitad inferior de la columna
        self._informar = informar                      # mensajes de ENTORNO a la terminal (desde cualquier hilo)
        import tkinter as tk
        from tkinter import ttk
        from interfaz.instalacion_ui import barra_verde
        self.tk, self.ttk, self.barra_verde = tk, ttk, barra_verde
        self.ventana = padre
        self.t, self.fuente = tema, fuente
        self.fuente_negrita = (fuente[0], fuente[1], "bold")
        self.fuente_chica = (fuente[0], max(7, fuente[1] - 1))
        self.base = Path(base).resolve()
        self._en_uso_fn = en_uso if callable(en_uso) else (lambda: set())
        self.actual = None                        # None = la raíz de MILLER (sus dos discos)
        self.historial, self.pos = [], -1
        self._todas, self._entradas = [], []
        self._orden = ("nombre", False)
        self._portapapeles = None                 # ("copiar" | "cortar", [rutas])
        self._tarea = None                        # trabajo de disco en curso (hilo aparte)
        self._llaves_vistas = self._llaves()
        self._firma_carpeta = None               # vigilancia del disco: se refresca sola, sin botón
        self._ultima_vigilancia = 0.0
        self._buffer, self._buffer_t = "", 0.0
        self._seguimiento = None
        self.audio = audio                        # AccionesAudio: cola, reproducir y papelera de las canciones
        if audio is not None:
            audio.prever = self._repintar_audio     # la vista se pinta al instante, antes del disco
        self._modo_tarjetas, self._marcos = False, []
        self._modo_cola = False                       # la derecha muestra la COLA de reproducción
        self._sel_rutas, self._ancla_ruta = set(), None
        self._firma_audio, self._orden_tarjetas = None, None
        self._tarjetas_cache = {}                # ruta -> tarjeta ya construida (se reutiliza)
        self._estilos()
        self._construir()
        self._poblar_arbol()
        self.ir(ex.raiz_de(self.base, "archivos"), forzar=True)     # por defecto: Archivos de MILLER
        self._tick()

    def al_mostrar(self):
        """La página EXPLORADOR se ha abierto otra vez: se actualiza el contenido y el modo."""
        self.recargar()

    def ocupado(self):
        """True mientras hay una copia, un pegado, un borrado o una medición en curso (el panel no cierra la página)."""
        return self._tarea is not None

    def _llaves(self):
        return frozenset(acceso.activas())

    def _en_uso(self):
        try:
            return set(self._en_uso_fn() or ())
        except Exception:
            return set()

    # ------------------------------------------------------------ construcción
    def _estilos(self):
        st = self.ttk.Style(self.ventana)
        st.theme_use("clam")
        F, V, VO = self.t["FONDO"], self.t["VERDE"], self.t["VERDE_OSCURO"]
        st.configure("Miller.Treeview", background=F, fieldbackground=F, foreground=V, bordercolor=F,
                     borderwidth=0, rowheight=20, font=self.fuente)
        st.map("Miller.Treeview", background=[("selected", VO)], foreground=[("selected", V)])
        st.configure("Miller.Treeview.Heading", background=VO, foreground=V, relief="flat", borderwidth=0,
                     font=self.fuente_negrita)
        st.map("Miller.Treeview.Heading", background=[("active", V)], foreground=[("active", F)])

    def _boton(self, padre, texto, orden, fuente=None):
        return self.tk.Button(padre, text=texto, font=fuente or self.fuente, bg=self.t["FONDO"],
                              fg=self.t["VERDE"], activebackground=self.t["VERDE_OSCURO"],
                              activeforeground=self.t["VERDE"], relief="flat", bd=0, padx=3, cursor="hand2",
                              command=orden)

    def _construir(self):
        tk, F, V, VO, G = self.tk, self.t["FONDO"], self.t["VERDE"], self.t["VERDE_OSCURO"], self.t["GRIS"]
        v = self.ventana

        # Fila 1: navegación, dirección y Buscar a la derecha.
        nav = tk.Frame(v, bg=F)
        nav.pack(side="top", fill="x", padx=2, pady=(2, 1))
        self.b_atras = self._boton(nav, "◀", self.atras)
        self.b_adelante = self._boton(nav, "▶", self.adelante)
        self.b_subir = self._boton(nav, "▲", self.subir)
        for boton in (self.b_atras, self.b_adelante, self.b_subir):
            boton.pack(side="left", padx=(0, 1))
        self.buscar_var = tk.StringVar(master=v)
        self.buscar_var.trace_add("write", lambda *_: self._llenar_lista())
        self.caja_buscar = tk.Entry(nav, textvariable=self.buscar_var, width=10, bg="#03140a", fg=V,
                                    insertbackground=V, font=self.fuente, relief="flat", highlightthickness=1,
                                    highlightbackground=VO, highlightcolor=V)
        self.caja_buscar.pack(side="right", ipady=1, padx=(3, 0))
        self.caja_buscar.bind("<Escape>", lambda e: self.buscar_var.set(""))
        self.caja_buscar.bind("<Return>", lambda e: self._enfocar(self.lista))
        tk.Label(nav, text="Buscar", font=self.fuente, bg=F, fg=G).pack(side="right")
        self.direccion = tk.Entry(nav, bg="#03140a", fg=V, insertbackground=V, font=self.fuente, relief="flat",
                                  highlightthickness=1, highlightbackground=VO, highlightcolor=V)
        self.direccion.pack(side="left", fill="x", expand=True, ipady=1, padx=(3, 0))
        self.direccion.bind("<Return>", self._ir_escrita)


        # Resumen y estado: ya no se muestran (el espacio está en la ventana MILLER); se crean por si algo los usa.
        pie = tk.Frame(v, bg=F)
        self.resumen = tk.Label(pie, text="", anchor="w", font=self.fuente_chica, bg=F, fg=G)
        self.estado = tk.Label(pie, text="", anchor="w", font=self.fuente, bg=F, fg=V)

        # Cuerpo: árbol a la izquierda, contenido a la derecha.
        cuerpo = tk.Frame(v, bg=F)
        cuerpo.pack(side="top", fill="both", expand=True, padx=2)
        izquierda = tk.Frame(cuerpo, bg=F, width=ANCHO_IZQUIERDA)
        izquierda.pack(side="left", fill="y")
        izquierda.pack_propagate(False)
        # Columna izquierda: arriba el árbol de MILLER, abajo la TERMINAL; cada una ocupa la mitad de la altura.
        arriba = tk.Frame(izquierda, bg=F)
        arriba.place(relx=0, rely=0, relwidth=1, relheight=0.5)
        abajo = tk.Frame(izquierda, bg=F)
        abajo.place(relx=0, rely=0.5, relwidth=1, relheight=0.5)
        self.arbol = self.ttk.Treeview(arriba, show="tree", style="Miller.Treeview", selectmode="browse")
        barra_a = self.barra_verde(arriba, self.arbol.yview, self.t)
        self.arbol.configure(yscrollcommand=barra_a.set)
        barra_a.pack(side="right", fill="y")
        self.arbol.pack(side="left", fill="both", expand=True)
        if callable(self._panel_terminal):
            self._panel_terminal(abajo)
        self.arbol.bind("<<TreeviewOpen>>", self._expandir)
        self.arbol.bind("<<TreeviewSelect>>", self._seleccion_arbol)

        derecha = tk.Frame(cuerpo, bg=F)
        derecha.pack(side="left", fill="both", expand=True, padx=(3, 0))
        self.franja_biblioteca = tk.Frame(derecha, bg=F)
        self.titulo_franja = tk.Label(self.franja_biblioteca, text="BIBLIOTECA MUSICAL", font=self.fuente_negrita,
                                      bg=F, fg=G, anchor="w")
        self.titulo_franja.pack(side="left", fill="x", expand=True, padx=(4, 0), pady=3)
        self.boton_cola = tk.Button(self.franja_biblioteca, text="COLA", font=self.fuente_negrita, bg=VO, fg=V,
                                    activebackground=V, activeforeground=F, relief="flat", bd=0, cursor="hand2",
                                    command=self._alternar_cola_vista)
        self.boton_cola.pack(side="right", padx=4, pady=3)
        self.boton_cola.configure(highlightthickness=0, highlightbackground=F)   # sin borde blanco al repintar
        self._titulos_base = {clave: titulo for clave, titulo, _, _ in COLUMNAS}
        self.vista_lista = tk.Frame(derecha, bg=F)            # la lista de siempre (carpetas y documentos)
        self.lista = self.ttk.Treeview(self.vista_lista, columns=[c[0] for c in COLUMNAS], show="headings",
                                       style="Miller.Treeview", selectmode="extended")
        for clave, titulo, ancho, estira in COLUMNAS:
            self.lista.heading(clave, text=titulo, anchor="w", command=lambda c=clave: self._ordenar_por(c))
            self.lista.column(clave, width=ancho, minwidth=40, anchor="w", stretch=estira)
        self.lista.tag_configure("gris", foreground=G)
        barra_l = self.barra_verde(self.vista_lista, self.lista.yview, self.t)
        self.lista.configure(yscrollcommand=barra_l.set)
        barra_l.pack(side="right", fill="y")
        self.lista.pack(side="left", fill="both", expand=True)
        self.vista_lista.pack(side="left", fill="both", expand=True)
        self._construir_tarjetas(derecha)
        self.vista_cola = None
        if self.audio is not None:
            from interfaz.vista_cola import VistaCola
            self.vista_cola = VistaCola(tk, derecha, self.t, self.fuente, self.audio, self.barra_verde)
        self.lista.bind("<<TreeviewSelect>>", self._seleccion_lista)
        self.lista.bind("<Double-1>", self._doble_clic)
        self.lista.bind("<Return>", self._doble_clic)
        self.lista.bind("<Alt-Return>", lambda e: self._propiedades())
        self.lista.bind("<BackSpace>", lambda e: self.subir())
        self.lista.bind("<F2>", lambda e: self._renombrar())
        self.lista.bind("<Delete>", lambda e: self._eliminar())
        self.lista.bind("<Control-x>", lambda e: self._cortar())
        self.lista.bind("<Control-c>", lambda e: self._copiar())
        self.lista.bind("<Control-v>", lambda e: self._pegar())
        self.lista.bind("<Control-a>", self._seleccionar_todo)
        self.lista.bind("<Control-n>", lambda e: self._nueva_carpeta())
        self.lista.bind("<Control-N>", lambda e: self._nueva_carpeta())
        self.lista.bind("<Button-3>", self._menu_contextual)
        self.lista.bind("<KeyPress>", self._teclear)
        for widget in (self.lista, self.arbol, self.direccion, self.caja_buscar, self.lienzo_tarjetas):
            widget.bind("<F5>", lambda e: self.recargar())
            widget.bind("<Alt-Left>", lambda e: self.atras())
            widget.bind("<Alt-Right>", lambda e: self.adelante())
            widget.bind("<Alt-Up>", lambda e: self.subir())
            widget.bind("<Alt-Home>", lambda e: self.ir(None))
            widget.bind("<Control-l>", lambda e: self._enfocar_seleccionando(self.direccion))
            widget.bind("<Control-f>", lambda e: self._enfocar_seleccionando(self.caja_buscar))
        self.arbol.bind("<Button-3>", self._menu_contextual)

        self.menu = tk.Menu(v, tearoff=0, bg=F, fg=V, activebackground=VO, activeforeground=V,
                            font=self.fuente, bd=1, relief="flat")
        for entrada in (("Abrir", self._doble_clic, "Intro"), ("Cortar", self._cortar, "Ctrl+X"),
                                       ("Copiar", self._copiar, "Ctrl+C"), ("Pegar", self._pegar, "Ctrl+V"),
                                       ("Copiar ruta", self._copiar_ruta, ""), None,
                                       ("Nueva carpeta", self._nueva_carpeta, "Ctrl+N"),
                                       ("Cambiar nombre", self._renombrar, "F2"),
                                       ("Eliminar", self._eliminar, "Supr"), None,
                                       ("Propiedades", self._propiedades, "Alt+Intro"), None,
                                       ("Actualizar", self.recargar, "F5")):
            if entrada is None:
                self.menu.add_separator()
            else:
                etiqueta, orden, atajo = entrada
                self.menu.add_command(label=etiqueta, command=orden, accelerator=atajo)

    def _enfocar(self, widget):
        widget.focus_set()
        return "break"

    def _enfocar_seleccionando(self, entrada):
        entrada.focus_set()
        entrada.select_range(0, "end")
        return "break"

    # ------------------------------------------------------------ árbol: MILLER, sus discos y las carpetas
    def _poblar_arbol(self):
        self.arbol.delete(*self.arbol.get_children())
        self.arbol.insert("", "end", iid=RAIZ_MILLER, text=RAIZ_MILLER, open=True)
        llaves = self._llaves()
        for vista, iid in (("programa", RAIZ_PROGRAMA), ("archivos", RAIZ_ARCHIVOS)):
            texto = ex.DISCOS[vista] + ("" if ex.puede_ver(vista, llaves) else "  ⛔")
            self.arbol.insert(RAIZ_MILLER, "end", iid=iid, text=texto, open=False)
            self._cargar_hijos(iid, ex.raiz_de(self.base, vista))

    def _cargar_hijos(self, iid, carpeta):
        for hijo in self.arbol.get_children(iid):
            self.arbol.delete(hijo)
        for sub in ex.subcarpetas(carpeta, self.base, self._llaves()):
            nodo = str(sub["ruta"])
            if self.arbol.exists(nodo):
                continue
            self.arbol.insert(iid, "end", iid=nodo, text=sub["nombre"])
            self.arbol.insert(nodo, "end", iid=nodo + MARCA_VACIO, text="")     # marca: muestra la flecha

    def _cargado(self, iid):
        hijos = self.arbol.get_children(iid)
        return bool(hijos) and not (len(hijos) == 1 and hijos[0].endswith(MARCA_VACIO))

    def _expandir(self, _evento=None):
        iid = self.arbol.focus()
        if not iid or iid.endswith(MARCA_VACIO) or iid.startswith("raiz|") or self._cargado(iid):
            return
        self._cargar_hijos(iid, Path(iid))

    def _seleccion_arbol(self, _evento=None):
        sel = self.arbol.selection()
        if not sel or sel[0].endswith(MARCA_VACIO):
            return
        iid = sel[0]
        if iid == RAIZ_MILLER:
            self.ir(None)
        elif iid == RAIZ_PROGRAMA:
            self.ir(ex.raiz_de(self.base, "programa"))
        elif iid == RAIZ_ARCHIVOS:
            self.ir(ex.raiz_de(self.base, "archivos"))
        else:
            self.ir(Path(iid))
        # Un solo clic basta: la carpeta elegida se despliega para ver sus subcarpetas.
        if self.arbol.exists(iid):
            if not iid.startswith("raiz|") and not self._cargado(iid):
                self._cargar_hijos(iid, Path(iid))
            self.arbol.item(iid, open=True)

    def _seleccionar(self, iid):
        if self.arbol.exists(iid):
            self.arbol.selection_set(iid)
            self.arbol.see(iid)

    def _mostrar_en_arbol(self):
        """Abre en el árbol el camino hasta la carpeta actual y la deja seleccionada."""
        if self.actual is None:
            self._seleccionar(RAIZ_MILLER)
            return
        vista = ex.vista_de(self.base, self.actual)
        disco = RAIZ_ARCHIVOS if vista == "archivos" else RAIZ_PROGRAMA
        raiz = ex.raiz_de(self.base, vista)
        self.arbol.item(RAIZ_MILLER, open=True)
        self.arbol.item(disco, open=True)
        partes = self.actual.relative_to(raiz).parts
        padre = disco
        for i in range(1, len(partes) + 1):
            nodo = str(raiz.joinpath(*partes[:i]))
            if not self.arbol.exists(nodo):
                self._cargar_hijos(padre, raiz.joinpath(*partes[:i - 1]))
                if not self.arbol.exists(nodo):
                    break
            self.arbol.item(padre, open=True)
            if not self._cargado(nodo):
                self._cargar_hijos(nodo, Path(nodo))
            padre = nodo
        self._seleccionar(str(self.actual))

    # ------------------------------------------------------------ navegación
    def _aprender(self, tipo):
        """Avisa a MILLER de un evento del entorno. Sin aprendiz (p. ej. en pruebas), no hace nada."""
        fn = getattr(self, "_aprender_fn", None)
        if fn is not None:
            fn(tipo)

    def ir(self, ruta, registrar=True, forzar=False):
        """ruta None = la raíz de MILLER (sus dos discos). Ir a la misma carpeta no hace nada salvo forzar."""
        if ruta is not None:
            ruta = Path(ruta).resolve()
            if not ex.dentro_de(self.base, ruta) or not ex.navegable(self.base, ruta):
                self._avisar("Negativo. Esa carpeta no pertenece a MILLER, señor.")
                return
            if not ex.puede_ver(ex.vista_de(self.base, ruta), self._llaves()):
                self._avisar(ex.MENSAJE_BLOQUEADO)
                return
        if ruta == self.actual and not forzar:
            return
        if registrar:
            del self.historial[self.pos + 1:]
            if not self.historial or self.historial[-1] != ruta:
                self.historial.append(ruta)
            self.pos = len(self.historial) - 1
            self._aprender("carpeta")
        self.actual = ruta
        if registrar and self.buscar_var.get():
            self.buscar_var.set("")               # como el Explorador: la búsqueda se limpia al cambiar de carpeta
        self._llenar_lista()
        self._mostrar_en_arbol()
        self._actualizar_botones()
        self._escribir_direccion()

    def atras(self):
        if self.pos > 0:
            self.pos -= 1
            self.ir(self.historial[self.pos], registrar=False, forzar=True)

    def adelante(self):
        if self.pos < len(self.historial) - 1:
            self.pos += 1
            self.ir(self.historial[self.pos], registrar=False, forzar=True)

    def subir(self):
        self.ir(ex.subir(self.base, self.actual))

    def recargar(self):
        """Vuelve a leer el árbol y la carpeta. Si el disco en el que se estaba ya no se puede ver, va a MILLER."""
        self._poblar_arbol()
        perdido = self.actual is not None and not ex.puede_ver(ex.vista_de(self.base, self.actual), self._llaves())
        if perdido:
            self.actual = None
        self.ir(self.actual, registrar=False, forzar=True)
        if perdido:
            self._avisar(ex.MENSAJE_BLOQUEADO)

    def _ir_escrita(self, _evento=None):
        ok, dato = ex.ruta_desde_texto(self.base, self.direccion.get())
        if not ok:
            self._avisar(dato)
        else:
            self.ir(dato)
        return "break"

    def _escribir_direccion(self):
        self.direccion.delete(0, "end")
        self.direccion.insert(0, ex.direccion(self.base, self.actual))

    def _actualizar_botones(self):
        self.b_atras.configure(state="normal" if self.pos > 0 else "disabled")
        self.b_adelante.configure(state="normal" if self.pos < len(self.historial) - 1 else "disabled")
        self.b_subir.configure(state="disabled" if self.actual is None else "normal")

    # ------------------------------------------------------------ contenido
    def _llenar_lista(self):
        self.lista.delete(*self.lista.get_children())
        llaves = self._llaves()
        if self.actual is None:
            self._todas = ex.unidades(self.base, llaves)
        else:
            self._todas = ex.listar(self.actual, self.base, llaves)
        clave, descendente = self._orden
        self._entradas = ex.filtrar(ex.ordenar(self._todas, clave, descendente), self.buscar_var.get())
        for indice, e in enumerate(self._entradas):
            tipo = e["tipo"]
            if e["protegida"]:
                tipo += " · protegida"
            elif e["solo_lectura"]:
                tipo += " · solo lectura"
            elif e["bloqueada"]:
                tipo += " · bloqueado"
            gris = bool(e["protegida"] or e["solo_lectura"] or e["bloqueada"])
            self.lista.insert("", "end", iid=str(indice), tags=("gris",) if gris else (), values=(
                e["nombre"], tipo, ex.tamano_legible(e["tamano"]), e["modificado"]))
        self._pintar_resumen(llaves)
        self._titulos_columnas()
        self._aplicar_vista()

    def _pintar_resumen(self, llaves):
        if self.actual is None:
            cuenta = f"{len(self._todas)} discos"
        else:
            cuenta = ex.resumen(self._entradas)
        if self.buscar_var.get().strip():
            cuenta = f"coinciden {len(self._entradas)} de {len(self._todas)}  ·  {cuenta}"
        avisos = []
        if not ex.LLAVES_DISCO_C <= set(llaves):
            avisos.append("Disco local (C:) necesita PRO y NIÑOS")
        if "pro" not in llaves:
            avisos.append("solo lectura (llave PRO para modificar)")
        extra = ("  ·  " + "  ·  ".join(avisos)) if avisos else ""
        self.resumen.configure(text=f"{ex.direccion(self.base, self.actual)}  ·  {cuenta}{extra}")

    def _ordenar_por(self, clave):
        actual, descendente = self._orden
        self._orden = (clave, (not descendente) if actual == clave else False)
        self._llenar_lista()

    def _titulos_columnas(self):
        for clave, titulo in self._titulos_base.items():
            if clave == self._orden[0]:
                titulo += " ▼" if self._orden[1] else " ▲"
            self.lista.heading(clave, text=titulo)

    def _seleccionadas(self):
        if self._modo_tarjetas:
            return [e for e in self._entradas if str(e["ruta"]) in self._sel_rutas]
        return [self._entradas[int(i)] for i in self.lista.selection()
                if i.isdigit() and int(i) < len(self._entradas)]

    def _seleccion_lista(self, _evento=None):
        sel = self._seleccionadas()
        if not sel:
            self._estado("")
            return
        if len(sel) == 1:
            e = sel[0]
            texto = f"{e['nombre']}  ·  {e['tipo']}"
            if not e["carpeta"]:
                texto += f"  ·  {ex.tamano_exacto(e['tamano'])}"
        else:
            total = sum(e["tamano"] or 0 for e in sel if not e["carpeta"])
            texto = f"{len(sel)} elementos seleccionados  ·  {ex.tamano_exacto(total)} en archivos"
        self._estado(texto)

    def _seleccionar_todo(self, _evento=None):
        if self._modo_tarjetas:
            self._sel_rutas = {str(e["ruta"]) for e in self._entradas}
            self._pintar_seleccion()
            self._seleccion_lista()
            return "break"
        self.lista.selection_set(self.lista.get_children())
        return "break"

    def _doble_clic(self, _evento=None):
        sel = self._seleccionadas()
        if len(sel) != 1:
            if sel:
                self._avisar("Negativo. Seleccione un solo elemento para abrirlo, señor.")
            return "break"
        e = sel[0]
        if e["carpeta"]:
            self.ir(e["ruta"])
        else:
            self.abrir(e)
        return "break"

    def _teclear(self, evento):
        """Escribir letras salta al primer elemento cuyo nombre empieza por lo escrito (como el Explorador)."""
        if not evento.char or len(evento.char) != 1 or not evento.char.isprintable() or evento.state & 0x0C:
            return None
        ahora = time.monotonic()
        self._buffer = (self._buffer if ahora - self._buffer_t < 1.0 else "") + evento.char.lower()
        self._buffer_t = ahora
        for i, e in enumerate(self._entradas):
            if e["nombre"].lower().startswith(self._buffer):
                self.lista.selection_set(str(i))
                self.lista.focus(str(i))
                self.lista.see(str(i))
                break
        return "break"

    def _menu_contextual(self, evento):
        if evento.widget is self.arbol:
            fila = self.arbol.identify_row(evento.y)
            if fila:
                self.arbol.selection_set(fila)
            self.menu.entryconfigure("Pegar", state="disabled")
            self.menu.tk_popup(evento.x_root, evento.y_root)
            self.menu.grab_release()
            return
        if evento.widget is self.lista:
            fila = self.lista.identify_row(evento.y)
            if fila and fila not in self.lista.selection():
                self.lista.selection_set(fila)
            if fila:
                self.lista.focus(fila)
        self._abrir_menu(evento)

    def _abrir_menu(self, evento):
        """Menú contextual con las opciones que valen para la selección actual."""
        hay = bool(self._seleccionadas())
        for etiqueta in ("Abrir", "Cortar", "Copiar", "Cambiar nombre", "Eliminar", "Propiedades"):
            self.menu.entryconfigure(etiqueta, state="normal" if hay else "disabled")
        self.menu.entryconfigure("Pegar", state="normal" if self._portapapeles and self.actual is not None
                                 else "disabled")
        try:
            self.menu.tk_popup(evento.x_root, evento.y_root)
        finally:
            self.menu.grab_release()

    def _copiar_ruta(self):
        sel = self._seleccionadas()
        ruta = sel[0]["ruta"] if len(sel) == 1 else self.actual
        texto = ex.direccion(self.base, ruta)
        self.ventana.clipboard_clear()
        self.ventana.clipboard_append(texto)
        self._avisar(f"Afirmativo. Ruta copiada: {texto}, señor.")

    def abrir(self, entrada):
        ok, motivo = ex.abrir_permitido(self.base, entrada["ruta"], self._llaves())
        if not ok:
            self._avisar(motivo)
            return
        try:
            os.startfile(str(entrada["ruta"]))
            self._avisar(f"Afirmativo. Abriendo {entrada['nombre']}, señor.")
        except OSError as error:
            self._avisar(f"Negativo. No pude abrir {entrada['nombre']}: {error}, señor.")

    def _avisar(self, texto):
        """Resultado de una acción: se ve en la barra de estado y se escribe en la terminal."""
        self._estado(texto)
        if callable(self._informar):
            self._informar(texto)

    def _estado(self, texto):
        self.estado.configure(text=texto)

    # ------------------------------------------------------------ biblioteca musical: tarjetas
    def _construir_tarjetas(self, derecha):
        """Vista de tarjetas (una por canción). Ocupa el mismo sitio que la lista; _aplicar_vista la muestra."""
        tk, F = self.tk, self.t["FONDO"]
        self.vista_tarjetas = tk.Frame(derecha, bg=F)
        self.lienzo_tarjetas = tk.Canvas(self.vista_tarjetas, bg=F, highlightthickness=0, bd=0)
        barra_t = self.barra_verde(self.vista_tarjetas, self.lienzo_tarjetas.yview, self.t)
        self.lienzo_tarjetas.configure(yscrollcommand=barra_t.set)
        barra_t.pack(side="right", fill="y")
        self.lienzo_tarjetas.pack(side="left", fill="both", expand=True)
        self.interior_tarjetas = tk.Frame(self.lienzo_tarjetas, bg=F)
        ventana = self.lienzo_tarjetas.create_window((0, 0), window=self.interior_tarjetas, anchor="nw")
        self.interior_tarjetas.bind("<Configure>", lambda e: self.lienzo_tarjetas.configure(
            scrollregion=self.lienzo_tarjetas.bbox("all")))
        self.lienzo_tarjetas.bind("<Configure>", lambda e: self.lienzo_tarjetas.itemconfigure(ventana, width=e.width))
        self.lienzo_tarjetas.bind("<MouseWheel>", self._rueda_tarjetas)
        self.lienzo_tarjetas.bind("<Button-1>", lambda e: self._sin_seleccion())
        self.lienzo_tarjetas.bind("<Button-3>", self._abrir_menu)
        for tecla, orden in (("<Delete>", lambda e: self._eliminar()), ("<Return>", lambda e: self._doble_clic()),
                             ("<Control-c>", lambda e: self._copiar()), ("<Control-x>", lambda e: self._cortar()),
                             ("<Control-v>", lambda e: self._pegar()), ("<Control-a>", self._seleccionar_todo),
                             ("<F2>", lambda e: self._renombrar())):
            self.lienzo_tarjetas.bind(tecla, orden)

    def _es_cancion(self, e):
        return (not e["carpeta"]) and ex.categoria_de(e["nombre"]) == "Biblioteca musical"

    def _es_biblioteca(self):
        return self.audio is not None and self.actual is not None \
            and ex.seccion_de(self.base, self.actual) == "Biblioteca musical"

    def _aplicar_vista(self):
        """En «Biblioteca musical» se ven tarjetas; en el resto de carpetas, la lista de siempre."""
        tarjetas = self._es_biblioteca()
        if tarjetas != self._modo_tarjetas:
            self._modo_tarjetas = tarjetas
            self._orden_tarjetas = None
        self._colocar_vistas()
        self._actualizar_franja()
        if tarjetas and not self._modo_cola:
            self._pintar_tarjetas()

    def _franja_visible(self):
        return self.vista_cola is not None and (self._es_biblioteca() or self._modo_cola)

    def _colocar_vistas(self):
        """Orden de la derecha: la franja de la biblioteca arriba (cuando toca) y debajo la vista que corresponde."""
        piezas = [self.franja_biblioteca, self.vista_lista, self.vista_tarjetas]
        if self.vista_cola is not None:
            piezas.append(self.vista_cola.marco)
        for pieza in piezas:
            pieza.pack_forget()
        if self._franja_visible():
            self.franja_biblioteca.pack(side="top", fill="x", pady=(0, 2))
        if self._modo_cola and self.vista_cola is not None:
            self.vista_cola.marco.pack(side="left", fill="both", expand=True)
        elif self._modo_tarjetas:
            self.vista_tarjetas.pack(side="left", fill="both", expand=True)
        else:
            self.vista_lista.pack(side="left", fill="both", expand=True)

    def _actualizar_franja(self):
        """El botón COLA queda fijo y activo mientras haya canciones en cola (o la cola esté abierta, para cerrarla)."""
        if self.vista_cola is None or self.audio is None:
            return
        try:
            n = len(self.audio.estado_visible()["cola"])
        except Exception:
            n = 0
        activo = bool(n) or self._modo_cola
        self.boton_cola.configure(text=f"COLA ({n})",
                                  bg=self.t["VERDE"] if activo else self.t["VERDE_OSCURO"],
                                  fg=self.t["FONDO"] if activo else self.t["GRIS"],
                                  activebackground=self.t["VERDE"], activeforeground=self.t["FONDO"],
                                  relief="sunken" if self._modo_cola else "flat",
                                  state="normal" if activo else "disabled")
        self.titulo_franja.configure(text=f"BIBLIOTECA MUSICAL · {n} en cola" if n else "BIBLIOTECA MUSICAL")

    def refrescar_cola(self):
        """Lo llama la orden al terminar (o la voz): repinta lo real. Sin esperar al siguiente ciclo."""
        self._firma_audio = None
        self._repintar_audio()

    def _repintar_audio(self):
        """Repinta la franja COLA y la vista activa con lo que se ve: lo previsto si hay órdenes en curso, si no lo real.
        Si la cola abierta se queda vacía, se cierra sola."""
        if self.audio is None:
            return
        if self._modo_cola and not self.audio.estado_visible()["cola"]:
            self._modo_cola = False
            self._orden_tarjetas = None
            self._colocar_vistas()
        self._actualizar_franja()
        if self._modo_cola:
            self._pintar_cola()
        elif self._modo_tarjetas:
            self._pintar_tarjetas()

    def _alternar_cola_vista(self, _evento=None):
        """El botón COLA de la biblioteca abre y cierra la cola de reproducción."""
        if self.vista_cola is None:
            self._avisar("Negativo. La cola solo está disponible con el reproductor, señor.")
            return
        self._modo_cola = not self._modo_cola
        if self._modo_cola:
            self._pintar_cola()
        else:
            self._orden_tarjetas = None           # al volver, las tarjetas se repintan enteras
            self._firma_audio = None
        self._colocar_vistas()
        self._actualizar_franja()
        if not self._modo_cola and self._modo_tarjetas:
            self._pintar_tarjetas()

    def _pintar_cola(self):
        if self.vista_cola is None or self.audio is None:
            return
        foto = self.audio.instantanea()
        self.vista_cola.pintar(self.audio.estado_visible()["cola"], foto["nombre"], pausada=foto["pausada"])
        self._firma_audio = self.audio.firma()

    def _pintar_tarjetas(self):
        """Las tarjetas se crean una vez y se guardan en caché (una por archivo). Al cambiar la cola o lo que suena
        solo se actualiza su texto; al cambiar el orden solo se recolocan. Nunca se vuelven a crear todas."""
        from interfaz import tarjeta_cancion
        foto = self.audio.instantanea()          # una sola lectura de la cola para todas las tarjetas
        cache = self._tarjetas_cache
        rutas = [str(e["ruta"]) for e in self._entradas]
        vivas = set(rutas)
        for ruta in [r for r in cache if r not in vivas]:
            cache.pop(ruta).destroy()
        marcos = []
        for e in self._entradas:
            ruta = str(e["ruta"])
            info = self._info_tarjeta(e, foto)
            seleccionada = ruta in self._sel_rutas
            marco = cache.get(ruta)
            if marco is None:
                marco = tarjeta_cancion.crear(self.tk, self.interior_tarjetas, e, info, self.t, self.fuente,
                                              self._acciones_de(e), seleccionada=seleccionada)
                cache[ruta] = marco
            elif tarjeta_cancion.actualizar(marco, info, seleccionada):
                self._transicion_cola(marco)
            marcos.append((ruta, marco))
        if rutas != self._orden_tarjetas:          # solo si cambió el orden o entró/salió alguna canción
            for _ruta, marco in marcos:
                marco.pack_forget()
                marco.pack(fill="x", padx=3, pady=2)
            self._orden_tarjetas = rutas
        self._marcos = marcos
        self._firma_audio = self.audio.firma()

    def _transicion_cola(self, marco, pasos=8):
        """Al entrar o salir de la cola, el botón se enciende en ámbar y vuelve a su color poco a poco."""
        from interfaz import tarjeta_cancion
        boton = getattr(marco, "partes", {}).get("cola")
        if boton is None:
            return
        ambar, base = self.t.get("AMBAR", self.t["VERDE"]), self.t["VERDE_OSCURO"]

        def paso(n=0):
            try:
                boton.configure(bg=tarjeta_cancion.mezclar(ambar, base, n / pasos))
                if n < pasos:
                    self.ventana.after(40, lambda: paso(n + 1))
            except self.tk.TclError:
                pass                                  # la tarjeta ya no existe

        paso(0)

    def _info_tarjeta(self, e, foto=None):
        ruta = e["ruta"]
        if e["carpeta"]:
            texto = "Carpeta"
        else:
            texto = f"{e['tipo']}  ·  {ex.tamano_legible(e['tamano'])}  ·  {e['modificado']}"
        return {"texto": texto, **self.audio.info_de(ruta, foto)}

    def _acciones_de(self, entrada):
        """Lo que hace cada botón y cada gesto de la tarjeta. Las canciones pasan por el supervisor."""
        ruta = entrada["ruta"]

        def reproducir(_e=None):
            self.audio.reproducir(ruta)

        def cola(_e=None):
            self.audio.alternar_cola(ruta)

        def copiar(_e=None):
            self._seleccion_unica(entrada)
            self._copiar()

        def papelera(_e=None):
            self._seleccion_unica(entrada)
            self._eliminar()

        def abrir(_e=None):
            self.ir(ruta)

        def doble(_e=None):
            if entrada["carpeta"]:
                self.ir(ruta)
            else:
                self.audio.reproducir(ruta)

        def seleccionar(evento, _e=None):
            self._seleccionar_tarjeta(entrada, evento)

        def menu(evento, _e=None):
            if str(ruta) not in self._sel_rutas:
                self._seleccionar_tarjeta(entrada)
            self._abrir_menu(evento)

        return {"reproducir": reproducir, "cola": cola, "copiar": copiar, "papelera": papelera,
                "abrir": abrir, "doble": doble, "seleccionar": seleccionar, "menu": menu,
                "rueda": self._rueda_tarjetas}

    def _seleccionar_tarjeta(self, entrada, evento=None):
        """Clic = solo esta; Ctrl = añadir o quitar; Mayús = rango desde la última marcada."""
        self.lienzo_tarjetas.focus_set()
        ruta = str(entrada["ruta"])
        estado = getattr(evento, "state", 0) or 0
        orden = [str(x["ruta"]) for x in self._entradas]
        if (estado & 0x0001) and self._ancla_ruta in orden and ruta in orden:
            a, b = sorted((orden.index(self._ancla_ruta), orden.index(ruta)))
            self._sel_rutas = set(orden[a:b + 1])
        elif estado & 0x0004:
            self._sel_rutas ^= {ruta}
            self._ancla_ruta = ruta
        else:
            self._sel_rutas = {ruta}
            self._ancla_ruta = ruta
        self._pintar_seleccion()
        self._seleccion_lista()

    def _seleccion_unica(self, entrada):
        self._sel_rutas = {str(entrada["ruta"])}
        self._ancla_ruta = str(entrada["ruta"])
        self._pintar_seleccion()

    def _sin_seleccion(self):
        self.lienzo_tarjetas.focus_set()
        self._sel_rutas, self._ancla_ruta = set(), None
        self._pintar_seleccion()
        self._seleccion_lista()

    def _pintar_seleccion(self):
        V, VO = self.t["VERDE"], self.t["VERDE_OSCURO"]
        for ruta, marco in self._marcos:
            try:
                marco.configure(highlightbackground=V if ruta in self._sel_rutas else VO)
            except self.tk.TclError:
                pass                                  # la tarjeta ya no existe (la lista se rehízo)

    def _rueda_tarjetas(self, evento):
        self.lienzo_tarjetas.yview_scroll(-1 if getattr(evento, "delta", 0) > 0 else 1, "units")

    # ------------------------------------------------------------ trabajo en otro hilo
    def _en_hilo(self, etiqueta, trabajo, despues):
        """Corre «trabajo» en un hilo aparte. Cuando termina, «despues(resultado, error)» se llama desde la ventana."""
        if self._tarea is not None:
            self._avisar("Negativo. Espere, hay otra operación en curso, señor.")
            return False
        tarea = {"hecho": False, "resultado": None, "error": None, "despues": despues}

        def correr():
            try:
                tarea["resultado"] = trabajo()
            except Exception as error:
                tarea["error"] = error
            tarea["hecho"] = True
        self._tarea = tarea
        self._avisar(f"En curso: {etiqueta}…")
        threading.Thread(target=correr, daemon=True).start()
        return True

    # ------------------------------------------------------------ modificar (solo con llave PRO)
    def _nueva_carpeta(self):
        from tkinter import simpledialog
        if self.actual is None:
            self._avisar("Negativo. Entre primero en un disco para crear una carpeta, señor.")
            return
        ok, motivo = ex.puede_crear_en(self.base, self.actual, self._llaves())
        if not ok:
            self._avisar(motivo)
            return
        nombre = simpledialog.askstring("Nueva carpeta", "Nombre de la carpeta:",
                                        initialvalue=ex.nombre_nueva_carpeta(self.actual), parent=self.ventana)
        if nombre is None:
            return
        ok, limpio = ex.nombre_valido(nombre)
        if not ok:
            self._avisar(limpio)
            return
        destino = self.actual / limpio
        if destino.exists():
            self._avisar("Negativo. Ya existe algo con ese nombre, señor.")
            return
        try:
            destino.mkdir()
        except OSError as error:
            self._avisar(f"Negativo. No pude crear la carpeta: {error}, señor.")
            return
        self.recargar()
        self._avisar(f"Afirmativo. Carpeta creada: {limpio}, señor.")

    def _renombrar(self):
        from tkinter import simpledialog
        sel = self._seleccionadas()
        if len(sel) != 1:
            self._avisar("Negativo. Seleccione un solo elemento para renombrarlo, señor.")
            return
        e = sel[0]
        ok, motivo = ex.modificable(self.base, e["ruta"], self._llaves())
        if not ok:
            self._avisar(motivo)
            return
        if ex.en_uso_bajo(e["ruta"], self._en_uso()):
            self._avisar("Negativo. Esa canción está sonando o en la cola: no se renombra, señor.")
            return
        nuevo = simpledialog.askstring("Cambiar nombre", "Nombre nuevo:", initialvalue=e["nombre"],
                                       parent=self.ventana)
        if nuevo is None:
            return
        ok, limpio = ex.nombre_valido(nuevo)
        if not ok:
            self._avisar(limpio)
            return
        if limpio == e["nombre"]:
            return
        destino = e["ruta"].with_name(limpio)
        if destino.exists() and destino.name.lower() != e["nombre"].lower():
            self._avisar("Negativo. Ya existe algo con ese nombre, señor.")
            return
        try:
            e["ruta"].rename(destino)
            self._aprender("archivo_renombrado")
        except OSError as error:
            self._avisar(f"Negativo. No pude cambiar el nombre: {error}, señor.")
            return
        self.recargar()
        self._avisar(f"Afirmativo. Nombre cambiado a {limpio}, señor.")

    def _eliminar(self):
        from tkinter import messagebox
        sel = self._seleccionadas()
        if not sel:
            self._avisar("Negativo. Seleccione primero un elemento, señor.")
            return
        for e in sel:
            ok, motivo = ex.modificable(self.base, e["ruta"], self._llaves())
            if not ok:
                self._avisar(motivo)
                return
            if ex.en_uso_bajo(e["ruta"], self._en_uso()):
                self._avisar(f"Negativo. {e['nombre']} está sonando o en la cola: no se borra, señor.")
                return
        canciones = [e for e in sel if self._es_cancion(e)]
        otros = [e for e in sel if not self._es_cancion(e)]
        if canciones and self.audio is None:
            self._avisar("Negativo. Las canciones solo se borran con el supervisor de MILLER, señor.")
            return
        aviso = ""
        if any(ex.vista_de(self.base, e["ruta"]) == "programa" for e in otros):
            aviso = "Es parte del programa: MILLER podría no arrancar sin ello. "
        nombres = ", ".join(e["nombre"] for e in sel[:3]) + (" y más" if len(sel) > 3 else "")
        if not otros:
            pregunta = (f"¿Mandar a la papelera de MILLER: {nombres}? "
                        "El supervisor la guarda y se puede restaurar.")
        elif canciones:
            pregunta = (f"{aviso}¿Mandar a la papelera de MILLER las canciones y a la papelera del explorador "
                        f"el resto: {nombres}? Se recupera desde datos\\papelera_explorador.")
        else:
            pregunta = (f"{aviso}¿Mover a la papelera del explorador: {nombres}? "
                        "Se recupera desde datos\\papelera_explorador.")
        if not messagebox.askyesno("Eliminar", pregunta, parent=self.ventana):
            return
        base, audio = self.base, self.audio

        def trabajo():
            ahora = datetime.now()
            respuestas = [audio.texto_papelera(e["ruta"]) for e in canciones]
            for e in otros:
                destino = ex.destino_papelera(base, e["ruta"], ahora)
                destino.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(e["ruta"]), str(destino))
            return respuestas, len(otros)

        def despues(resultado, error):
            if error:
                self._avisar(f"Negativo. No pude mover a la papelera: {error}, señor.")
            else:
                respuestas, cuantos = resultado
                for texto in respuestas:
                    audio.informar_texto(texto)       # la respuesta queda en la terminal, como una orden de voz
                if cuantos:
                    self._aprender("archivo_borrado")
                    self._avisar(f"Afirmativo. {cuantos} elemento(s) a la papelera del explorador, señor.")
                elif respuestas:
                    self._avisar("Afirmativo. Canciones enviadas a la papelera de MILLER, señor.")
            self.recargar()
        self._en_hilo("Eliminando", trabajo, despues)

    def _copiar(self):
        self._llevar(cortar=False)

    def _cortar(self):
        self._llevar(cortar=True)

    def _llevar(self, cortar):
        sel = self._seleccionadas()
        if not sel:
            self._avisar("Negativo. Seleccione primero un elemento, señor.")
            return
        rutas = []
        for e in sel:
            ok, motivo = ex.copiable(self.base, e["ruta"], self._llaves())
            if not ok:
                self._avisar(motivo)
                return
            if cortar:
                ok, motivo = ex.modificable(self.base, e["ruta"], self._llaves())
                if not ok:
                    self._avisar(motivo)
                    return
                if ex.en_uso_bajo(e["ruta"], self._en_uso()):
                    self._avisar(f"Negativo. {e['nombre']} está sonando o en la cola: no se corta, señor.")
                    return
            rutas.append(e["ruta"])
        self._portapapeles = ("cortar" if cortar else "copiar", rutas)
        self._aprender("archivo_movido" if cortar else "archivo_copiado")
        self._avisar(f"Afirmativo. {'Cortado' if cortar else 'Copiado'}: {len(rutas)} elemento(s). Pegue con Ctrl+V, señor.")

    def _pegar(self):
        if self._portapapeles is None:
            self._avisar("Negativo. No hay nada copiado ni cortado, señor.")
            return
        destino = self.actual
        if destino is None:
            self._avisar("Negativo. Entre primero en un disco para pegar, señor.")
            return
        ok, motivo = ex.puede_crear_en(self.base, destino, self._llaves())
        if not ok:
            self._avisar(motivo)
            return
        modo, rutas = self._portapapeles
        for r in rutas:
            if not r.exists() and not r.is_symlink():
                self._portapapeles = None
                self._avisar(f"Negativo. Ya no existe {r.name}, señor.")
                return
            if r.is_dir() and ex.dentro_de(r, destino):
                self._avisar("Negativo. No puedo pegar una carpeta dentro de sí misma, señor.")
                return
            if modo == "cortar":
                ok, motivo = ex.modificable(self.base, r, self._llaves())
                if not ok or ex.en_uso_bajo(r, self._en_uso()):
                    self._avisar(motivo if not ok else f"Negativo. {r.name} está sonando o en la cola, señor.")
                    return

        def trabajo():
            hechos = 0
            for r in rutas:
                if not r.exists() or (modo == "cortar" and r.parent == destino):
                    continue
                nombre = r.name
                if (destino / nombre).exists():
                    nombre = ex.nombre_copia(destino, r.name)
                final = destino / nombre
                if modo == "cortar":
                    shutil.move(str(r), str(final))
                elif r.is_dir():
                    shutil.copytree(str(r), str(final), ignore=_ignorar_enlaces)
                else:
                    shutil.copy2(str(r), str(final))
                hechos += 1
            return hechos

        def despues(resultado, error):
            if error:
                self._avisar(f"Negativo. No pude pegar: {error}, señor.")
            else:
                if modo == "cortar":
                    self._portapapeles = None
                self._avisar(f"Afirmativo. Pegado: {resultado} elemento(s), señor.")
            self.recargar()
        self._en_hilo("Pegando", trabajo, despues)

    # ------------------------------------------------------------ propiedades (tamaños exactos)
    def _propiedades(self):
        from tkinter import messagebox
        sel = self._seleccionadas()
        if not sel:
            self._avisar("Negativo. Seleccione primero un elemento, señor.")
            return
        if len(sel) > 1:
            total = sum(e["tamano"] or 0 for e in sel if not e["carpeta"])
            messagebox.showinfo("Propiedades", f"{len(sel)} elementos\nTamaño de los archivos: "
                                f"{ex.tamano_exacto(total)}", parent=self.ventana)
            return
        e = sel[0]
        if not e["carpeta"]:
            self._mostrar_propiedades(e, None)
            return

        def despues(resultado, error):
            if error:
                self._avisar(f"Negativo. No pude medir la carpeta: {error}, señor.")
            else:
                self._mostrar_propiedades(e, resultado)
        self._en_hilo("Midiendo la carpeta", lambda: ex.medir_carpeta(e["ruta"], self.base), despues)

    def _mostrar_propiedades(self, e, medicion):
        from tkinter import messagebox
        ruta = e["ruta"]
        try:
            st = ruta.stat()
        except OSError:
            st = None
        if e.get("unidad"):
            lineas = [f"Nombre: {e['nombre']}", f"Tipo: {e['tipo']}", "Ubicación: MILLER"]
        else:
            lineas = [f"Nombre: {e['nombre']}", f"Tipo: {e['tipo']}",
                      f"Ubicación: {ex.direccion(self.base, ruta.parent)}"]
        lineas.append(f"Ruta: {ex.direccion(self.base, ruta)}")
        if medicion is not None:
            lineas.append(f"Contiene: {medicion['archivos']} archivos y {medicion['carpetas']} carpetas")
            lineas.append(f"Tamaño total: {ex.tamano_exacto(medicion['bytes'])}")
            if medicion["errores"]:
                lineas.append(f"No se pudo leer: {medicion['errores']} elemento(s)")
        elif not e["carpeta"]:
            lineas.append(f"Tamaño: {ex.tamano_exacto(e['tamano'])}")
        if st is not None:
            lineas.append(f"Creado: {ex.fecha_legible(st.st_ctime)}")
            lineas.append(f"Modificado: {ex.fecha_legible(st.st_mtime)}")
        lineas.append(f"Permisos: {self._permiso_de(e)}")
        messagebox.showinfo(f"Propiedades de {e['nombre']}", "\n".join(lineas), parent=self.ventana)

    def _permiso_de(self, e):
        if e["protegida"]:
            return "protegida: se ve, no se abre ni se copia"
        if e["solo_lectura"]:
            return "solo lectura (datos)"
        if e["bloqueada"]:
            return "bloqueado: necesita las llaves PRO y NIÑOS"
        if "pro" in self._llaves():
            return "modificable"
        return "solo lectura (llave PRO para modificar)"

    def _vigilar_carpeta(self):
        """Refresca sola la carpeta y el árbol cuando cambia el disco: ya no hace falta el botón de recargar."""
        ahora = time.monotonic()
        if ahora - self._ultima_vigilancia < 1.0:
            return
        self._ultima_vigilancia = ahora
        ruta = self.actual if self.actual is not None else self.base
        try:
            firma = (str(ruta), os.stat(ruta).st_mtime_ns)
        except OSError:
            firma = None
        previa, self._firma_carpeta = self._firma_carpeta, firma
        if firma is None or previa is None or firma[0] != previa[0]:
            return                                   # primera vez, carpeta no legible, o cambió al navegar
        if firma[1] != previa[1]:
            self.recargar()

    def _tick(self):
        """Ciclo de 120 ms. Cada parte va aislada: si una falla, las demás siguen. La cola va antes que el disco."""
        try:
            if not self.ventana.winfo_exists():
                return
        except Exception:
            return
        self._paso("tareas", self._tick_tareas)
        self._paso("reproductor", self._tick_audio)
        self._paso("disco", self._tick_disco)
        try:
            self._seguimiento = self.ventana.after(120, self._tick)
        except Exception:
            pass

    def _paso(self, nombre, funcion):
        try:
            funcion()
        except Exception as error:
            print(f"[ENTORNO] Error en {nombre}: {error}")

    def _tick_tareas(self):
        tarea = self._tarea
        if tarea is not None and tarea["hecho"]:
            self._tarea = None
            try:
                tarea["despues"](tarea["resultado"], tarea["error"])
            except Exception as error:
                self._avisar(f"Negativo. Algo falló: {error}, señor.")

    def _tick_audio(self):
        if self.audio is None:
            return
        firma = self.audio.firma()
        if firma != self._firma_audio:               # cambió lo que suena (reproducir, pausa, parar) o la cola
            self._firma_audio = firma
            self._repintar_audio()

    def _tick_disco(self):
        llaves = self._llaves()
        if llaves != self._llaves_vistas:
            self._llaves_vistas = llaves
            self.recargar()
        self._vigilar_carpeta()
