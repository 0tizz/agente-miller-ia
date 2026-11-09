"""Plantilla de tarjeta de la Biblioteca musical del explorador: una tarjeta por canción o carpeta.

La tarjeta solo pinta y avisa. Las tarjetas se guardan en caché (una por archivo): cuando cambia la cola o lo que
suena, la tarjeta ya construida se actualiza en sitio (actualizar) y solo cambia el texto que corresponde. Nunca se
vuelve a crear para mostrar un cambio, así no hay parpadeo.

acciones: "reproducir", "cola", "copiar", "papelera", "abrir" (botones, reciben la entrada),
          "doble" (doble clic, recibe la entrada), "seleccionar" y "menu" (reciben (evento, entrada)),
          "rueda" (recibe el evento).
Las funciones de texto y de color no usan Tkinter y se prueban sin ventana.
"""


def texto_boton_cola(en_cola):
    """Lo que dice el botón de la cola según el puesto de la canción (None = no está en la cola)."""
    return "Quitar cola" if en_cola else "A la cola"


def botones_de(entrada, en_cola=None):
    """Botones de la tarjeta: una carpeta solo se abre; una canción tiene reproducir, cola, copiar y papelera."""
    if entrada.get("carpeta"):
        return (("abrir", "Abrir"),)
    return (("reproducir", "Reproducir"), ("cola", texto_boton_cola(en_cola)),
            ("copiar", "Copiar"), ("papelera", "Papelera"))


def insignias(info):
    """Etiquetas de estado: SONANDO (o PAUSADA si la canción actual está parada) y el puesto en la cola."""
    salida = []
    if info.get("sonando"):
        salida.append("SONANDO")
    elif info.get("pausada"):
        salida.append("PAUSADA")
    if info.get("en_cola"):
        salida.append(f"COLA {info['en_cola']}")
    return salida


def estado_de(info):
    """Lo que puede cambiar en una tarjeta: su puesto en la cola, si suena y si está en pausa."""
    return (info.get("en_cola"), bool(info.get("sonando")), bool(info.get("pausada")))


def mezclar(desde, hasta, t):
    """Color intermedio entre dos colores «#rrggbb»; t va de 0 (desde) a 1 (hasta)."""
    a = [int(desde[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(hasta[i:i + 2], 16) for i in (1, 3, 5)]
    t = min(1.0, max(0.0, t))
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def _texto_insignia(info):
    return "  ".join(insignias(info))


def crear(tk, padre, entrada, info, tema, fuente, acciones, seleccionada=False):
    """Construye la tarjeta de una entrada. Guarda sus partes para actualizarla sin volver a crearla."""
    fondo, verde, verde_oscuro, gris = tema["FONDO"], tema["VERDE"], tema["VERDE_OSCURO"], tema["GRIS"]
    ambar = tema.get("AMBAR", verde)
    chica = (fuente[0], max(7, fuente[1] - 1))
    negrita = (fuente[0], fuente[1], "bold")
    marco = tk.Frame(padre, bg=fondo, highlightthickness=1,
                     highlightbackground=verde if seleccionada else verde_oscuro)
    cabecera = tk.Frame(marco, bg=fondo)
    cabecera.pack(fill="x", padx=5, pady=(3, 0))
    titulo = tk.Label(cabecera, text=entrada["nombre"], font=negrita, bg=fondo, fg=verde, anchor="w")
    titulo.pack(side="left", fill="x", expand=True)
    insignia = tk.Label(cabecera, text=_texto_insignia(info), font=chica, bg=fondo, fg=ambar, anchor="e")
    insignia.pack(side="right")
    detalle = tk.Label(marco, text=info.get("texto", ""), font=chica, bg=fondo, fg=gris, anchor="w")
    detalle.pack(fill="x", padx=5)
    fila = tk.Frame(marco, bg=fondo)
    fila.pack(fill="x", padx=3, pady=(1, 3))
    partes = {"insignia": insignia, "detalle": detalle}
    mostrado = {"insignia": _texto_insignia(info), "detalle": info.get("texto", "")}
    for clave, texto in botones_de(entrada, info.get("en_cola")):
        # highlightthickness=0: el borde por defecto de Tk en Windows parpadea en blanco al aparecer.
        boton = tk.Button(fila, text=texto, font=chica, bg=verde_oscuro, fg=verde, activebackground=verde,
                          activeforeground=fondo, relief="flat", bd=0, padx=4, cursor="hand2",
                          highlightthickness=0, highlightbackground=fondo,
                          command=lambda c=clave: acciones[c](entrada))
        boton.pack(side="left", padx=(0, 2))
        boton.bind("<Button-3>", lambda ev: acciones["menu"](ev, entrada))
        if clave == "cola":
            partes["cola"] = boton
            mostrado["cola"] = texto
    # Clic = seleccionar, doble clic = reproducir o abrir, clic derecho = menú (igual que en el explorador).
    for widget in (marco, cabecera, titulo, detalle, fila):
        widget.bind("<Button-1>", lambda ev: acciones["seleccionar"](ev, entrada))
        widget.bind("<Double-1>", lambda ev: acciones["doble"](entrada))
        widget.bind("<Button-3>", lambda ev: acciones["menu"](ev, entrada))
        widget.bind("<MouseWheel>", acciones["rueda"])
    marco.partes = partes
    marco.mostrado = mostrado
    marco.colores = (verde, verde_oscuro)
    marco.estado = estado_de(info)
    return marco


def actualizar(marco, info, seleccionada=None):
    """Pone al día lo que cambia (detalle, insignias, botón de cola y borde de selección) sin recrear la tarjeta.
    Solo se toca lo que de verdad cambió. Devuelve True si cambió el puesto en la cola (para la transición)."""
    partes = getattr(marco, "partes", None) or {}
    previo = getattr(marco, "estado", None)
    nuevo = estado_de(info)
    marco.estado = nuevo
    mostrado = getattr(marco, "mostrado", None) or {}
    textos = {"detalle": info.get("texto", ""), "insignia": _texto_insignia(info)}
    if "cola" in partes:
        textos["cola"] = texto_boton_cola(info.get("en_cola"))
    for clave, texto in textos.items():
        if clave in partes and mostrado.get(clave) != texto:
            partes[clave].configure(text=texto)
            mostrado[clave] = texto
    marco.mostrado = mostrado
    colores = getattr(marco, "colores", None)
    if seleccionada is not None and colores is not None:
        verde, verde_oscuro = colores
        marco.configure(highlightbackground=verde if seleccionada else verde_oscuro)
    return previo is not None and previo[0] != nuevo[0]
