"""MILLER · Sección INSTALACIÓN (dentro de la página MILLER).

Disposición (de arriba abajo):
  - Zona con desplazamiento (rueda del ratón o barra lateral): resumen, lista compacta
    (✓ verde instalado, ✗ rojo falta, con la ruta encontrada en este equipo) y bitácora corta.
  - Barras de progreso: la de la descarga o paso actual, y la del progreso total.
  - Botones compactos, siempre al pie.

Reglas de los botones:
  - COMPROBAR ESTADO: disponible cuando no hay trabajo en curso. Vuelve a mirar qué falta.
  - INSTALAR LO QUE FALTA (n): solo si falta algo. Sigue el plan predefinido de plan_instalacion.
  - 📂 (buscar en este equipo) y ELEGIR CARPETA…: solo si falta algo. Buscar copia a modelos/ lo que encuentra
    con nombre exacto; si copió bien, estos dos botones se ocultan y solo quedan COMPROBAR e INSTALAR.

El trabajo pesado corre en hilos. Todo cambio de la ventana vuelve al hilo de la interfaz por la cola del panel.
"""
import threading

from utilidades import instalador, plan_instalacion as plan

LARGO_RUTA = 54      # caracteres de ruta que se muestran en la lista; si es más larga, se corta por delante
ESTILO_BARRA = "MillerVerde.Vertical.TScrollbar"


def barra_verde(padre, comando, tema):
    """Barra de desplazamiento fina en verde (7 px), dibujada a mano: el ancho de la barra nativa de Windows
    no se puede cambiar. Sirve para cualquier cosa con yview (lista, árbol, tarjetas, página INSTALACIÓN)."""
    import tkinter as tk
    try:
        return _barra_fina(tk, padre, comando, tema)
    except Exception:
        return tk.Scrollbar(padre, orient="vertical", command=comando)


def _barra_fina(tk, padre, comando, tema, ancho=7):
    lienzo = tk.Canvas(padre, width=ancho, bg=tema["FONDO"], highlightthickness=0, bd=0)
    est = {"a": 0.0, "b": 1.0, "arrastre": None}

    def dibujar(_evento=None):
        lienzo.delete("all")
        alto = max(lienzo.winfo_height(), 1)
        lienzo.create_rectangle(0, 0, ancho, alto, fill=tema["VERDE_OSCURO"], outline="")
        y1 = int(est["a"] * alto)
        y2 = max(int(est["b"] * alto), y1 + 16)
        lienzo.create_rectangle(1, y1, ancho - 1, min(y2, alto), fill=tema["VERDE"], outline="")

    def fijar(primera, ultima):
        est["a"], est["b"] = float(primera), float(ultima)
        dibujar()

    def fraccion(evento):
        return min(max(evento.y / max(lienzo.winfo_height(), 1), 0.0), 1.0)

    def pulsar(evento):
        f = fraccion(evento)
        if est["a"] <= f <= est["b"]:
            est["arrastre"] = f - est["a"]                  # agarra el deslizador donde se pulsó
        else:
            est["arrastre"] = (est["b"] - est["a"]) / 2     # salta: el deslizador se centra en el clic
            comando("moveto", max(0.0, f - est["arrastre"]))

    def mover(evento):
        if est["arrastre"] is not None:
            tope = max(0.0, 1.0 - (est["b"] - est["a"]))
            comando("moveto", max(0.0, min(fraccion(evento) - est["arrastre"], tope)))

    def soltar(_evento=None):
        est["arrastre"] = None

    def rueda(evento):
        comando("scroll", -1 if evento.delta > 0 else 1, "units")

    lienzo.bind("<Configure>", dibujar)
    lienzo.bind("<Button-1>", pulsar)
    lienzo.bind("<B1-Motion>", mover)
    lienzo.bind("<ButtonRelease-1>", soltar)
    lienzo.bind("<MouseWheel>", rueda)
    lienzo.set = fijar                                      # misma interfaz que tk.Scrollbar: yscrollcommand=barra.set
    return lienzo


class PaginaInstalacion:
    def __init__(self, panel, marco, tema, fuente, fuente_negrita):
        self.panel = panel
        self.tk = panel.tk
        self.t = tema                      # colores del panel: FONDO, VERDE, VERDE_OSCURO, ROJO, GRIS, AMBAR
        self.fuente, self.fuente_negrita = fuente, fuente_negrita
        self.filas = None                  # None = todavía no revisado; si no, estado() de instalador
        self.encontrados = {}              # clave -> carpeta encontrada en este equipo
        self.ocupado = False               # hay una instalación, copia o búsqueda en curso
        self.copia_hecha = False           # una búsqueda copió lo que encontró: ocultar BUSCAR y ELEGIR
        self._pulso, self._pulsando, self._latiendo = 0, False, False
        self._construir(marco)
        self.revisar()

    # ------------------------------------------------------------ construcción
    def _construir(self, marco):
        f = self.t["FONDO"]
        # Primero se reserva el pie (botones) y luego las barras encima; la zona con desplazamiento ocupa el resto.
        botones = self.tk.Frame(marco, bg=f)
        botones.pack(side="bottom", fill="x", padx=4, pady=(0, 3))
        progreso = self.tk.Frame(marco, bg=f)
        progreso.pack(side="bottom", fill="x", padx=4, pady=(2, 0))
        zona = self.tk.Frame(marco, bg=f)
        zona.pack(side="top", fill="both", expand=True, padx=4, pady=(2, 0))

        # Zona con desplazamiento
        self.lienzo = self.tk.Canvas(zona, bg=f, highlightthickness=0, bd=0)
        self.barra_scroll = self._barra_verde(zona, self.lienzo.yview)
        self.lienzo.configure(yscrollcommand=self.barra_scroll.set)
        self.barra_scroll.pack(side="right", fill="y")
        self.lienzo.pack(side="left", fill="both", expand=True)
        self.contenido = self.tk.Frame(self.lienzo, bg=f)
        self._ventana = self.lienzo.create_window((0, 0), window=self.contenido, anchor="nw")
        self.contenido.bind("<Configure>", self._ajustar_scroll)
        self.lienzo.bind("<Configure>", self._ajustar_ancho)

        self.resumen = self.tk.Label(self.contenido, text="", anchor="w", font=self.fuente, bg=f, fg=self.t["GRIS"])
        self.resumen.pack(fill="x")
        self.lista = self.tk.Frame(self.contenido, bg=f)
        self.lista.pack(fill="x")
        self.bitacora = self.panel._texto(self.contenido, 4)
        self.bitacora.pack(fill="x", pady=(3, 0))

        # Barras de progreso (encima de los botones)
        self.texto_actual = self.tk.Label(progreso, text="", anchor="w", font=self.fuente, bg=f, fg=self.t["GRIS"])
        self.texto_actual.pack(fill="x")
        self.barra_actual = self.tk.Canvas(progreso, height=8, bg=f, highlightthickness=0)
        self.barra_actual.pack(fill="x", pady=(0, 2))
        self.texto_total = self.tk.Label(progreso, text="", anchor="w", font=self.fuente, bg=f, fg=self.t["GRIS"])
        self.texto_total.pack(fill="x")
        self.barra_total = self.tk.Canvas(progreso, height=8, bg=f, highlightthickness=0)
        self.barra_total.pack(fill="x")

        # Botones compactos en una fila (grid, para que los que se ocultan no muevan a los demás)
        self.b_comprobar = self.tk.Button(botones, text="COMPROBAR ESTADO", font=self.fuente, bg=f,
                                          fg=self.t["GRIS"], relief="flat", padx=4, pady=0, command=self.revisar)
        self.b_comprobar.grid(row=0, column=0, padx=(0, 3), sticky="w")
        self.b_buscar = self.tk.Button(botones, text="📂", font=("Segoe UI Emoji", 11), bg=f,
                                       fg=self.t["AMBAR"], relief="flat", padx=4, pady=0, command=self.buscar)
        self.b_buscar.grid(row=0, column=1, padx=3, sticky="w")
        self.b_elegir = self.tk.Button(botones, text="ELEGIR CARPETA…", font=self.fuente, bg=f,
                                       fg=self.t["GRIS"], relief="flat", padx=4, pady=0,
                                       command=self.elegir_carpeta)
        self.b_elegir.grid(row=0, column=2, padx=3, sticky="w")
        self.b_instalar = self.tk.Button(botones, text="REVISANDO…", font=self.fuente_negrita,
                                         bg=self.t["VERDE_OSCURO"], fg=self.t["VERDE"],
                                         activebackground=self.t["VERDE"], relief="flat", padx=6, pady=0,
                                         command=self.instalar)
        self.b_instalar.grid(row=0, column=3, padx=(3, 0), sticky="ew")
        botones.columnconfigure(3, weight=1)

    def _barra_verde(self, padre, comando):
        return barra_verde(padre, comando, self.t)

    def desplazar(self, paso):
        """Lo llama el panel con la rueda del ratón cuando esta página está abierta."""
        if self.contenido.winfo_reqheight() > self.lienzo.winfo_height():
            self.lienzo.yview_scroll(paso, "units")

    def _ajustar_scroll(self, _evento=None):
        alto = max(self.lienzo.winfo_height(), self.contenido.winfo_reqheight())
        self.lienzo.configure(scrollregion=(0, 0, self.lienzo.winfo_width(), alto))

    def _ajustar_ancho(self, evento):
        self.lienzo.itemconfigure(self._ventana, width=evento.width)
        self._ajustar_scroll()

    # ------------------------------------------------------------ hilos -> ventana
    def _ui(self, funcion):
        self.panel.cola.put(("ui", funcion))

    def _log(self, texto):
        self.panel.cola.put(("bitacora", texto))

    def _cb_actual(self, fraccion, texto):
        self._ui(lambda f=fraccion, t=texto: self._mostrar_actual(f, t))

    def _cb_total(self, fraccion, texto):
        self._ui(lambda f=fraccion, t=texto: self._mostrar_total(f, t))

    # ------------------------------------------------------------ dibujo
    def _pintar_barra(self, lienzo, fraccion):
        """fraccion 0..1 = barra fija; None = segmento que se desplaza (trabajo sin porcentaje)."""
        ancho, alto = max(lienzo.winfo_width(), 300), 8
        lienzo.delete("all")
        lienzo.create_rectangle(0, 0, ancho, alto, fill=self.t["VERDE_OSCURO"], outline="")
        if fraccion is None:
            tramo = 80
            x = int(self._pulso / 100 * (ancho + tramo)) - tramo
            if x < ancho and x + tramo > 0:
                lienzo.create_rectangle(max(0, x), 0, min(ancho, x + tramo), alto, fill=self.t["VERDE"], outline="")
        elif fraccion > 0:
            lienzo.create_rectangle(0, 0, int(ancho * min(1.0, fraccion)), alto, fill=self.t["VERDE"], outline="")

    def _mostrar_actual(self, fraccion, texto):
        self.texto_actual.configure(text=texto)
        if fraccion is None:
            self._pulsando = True
            if not self._latiendo:
                self._latiendo = True
                self._latir()
        else:
            self._pulsando = False
            self._pintar_barra(self.barra_actual, fraccion)

    def _mostrar_total(self, fraccion, texto):
        self.texto_total.configure(text=texto)
        self._pintar_barra(self.barra_total, fraccion)

    def _latir(self):
        """Mueve la barra indeterminada mientras haya trabajo sin porcentaje."""
        if not self._pulsando:
            self._latiendo = False
            return
        self._pulso = (self._pulso + 2) % 100
        self._pintar_barra(self.barra_actual, None)
        self.panel.raiz.after(90, self._latir)

    def _corta(self, ruta):
        texto = str(ruta)
        return texto if len(texto) <= LARGO_RUTA else "…" + texto[-(LARGO_RUTA - 1):]

    def _pintar_lista(self):
        for hijo in self.lista.winfo_children():
            hijo.destroy()
        for clave, nombre, listo, tipo in (self.filas or []):
            if listo:
                texto, color = f"✓ {nombre}", self.t["VERDE"]
            else:
                texto, color = f"✗ {nombre}", self.t["ROJO"]
                if tipo == "modelo":
                    if self.encontrados.get(clave):
                        texto += f" · en este equipo: {self._corta(self.encontrados[clave])}"
                    else:
                        texto += " · se descargará"
            self.tk.Label(self.lista, text=texto, anchor="w", font=self.fuente, bg=self.t["FONDO"],
                          fg=color).pack(fill="x")
        self._pintar_resumen()

    def _faltan(self):
        """Cuántos componentes faltan, o None si todavía no se ha revisado."""
        if self.filas is None:
            return None
        return sum(1 for _, _, listo, _ in self.filas if not listo)

    def _pendientes(self):
        """Modelos que faltan ahora mismo (no mira las librerías de Python)."""
        return [c for c, m in instalador.MODELOS.items() if not m["prueba"]()]

    def _pintar_resumen(self):
        total = len(self.filas or [])
        faltan = self._faltan()
        if faltan is None:
            texto = "Revisando componentes…"
        elif faltan:
            texto = f"{total - faltan} de {total} listos · faltan {faltan}"
        else:
            texto = f"{total} de {total} listos · todo instalado"
        self.resumen.configure(text=texto)

    def _pintar_botones(self):
        faltan = self._faltan()
        self.panel.faltan = faltan or 0                # la pestaña INSTALACIÓN se marca si falta algo
        libre = not self.ocupado
        estado_libre = "normal" if libre else "disabled"
        self.b_comprobar.configure(state=estado_libre)

        # BUSCAR y ELEGIR solo si falta algo y la última búsqueda no dejó ya copiado lo que había
        mostrar_buscar = bool(faltan) and not self.copia_hecha
        for boton, columna in ((self.b_buscar, 1), (self.b_elegir, 2)):
            if mostrar_buscar:
                boton.grid(row=0, column=columna)
                boton.configure(state=estado_libre)
            else:
                boton.grid_remove()

        if self.ocupado:
            texto, estado = "TRABAJANDO…", "disabled"
        elif faltan is None:
            texto, estado = "REVISANDO…", "disabled"
        elif faltan:
            texto, estado = f"INSTALAR LO QUE FALTA ({faltan})", "normal"
        else:
            texto, estado = "TODO INSTALADO", "disabled"
        self.b_instalar.configure(text=texto, state=estado)

    def _aplicar_estado(self, filas):
        self.filas = filas
        if not self._faltan():
            self.copia_hecha = False                   # si luego falta algo otra vez, BUSCAR vuelve a aparecer
        self._pintar_lista()
        self._pintar_botones()

    def _guardar_hallazgos(self, hallados):
        self.encontrados.update({clave: ruta for clave, ruta in hallados.items() if ruta})
        self._pintar_lista()

    # ------------------------------------------------------------ acciones
    def _empezar(self):
        self.ocupado = True
        self._pintar_botones()
        self._mostrar_actual(None, "Preparando…")

    def _terminar(self, copia_ok=False):
        self.ocupado = False
        self._pulsando = False
        if copia_ok:
            self.copia_hecha = True
        self._mostrar_actual(0.0, "")
        self._pintar_botones()
        self.revisar()

    def revisar(self):
        """Vuelve a mirar qué está instalado. Es de solo lectura: se puede pulsar aunque haya trabajo."""
        def trabajo():
            try:
                filas = instalador.estado()
                self._ui(lambda f=filas: self._aplicar_estado(f))
            except Exception as error:
                self._log(f"No se pudo revisar: {error}")
        threading.Thread(target=trabajo, daemon=True, name="MILLER-Revisar").start()

    def _copiar(self, pasos):
        """Ejecuta solo las copias del plan. Devuelve True si todas quedaron verificadas."""
        plan.ejecutar_plan(pasos, avisar=self._log, progreso_paso=self._cb_actual, progreso_total=self._cb_total)
        return all(instalador.MODELOS[p["clave"]]["prueba"]() for p in pasos)

    def buscar(self):
        """Busca en este equipo los modelos que faltan, con nombre exacto, y los copia a modelos/ (sin descargar)."""
        if self.ocupado or not self._faltan():
            return
        self._empezar()

        def trabajo():
            copia_ok = False
            try:
                pendientes = self._pendientes()
                self._log("Buscando en este equipo: carpeta de MILLER, Escritorio, Documentos, Descargas…")
                hallados = plan.buscar_en_equipo(pendientes, progreso=self._cb_actual)
                self._ui(lambda h=hallados: self._guardar_hallazgos(h))
                for clave in pendientes:
                    nombre = instalador.MODELOS[clave]["nombre"]
                    if hallados.get(clave):
                        self._log(f"Encontrado: {nombre} en {hallados[clave]}")
                    else:
                        self._log(f"No está en este equipo: {nombre}")
                pasos = [p for p in plan.plan_instalacion(hallados, solo_copiar=True) if p["tipo"] == "copia"]
                if pasos:
                    copia_ok = self._copiar(pasos)
                    self._log("Copia terminada y verificada." if copia_ok else "Hubo un problema al copiar: revise la bitácora.")
                else:
                    self._log("Nada que copiar: no se encontró ningún modelo que falte.")
            except Exception as error:
                self._log(f"Error buscando: {error}")
            finally:
                self._ui(lambda ok=copia_ok: self._terminar(ok))
        threading.Thread(target=trabajo, daemon=True, name="MILLER-Buscar").start()

    def instalar(self):
        """Plan predefinido: 1) librerías si faltan, 2) buscar y copiar lo que haya en el equipo, 3) descargar el resto."""
        if self.ocupado or not self._faltan():
            return
        self._empezar()

        def trabajo():
            try:
                pendientes = self._pendientes()
                por_buscar = [c for c in pendientes if c not in self.encontrados]
                if por_buscar:
                    hallados = plan.buscar_en_equipo(por_buscar, progreso=self._cb_actual)
                    self._ui(lambda h=hallados: self._guardar_hallazgos(h))
                pasos = plan.plan_instalacion(dict(self.encontrados))
                self._log("Plan: " + " → ".join(
                    f"{p['nombre']} ({'copiar' if p['tipo'] == 'copia' else 'descargar' if p['tipo'] == 'descarga' else 'pip'})"
                    for p in pasos) if pasos else "Plan: nada que instalar.")
                ok = plan.ejecutar_plan(pasos, avisar=self._log, progreso_paso=self._cb_actual,
                                        progreso_total=self._cb_total)
                self._log("Instalación terminada. Reinicie MILLER para activar la voz." if ok
                          else "Terminó con avisos: revise la bitácora.")
            except Exception as error:
                self._log(f"Error inesperado instalando: {error}")
            finally:
                self._ui(self._terminar)
        threading.Thread(target=trabajo, daemon=True, name="MILLER-Instalador").start()

    def elegir_carpeta(self):
        """Usa los modelos de otra copia de MILLER: se elige su carpeta y se copian los que sirvan."""
        if self.ocupado:
            return
        from tkinter import filedialog
        carpeta = filedialog.askdirectory(parent=self.panel.raiz, title="Elija la carpeta de MILLER que tiene modelos/")
        if not carpeta:
            return
        self._empezar()

        def trabajo():
            copia_ok = False
            try:
                hallados = plan.encontrados_en_carpeta(carpeta)
                self._ui(lambda h=hallados: self._guardar_hallazgos(h))
                pasos = [p for p in plan.plan_instalacion(hallados, solo_copiar=True) if p["tipo"] == "copia"]
                self._log(f"Copiando desde {carpeta}: {len(pasos)} paso(s).")
                if not pasos:
                    self._log("Esa carpeta no tiene modelos que falten aquí.")
                else:
                    copia_ok = self._copiar(pasos)
            except Exception as error:
                self._log(f"Error copiando modelos: {error}")
            finally:
                self._ui(lambda ok=copia_ok: self._terminar(ok))
        threading.Thread(target=trabajo, daemon=True, name="MILLER-Copiar").start()
