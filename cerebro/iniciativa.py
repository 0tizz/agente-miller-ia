"""MILLER · INICIATIVA: hablar por cuenta propia, siempre con permiso."""
import json
import os
import random
from utilidades.reloj import hora_12_de
import re
import threading
import time
import unicodedata
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from utilidades import seguridad

ALTA, MEDIA, BAJA = 3, 2, 1


def _normalizar(texto):
    texto = unicodedata.normalize("NFD", str(texto or "").lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9ñ ]+", " ", texto)).strip()


def _sin_extension(nombre):
    return re.sub(r"\.[A-Za-z0-9]{2,5}$", "", str(nombre or ""))


class Iniciativa:
    # Palabras de autorización / negación (la frase completa, sin "miller" ni "señor").
    _RE_AUTORIZA = re.compile(
        r"(?:si |claro |bien |ok |vale )?(?:adelante|diga|digame|dime|siga|sigue|hable|habla|hablame|"
        r"proceda|procede|continue|continua|te escucho|lo escucho|le escucho|escucho|autorizado|autorizo|"
        r"permiso concedido|concedido|tiene permiso|tienes permiso|cuentame|cuenteme|a ver|que pasa|"
        r"que sucede|que ocurre|que hay|informe|reporte|si)(?: por favor)?")
    _RE_DENIEGA = re.compile(
        r"(?:no|ahora no|ahora mismo no|despues|luego|mas tarde|en otro momento|negativo|denegado|"
        r"permiso denegado|no gracias|espera|espere|silencio|callate|calla|no es momento|"
        r"no me interrumpas|ahora no puedo)(?: por favor)?")
    _RE_RELLENO = re.compile(r"\b(miller|senor|señor|por favor|oye|bueno|pues)\b")
    FRASES_PERMISO = ("Permiso para hablar, señor.",)
    ESPERA_RESPUESTA_PREGUNTA = 90.0
    APERTURAS = ("Señor, ", "Informo, señor: ", "Novedad, señor: ", "Reporte: ")

    def __init__(self, cerebro, ruta_estado=None, activa=True, intervalo_minimo=900.0,
                 intervalo_urgente=60.0, silencio_previo=20.0, espera_autorizacion=25.0,
                 intervalo_observacion=120.0, max_peticiones_hora=4, frases_permiso=None):
        self.cerebro = cerebro
        self.activa = bool(activa)
        self.intervalo_minimo = float(intervalo_minimo)          # entre peticiones por asuntos normales
        self.intervalo_urgente = float(intervalo_urgente)        # entre peticiones por asuntos importantes
        self.silencio_previo = float(silencio_previo)            # s sin órdenes ni voz antes de pedir permiso
        self.espera_autorizacion = float(espera_autorizacion)    # s esperando "adelante"
        self.intervalo_observacion = float(intervalo_observacion)
        self.max_peticiones_hora = int(max_peticiones_hora)
        if frases_permiso:
            self.FRASES_PERMISO = tuple(frases_permiso)
        self.ruta_estado = Path(ruta_estado) if ruta_estado else None
        self._lock = threading.RLock()
        self._pendientes = []               # [{clave, texto, prioridad, creado}]
        self._ocupado = 0                   # órdenes en ejecución (contador anidable)
        self._esperando_desde = None        # instante en que se pidió permiso
        self._ultima_actividad = time.monotonic()
        self._ultima_peticion = 0.0
        self._peticiones = []               # instantes de peticiones (límite por hora)
        self._ultima_descarga_vista = None
        self._estado = self._cargar_estado()
        self._linea_base_hecha = False
        self._stop = threading.Event()
        self._hilo = None

    @property
    def emociones(self):
        """Estado emocional de MILLER (cerebro/emociones.py), si está disponible."""
        return getattr(self.cerebro, "emociones", None)

    def _sentir(self, tipo, detalle=""):
        emociones = self.emociones
        if emociones is not None:
            try:
                emociones.registrar_evento(tipo, detalle)
            except Exception as error:
                print(f"[INICIATIVA] Emociones: {error}")

    def _factor_emocional(self):
        emociones = self.emociones
        try:
            return float(emociones.factor_iniciativa()) if emociones is not None else 1.0
        except Exception:
            return 1.0

    def _factor_vinculo(self):
        """Con el vínculo bajo y ganas de compartir, pide la palabra antes (nunca sin permiso)."""
        necesidades = getattr(self.cerebro, "necesidades", None)
        try:
            return float(necesidades.factor_iniciativa()) if necesidades is not None else 1.0
        except Exception:
            return 1.0

    def _cargar_estado(self):
        estado = {"dichos": {}, "cuarentena_vista": [], "pruebas_vistas": {}}
        if self.ruta_estado and self.ruta_estado.is_file():
            try:
                leido = seguridad.leer_json(self.ruta_estado, {}) or {}
                for clave, valor in estado.items():
                    if isinstance(leido.get(clave), type(valor)):
                        estado[clave] = leido[clave]
            except Exception as error:
                print(f"[INICIATIVA] Estado ilegible, se empieza de cero: {error}")
        return estado

    def _guardar_estado(self):
        if not self.ruta_estado:
            return
        try:
            with self._lock:
                dichos = sorted(self._estado["dichos"].items(), key=lambda x: x[1])[-300:]
                self._estado["dichos"] = dict(dichos)
                self._estado["cuarentena_vista"] = self._estado["cuarentena_vista"][-500:]
                datos = json.loads(json.dumps(self._estado))
            seguridad.escribir_json(self.ruta_estado, datos)
        except Exception as error:
            print(f"[INICIATIVA] No se pudo guardar el estado: {error}")

    def iniciar(self):
        if self._hilo and self._hilo.is_alive():
            return True
        self._stop.clear()
        self._hilo = threading.Thread(target=self._bucle, daemon=True, name="MILLER-Iniciativa")
        self._hilo.start()
        return True

    def detener(self):
        self._stop.set()
        hilo, self._hilo = self._hilo, None
        if hilo is not None and hilo.is_alive() and hilo is not threading.current_thread():
            hilo.join(timeout=3.0)
        self._guardar_estado()

    def _bucle(self):
        if self._stop.wait(5.0):
            return
        while not self._stop.is_set():
            try:
                self.observar()
            except Exception as error:
                print(f"[INICIATIVA] Error observando: {error}")
            self._stop.wait(self.intervalo_observacion)

    @contextmanager
    def ocupado(self):
        """Envuelve la ejecución de una orden: mientras dure, MILLER no pide permiso."""
        with self._lock:
            self._ocupado += 1
        try:
            yield
        finally:
            with self._lock:
                self._ocupado = max(0, self._ocupado - 1)
                self._ultima_actividad = time.monotonic()

    def marcar_actividad(self):
        """Se ha oído hablar a alguien (aunque no fuera a MILLER): no interrumpir."""
        with self._lock:
            self._ultima_actividad = time.monotonic()

    def tareas_en_curso(self):
        """Órdenes que siguen en marcha o esperando respuesta del usuario."""
        tareas = []
        c = self.cerebro
        comandos = getattr(c, "comandos", None)
        try:
            if comandos is not None and callable(getattr(comandos, "tareas_en_curso", None)):
                tareas.extend(comandos.tareas_en_curso())
        except Exception:
            pass
        if getattr(c, "rutina_matutina_activa", False):
            tareas.append("rutina")
        # Una pregunta de MILLER sin contestar ("¿qué canción reproduzco?") cuenta como orden
        reciente = time.monotonic() - self._ultima_actividad < self.ESPERA_RESPUESTA_PREGUNTA
        if reciente and any(getattr(c, a, None) for a in ("cancion_pendiente", "cola_pendiente",
                                                         "volumen_pendiente", "tema_memoria_pendiente")):
            tareas.append("pregunta")
        return tareas

    _RE_MALO = re.compile(r"\b(fall\w*|dañad\w*|danad\w*|elimin\w*|error\w*|cuarentena|no (?:comprendo|entiendo|logro)|"
                          r"preocup\w*|problema\w*|perdid\w*|sin conexi\w*|incidencia\w*|no qued\w*|incorrect\w*)", re.I)
    _RE_BUENO = re.compile(r"\b(complet\w*|lista|listo|aprend\w*|recomiendo|sin fallos|en verde|reparad\w*|"
                           r"exito\w*|éxito\w*|correct\w*)", re.I)

    @classmethod
    def clasificar_tono(cls, texto):
        """'malo', 'bueno' o 'neutro' según el contenido, para que el tono sea congruente."""
        if cls._RE_MALO.search(texto or ""):
            return "malo"
        return "bueno" if cls._RE_BUENO.search(texto or "") else "neutro"

    def agregar(self, clave, texto, prioridad=MEDIA, una_vez=True, tono=None, adjunto=None):
        """Añade algo que MILLER quiere decir. una_vez: no se repite nunca (clave guardada).
        adjunto: texto que se escribe en la TERMINAL junto con la frase, en el momento en que MILLER la dice."""
        texto = str(texto or "").strip()
        tono = tono or self.clasificar_tono(texto)
        if not texto:
            return False
        with self._lock:
            if una_vez and clave in self._estado["dichos"]:
                return False
            if any(p["clave"] == clave for p in self._pendientes):
                return False
            self._pendientes.append({"clave": clave, "texto": texto, "prioridad": int(prioridad),
                                     "creado": time.time(), "una_vez": una_vez, "tono": tono,
                                     "adjunto": adjunto})
            self._pendientes.sort(key=lambda p: (-p["prioridad"], p["creado"]))
            del self._pendientes[12:]
        return True

    def pendientes(self):
        with self._lock:
            return [dict(p) for p in self._pendientes]

    def nombre_aprendido(self, variante):
        """Callback del activador."""
        self._sentir("nombre_aprendido", variante)
        self.agregar(f"nombre:{variante}", f"aprendí a reconocer «{variante}» como mi nombre.", MEDIA, tono="bueno")

    def esta_esperando(self):
        with self._lock:
            if self._esperando_desde is None:
                return False
            if time.monotonic() - self._esperando_desde > self.espera_autorizacion:
                self._esperando_desde = None          # sin respuesta: se guarda para más tarde
                return False
            return True

    def debe_pedir_permiso(self):
        if not self.activa:
            return False
        with self._lock:
            if self._ocupado or not self._pendientes or self._esperando_desde is not None:
                return False
            ahora = time.monotonic()
            if ahora - self._ultima_actividad < self.silencio_previo:
                return False
            urgente = self._pendientes[0]["prioridad"] >= ALTA
            # Las emociones y la personalidad dan más o menos ganas de hablar (nunca sin permiso).
            intervalo = self.intervalo_urgente if urgente else (self.intervalo_minimo * self._factor_emocional()
                                                                 * self._factor_vinculo())
            if ahora - self._ultima_peticion < intervalo:
                return False
            self._peticiones = [t for t in self._peticiones if ahora - t < 3600]
            if not urgente and len(self._peticiones) >= self.max_peticiones_hora:
                return False
        return not self.tareas_en_curso()

    def pedir_permiso(self):
        with self._lock:
            ahora = time.monotonic()
            self._esperando_desde = ahora
            self._ultima_peticion = ahora
            self._peticiones.append(ahora)
        return random.choice(self.FRASES_PERMISO)

    def interpretar(self, texto):
        """'autoriza', 'deniega' o None (no es una respuesta al permiso)."""
        t = self._RE_RELLENO.sub(" ", _normalizar(texto))
        t = re.sub(r"\s+", " ", t).strip()
        if not t:
            return None
        if self._RE_DENIEGA.fullmatch(t):
            return "deniega"
        if self._RE_AUTORIZA.fullmatch(t):
            return "autoriza"
        return None

    def retirar_peticion(self):
        """Llegó otra orden: la orden manda y el asunto queda para más tarde."""
        with self._lock:
            self._esperando_desde = None

    def posponer(self):
        with self._lock:
            self._esperando_desde = None
            self._ultima_peticion = time.monotonic()
        self._sentir("permiso_denegado")
        return random.choice(("Entendido, señor. Queda para más tarde.", "Recibido. Lo informo después.",
                              "Afirmativo. En espera."))

    def _sacar(self):
        with self._lock:
            if not self._pendientes:
                return None
            asunto = self._pendientes.pop(0)
            if asunto.get("una_vez", True):
                self._estado["dichos"][asunto["clave"]] = datetime.now().isoformat(timespec="seconds")
        return asunto

    def _formular(self, texto, tono="neutro"):
        texto = texto.strip()
        if re.match(r"^(señor|senor)\b", texto, re.I):
            return texto[0].upper() + texto[1:]
        aperturas = {"malo": ("Atención, señor: ",), "bueno": ("Señor, ",)}.get(tono, self.APERTURAS)
        emociones = self.emociones
        if emociones is not None:
            try:
                aperturas = emociones.apertura(tono) or aperturas   # contenido + emoción, siempre congruentes
            except Exception:
                pass
        return random.choice(aperturas) + texto

    def entregar(self, maximo=1):
        """Dice el/los asunto(s) pendientes más importantes."""
        with self._lock:
            con_permiso = self._esperando_desde is not None
            self._esperando_desde = None
        if con_permiso:
            self._sentir("permiso_concedido")
        partes = []
        for _ in range(max(1, maximo)):
            asunto = self._sacar()
            if not asunto:
                break
            if asunto.get("adjunto"):
                self._adjunto_entregado = asunto["adjunto"]
            partes.append(self._formular(asunto["texto"], asunto.get("tono") or self.clasificar_tono(asunto["texto"]))
                          if not partes else asunto["texto"][0].upper() + asunto["texto"][1:])
        self._guardar_estado()
        if not partes:
            return "Sin novedades, señor."
        necesidades = getattr(self.cerebro, "necesidades", None)
        if necesidades is not None:                 # compartir con usted recarga el vínculo
            try:
                necesidades.compartio(len(partes))
            except Exception:
                pass
        restantes = len(self.pendientes())
        cierre = f" Hay {restantes} más." if restantes else " Fin del reporte."
        return " ".join(p if p.endswith((".", "?", "!")) else p + "." for p in partes) + cierre

    def adjunto_terminal(self):
        """Texto para la terminal que acompaña a lo último que MILLER dijo (la clave BOY). Se consume una vez."""
        with self._lock:
            texto = getattr(self, "_adjunto_entregado", None)
            self._adjunto_entregado = None
        return texto

    def entregar_novedades(self):
        """Orden directa: "Miller, novedades" / "¿tienes algo que decir?"."""
        try:
            self.observar()
        except Exception:
            pass
        return self.entregar(maximo=3)

    def observar(self):
        """Revisa todo lo que MILLER sabe y anota lo que merece la pena contar."""
        primera = not self._linea_base_hecha
        for fuente in (self._observar_supervisor, self._observar_descarga, self._observar_pruebas,
                       self._observar_aprendizaje, self._observar_emociones, self._observar_vinculo,
                       self._observar_conexiones, self._observar_disco):
            try:
                fuente(primera)
            except Exception as error:
                print(f"[INICIATIVA] Fuente {fuente.__name__} falló: {error}")
        self._linea_base_hecha = True

    def _comandos(self):
        return getattr(self.cerebro, "comandos", None)

    def _observar_supervisor(self, primera):
        supervisor = getattr(self._comandos(), "supervisor", None)
        if supervisor is None:
            return
        vistas = set(self._estado["cuarentena_vista"])
        nuevas = [e for e in supervisor.listar_cuarentena()
                  if e.get("id") not in vistas and e.get("categoria") != "papelera"]
        for e in supervisor.listar_cuarentena():
            if e.get("id") not in vistas:
                self._estado["cuarentena_vista"].append(e.get("id"))
        if nuevas and not primera:
            self._sentir("cuarentena", len(nuevas))
            nombres = [_sin_extension(e.get("nombre")) for e in nuevas]
            lista = ", ".join(nombres[:3]) + (f" y {len(nombres) - 3} más" if len(nombres) > 3 else "")
            self.agregar(f"cuarentena:{nuevas[-1].get('id')}",
                         f"{len(nuevas)} {'archivo dañado' if len(nuevas) == 1 else 'archivos dañados'} a cuarentena: {lista}.",
                         MEDIA, tono="malo")
        hoy = datetime.now().strftime("%Y-%m-%d")
        for p in supervisor.plan_eliminacion():
            dias = p.get("dias_restantes")
            if dias is not None and dias < 2:
                cuando = "hoy" if dias < 1 else "mañana"
                donde = "la papelera" if p.get("categoria") == "papelera" else "la cuarentena"
                if self.agregar(f"eliminacion:{p.get('id')}:{hoy}",
                             f"{_sin_extension(p.get('nombre'))} se elimina {cuando} de {donde}. "
                             f"Para conservarla: restaura {_sin_extension(p.get('nombre'))}.", MEDIA, tono="malo"):
                    self._sentir("eliminacion_cerca", p.get("nombre"))
                break

    def _observar_descarga(self, primera):
        r = getattr(self._comandos(), "_ultima_descarga", None)
        if not r or r is self._ultima_descarga_vista:
            return
        self._ultima_descarga_vista = r
        clave = f"descarga:{r.get('titulo') or r.get('mensaje')}:{int(time.time() // 60)}"
        self._sentir("descarga_ok" if r.get("exito") else "descarga_fallo", r.get("titulo", ""))
        if r.get("exito"):
            self.agregar(clave, f"descarga lista: {r.get('titulo')}.", ALTA, False, tono="bueno")
        else:
            self.agregar(clave, f"falló la descarga. {r.get('mensaje', '')}".strip(), ALTA, False, tono="malo")

    def _observar_pruebas(self, primera):
        probador = getattr(self._comandos(), "probador", None)
        if probador is None or probador.en_curso().get("activo"):
            return
        vistas = self._estado["pruebas_vistas"]
        fallidas, nuevas = [], 0
        for nombre, r in probador.resultados().items():
            fecha = r.get("fecha")
            if vistas.get(nombre) == fecha:
                continue
            vistas[nombre] = fecha
            nuevas += 0 if primera else 1
            if r.get("estado") not in ("ok", "omitida", "interactiva") and not primera:
                fallidas.append(probador.nombre_legible(nombre) if hasattr(probador, "nombre_legible") else nombre)
        if nuevas:
            self._sentir("pruebas_fallo" if fallidas else "pruebas_ok", ", ".join(fallidas))
        if fallidas:
            self.agregar(f"pruebas:{'-'.join(fallidas)}:{int(time.time() // 60)}",
                         f"{'falló la prueba' if len(fallidas) == 1 else f'fallaron {len(fallidas)} pruebas'}: "
                         f"{', '.join(fallidas[:4])}.", ALTA, False, tono="malo")

    def _observar_aprendizaje(self, primera):
        """Lo aprendido de la memoria y de los hábitos: como mucho una observación por día y tipo."""
        memoria = getattr(self.cerebro, "memoria", None)
        if memoria is None:
            return
        hoy = datetime.now().strftime("%Y-%m-%d")
        a = memoria._aprendizaje() if hasattr(memoria, "_aprendizaje") else {}
        top = lambda d: sorted(d.items(), key=lambda x: (-x[1], x[0]))[0] if d else None
        # 1. Órdenes que el usuario repite y MILLER no entiende: lo más útil de contar.
        no_entendida = top(a.get("no_entendidas", {}))
        if no_entendida and no_entendida[1] >= 3 and no_entendida[0] not in a.get("alias", {}):
            self.agregar(f"no_entendida:{no_entendida[0]}",
                         f"no entiendo «{no_entendida[0]}». Dígalo de otra forma justo después y lo aprenderé.",
                         MEDIA, tono="neutro")
        # 2. Música.
        musica = a.get("musica", {})
        favorita = top(musica.get("pedidas", {})) or top(musica.get("escuchadas", {}))
        rep = getattr(self._comandos(), "reproductor", None)
        sonando = False
        try:
            sonando = bool(rep and rep.esta_reproduciendo())
        except Exception:
            pass
        if favorita and favorita[1] >= 3 and not sonando:
            nombre = _sin_extension(favorita[0])
            self.agregar(f"favorita:{hoy}", f"su canción más pedida: {nombre}.", BAJA, tono="neutro")
        clave_rec = f"recomendacion:{hoy}"
        ya_decidida = clave_rec in self._estado["dichos"] or any(p["clave"] == clave_rec for p in self.pendientes())
        if rep is not None and not sonando and not ya_decidida:      # cálculo costoso: una vez al día
            try:
                recomendadas = rep.recomendar_canciones(limite=1)
                if recomendadas:
                    r = recomendadas[0]
                    nombre = _sin_extension(getattr(r, "name", None) or (r.get("nombre") if isinstance(r, dict) else r))
                    self.agregar(f"recomendacion:{hoy}", f"le recomiendo {nombre}.", BAJA, tono="bueno")
            except Exception:
                pass
        # 3. Hábitos.
        hora = top(a.get("horario", {}))
        if hora and sum(a.get("horario", {}).values()) >= 30:
            self.agregar(f"habito_hora:{hora[0]}", f"su hora de más actividad: las {hora_12_de(hora[0])}", BAJA, tono="neutro")
        volumen = (musica.get("volumen") or {}).get("promedio")
        if volumen is not None and (musica.get("volumen") or {}).get("muestras", 0) >= 5:
            self.agregar(f"volumen_preferido:{round(volumen / 10)}",
                         f"su volumen preferido: {round(volumen)} %.", BAJA, tono="neutro")
        # 3b. Rutinas: la misma orden a esta hora en 3 o más días; se ofrece (con permiso), nunca se ejecuta sola.
        try:
            rutinas = memoria.patrones_rutina() if hasattr(memoria, "patrones_rutina") else []
        except Exception:
            rutinas = []
        for r in rutinas[:1]:
            self.agregar(f"rutina:{r['intencion']}:{r['hora']}:{hoy}",
                         f"a esta hora suele pedirme «{r['frase']}». Si lo desea, dígalo y lo hago.", BAJA, tono="neutro")
        # 4. Recuerdos guardados.
        try:
            recuerdos = memoria.obtener_recuerdos() or []
        except Exception:
            recuerdos = []
        if recuerdos:
            elegido = random.Random(hoy).choice(recuerdos)
            contenido = str(elegido.get("contenido", "")).strip()
            if contenido:
                self.agregar(f"recuerdo:{hoy}", f"recuerdo que {contenido}.", BAJA, tono="neutro")

    def _observar_conexiones(self, primera):
        """Cuando la red de recuerdos crece de verdad (3 conexiones nuevas o más), lo cuenta una vez al día."""
        red = getattr(self.cerebro, "_conexiones", None)
        if red is None or not callable(red):
            return
        try:
            red = red()
            if red is None:
                return
            total = red.cantidad()
        except Exception:
            return
        anterior = self._estado.get("conexiones")
        if primera or anterior is None:
            self._estado["conexiones"] = total
            return
        nuevas = total - anterior
        if nuevas >= 3:
            hoy = datetime.now().strftime("%Y-%m-%d")
            self.agregar(f"conexiones:{hoy}",
                         f"he encontrado {nuevas} conexiones nuevas entre mis recuerdos; ya son {total}.",
                         BAJA, tono="neutro")
            self._estado["conexiones"] = total

    def _observar_disco(self, primera):
        """Avisa una vez cada vez que el disco cambia de nivel (poco espacio, crítico o recuperado)."""
        try:
            from utilidades import cuota
            estado = cuota.estado_disco()
        except Exception:
            return
        nivel = estado["nivel"]
        anterior = self._estado.get("disco")
        self._estado["disco"] = nivel
        if primera or anterior is None or nivel == anterior:
            return
        hoy = datetime.now().strftime("%Y-%m-%d")
        libre = estado["libre"] / (1024 ** 3)
        if nivel == "critica":
            self.agregar(f"disco:{hoy}:critica",
                         f"el disco casi no tiene espacio, quedan {libre:.1f} gigas; no descargo nada y reduzco mi memoria.",
                         ALTA, tono="neutro")
        elif nivel == "baja":
            self.agregar(f"disco:{hoy}:baja",
                         f"queda poco espacio en el disco, {libre:.1f} gigas; reviso mi memoria con cuidado.",
                         MEDIA, tono="neutro")
        elif anterior != "normal":
            self.agregar(f"disco:{hoy}:normal",
                         f"el disco vuelve a tener espacio libre, {libre:.1f} gigas.",
                         BAJA, tono="neutro")

    def _observar_vinculo(self, primera):
        """Si el orbe busca el vínculo y no tiene nada que contar, quiere compartir cómo está (con permiso)."""
        necesidades = getattr(self.cerebro, "necesidades", None)
        if necesidades is None or primera or self.pendientes():
            return
        try:
            if not necesidades.buscando_vinculo() or necesidades.niveles["vinculo"] >= 0.6:
                return
            hora = datetime.now().strftime("%Y-%m-%d-%H")
            texto = necesidades.describir()
            self.agregar(f"vinculo:{hora}", "quería compartir con usted cómo estoy. " + texto, BAJA, tono="neutro")
        except Exception:
            pass

    def _observar_emociones(self, primera):
        """Cuando una emoción es fuerte y tiene motivo, MILLER quiere expresarla (con permiso)."""
        emociones = self.emociones
        if emociones is None or primera:
            return
        deseo = emociones.algo_que_expresar()
        if deseo:
            clave, texto, prioridad = deseo
            self.agregar(clave, texto, prioridad)

    def conocimiento_general(self):
        """Miller, ¿qué sabes?": resumen de todo lo que conoce de sí mismo, del programa y del usuario."""
        partes = []
        c = self.cerebro
        comandos = self._comandos()
        rep = getattr(comandos, "reproductor", None)
        try:
            if rep is not None:
                partes.append(f"Biblioteca: {rep.cantidad_canciones()} canciones.")
        except Exception:
            pass
        supervisor = getattr(comandos, "supervisor", None)
        try:
            if supervisor is not None:
                entradas = supervisor.listar_cuarentena()
                papelera = sum(1 for e in entradas if e.get("categoria") == "papelera")
                if len(entradas) - papelera:
                    partes.append(f"Cuarentena: {len(entradas) - papelera}.")
                if papelera:
                    partes.append(f"Papelera: {papelera}.")
        except Exception:
            pass
        try:
            partes.append(f"Memoria: {c.memoria.cantidad_recuerdos()} recuerdos.")
        except Exception:
            pass
        activador = getattr(c, "activador", None)
        try:
            aprendidas = activador.variantes_aprendidas() if activador else []
            if aprendidas:
                partes.append(f"Reconozco mi nombre de {len(aprendidas)} formas aprendidas.")
        except Exception:
            pass
        try:
            resumen = c.memoria.resumen_aprendizaje(getattr(c, "INTENCIONES_BIBLIOTECA", None))
            if resumen and not resumen.startswith("Sin datos"):
                partes.append(resumen)
        except Exception:
            pass
        emociones = self.emociones
        if emociones is not None:
            try:
                partes.append(emociones.describir())
                partes.append(emociones.describir_personalidad())
            except Exception:
                pass
        n = len(self.pendientes())
        if n:
            partes.append(f"Tengo {n} {'asunto' if n == 1 else 'asuntos'} por informar.")
        return " ".join(partes) or "Sin datos todavía, señor."

    def estado(self):
        with self._lock:
            return {"activa": self.activa, "pendientes": len(self._pendientes), "ocupado": bool(self._ocupado),
                    "esperando": self._esperando_desde is not None}
