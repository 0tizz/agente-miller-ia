"""MILLER · Página INSTALACIÓN de la ventana.

- Lista de componentes: ✓ verde si está instalado, ✗ rojo si falta (y dónde se encontró en este equipo).
- Barra de la descarga o paso actual, y barra del progreso total.
- Botones que solo se activan cuando tienen sentido: INSTALAR LO QUE FALTA solo si falta algo.

El trabajo pesado corre en hilos. Todo cambio de la ventana vuelve al hilo de la interfaz por la cola del panel.
"""
import threading

from utilidades import instalador, plan_instalacion as plan


class PaginaInstalacion:
    def __init__(self, panel, marco, tema, fuente, fuente_negrita):
        self.panel = panel
        self.tk = panel.tk
        self.t = tema                      # colores del panel: FONDO, VERDE, VERDE_OSCURO, ROJO, GRIS, AMBAR
        self.fuente, self.fuente_negrita = fuente, fuente_negrita
        self.filas = None                  # None = todavía no revisado; si no, estado() de instalador
        self.encontrados = {}              # clave -> carpeta encontrada en este equipo
        self.ocupado = False               # hay una instalación, copia o búsqueda en curso
        self._pulso, self._pulsando, self._latiendo = 0, False, False
        self._construir(marco)
        self.revisar()

    # ------------------------------------------------------------ construcción
    def _construir(self, marco):
        f = self.t["FONDO"]
        acciones = self.tk.Frame(marco, bg=f)
        acciones.pack(fill="x", padx=4, pady=2)
        self.b_instalar = self.tk.Button(acciones, text="REVISANDO…", font=self.fuente_negrita, bg=self.t["VERDE_OSCURO"],
                                         fg=self.t["VERDE"], activebackground=self.t["VERDE"], relief="flat",
                                         command=self.instalar)
        self.b_instalar.pack(side="left")
        self.b_buscar = self.tk.Button(acciones, text="BUSCAR EN ESTE EQUIPO", font=self.fuente, bg=f,
                                       fg=self.t["AMBAR"], relief="flat", command=self.buscar)
        self.b_buscar.pack(side="left", padx=6)
        self.b_elegir = self.tk.Button(acciones, text="ELEGIR CARPETA…", font=self.fuente, bg=f,
                                       fg=self.t["GRIS"], relief="flat", command=self.elegir_carpeta)
        self.b_elegir.pack(side="left", padx=6)
        self.b_revisar = self.tk.Button(acciones, text="REVISAR", font=self.fuente, bg=f, fg=self.t["GRIS"],
                                        relief="flat", command=self.revisar)
        self.b_revisar.pack(side="left", padx=6)

        self.resumen = self.tk.Label(marco, text="", anchor="w", font=self.fuente, bg=f, fg=self.t["GRIS"])
        self.resumen.pack(fill="x", padx=4, pady=(2, 0))
        self.lista = self.tk.Frame(marco, bg=f)
        self.lista.pack(fill="x", padx=4)

        self.texto_actual = self.tk.Label(marco, text="", anchor="w", font=self.fuente, bg=f, fg=self.t["GRIS"])
        self.texto_actual.pack(fill="x", padx=4, pady=(6, 0))
        self.barra_actual = self.tk.Canvas(marco, height=10, bg=f, highlightthickness=0)
        self.barra_actual.pack(fill="x", padx=4)
        self.texto_total = self.tk.Label(marco, text="", anchor="w", font=self.fuente, bg=f, fg=self.t["GRIS"])
        self.texto_total.pack(fill="x", padx=4, pady=(4, 0))
        self.barra_total = self.tk.Canvas(marco, height=10, bg=f, highlightthickness=0)
        self.barra_total.pack(fill="x", padx=4, pady=(0, 4))

        self.bitacora = self.panel._texto(marco, 5)
        self.bitacora.pack(fill="both", expand=True, padx=4, pady=2)

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
        ancho, alto = max(lienzo.winfo_width(), 300), 10
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

    def _pintar_lista(self):
        for hijo in self.lista.winfo_children():
            hijo.destroy()
        for clave, nombre, listo, tipo in (self.filas or []):
            fila = self.tk.Frame(self.lista, bg=self.t["FONDO"])
            fila.pack(fill="x")
            self.tk.Label(fila, text=("✓ " if listo else "✗ ") + nombre, anchor="w", font=self.fuente,
                          bg=self.t["FONDO"], fg=self.t["VERDE"] if listo else self.t["ROJO"]).pack(side="left")
            if not listo and tipo == "modelo":
                if self.encontrados.get(clave):
                    detalle, color = f"   · encontrado en {self.encontrados[clave]}", self.t["AMBAR"]
                else:
                    detalle, color = "   · no está en este equipo: se descargará", self.t["GRIS"]
                self.tk.Label(fila, text=detalle, anchor="w", font=self.fuente, bg=self.t["FONDO"],
                              fg=color).pack(side="left")
        self._pintar_resumen()

    def _faltan(self):
        """Cuántos componentes faltan, o None si todavía no se ha revisado."""
        if self.filas is None:
            return None
        return sum(1 for _, _, listo, _ in self.filas if not listo)

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
        self.b_revisar.configure(state="normal" if libre else "disabled")
        puede_faltar = bool(faltan) and libre
        self.b_buscar.configure(state="normal" if puede_faltar else "disabled")
        self.b_elegir.configure(state="normal" if puede_faltar else "disabled")
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

    def _terminar(self):
        self.ocupado = False
        self._pulsando = False
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

    def buscar(self):
        """Busca en este equipo los modelos que faltan (sin descargar ni copiar nada)."""
        if self.ocupado or not self._faltan():
            return
        self._empezar()

        def trabajo():
            try:
                pendientes = [c for c, m in instalador.MODELOS.items() if not m["prueba"]()]
                self._log("Buscando modelos en este equipo: carpeta de MILLER, Escritorio, Documentos, Descargas…")
                hallados = plan.buscar_en_equipo(pendientes, progreso=self._cb_actual)
                self._ui(lambda h=hallados: self._guardar_hallazgos(h))
                for clave in pendientes:
                    nombre = instalador.MODELOS[clave]["nombre"]
                    if hallados.get(clave):
                        self._log(f"Encontrado: {nombre} en {hallados[clave]}")
                    else:
                        self._log(f"No está en este equipo: {nombre}")
            except Exception as error:
                self._log(f"Error buscando: {error}")
            finally:
                self._ui(self._terminar)
        threading.Thread(target=trabajo, daemon=True, name="MILLER-Buscar").start()

    def instalar(self):
        """Instala solo lo que falta: copia lo que se encontró en el equipo y descarga el resto."""
        if self.ocupado or not self._faltan():
            return
        self._empezar()

        def trabajo():
            try:
                pendientes = [c for c, m in instalador.MODELOS.items() if not m["prueba"]()]
                por_buscar = [c for c in pendientes if c not in self.encontrados]
                if por_buscar:
                    hallados = plan.buscar_en_equipo(por_buscar, progreso=self._cb_actual)
                    self._ui(lambda h=hallados: self._guardar_hallazgos(h))
                pasos = plan.plan_instalacion(dict(self.encontrados))
                self._log(f"Plan: {len(pasos)} paso(s).")
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
            try:
                hallados = plan.encontrados_en_carpeta(carpeta)
                self._ui(lambda h=hallados: self._guardar_hallazgos(h))
                pasos = plan.plan_instalacion(hallados, solo_copiar=True)
                self._log(f"Copiando desde {carpeta}: {len(pasos)} paso(s).")
                if not pasos:
                    self._log("Esa carpeta no tiene modelos que falten aquí.")
                else:
                    plan.ejecutar_plan(pasos, avisar=self._log, progreso_paso=self._cb_actual,
                                       progreso_total=self._cb_total)
            except Exception as error:
                self._log(f"Error copiando modelos: {error}")
            finally:
                self._ui(self._terminar)
        threading.Thread(target=trabajo, daemon=True, name="MILLER-Copiar").start()
