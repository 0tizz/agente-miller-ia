"""Acciones de la Biblioteca musical del explorador: reproducir y cola, y la papelera del supervisor.

Usan los mismos métodos que la voz:
- reproducir  -> reproductor.reproducir
- cola        -> agregar_archivo_a_cola / eliminar_de_cola
- papelera    -> comandos.enviar_a_papelera (el supervisor la lleva a la papelera, recuperable)
Los textos se devuelven para que la ventana los escriba en la terminal. Las lecturas de cola y de canción
actual no toman el candado del reproductor.
"""
import os
import threading
from pathlib import Path


def _clave(ruta):
    return os.path.normcase(os.path.abspath(str(ruta)))


def _mover_en(estado, origen, destino):
    """Estado previsto al mover una canción de un puesto a otro (1 = la siguiente)."""
    cola = estado["cola"]
    if 1 <= origen <= len(cola) and 1 <= destino <= len(cola):
        cola.insert(destino - 1, cola.pop(origen - 1))
    return estado


def _quitar_en(estado, posicion):
    cola = estado["cola"]
    if 1 <= posicion <= len(cola):
        cola.pop(posicion - 1)
    return estado


def _reproducir_en(estado, posicion):
    cola = estado["cola"]
    if 1 <= posicion <= len(cola):
        ruta = cola.pop(posicion - 1)
        return dict(estado, actual=ruta, suena=True, pausada=False)
    return estado


def _siguiente_en(estado):
    """Como el reproductor: la cola va primero; si está vacía, la siguiente sale de la biblioteca (no se prevé)."""
    cola = estado["cola"]
    if cola:
        return dict(estado, cola=cola[1:], actual=cola[0], suena=True, pausada=False)
    return estado


def _alternar_en(estado, ruta):
    """Como texto_cola: si la canción está en la cola la quita; si no, la pone al final."""
    cola, clave = estado["cola"], _clave(ruta)
    indice = next((i for i, p in enumerate(cola) if _clave(p) == clave), None)
    if indice is None:
        cola.append(str(ruta))
    else:
        cola.pop(indice)
    return estado


class AccionesAudio:
    def __init__(self, comandos, informar=None, aprender=None, cambio=None, prever=None):
        self.comandos = comandos
        self.reproductor = getattr(comandos, "reproductor", None)
        self.aprender = aprender if callable(aprender) else (lambda tipo: None)   # evento del entorno
        self.cambio = cambio if callable(cambio) else (lambda: None)   # avisa a la ventana: la cola cambió
        self.informar = informar                 # recibe el texto de la respuesta (puede llamarse desde otro hilo)
        self.prever = prever if callable(prever) else (lambda: None)   # repinta ya lo que la orden va a cambiar
        self._cerrojo = threading.Lock()         # protege _pred y _pendientes (hilo de Tk y hilos de órdenes)
        self._pred = None                        # estado previsto mientras hay órdenes en curso
        self._pendientes = 0

    # ------------------------------------------------------------ lectura de estado
    def cola(self):
        return list(getattr(self.reproductor, "cola", []) or [])

    def posicion_en_cola(self, ruta):
        """Puesto (1 = primero) de la canción en la cola, o None si no está."""
        destino = _clave(ruta)
        for i, p in enumerate(self.cola(), start=1):
            if _clave(p) == destino:
                return i
        return None

    def reproduciendo_ahora(self):
        """Ruta de la canción que suena de verdad, o None. cancion_actual no se borra al parar ni al terminar,
        así que además se mira si está sonando y no en pausa."""
        rep = self.reproductor
        actual = getattr(rep, "cancion_actual", None)
        if actual is None or not getattr(rep, "reproduciendo", False) or getattr(rep, "pausado", False):
            return None
        return actual

    def sonando(self, ruta):
        actual = self.reproduciendo_ahora()
        return actual is not None and _clave(actual) == _clave(ruta)

    def pausada(self, ruta):
        """True si es la canción actual y está en pausa."""
        rep = self.reproductor
        actual = getattr(rep, "cancion_actual", None)
        return bool(actual is not None and getattr(rep, "reproduciendo", False)
                    and getattr(rep, "pausado", False) and _clave(actual) == _clave(ruta))

    def estado_real(self):
        """Cola y reproducción tal como están ahora, en una sola lectura."""
        rep = self.reproductor
        actual = getattr(rep, "cancion_actual", None)
        activa = actual is not None and bool(getattr(rep, "reproduciendo", False))
        pausa = bool(getattr(rep, "pausado", False))
        return {"cola": [str(p) for p in self.cola()], "actual": str(actual) if actual is not None else None,
                "suena": activa and not pausa, "pausada": activa and pausa}

    def estado_visible(self):
        """Lo que la ventana debe mostrar: lo previsto mientras una orden está en curso, si no lo real."""
        with self._cerrojo:
            pred = self._pred
        return pred if pred is not None else self.estado_real()

    def foto_de(self, estado):
        """Índice de puestos y estados para pintar muchas tarjetas de golpe, sin recorrer la cola por cada una."""
        puestos = {}
        for i, p in enumerate(estado["cola"], start=1):
            puestos.setdefault(_clave(p), i)
        actual = estado["actual"]
        return {"puestos": puestos, "actual": _clave(actual) if actual else None,
                "suena": estado["suena"], "pausada": estado["pausada"],
                "nombre": Path(actual).name if actual and (estado["suena"] or estado["pausada"]) else ""}

    def instantanea(self):
        return self.foto_de(self.estado_visible())

    def info_de(self, ruta, foto=None):
        """Puesto en la cola, si suena y si está en pausa, para una tarjeta."""
        foto = foto if foto is not None else self.instantanea()
        clave = _clave(ruta)
        es_actual = foto["actual"] == clave
        return {"en_cola": foto["puestos"].get(clave), "sonando": foto["suena"] and es_actual,
                "pausada": foto["pausada"] and es_actual}

    def firma(self):
        """Cambia cuando cambia lo que suena (canción, reproducir, pausa, parar) o la cola; sirve para repintar."""
        rep = self.reproductor
        actual = getattr(rep, "cancion_actual", None)
        return (str(actual) if actual else "", bool(getattr(rep, "reproduciendo", False)),
                bool(getattr(rep, "pausado", False)), tuple(str(p) for p in self.cola()))

    # ------------------------------------------------------------ textos de cada acción (sin hilos)
    def texto_reproducir(self, ruta):
        nombre = Path(ruta).name
        if self.reproductor is None:
            return "Negativo. El reproductor no está disponible, señor."
        if self.reproductor.reproducir(nombre):
            self.aprender("cancion_sonando")
            return f"Afirmativo. Reproduciendo {nombre}, señor."
        return f"Negativo. No pude reproducir {nombre}, señor."

    def texto_cola(self, ruta):
        nombre = Path(ruta).name
        if self.reproductor is None:
            return "Negativo. El reproductor no está disponible, señor."
        pos = self.posicion_en_cola(ruta)
        if pos is None:
            if self.reproductor.agregar_archivo_a_cola(Path(ruta)):
                self.aprender("cancion_cola")
                return f"Afirmativo. {nombre} en la cola, señor."
            return f"Negativo. No pude poner {nombre} en la cola, señor."
        if self.reproductor.eliminar_de_cola(pos):
            return f"Afirmativo. {nombre} quitada de la cola, señor."
        return f"Negativo. No pude quitar {nombre} de la cola, señor."

    def texto_papelera(self, ruta):
        if self.comandos is None:
            return "Negativo. Sin el supervisor de MILLER no puedo mover la canción a la papelera, señor."
        texto = self.comandos.enviar_a_papelera(Path(ruta))
        if str(texto).startswith("Afirmativo"):
            self.aprender("cancion_papelera")
        return texto

    # ------------------------------------------------------------ la cola (vista COLA de ENTORNO)
    def _nombre_en_cola(self, posicion):
        cola = self.cola()
        if 1 <= posicion <= len(cola):
            return cola[posicion - 1].name
        return None

    def texto_mover_cola(self, posicion, destino):
        if self.reproductor is None:
            return "Negativo. El reproductor no está disponible, señor."
        nombre = self._nombre_en_cola(posicion)
        if nombre is None:
            return "Negativo. Esa canción ya no está en la cola, señor."
        total = len(self.cola())
        if not 1 <= destino <= total:
            return ("Negativo. Ya está en el último puesto de la cola, señor." if destino > total
                    else "Negativo. Ya está en el primer puesto de la cola, señor.")
        if self.reproductor.mover_en_cola(posicion, destino):
            return f"Afirmativo. {nombre} pasa al puesto {destino} de la cola, señor."
        return f"Negativo. No pude mover {nombre} en la cola, señor."

    def texto_quitar_de_cola(self, posicion):
        if self.reproductor is None:
            return "Negativo. El reproductor no está disponible, señor."
        nombre = self._nombre_en_cola(posicion)
        if nombre is None:
            return "Negativo. Esa canción ya no está en la cola, señor."
        if self.reproductor.eliminar_de_cola(posicion):
            return f"Afirmativo. {nombre} quitada de la cola, señor."
        return f"Negativo. No pude quitar {nombre} de la cola, señor."

    def texto_reproducir_de_cola(self, posicion):
        if self.reproductor is None:
            return "Negativo. El reproductor no está disponible, señor."
        nombre = self._nombre_en_cola(posicion)
        if nombre is None:
            return "Negativo. Esa canción ya no está en la cola, señor."
        if not self.reproductor.reproducir(nombre):
            return f"Negativo. No pude reproducir {nombre}, señor."
        self.reproductor.eliminar_de_cola(posicion)      # ya suena: sale de su puesto
        return f"Afirmativo. Reproduciendo {nombre} ahora, señor."

    def texto_vaciar_cola(self):
        if self.reproductor is None:
            return "Negativo. El reproductor no está disponible, señor."
        if not self.cola():
            return "Negativo. La cola ya está vacía, señor."
        if self.reproductor.limpiar_cola():
            return "Afirmativo. Cola vaciada, señor."
        return "Negativo. No pude vaciar la cola, señor."

    def subir_cola(self, posicion):
        self._en_hilo(lambda: self.texto_mover_cola(posicion, posicion - 1),
                      previsto=lambda e: _mover_en(e, posicion, posicion - 1))

    def bajar_cola(self, posicion):
        self._en_hilo(lambda: self.texto_mover_cola(posicion, posicion + 1),
                      previsto=lambda e: _mover_en(e, posicion, posicion + 1))

    def quitar_de_cola(self, posicion):
        self._en_hilo(lambda: self.texto_quitar_de_cola(posicion),
                      previsto=lambda e: _quitar_en(e, posicion))

    def reproducir_de_cola(self, posicion):
        self._en_hilo(lambda: self.texto_reproducir_de_cola(posicion),
                      previsto=lambda e: _reproducir_en(e, posicion))

    def vaciar_cola(self):
        self._en_hilo(self.texto_vaciar_cola, previsto=lambda e: dict(e, cola=[]))

    # ------------------------------------------------------------ botones (no bloquean la ventana)
    def reproducir(self, ruta):
        self._en_hilo(lambda: self.texto_reproducir(ruta),
                      previsto=lambda e: dict(e, actual=str(ruta), suena=True, pausada=False))

    def controlar(self, clave):
        """Controles de la barra: pausa, siguiente, anterior y parar. Se llama desde la ventana (hilo de Tk), así que
        la vista se anticipa en el mismo clic; lo real llega al terminar la orden."""
        estado = self.estado_visible()
        if clave == "pausa":
            if estado["pausada"]:
                return self._en_hilo(lambda: self.comandos.ejecutar("CONTINUAR_AUDIO"),
                                     previsto=lambda e: dict(e, suena=True, pausada=False))
            if estado["suena"]:
                return self._en_hilo(lambda: self.comandos.ejecutar("PAUSAR_AUDIO"),
                                     previsto=lambda e: dict(e, suena=False, pausada=True))
            return self._en_hilo(lambda: self.comandos.ejecutar("REPRODUCIR_MUSICA"))
        if clave == "siguiente":
            return self._en_hilo(lambda: self.comandos.ejecutar("SIGUIENTE_AUDIO"), previsto=_siguiente_en)
        if clave == "anterior":
            return self._en_hilo(lambda: self.comandos.ejecutar("ANTERIOR_AUDIO"))
        if clave == "detener":
            return self._en_hilo(lambda: self.comandos.ejecutar("DETENER_AUDIO"),
                                 previsto=lambda e: dict(e, suena=False, pausada=False))

    def alternar_cola(self, ruta):
        self._en_hilo(lambda: self.texto_cola(ruta), previsto=lambda e: _alternar_en(e, ruta))

    def informar_texto(self, texto):
        if texto and self.informar is not None:
            self.informar(str(texto))

    def _anticipar(self, transformar):
        """Aplica ya a la vista lo que la orden va a hacer, sin esperar al disco, y avisa para repintar."""
        with self._cerrojo:
            base = self._pred if self._pred is not None else self.estado_real()
            self._pred = transformar(dict(base, cola=list(base["cola"])))
            self._pendientes += 1
        try:
            self.prever()
        except Exception:
            pass

    def _en_hilo(self, funcion, previsto=None):
        anticipado = previsto is not None
        if anticipado:
            self._anticipar(previsto)

        def trabajo():
            try:
                texto = funcion()
            except Exception as error:
                texto = f"Negativo. No pude completar la orden: {error}"
            self.informar_texto(texto)
            self._terminar(anticipado)
        threading.Thread(target=trabajo, daemon=True).start()

    def _terminar(self, anticipado):
        """La orden acabó (en su hilo). Cuando no queda ninguna anticipada, la vista vuelve a lo real."""
        if anticipado:
            with self._cerrojo:
                self._pendientes = max(0, self._pendientes - 1)
                if self._pendientes == 0:
                    self._pred = None
        try:
            self.cambio()
        except Exception:
            pass
