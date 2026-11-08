"""MILLER · Panel bajo la esencia: páginas TERMINAL, INSTALACIÓN y MILLER (perfil, plan, espacio, llaves y acciones).
Cada página solo se ve si se abre."""
import queue
import re
import threading
import time

import configuracion
from utilidades import nombre as nombre_asistente

VERDE, VERDE_OSCURO, GRIS, ROJO, FONDO = "#2ee86a", "#0b2a12", "#5f8f6a", "#ff7a5a", "#000000"
AMBAR = "#ffc857"
TARJETA_LIBRE, TARJETA_PUESTA = "#070d09", "#0d4a22"
FUENTE, FUENTE_NEGRITA = ("Consolas", 8), ("Consolas", 8, "bold")
FUENTE_TITULO = ("Consolas", 11, "bold")
ALIAS = {"registro": "terminal"}                      # nombre antiguo de la página
BOTONES = (("terminal", "TERMINAL"), ("instalacion", "INSTALACIÓN"), ("llaves", "MILLER"))
PLANES = (("boy", "NIÑOS"), ("pro", "PRO"))
NOMBRE_PLAN = {"free": "FREE", "boy": "NIÑOS", "pro": "PRO"}
DESCRIPCION_PLAN = {
    "free": "Música, ventanas, alarmas y ecualizador",
    "boy": "Aprendizaje de sinónimos y órdenes; memoria",
    "pro": "Descargas, internet, archivos y biblioteca",
}
REFRESCO_LLAVES_MS = 700                              # cada cuánto se mira el estado de las llaves (solo lee memoria)
PURGA_CONFIRMAR_S = 6.0                               # segundos para confirmar PURGAR con otra pulsación
ALTO_MAX_ZONA_LLAVES = 150                            # alto máximo de la zona de tarjetas; si hay más, se desplaza
REFRESCO_DISCO_S = 5.0
HISTORIAL_MAXIMO = 100                                 # órdenes de la terminal que se recuerdan (flechas ↑ ↓)
_RE_CLAVE = re.compile(r"^\s*(miller[\s,]+)?(acceso|llave|clave|contrasena|password|ingresa)\b", re.IGNORECASE)


def _es_clave(texto):
    """Las órdenes que llevan una llave no se recuerdan: ni en las flechas ni en el archivo."""
    return bool(_RE_CLAVE.match(str(texto or "")))


def _ruta_historial():
    return configuracion.RUTA_DATOS / "terminal_historial.json"


def _leer_historial():
    try:
        from utilidades import seguridad
        datos = seguridad.leer_json(_ruta_historial(), None) or {}
        ordenes = datos.get("ordenes", []) if isinstance(datos, dict) else []
        return [o for o in ordenes if isinstance(o, str) and o and not _es_clave(o)][-HISTORIAL_MAXIMO:]
    except Exception:
        return []


def _guardar_historial(ordenes):
    try:
        from utilidades import seguridad
        seguridad.escribir_json(_ruta_historial(), {"ordenes": list(ordenes)[-HISTORIAL_MAXIMO:]}, indent=None)
    except Exception:
        pass
                                # cada cuánto se vuelve a medir el disco (en otro hilo)


def _tamano(bytes_):
    """Tamaño corto para la ventana: 850 MB, 2.4 GB."""
    if bytes_ >= 1024 ** 3:
        return f"{bytes_ / 1024 ** 3:.1f} GB"
    return f"{bytes_ / 1024 ** 2:.0f} MB"


class PanelInteraccion:
    """Vive en el hilo de Tk. El resto de MILLER le habla solo a través de una cola (seguro entre hilos).
    al_enviar(texto): se llama con cada orden escrita en la terminal (MILLER la ejecuta en otro hilo).
    al_redimensionar(): avisa a la ventana para que ajuste su alto al abrir o cerrar una página.
    al_cerrar(): cierra la ventana (PURGAR la usa al pedir la purga).
    La página MILLER comprueba las llaves en otro hilo (PBKDF2 tarda) y nunca deja la llave en pantalla.
    Las respuestas de los botones y de las llaves van a la TERMINAL, nunca a la ventana MILLER."""
    MAX_LINEAS = 200

    def __init__(self, tk, raiz, ancho, alto, al_enviar=None, al_redimensionar=None, al_cerrar=None, al_purgar=None):
        self.tk, self.raiz = tk, raiz
        self.al_enviar, self.al_redimensionar, self.al_cerrar = al_enviar, al_redimensionar, al_cerrar
        self.al_purgar = al_purgar          # la purga pide cerrar MILLER SIN cerrar la ventana todavía
        self.cola = queue.Queue()
        self.historial, self.pos_historial = _leer_historial(), 0
        self._borrador = ""                                    # lo escrito antes de empezar a subir por el historial
        self.pos_historial = len(self.historial)
        self.faltan = 0
        self._tarjetas = {}
        self._comprobando = set()                      # llaves que se están comprobando (en otro hilo)
        self._hay_llaves = False
        self._avatar_hay = None
        self._instantanea = None                       # última medición del disco y de los topes (la hace otro hilo)
        self._disco_medido, self._midiendo_disco = 0.0, False
        self._purga_armada, self._sellando = 0.0, False
        self._alto_zona_llaves = None                 # alto que pide ahora la zona de tarjetas
        self.ancho = ancho
        self._nombrando = False                        # hay un guardado del nombre en curso (lo hace otro hilo)
        try:                                           # primera vez: el nombre se pone en la página INSTALACIÓN
            self.nombre_pendiente = not nombre_asistente.fijado()
        except Exception:
            self.nombre_pendiente = False
        barra = tk.Frame(raiz, bg=FONDO, highlightthickness=1, highlightbackground=VERDE_OSCURO)
        barra.pack(fill="x")
        self.botones = {}
        for clave, texto in BOTONES:
            b = tk.Button(barra, text=texto, font=FUENTE_NEGRITA, bg=FONDO, fg=GRIS, activebackground=VERDE_OSCURO,
                          activeforeground=VERDE, relief="flat", bd=0, cursor="hand2",
                          command=lambda c=clave: self.alternar(c))
            b.pack(side="left", padx=4, pady=2)
            self.botones[clave] = b
        # Contenedor de páginas: solo se empaqueta cuando hay una abierta.
        self.marco = tk.Frame(raiz, bg=FONDO, width=ancho, height=alto, highlightthickness=1,
                              highlightbackground=VERDE_OSCURO)
        self.marco.pack_propagate(False)
        self.paginas = {"terminal": self._pagina_terminal(), "instalacion": self._pagina_instalacion(),
                        "llaves": self._pagina_llaves()}
        self.actual = None
        if self.nombre_pendiente:                      # saluda en la TERMINAL y abre la página del nombre
            self.registrar("MILLER", configuracion.MENSAJE_SALUDO_PRIMERA_VEZ)
            self.cola.put(("mostrar", "instalacion"))
        self.actualizar_estado()                       # revisa en segundo plano; solo marca el botón
        self.raiz.after(150, self._atender_cola)
        self.raiz.after(REFRESCO_LLAVES_MS, self._refrescar_llaves)

    # ------------------------------------------------------------ páginas
    def _texto(self, padre, alto):
        t = self.tk.Text(padre, height=alto, bg=FONDO, fg=VERDE, insertbackground=VERDE, font=FUENTE, relief="flat",
                         wrap="word", highlightthickness=0, bd=0)
        t.tag_configure("tu", foreground="#d8ffd8")
        t.tag_configure("aviso", foreground=GRIS)
        t.configure(state="disabled")
        return t

    def _pagina_terminal(self):
        marco = self.tk.Frame(self.marco, bg=FONDO)
        fila = self.tk.Frame(marco, bg=FONDO)
        fila.pack(side="bottom", fill="x", padx=4, pady=(0, 3))
        self.tk.Label(fila, text=">", font=FUENTE_NEGRITA, bg=FONDO, fg=VERDE).pack(side="left")
        self.entrada = self.tk.Entry(fila, bg="#03140a", fg=VERDE, insertbackground=VERDE, font=FUENTE, relief="flat",
                                     highlightthickness=1, highlightbackground=VERDE_OSCURO, highlightcolor=VERDE)
        self.entrada.pack(side="left", fill="x", expand=True, padx=(3, 3), ipady=2)
        self.entrada.bind("<Return>", self._enviar)
        self.entrada.bind("<Up>", lambda e: self._navegar(-1))
        self.entrada.bind("<Down>", lambda e: self._navegar(1))
        self.tk.Button(fila, text="ENVIAR", font=FUENTE_NEGRITA, bg=VERDE_OSCURO, fg=VERDE, activebackground=VERDE,
                       activeforeground=FONDO, relief="flat", bd=0, cursor="hand2",
                       command=self._enviar).pack(side="left")
        self.terminal = self._texto(marco, 10)
        self.terminal.pack(fill="both", expand=True, padx=4, pady=2)
        return marco

    def _pagina_instalacion(self):
        marco = self.tk.Frame(self.marco, bg=FONDO)
        # Nombre del asistente: solo la primera vez; se quita en cuanto queda fijado.
        self.bloque_nombre = self.tk.Frame(marco, bg=FONDO, highlightthickness=1, highlightbackground=AMBAR)
        self.tk.Label(self.bloque_nombre, text=configuracion.MENSAJE_SALUDO_PRIMERA_VEZ, font=FUENTE, bg=FONDO,
                      fg=AMBAR, justify="left", wraplength=max(200, self.ancho - 40)).pack(anchor="w", padx=4, pady=(2, 0))
        self.tk.Label(self.bloque_nombre, text="NOMBRE DEL ASISTENTE · se pone una sola vez", font=FUENTE_NEGRITA,
                      bg=FONDO, fg=VERDE).pack(anchor="w", padx=4)
        fila = self.tk.Frame(self.bloque_nombre, bg=FONDO)
        fila.pack(fill="x", padx=4, pady=2)
        self.entrada_nombre = self.tk.Entry(fila, bg="#03140a", fg=VERDE, insertbackground=VERDE, font=FUENTE,
                                            relief="flat", highlightthickness=1, highlightbackground=VERDE_OSCURO,
                                            highlightcolor=VERDE)
        self.entrada_nombre.pack(side="left", fill="x", expand=True, ipady=2)
        self.entrada_nombre.bind("<Return>", self._enviar_nombre)
        self.boton_nombre = self.tk.Button(fila, text="ENVIAR", font=FUENTE_NEGRITA, bg=VERDE_OSCURO, fg=VERDE,
                                           activebackground=VERDE, activeforeground=FONDO, relief="flat", bd=0,
                                           cursor="hand2", command=self._enviar_nombre)
        self.boton_nombre.pack(side="left", padx=(4, 0))
        self.tk.Label(self.bloque_nombre, text="Vacío = Miller. Enter o ENVIAR lo guardan.", font=FUENTE, bg=FONDO,
                      fg=GRIS).pack(anchor="w", padx=4, pady=(0, 2))
        if self.nombre_pendiente:
            self.bloque_nombre.pack(fill="x", padx=4, pady=(4, 2))
        self.lista = self.tk.Frame(marco, bg=FONDO)
        self.lista.pack(fill="x", padx=4)
        acciones = self.tk.Frame(marco, bg=FONDO)
        acciones.pack(fill="x", padx=4, pady=2)
        self.boton_instalar = self.tk.Button(acciones, text="INSTALAR LO QUE FALTA", font=FUENTE_NEGRITA, bg=VERDE_OSCURO,
                                             fg=VERDE, activebackground=VERDE, activeforeground=FONDO, relief="flat",
                                             command=self._instalar)
        self.boton_instalar.pack(side="left")
        self.tk.Button(acciones, text="REVISAR", font=FUENTE, bg=FONDO, fg=GRIS, relief="flat",
                       command=self.actualizar_estado).pack(side="left", padx=6)
        self.bitacora = self._texto(marco, 5)
        self.bitacora.pack(fill="both", expand=True, padx=4, pady=2)
        return marco

    def _pagina_llaves(self):
        """Página MILLER. Arriba: el perfil (avatar y plan) y las acciones PURGAR y SELLAR. Debajo: la única barra
        de progreso (lo consumido según la llave que manda), la descripción del plan. Al final,
        las dos tarjetas de llave, con desplazamiento si no caben."""
        marco = self.tk.Frame(self.marco, bg=FONDO)
        cabecera = self.tk.Frame(marco, bg=FONDO)
        cabecera.pack(side="top", fill="x", padx=6, pady=(4, 0))
        self.avatar = self.tk.Canvas(cabecera, width=30, height=30, bg=FONDO, highlightthickness=0)
        self.avatar.pack(side="left")
        acciones = self.tk.Frame(cabecera, bg=FONDO)
        acciones.pack(side="right")
        cabecera_texto = self.tk.Frame(cabecera, bg=FONDO)
        cabecera_texto.pack(side="left", padx=6, fill="x", expand=True)
        self.tk.Label(cabecera_texto, text="MILLER", font=FUENTE_TITULO, bg=FONDO, fg=VERDE, anchor="w").pack(fill="x")
        self.plan_llave = self.tk.Label(cabecera_texto, text="", font=FUENTE_NEGRITA, bg=FONDO, fg=VERDE, anchor="w")
        self.plan_llave.pack(fill="x")
        self.boton_purgar = self.tk.Button(acciones, text="PURGAR", width=10, font=FUENTE_NEGRITA, bg=VERDE_OSCURO,
                                           fg=VERDE, activebackground=VERDE, activeforeground=FONDO, relief="flat",
                                           bd=0, cursor="hand2", command=self._pulsar_purgar)
        self.boton_purgar.pack(fill="x", pady=(0, 2))
        self.boton_sellar = self.tk.Button(acciones, text="SELLAR", width=10, font=FUENTE_NEGRITA, bg=VERDE_OSCURO,
                                           fg=VERDE, activebackground=VERDE, activeforeground=FONDO, relief="flat",
                                           bd=0, cursor="hand2", command=self._pulsar_sellar)
        self.boton_sellar.pack(fill="x")
        self.descripcion_llave = self.tk.Label(marco, text="", font=FUENTE, bg=FONDO, fg=GRIS, anchor="w",
                                               justify="left", wraplength=318)
        self.descripcion_llave.pack(side="top", fill="x", padx=6, pady=(2, 0))
        # La única barra: lo que MILLER ocupa frente al tope total del modo que manda (la llave puesta).
        espacio = self.tk.Frame(marco, bg=FONDO)
        espacio.pack(side="top", fill="x", padx=6, pady=(3, 0))
        self.espacio_texto = self.tk.Label(espacio, text="", font=FUENTE, bg=FONDO, fg=GRIS, anchor="w")
        self.espacio_texto.pack(fill="x")
        self.espacio_barra = self.tk.Canvas(espacio, height=10, bg=VERDE_OSCURO, highlightthickness=0)
        self.espacio_barra.pack(fill="x", pady=(1, 0))
        self.espacio_barra.bind("<Configure>", lambda e: self._redibujar(self.espacio_barra))
        self.disco_llave = self.tk.Label(espacio, text="", font=FUENTE, bg=FONDO, fg=GRIS, anchor="w")
        self.disco_llave.pack(fill="x")
        # Zona con desplazamiento para las tarjetas: si no caben, se baja con la barra o con la rueda del ratón.
        zona = self.tk.Frame(marco, bg=FONDO)
        zona.pack(side="top", fill="both", expand=True, padx=4, pady=(0, 4))
        self.lienzo_llaves = self.tk.Canvas(zona, bg=FONDO, highlightthickness=0, bd=0)
        self.barra_llaves = self.tk.Scrollbar(zona, orient="vertical", command=self.lienzo_llaves.yview)
        self.lienzo_llaves.configure(yscrollcommand=self.barra_llaves.set)
        self.barra_llaves.pack(side="right", fill="y")
        self.lienzo_llaves.pack(side="left", fill="both", expand=True)
        self.interior_llaves = self.tk.Frame(self.lienzo_llaves, bg=FONDO)
        self._ventana_llaves = self.lienzo_llaves.create_window((0, 0), window=self.interior_llaves, anchor="nw")
        self.interior_llaves.bind("<Configure>", self._ajustar_scroll_llaves)
        self.lienzo_llaves.bind("<Configure>", self._ajustar_ancho_llaves)
        self.lienzo_llaves.bind_all("<MouseWheel>", self._rueda_llaves)
        self.lienzo_llaves.bind_all("<Button-4>", lambda e: self._rueda_llaves(e, -1))
        self.lienzo_llaves.bind_all("<Button-5>", lambda e: self._rueda_llaves(e, 1))
        for numero, (plan, nombre) in enumerate(PLANES, start=1):
            tarjeta = self._crear_tarjeta(self.interior_llaves, plan, nombre, numero)
            tarjeta["marco"].pack(fill="x", padx=4, pady=(2, 4))
            self._tarjetas[plan] = tarjeta
        return marco

    def _crear_tarjeta(self, padre, plan, nombre, numero):
        """Tarjeta compacta, una sola fila. Sin llave: «ingresa clave boy», la casilla y ENVIAR. Con la llave correcta,
        la fila se pone verde («LLAVE 1 · NIÑOS ✓ PUESTA») y ya no tiene casilla: el registro se hace una sola vez."""
        marco = self.tk.Frame(padre, bg=TARJETA_LIBRE, highlightthickness=1, highlightbackground=VERDE_OSCURO)
        fila = self.tk.Frame(marco, bg=TARJETA_LIBRE)
        fila.pack(fill="x", padx=5, pady=4)
        pregunta = self.tk.Label(fila, text=f"ingresa clave {plan}", font=FUENTE_NEGRITA, bg=TARJETA_LIBRE, fg=GRIS)
        pregunta.pack(side="left", padx=(0, 4))
        entrada = self.tk.Entry(fila, show="•", bg="#03140a", fg=VERDE, insertbackground=VERDE, font=FUENTE,
                                relief="flat", highlightthickness=1, highlightbackground=VERDE_OSCURO,
                                highlightcolor=VERDE)
        entrada.pack(side="left", fill="x", expand=True, ipady=2)
        entrada.bind("<Return>", lambda e, p=plan: self._aplicar_llave(p))
        enviar = self.tk.Button(fila, text="ENVIAR", font=FUENTE_NEGRITA, bg=VERDE_OSCURO, fg=VERDE,
                                activebackground=VERDE, activeforeground=FONDO, relief="flat", bd=0, cursor="hand2",
                                command=lambda p=plan: self._aplicar_llave(p))
        enviar.pack(side="left", padx=(4, 0))
        estado = self.tk.Label(fila, text="", font=FUENTE_NEGRITA, bg=TARJETA_LIBRE, fg=VERDE, anchor="w")
        return {"marco": marco, "fila": fila, "fondos": [marco, fila, pregunta, estado], "puesta": None,
                "numero": numero, "nombre": nombre, "pregunta": pregunta, "entrada": entrada, "enviar": enviar,
                "estado": estado}

    def _ajustar_scroll_llaves(self, _evento=None):
        """La zona de desplazamiento llega hasta el final de las tarjetas (nunca es menor que la zona visible)."""
        alto = max(self.lienzo_llaves.winfo_height(), self.interior_llaves.winfo_reqheight())
        self.lienzo_llaves.configure(scrollregion=(0, 0, self.lienzo_llaves.winfo_width(), alto))

    def _ajustar_zona_llaves(self):
        """La zona de tarjetas pide solo el alto que miden, con tope ALTO_MAX_ZONA_LLAVES: si hay más, se desplaza.
        Devuelve True si el alto cambió, para que la ventana se vuelva a medir."""
        self.interior_llaves.update_idletasks()
        alto = min(self.interior_llaves.winfo_reqheight(), ALTO_MAX_ZONA_LLAVES)
        if alto == self._alto_zona_llaves:
            return False
        self._alto_zona_llaves = alto
        self.lienzo_llaves.configure(height=alto)
        return True

    def _ajustar_ancho_llaves(self, evento):
        """Las tarjetas ocupan todo el ancho de la zona con desplazamiento."""
        self.lienzo_llaves.itemconfigure(self._ventana_llaves, width=evento.width)
        self._ajustar_scroll_llaves()

    def _rueda_llaves(self, evento, paso=None):
        """Rueda del ratón (o botones 4 y 5 en Linux): solo desplaza cuando la página MILLER está abierta."""
        if self.actual != "llaves":
            return
        if paso is None:
            paso = -1 if evento.delta > 0 else 1
        self.lienzo_llaves.yview_scroll(paso, "units")

    def alternar(self, clave):
        """Un clic abre la página; otro clic en el mismo botón la cierra (solo quedan los botones)."""
        clave = ALIAS.get(clave, clave)
        self.mostrar(None if clave == self.actual else clave)

    def mostrar(self, clave):
        clave = ALIAS.get(clave, clave)
        if clave == self.actual:
            return
        if self.actual:
            self.paginas[self.actual].pack_forget()
        if clave is None:
            self.marco.pack_forget()
        else:
            self.marco.pack(fill="x")
            self.paginas[clave].pack(fill="both", expand=True)
        self.actual = clave
        self._pintar_botones()
        if clave == "instalacion":
            self.actualizar_estado()
            if self.nombre_pendiente:
                self.entrada_nombre.focus_set()
        elif clave == "llaves":
            self._pintar_llaves()
            self._medir_disco()
            self._ajustar_zona_llaves()
        elif clave == "terminal":
            self.entrada.focus_set()
        if callable(self.al_redimensionar):
            self.al_redimensionar()

    def _pintar_botones(self):
        nombres = dict(BOTONES)
        for nombre, boton in self.botones.items():
            activo = nombre == self.actual
            alerta = bool(nombre == "instalacion" and (self.faltan or self.nombre_pendiente))
            texto = nombres[nombre] + (" !" if alerta else "")
            if nombre == "llaves" and self._hay_llaves:
                texto += " ●"                          # hay alguna llave puesta: MILLER trabaja con potencia
            color = VERDE if activo else (ROJO if alerta else GRIS)
            boton.configure(text=("▾ " if activo else "▸ ") + texto, fg=color)

    # ------------------------------------------------------------ terminal (modo texto)
    # ------------------------------------------------------------ nombre del asistente (solo la primera vez)
    def _enviar_nombre(self, _evento=None):
        """ENVIAR o Enter: pone el nombre. Vacío = el predeterminado. El guardado va en otro hilo."""
        if self._nombrando or not self.nombre_pendiente:
            return "break"
        texto = self.entrada_nombre.get().strip() or configuracion.NOMBRE_PREDETERMINADO
        self._nombrando = True

        def trabajo():
            try:
                ok, resultado = nombre_asistente.fijar(texto)
            except Exception as error:
                ok, resultado = False, f"No pude guardar el nombre ({error})."
            self.cola.put(("nombre", (ok, resultado)))
        threading.Thread(target=trabajo, daemon=True, name="MILLER-Nombre").start()
        return "break"

    def _resultado_nombre(self, ok, resultado):
        """La respuesta del guardado va a la TERMINAL. Con el nombre fijado, el campo desaparece."""
        self._nombrando = False
        if not ok:
            try:
                fijado = nombre_asistente.fijado()
            except Exception:
                fijado = False
            if fijado:                                 # ya estaba puesto: no vuelve a pedirse
                self.nombre_pendiente = False
                self.bloque_nombre.pack_forget()
                self.mostrar("terminal")
            self.registrar("MILLER", f"Negativo. {resultado}")
            return
        self.nombre_pendiente = False
        self.bloque_nombre.pack_forget()
        self.entrada_nombre.delete(0, "end")
        self.registrar("MILLER", f"Afirmativo, señor. Desde ahora me llamo {resultado}.")
        self.mostrar("terminal")

    def _enviar(self, _evento=None):
        texto = self.entrada.get().strip()
        if not texto:
            return "break"
        self.entrada.delete(0, "end")
        if not self.historial or self.historial[-1] != texto:
            if not _es_clave(texto):                           # las claves nunca quedan guardadas
                self.historial.append(texto)
                self.historial = self.historial[-HISTORIAL_MAXIMO:]
                _guardar_historial(self.historial)
        self.pos_historial = len(self.historial)
        self._borrador = ""
        if callable(self.al_enviar):
            try:
                self.al_enviar(texto)                  # la orden aparece como "Tú:" cuando MILLER la toma
            except Exception as error:
                self._anadir(self.terminal, f"[error] {error}", "aviso")
        else:
            self._anadir(self.terminal, "Modo texto no disponible.", "aviso")
        return "break"

    def _navegar(self, paso):
        """Flechas: ↑ va a órdenes anteriores, ↓ a las siguientes; al final vuelve lo que estaba escribiendo."""
        if not self.historial:
            return "break"
        if self.pos_historial >= len(self.historial) and paso < 0:
            self._borrador = self.entrada.get()
        self.pos_historial = max(0, min(len(self.historial), self.pos_historial + paso))
        self.entrada.delete(0, "end")
        if self.pos_historial < len(self.historial):
            self.entrada.insert(0, self.historial[self.pos_historial])
        else:
            self.entrada.insert(0, self._borrador)
        self.entrada.icursor("end")
        return "break"

    # ------------------------------------------------------------ MILLER: llaves, plan y disco
    def _aplicar_llave(self, plan):
        """Envía la clave escrita en la tarjeta. La casilla se vacía al instante (la clave no queda en pantalla) y la
        comprobación (PBKDF2 tarda) va en otro hilo para no trabar la ventana. La respuesta va a la TERMINAL: si la
        clave es correcta, la tarjeta se pone verde en la siguiente pintura; si no lo es, la tarjeta destella en rojo."""
        t = self._tarjetas[plan]
        texto = t["entrada"].get().strip()
        t["entrada"].delete(0, "end")
        if not texto or t["puesta"]:
            return "break"
        self._comprobando.add(plan)

        def trabajo():
            from utilidades import acceso
            try:
                aviso = acceso.poner(plan, texto)
                self.registrar("MILLER", aviso)
                if plan not in acceso.activas():
                    self.cola.put(("destello", plan))
            except Exception as error:
                print(f"[INTERFAZ] Llave {plan}: {error}")
                self.registrar("MILLER", "Negativo. No se pudo comprobar esa llave, señor.")
                self.cola.put(("destello", plan))
            finally:
                self._comprobando.discard(plan)
        threading.Thread(target=trabajo, daemon=True, name="MILLER-Llave").start()
        return "break"

    def _destellar_tarjeta(self, plan):
        """Una llave que no vale: el borde de la tarjeta se pone rojo un momento. No escribe nada en la ventana."""
        t = self._tarjetas[plan]
        t["marco"].configure(highlightbackground=ROJO)
        self.raiz.after(700, lambda: t["marco"].configure(highlightbackground=VERDE if t["puesta"] else VERDE_OSCURO))

    def _pulsar_purgar(self):
        """PURGAR pide confirmación: la primera pulsación pone el botón en rojo durante PURGA_CONFIRMAR_S segundos y lo
        explica en la TERMINAL (sin escribir nada en el botón); la segunda pide la purga y cierra MILLER. La purga se
        hace al cerrarse, con todo parado: ningún archivo está en uso."""
        from utilidades import purga
        ahora = time.monotonic()
        if self._purga_armada and ahora - self._purga_armada <= PURGA_CONFIRMAR_S:
            self._purga_armada = 0.0
            self.boton_purgar.configure(bg=VERDE_OSCURO, fg=VERDE)
            purga.pedir()
            self.registrar("MILLER", "Purga pedida: MILLER se despide, se cierra y, al cerrarse, borra recuerdos, cachés y el nombre. "
                                     "Reábralo para empezar de nuevo, señor.")
            self.cola.put(("mostrar", "terminal"))
            if callable(self.al_purgar):
                self.al_purgar()                 # MILLER se despide, funde la música y cierra la ventana al final
            return "break"
        self._purga_armada = ahora
        self.boton_purgar.configure(bg=ROJO, fg=FONDO)
        self.registrar("MILLER", f"Purga armada: pulse PURGAR otra vez en {int(PURGA_CONFIRMAR_S)} segundos para "
                                 "confirmar, señor. Borra recuerdos, aprendizaje, cachés y el nombre.")
        self.raiz.after(int(PURGA_CONFIRMAR_S * 1000) + 100, self._desarmar_purga)
        return "break"

    def _desarmar_purga(self):
        """Si pasa el tiempo de confirmación sin segunda pulsación, PURGAR vuelve a su color y la TERMINAL lo dice."""
        if self._purga_armada and time.monotonic() - self._purga_armada >= PURGA_CONFIRMAR_S:
            self._purga_armada = 0.0
            self.boton_purgar.configure(bg=VERDE_OSCURO, fg=VERDE)
            self.registrar("MILLER", "Purga cancelada: no se confirmó a tiempo, señor.")

    def _pulsar_sellar(self):
        """SELLAR guarda las huellas del código tal como está. Solo con llave PRO (lo decide acceso.bloqueo). La
        respuesta va a la TERMINAL, y la ventana pasa a esa página para verla. El sellado va en otro hilo porque
        recorre los archivos .py y tarda un poco."""
        from utilidades import acceso
        if self._sellando:
            return "break"
        aviso = acceso.bloqueo("SELLAR_CODIGO")
        if aviso:
            self.registrar("MILLER", aviso)
            self.cola.put(("mostrar", "terminal"))
            return "break"
        self._sellando = True
        self.registrar("MILLER", "Sellando el código…")
        self.cola.put(("mostrar", "terminal"))

        def trabajo():
            from utilidades import seguridad
            try:
                n = seguridad.sellar_codigo()
                self.registrar("MILLER", f"Código sellado: {n} archivos. Avisaré si alguno cambia sin que usted lo diga.")
            except Exception as error:
                self.registrar("MILLER", f"Negativo. No se pudo sellar el código: {error}")
            finally:
                self._sellando = False
        threading.Thread(target=trabajo, daemon=True, name="MILLER-Sello").start()
        return "break"

    def _pintar_llaves(self):
        """Pinta lo que es estado: el plan, la descripción, el avatar, la barra y las tarjetas. No escribe respuestas:
        esas van a la TERMINAL."""
        from utilidades import acceso
        activas = acceso.activas()
        modo = acceso.modo()
        self.plan_llave.configure(text=f"Plan actual: {NOMBRE_PLAN[modo]}")
        self.descripcion_llave.configure(text=DESCRIPCION_PLAN.get(modo, ""))
        self._pintar_avatar(bool(activas))
        self._pintar_espacio(modo)
        for plan, _ in PLANES:
            self._pintar_tarjeta(plan, plan in activas)

    def _pintar_avatar(self, hay):
        """El avatar de MILLER se enciende cuando hay alguna llave puesta."""
        if hay == self._avatar_hay:
            return
        self._avatar_hay = hay
        self.avatar.delete("all")
        self.avatar.create_oval(1, 1, 29, 29, fill=VERDE if hay else VERDE_OSCURO, outline=VERDE)
        self.avatar.create_oval(9, 9, 21, 21, fill=FONDO if hay else VERDE, outline="")

    def _pintar_espacio(self, modo):
        """La única barra: lo que MILLER ocupa (asistente más archivos) frente al tope total del modo que manda.
        Las cifras son de la última medición de cuota.instantanea(), que corre en otro hilo mientras la página está
        abierta (cada 5 segundos). El tope cambia en cuanto se pone o se quita una llave; lo ocupado, en la medición."""
        s = self._instantanea
        if s is None:
            self.espacio_texto.configure(text="Midiendo el espacio…")
            self.disco_llave.configure(text="")
            self._dibujar_barra(self.espacio_barra, 0.0)
            return
        usado = s["uso"]["asistente"] + s["uso"]["archivos"]
        tope = s["limites"][modo]["asistente"] + s["limites"][modo]["archivos"]
        fraccion = usado / tope if tope else 1.0
        color = VERDE if fraccion < 0.8 else (AMBAR if fraccion < 0.95 else ROJO)
        self.espacio_texto.configure(text=f"Consumido ({NOMBRE_PLAN[modo]}): {_tamano(usado)} de {_tamano(tope)} · "
                                          f"{round(fraccion * 100)} %")
        self._dibujar_barra(self.espacio_barra, fraccion, color)
        self.disco_llave.configure(text=f"Disco: {_tamano(s['libre'])} libres de {_tamano(s['total'])}")

    def _pintar_tarjeta(self, plan, puesta):
        """Pinta la tarjeta según su llave. Puesta: verde, «✓ PUESTA» y sin casilla. Sin llave: la casilla y sin color.
        Solo cambia lo que cambia (se repite cada 0,7 s)."""
        t = self._tarjetas[plan]
        if t["puesta"] == puesta:
            return
        t["puesta"] = puesta
        fondo = TARJETA_PUESTA if puesta else TARJETA_LIBRE
        for widget in t["fondos"]:
            widget.configure(bg=fondo)
        t["marco"].configure(highlightbackground=VERDE if puesta else VERDE_OSCURO)
        if puesta:
            t["entrada"].delete(0, "end")                  # la clave no queda en la casilla
            for widget in (t["pregunta"], t["entrada"], t["enviar"]):
                widget.pack_forget()
            t["estado"].configure(text=f"LLAVE {t['numero']} · {t['nombre']}   ✓ PUESTA", fg=VERDE)
            t["estado"].pack(side="left", fill="x", expand=True)
        else:
            t["estado"].pack_forget()
            t["pregunta"].pack(side="left", padx=(0, 4))
            t["entrada"].pack(side="left", fill="x", expand=True, ipady=2)
            t["enviar"].pack(side="left", padx=(4, 0))

    def _dibujar_barra(self, lienzo, fraccion, color=VERDE):
        lienzo.dato = (max(0.0, min(1.0, fraccion)), color)
        ancho = lienzo.winfo_width()
        if ancho < 10:                                 # la ventana aún no se ha dibujado
            ancho = 120
        lienzo.delete("all")
        lienzo.create_rectangle(0, 0, ancho, 8, fill=VERDE_OSCURO, outline="")
        fraccion, color = lienzo.dato
        if fraccion > 0:
            lienzo.create_rectangle(0, 0, int(ancho * fraccion), 8, fill=color, outline="")

    def _redibujar(self, lienzo):
        fraccion, color = getattr(lienzo, "dato", (0.0, VERDE))
        self._dibujar_barra(lienzo, fraccion, color)

    def _medir_disco(self):
        """Mide el disco y los topes en otro hilo (recorrer las carpetas puede tardar). Se repite cada pocos segundos."""
        if self._midiendo_disco:
            return
        self._midiendo_disco = True
        self._disco_medido = time.monotonic()

        def trabajo():
            try:
                from utilidades import cuota
                self._instantanea = cuota.instantanea()
            except Exception as error:
                print(f"[INTERFAZ] Disco: {error}")
            finally:
                self._midiendo_disco = False
        threading.Thread(target=trabajo, daemon=True, name="MILLER-Disco").start()

    def _refrescar_llaves(self):
        """Cada 0,7 s: si cambia si hay llaves puestas, actualiza el botón; con la página abierta, la pinta."""
        try:
            from utilidades import acceso
            hay = bool(acceso.activas())
            if hay != self._hay_llaves:
                self._hay_llaves = hay
                self._pintar_botones()
            if self.actual == "llaves":
                self._pintar_llaves()
                if self._ajustar_zona_llaves() and callable(self.al_redimensionar):
                    self.al_redimensionar()
                if time.monotonic() - self._disco_medido > REFRESCO_DISCO_S:
                    self._medir_disco()
        except Exception as error:
            print(f"[INTERFAZ] Llaves: {error}")
        self.raiz.after(REFRESCO_LLAVES_MS, self._refrescar_llaves)

    # ------------------------------------------------------------ instalación
    def actualizar_estado(self):
        """Pinta cada componente con ✓ o ✗ (se calcula en otro hilo: no traba la ventana)."""
        def calcular():
            try:
                from utilidades import instalador
                self.cola.put(("estado", instalador.estado()))
            except Exception as error:
                self.cola.put(("bitacora", f"No se pudo revisar: {error}"))
        threading.Thread(target=calcular, daemon=True).start()

    def _pintar_estado(self, filas):
        for hijo in self.lista.winfo_children():
            hijo.destroy()
        faltan = 0
        for _, nombre, listo, _ in filas:
            faltan += 0 if listo else 1
            self.tk.Label(self.lista, text=("✓ " if listo else "✗ ") + nombre, anchor="w", font=FUENTE, bg=FONDO,
                          fg=VERDE if listo else ROJO).pack(fill="x")
        self.faltan = faltan
        self.boton_instalar.configure(state="normal" if faltan else "disabled",
                                      text="INSTALAR LO QUE FALTA" if faltan else "TODO INSTALADO")
        self._pintar_botones()

    def _instalar(self):
        self.boton_instalar.configure(state="disabled", text="INSTALANDO…")
        def trabajo():
            from utilidades import instalador
            instalador.instalar_todo(lambda texto: self.cola.put(("bitacora", texto)))
            self.cola.put(("refrescar", None))
        threading.Thread(target=trabajo, daemon=True, name="MILLER-Instalador").start()

    # ------------------------------------------------------------ desde cualquier hilo
    def registrar(self, quien, texto):
        self.cola.put(("registro", (f"{quien}: {texto}", "tu" if quien == "Tú" else None)))

    def _anadir(self, widget, linea, etiqueta=None):
        widget.configure(state="normal")
        widget.insert("end", linea + "\n", (etiqueta,) if etiqueta else ())
        lineas = int(widget.index("end-1c").split(".")[0])
        if lineas > self.MAX_LINEAS:
            widget.delete("1.0", f"{lineas - self.MAX_LINEAS}.0")
        widget.see("end")
        widget.configure(state="disabled")

    def limpiar_terminal(self):
        """Pide vaciar la TERMINAL. Es seguro desde cualquier hilo: pasa por la cola."""
        self.cola.put(("limpiar", None))

    def _vaciar(self, widget):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.configure(state="disabled")

    def _atender_cola(self):
        """Procesa como mucho 20 mensajes por vuelta: la ventana nunca se satura."""
        for _ in range(20):
            try:
                tipo, dato = self.cola.get_nowait()
            except queue.Empty:
                break
            try:
                if tipo == "registro":
                    self._anadir(self.terminal, *dato)
                elif tipo == "bitacora":
                    self._anadir(self.bitacora, dato)
                elif tipo == "estado":
                    self._pintar_estado(dato)
                elif tipo == "refrescar":
                    self.actualizar_estado()
                elif tipo == "mostrar":
                    self.mostrar(dato)
                elif tipo == "destello":
                    self._destellar_tarjeta(dato)
                elif tipo == "nombre":
                    self._resultado_nombre(*dato)
                elif tipo == "limpiar":
                    self._vaciar(self.terminal)
            except Exception as error:
                print(f"[INTERFAZ] Panel: {error}")
        self.raiz.after(150, self._atender_cola)
