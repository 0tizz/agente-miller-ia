"""MILLER · El orbe aprende de su entorno.

Percibe: la página abierta, si alguien toca la ventana, si suena música, la hora, dónde lo deja el usuario
y los eventos del entorno (carpetas que abre, canciones que pone o manda a la papelera, archivos que copia,
mueve, borra o renombra).
Aprende (solo números y posiciones relativas de la ventana, nada personal): qué páginas abre más, a qué horas
está activo, cuánto tiempo suena música y en qué punto de la ventana prefiere quedarse.
Se guarda firmado en datos/orbe.json. Sin ese archivo el orbe funciona igual, solo que no recuerda.
"""
import threading
import time
from pathlib import Path

import configuracion
from utilidades import seguridad

RUTA = Path(configuracion.RUTA_DATOS) / "orbe.json"
PAGINAS = ("terminal", "instalacion", "llaves", "explorador")
EVENTOS = ("carpeta", "cancion_sonando", "cancion_cola", "cancion_papelera", "archivo_copiado",
           "archivo_movido", "archivo_borrado", "archivo_renombrado")
INACTIVO_S = 60.0              # sin tocar la ventana durante este tiempo, el orbe se duerme
PAUSA_GUARDADO_S = 300.0       # como mucho un guardado cada cinco minutos
REPOSO_INICIAL = (0.5, 0.85)   # abajo, en el centro, hasta que el usuario lo deje en otro sitio


def _numero(valor, defecto=0.0):
    try:
        n = float(valor)
    except (TypeError, ValueError):
        return defecto
    return n if n == n and abs(n) != float("inf") else defecto      # descarta NaN e infinitos


def _unitario(valor):
    return min(1.0, max(0.0, _numero(valor, 0.5)))


class EntornoOrbe:
    def __init__(self, ruta=RUTA):
        self.ruta = Path(ruta)
        datos = seguridad.leer_json(self.ruta, {})
        if not isinstance(datos, dict):
            datos = {}
        paginas = datos.get("paginas") if isinstance(datos.get("paginas"), dict) else {}
        self.paginas = {p: max(0, int(_numero(paginas.get(p)))) for p in PAGINAS}
        horas = datos.get("horas") if isinstance(datos.get("horas"), list) else []
        self.horas = [max(0.0, _numero(horas[i])) if i < len(horas) else 0.0 for i in range(24)]
        reposo = datos.get("reposo")
        if isinstance(reposo, list) and len(reposo) == 2:
            self.reposo = [_unitario(reposo[0]), _unitario(reposo[1])]
        else:
            self.reposo = list(REPOSO_INICIAL)
        self.segundos_activo = max(0.0, _numero(datos.get("segundos_activo")))
        self.segundos_musica = max(0.0, _numero(datos.get("segundos_musica")))
        eventos = datos.get("eventos") if isinstance(datos.get("eventos"), dict) else {}
        self.eventos = {e: max(0, int(_numero(eventos.get(e)))) for e in EVENTOS}
        self._cerrojo = threading.Lock()                 # los eventos llegan desde hilos de la biblioteca
        self.cambios = 0
        self._ultimo_guardado = time.monotonic()

    # ------------------------------------------------------------ lo que percibe
    def registrar_pagina(self, pagina):
        if pagina in self.paginas:
            self.paginas[pagina] += 1
            self.cambios += 1

    def registrar_tiempo(self, segundos, activo, musica, hora):
        """Suma el tiempo transcurrido: activo (alguien toca la ventana), música sonando y la hora."""
        if segundos <= 0:
            return
        self.cambios += 1
        if activo:
            self.segundos_activo += segundos
            self.horas[int(hora) % 24] += segundos / 60.0
        if musica:
            self.segundos_musica += segundos

    def registrar_reposo(self, fraccion_x, fraccion_y):
        """Dónde deja el usuario el orbe (fracciones 0..1 de la zona)."""
        self.reposo = [_unitario(fraccion_x), _unitario(fraccion_y)]
        self.cambios += 1

    def registrar_evento(self, tipo):
        """Un evento del entorno (carpeta abierta, canción puesta en la cola, archivo borrado...)."""
        if tipo not in self.eventos:
            return
        with self._cerrojo:
            self.eventos[tipo] += 1
            self.cambios += 1

    def evento_frecuente(self):
        """El evento que MILLER más ha visto, o None si aún no ha visto ninguno."""
        with self._cerrojo:
            tipo, veces = max(self.eventos.items(), key=lambda par: par[1])
        return tipo if veces > 0 else None

    def estado(self, inactivo_s, musica):
        if musica:
            return "contento"
        if inactivo_s > INACTIVO_S:
            return "dormido"
        return "atento"

    # ------------------------------------------------------------ lo que aprendió
    def pagina_favorita(self):
        if sum(self.paginas.values()) <= 0:
            return None
        return max(PAGINAS, key=lambda p: self.paginas[p])

    def hora_habitual(self):
        if sum(self.horas) <= 0:
            return None
        return max(range(24), key=lambda h: self.horas[h])

    def posicion_de_reposo(self, ancho, alto, lado):
        """Punto (x, y) en píxeles donde el orbe prefiere quedarse, dentro de la zona."""
        return (self.reposo[0] * max(ancho - lado, 0), self.reposo[1] * max(alto - lado, 0))

    # ------------------------------------------------------------ guardado
    def guardar(self, forzar=False):
        ahora = time.monotonic()
        if not forzar and (self.cambios == 0 or ahora - self._ultimo_guardado < PAUSA_GUARDADO_S):
            return False
        try:
            seguridad.escribir_json(self.ruta, {
                "paginas": self.paginas,
                "horas": [round(h, 2) for h in self.horas],
                "reposo": [round(r, 4) for r in self.reposo],
                "segundos_activo": round(self.segundos_activo, 1),
                "segundos_musica": round(self.segundos_musica, 1),
                "eventos": dict(self.eventos),
            }, indent=2)
        except OSError:
            return False
        self.cambios = 0
        self._ultimo_guardado = ahora
        return True
