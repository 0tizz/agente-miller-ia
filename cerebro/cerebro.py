"""MILLER · Cerebro principal | el cerebro decide. los módulos ejecutan."""
import re
import time
import unicodedata
from datetime import datetime
from functools import lru_cache
import configuracion
from cerebro.memoria import Memoria
from cerebro.comandos import Comandos
from utilidades import seguridad
from utilidades import acceso
from utilidades import alarmas as _alarmas, calculadora as _calculadora, navegacion as _navegacion
from cerebro.contexto_ordenes import ContextoOrdenes
try:
    from utilidades import nombre as _nombre         # el nombre del asistente, que se pone al iniciar
except Exception as _error_nombre:               # sin nombre, MILLER usa el de siempre
    _nombre = None
    print(f"[CEREBRO] Nombre no disponible: {_error_nombre}")
try:
    from cerebro.emociones import Emociones
except Exception as _error_emociones:           # MILLER sigue funcionando sin emociones
    Emociones = None
    print(f"[CEREBRO] Emociones no disponibles: {_error_emociones}")
try:
    from cerebro.iniciativa import Iniciativa
except Exception as _error_iniciativa:          # MILLER sigue funcionando sin iniciativa
    Iniciativa = None
    print(f"[CEREBRO] Iniciativa no disponible: {_error_iniciativa}")
try:
    from cerebro.necesidades import Equilibrio
except Exception as _error_necesidades:         # sin necesidades, el orbe solo vaga
    Equilibrio = None
    print(f"[CEREBRO] Necesidades no disponibles: {_error_necesidades}")
try:
    from cerebro.patrones import Corrector
except Exception:
    Corrector = None

@lru_cache(maxsize=8192)
def _normalizar(texto):
    texto = unicodedata.normalize("NFD", str(texto).lower().strip())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", texto)

def _como_miller(texto):
    """Si la frase normalizada empieza por el nombre elegido al iniciar, lo cambia por «miller»: así las órdenes
    (que empiezan por «miller») funcionan con cualquier nombre. Con el nombre predeterminado no cambia nada."""
    if _nombre is None:
        return texto
    nombre_norm = _normalizar(_nombre.clave())
    if not nombre_norm or nombre_norm == "miller":
        return texto
    coincidencia = re.match(r"^" + re.escape(nombre_norm) + r"\b[\s,.:;!?¡¿]*", texto)
    if not coincidencia:
        return texto
    return ("miller " + texto[coincidencia.end():]).strip()


def _como_miller_crudo(texto):
    """Lo mismo, sobre el texto tal como se escribió: así los módulos que quitan «miller» de la frase quitan también
    el nombre elegido."""
    if _nombre is None:
        return texto
    nombre_original = _nombre.clave()
    if not nombre_original or _normalizar(nombre_original) == "miller":
        return texto
    coincidencia = re.match(r"^\s*" + re.escape(nombre_original) + r"\b[\s,.:;!?¡¿]*", texto, re.IGNORECASE)
    if not coincidencia:
        return texto
    return ("miller " + texto[coincidencia.end():]).strip()


class Cerebro:
    """Núcleo de procesamiento, contexto, memoria y decisiones."""
    def __init__(self):
        self.nombre = _nombre.clave() if _nombre is not None else configuracion.NOMBRE_ASISTENTE
        self.activo = True
        self._limitador = seguridad.LimitadorOrdenes()
        self.ultima_entrada = self.ultima_respuesta = self.ultima_intencion = None
        self.contexto = []
        self.maximo_contexto = getattr(configuracion, "MAXIMO_CONTEXTO", 20)
        try:
            self.memoria = Memoria(configuracion.RUTA_MEMORIA)
        except TypeError:
            self.memoria = Memoria()
        self.tema_memoria_pendiente = None
        self.ultimo_tema = self.ultima_accion = self.ultima_entidad = None
        self.cancion_pendiente = False
        self.cola_pendiente = False
        self.volumen_pendiente = False
        self.volumen_antes_silencio = None
        self.rutina_matutina_activa = False
        self.comandos = Comandos()
        self.comandos.memoria = self.memoria          # p. ej. respuestas de internet aprendidas, usadas sin conexión
        try:
            self.memoria.iniciar_sesion()
        except Exception as error:
            print(f"[CEREBRO] Memoria de aprendizaje no disponible: {error}")
        self.activador = None                       # lo conecta principal.py (aprendizaje del nombre)
        self.hablador = None                        # lo conecta principal.py (cambiar de voz)
        self.iniciativa = None
        self.emociones = None
        self._iniciar_emociones()
        self._iniciar_iniciativa()
        self.necesidades = None
        if Equilibrio is not None:
            try:
                self.necesidades = Equilibrio(configuracion.RUTA_DATOS / "equilibrio.json")
                self.necesidades.fuente_oraculo = self.introspeccion
                self.necesidades.fuente_deseo = self.deseo_compartir
                self.necesidades.iniciar(lambda: self.emociones)
            except Exception as error:
                print(f"[CEREBRO] Necesidades no disponibles: {error}")
        self.corrector = None
        if Corrector is not None:
            from pathlib import Path
            self.corrector = Corrector([Path(__file__)])
    def corregir_patron(self, texto):
        """Palabras mal oídas -> la orden conocida más parecida. Devuelve (frase, intención) o None."""
        if self.corrector is None or not texto:
            return None
        try:
            if not getattr(self, "_vocabulario_memoria", False):     # lo que ya funcionó también es vocabulario
                self._vocabulario_memoria = True
                comandos = self.memoria._aprendizaje().get("comandos", {}) if hasattr(self.memoria, "_aprendizaje") else {}
                self.corrector.agregar_frases(f for d in comandos.values() for f in d.get("frases", {}))
            corregida = self.corrector.corregir(texto)
        except Exception:
            return None
        if corregida == texto:
            return None
        intencion = self.detectar_intencion(corregida)
        return (corregida, intencion) if intencion != "DESCONOCIDA" else None
    def _foto_de_si(self):
        """Lo que MILLER sabe de sí mismo, en números: aprendizaje, alias, recuerdos y cachés."""
        a = self.memoria._aprendizaje() if hasattr(self.memoria, "_aprendizaje") else {}
        try:
            recuerdos = len(self.memoria.obtener_recuerdos() or [])
        except Exception:
            recuerdos = 0
        corrector = getattr(self, "corrector", None)
        try:
            correcciones = corrector.corregir_palabra.cache_info().currsize if corrector else 0
        except Exception:
            correcciones = 0
        act = getattr(self, "activador", None)
        try:
            nombres = len(act.variantes_aprendidas()) if act else 0
        except Exception:
            nombres = 0
        red = self._conexiones()
        try:
            conexiones = red.cantidad() if red else 0
        except Exception:
            conexiones = 0
        return {"conexiones": conexiones, "usos": sum(d.get("usos", 0) for d in a.get("comandos", {}).values()),
                "ordenes": len(a.get("comandos", {})), "alias": len(a.get("alias", {})),
                "internet": len(a.get("internet", [])), "recuerdos": recuerdos, "nombres": nombres,
                "cache_intenciones": len(self.__dict__.get("_cache_intenciones", {})), "correcciones": correcciones}
    def introspeccion(self):
        """Mirarse a sí mismo: 0-1 según cuánto ha cambiado lo que sabe desde la última vez (alimenta el oráculo)."""
        try:
            foto = self._foto_de_si()
        except Exception:
            return 0.1
        previa, self._foto_previa = getattr(self, "_foto_previa", None), foto
        if previa is None:
            return 0.6                                  # la primera mirada siempre descubre algo
        pesos = {"alias": 0.25, "ordenes": 0.2, "internet": 0.2, "recuerdos": 0.2, "nombres": 0.25,
                 "usos": 0.02, "cache_intenciones": 0.01, "correcciones": 0.05}
        nuevo = sum(max(0, foto[k] - previa.get(k, 0)) * p for k, p in pesos.items())
        return round(min(1.0, 0.1 + nuevo), 3)
    def deseo_compartir(self):
        """Ganas de compartir con el usuario (0-1): sociabilidad y ánimo de sus emociones."""
        if self.emociones is None:
            return 0.5
        try:
            factor = float(self.emociones.factor_iniciativa())          # 0.4 (muchas ganas) .. 2.5
            return round(max(0.0, min(1.0, (2.5 - factor) / 2.1)), 3)
        except Exception:
            return 0.5
    def _conexiones(self):
        """La red de conexiones entre recuerdos (se crea al primer uso; None si no se puede)."""
        if "_red_conexiones" not in self.__dict__:
            try:
                from cerebro.conexiones import Conexiones
                self.__dict__["_red_conexiones"] = Conexiones(self.memoria)
            except Exception:
                self.__dict__["_red_conexiones"] = None
        return self.__dict__["_red_conexiones"]

    def describir_conexiones(self, texto):
        """«conexiones» da el resumen; «conexiones de <tema>» dice qué recuerdos se relacionan con ese tema."""
        red = self._conexiones()
        if red is None:
            return "Red de conexiones fuera de línea."
        m = re.search(r"\b(?:conexiones|asociaciones|relaciona\w*)\s*(?:tienes |hay |veo )?(?:de |con |entre |sobre )?(.*)$", texto)
        tema = m.group(1).strip() if m else ""
        if not tema:
            return red.resumen()
        encontrados = red.asociados(tema)
        if not encontrados:
            return f"Negativo. Ningún recuerdo se relaciona con «{tema}»."
        return f"Se relacionan con «{tema}»: " + " · ".join(e[:80] for e in encontrados) + "."

    def autoconocimiento(self):
        f = self._foto_de_si()
        partes = [f"{f['ordenes']} tipos de orden y {f['usos']} órdenes cumplidas", f"{f['alias']} atajos aprendidos",
                  f"{f['internet']} respuestas de internet guardadas", f"{f['recuerdos']} recuerdos"]
        if f["conexiones"]:
            partes.append(f"{f['conexiones']} conexiones entre recuerdos")
        if f["nombres"]:
            partes.append(f"{f['nombres']} formas nuevas de mi nombre")
        cache = f"En caché tengo {f['cache_intenciones']} frases ya entendidas y {f['correcciones']} palabras corregidas."
        return "Esto sé de mí: " + ", ".join(partes) + ". " + cache
    def _experiencia(self, intencion, texto):
        """Lo vivido alimenta las tres necesidades (placer, oráculo, vínculo)."""
        if self.necesidades is not None:
            try:
                self.necesidades.experiencia(intencion, texto)
            except Exception:
                pass
    def _iniciar_emociones(self):
        """Estado emocional en segundo plano: solo se lee con self.estado_emocional()."""
        if Emociones is None or not getattr(configuracion, "EMOCIONES_ACTIVAS", True):
            return
        try:
            self.emociones = Emociones(
                ruta=getattr(configuracion, "RUTA_EMOCIONES", configuracion.RUTA_DATOS / "emociones.json"),
                reproductor=getattr(self.comandos, "reproductor", None))
            self.emociones.iniciar()
        except Exception as error:
            print(f"[CEREBRO] No se pudieron iniciar las emociones: {error}")
            self.emociones = None
    def estado_emocional(self):
        """Lo único que MILLER recibe de sus emociones: cómo se siente ahora."""
        try:
            return self.emociones.estado() if self.emociones is not None else None
        except Exception:
            return None
    def _iniciar_iniciativa(self):
        """MILLER habla por su cuenta, pidiendo siempre permiso. Si falla, todo sigue igual."""
        if Iniciativa is None or not getattr(configuracion, "INICIATIVA_ACTIVA", True):
            return
        try:
            g = lambda clave, defecto: getattr(configuracion, clave, defecto)
            self.iniciativa = Iniciativa(
                self, ruta_estado=configuracion.RUTA_DATOS / "iniciativa.json",
                intervalo_minimo=g("INICIATIVA_INTERVALO_MINIMO", 900),
                intervalo_urgente=g("INICIATIVA_INTERVALO_URGENTE", 60),
                silencio_previo=g("INICIATIVA_SILENCIO_PREVIO", 20),
                espera_autorizacion=g("INICIATIVA_ESPERA_AUTORIZACION", 25),
                max_peticiones_hora=g("INICIATIVA_MAX_PETICIONES_HORA", 4),
                frases_permiso=g("INICIATIVA_FRASES_PERMISO", None))
            self.iniciativa.iniciar()
        except Exception as error:
            print(f"[CEREBRO] No se pudo iniciar la iniciativa: {error}")
            self.iniciativa = None
    def procesar(self, texto):
        if texto is None or isinstance(texto, str) and not texto.strip():
            return "Sin instrucción recibida."
        if not isinstance(texto, str):
            return "Instrucción no válida."
        texto = seguridad.sanear_entrada(texto)
        texto = _como_miller_crudo(texto)      # «Jarvis, ...» se lee como «miller, ...»
        if not self._limitador.permitir():
            return "Demasiadas órdenes seguidas. Espere un momento, señor."
        if not texto:
            return "Sin instrucción recibida."
        if not getattr(self, "_en_compuesta", False):        # varias órdenes en una frase
            partes = self.dividir_ordenes(texto)
            if len(partes) > 1:
                aviso = acceso.bloqueo("ORDEN_MULTIPLE")          # varios comandos en una frase: modo PRO
                if aviso:
                    return aviso
                self._en_compuesta = True
                try:
                    respuestas = [self.procesar(p) for p in partes[:3]]
                finally:
                    self._en_compuesta = False
                return " ".join(r.strip() for r in respuestas if r)
        self.ultima_entrada = texto
        self.ultima_entidad = None                       # la entidad se fija en cada turno
        normalizado = self.normalizar_texto(texto)
        self.agregar_contexto("usuario", texto)
        if configuracion.es_comando_salida(normalizado):
            self.ultima_intencion, self.activo = "SALIR", False
            respuesta = configuracion.MENSAJE_DESPEDIDA
            self.guardar_respuesta(respuesta)
            return respuesta
        # Contexto: "otra vez", "más", "corrígelo", "y en brave"... se refieren a la orden anterior.
        contexto = self.__dict__.setdefault("contexto_ordenes", ContextoOrdenes())
        referida = contexto.resolver(normalizado)
        if referida:
            normalizado = referida
        # Respuesta sí / no a una limpieza de biblioteca pendiente de confirmar.
        hay_limpieza = getattr(self.comandos, "hay_limpieza_pendiente", None)
        if callable(hay_limpieza) and hay_limpieza():
            intencion = None
            if self._RE_AFIRMA.search(normalizado):
                intencion = "CONFIRMAR_LIMPIEZA"
            elif self._RE_NIEGA.search(normalizado):
                intencion = "CANCELAR_LIMPIEZA"
            if intencion:
                self.ultima_intencion = intencion
                self.ultima_accion = self.INTENCIONES_BIBLIOTECA[intencion]
                respuesta = acceso.bloqueo(intencion) or self.ejecutar_comando(intencion, normalizado)
                self.guardar_respuesta(respuesta)
                return respuesta
        if self.volumen_pendiente:
            volumen = self.extraer_porcentaje_volumen(normalizado)
            if volumen is not None:
                self.volumen_pendiente = False
                self.ultima_intencion = "ESTABLECER_VOLUMEN"
                respuesta = self.ejecutar_comando("ESTABLECER_VOLUMEN", f"volumen {volumen}")
                self.guardar_respuesta(respuesta)
                return respuesta
        if self.tema_memoria_pendiente:
            tema = (self.extraer_tema_memoria(normalizado) or self.interpretar_tema_contextual(normalizado))
            if tema:
                self.ultima_intencion = "BUSCAR_MEMORIA"
                respuesta = self.buscar_recuerdos_por_tema(tema)
                self.tema_memoria_pendiente = None
                self.ultimo_tema = tema
                self.guardar_respuesta(respuesta)
                return respuesta
        # Una respuesta pendiente puede ser solo el nombre de la canción:
        if self.cancion_pendiente or self.cola_pendiente:
            nombre = self.extraer_nombre_cancion(normalizado)
            if not nombre and self.es_nombre_cancion_posible(normalizado):
                nombre = self.limpiar_nombre_cancion(normalizado)
            if nombre:
                intencion = ("AGREGAR_COLA_AUDIO" if self.cola_pendiente else "REPRODUCIR_CANCION")
                self.cancion_pendiente = False
                self.cola_pendiente = False
                self.ultima_intencion = intencion
                self.ultima_entidad = nombre
                self.ultima_accion = (
                    "agregar canción a la lista de reproducción"
                    if intencion == "AGREGAR_COLA_AUDIO"
                    else "reproducir canción"
                )
                respuesta = self.ejecutar_comando(intencion, nombre)
                self.guardar_respuesta(respuesta)
                return respuesta
        # Aprendizaje autónomo: frases que antes no entendía y ya aprendió.
        aprendida = None
        if not normalizado.startswith(("aprende ", "cuando diga", "cuando te diga")):
            alias = self.memoria.usar_alias(normalizado) if hasattr(self.memoria, "usar_alias") else None
            if alias and alias.get("texto"):
                normalizado = alias["texto"]
            elif hasattr(self.memoria, "sinonimos_para"):          # «equal isolar» -> «ecualizador»
                normalizado, _ = self.memoria.sinonimos_para(normalizado)
        intencion = self.detectar_intencion(normalizado)
        if intencion == "DESCONOCIDA" and hasattr(self.memoria, "sinonimos_de_orden"):
            candidato = self.memoria.sinonimos_de_orden(normalizado)   # sinónimo aprendido para esa orden
            if candidato and self.detectar_intencion(candidato[0]) == candidato[1]:
                normalizado, intencion = candidato[0], candidato[1]
        if intencion == "DESCONOCIDA" and hasattr(self.memoria, "similar_conocida"):
            parecida = self.memoria.similar_conocida(normalizado)
            if parecida:                                   # se parece mucho a una orden ya cumplida
                aprendida = self.memoria.aprender_alias(normalizado, parecida[0], parecida[1], "similitud")
                normalizado, intencion = parecida[0], parecida[1]
        if intencion == "DESCONOCIDA":
            corregida = self.corregir_patron(normalizado)
            if corregida:                                  # patrón: era una orden conocida mal oída
                if hasattr(self.memoria, "aprender_alias"):
                    aprendida = self.memoria.aprender_alias(normalizado, corregida[0], corregida[1], "patrón")
                normalizado, intencion = corregida
        if intencion == "DESCONOCIDA":
            self._ultima_desconocida = (normalizado, time.monotonic())
        else:
            previa, self._ultima_desconocida = getattr(self, "_ultima_desconocida", None), None
            if previa and time.monotonic() - previa[1] < 40 and hasattr(self.memoria, "observar_sinonimo"):
                nuevo = self.memoria.observar_sinonimo(previa[0], normalizado, intencion)
                if nuevo:
                    self._anunciar_aprendizaje({"frase": nuevo["original"], "texto": nuevo["texto"]})
            if previa and time.monotonic() - previa[1] < 40 and hasattr(self.memoria, "proponer_alias"):
                aprendida = self.memoria.proponer_alias(previa[0], normalizado, intencion)
                aprendida = aprendida and dict(aprendida, frase=previa[0])
            elif aprendida:
                aprendida = dict(aprendida, frase=self.ultima_entrada)
        if aprendida:
            self._anunciar_aprendizaje(aprendida)
        self.ultima_intencion = intencion
        self._experiencia(intencion, texto)
        respuesta = self.generar_respuesta(normalizado, intencion)
        contexto.registrar(intencion, normalizado, objetivo=getattr(self.comandos, "ultimo_objetivo", None))
        self.guardar_respuesta(respuesta)
        return respuesta
    def normalizar_texto(self, texto):
        return _como_miller(_normalizar(texto)) if texto else ""
    def contiene_alguna(self, texto, palabras):
        texto = self.normalizar_texto(texto)
        return any(self.normalizar_texto(p) in texto for p in palabras) if texto else False
    def detectar_intencion(self, texto):
        """Igual frase -> igual intención: se memoriza (las órdenes repetidas no se recalculan)."""
        clave = self.normalizar_texto(texto)
        cache = self.__dict__.setdefault("_cache_intenciones", {})
        if clave in cache:
            return cache[clave]
        intencion = self._detectar_intencion(clave)
        if len(cache) >= 1024:
            cache.clear()
        cache[clave] = intencion
        return intencion
    def _detectar_intencion(self, texto):
        texto = self.normalizar_texto(texto)
        if re.fullmatch(r"(oye |hey |hola )?miller[.!?]*", texto):
            return "SALUDO"
        if re.match(r"^(miller )?(acceso|llave|clave|contrasena|password)\b", texto):
            return "LLAVE_VOZ"                       # las llaves no se dicen en voz alta
        if re.search(r"^(miller )?(en que|que) modo\b|\bcuanto espacio\b|\bestado (del |de )?(acceso|plan)\b", texto):
            return "ESTADO_ACCESO"
        if re.search(r"\bmodo (free|basico|gratis|normal)\b", texto) and re.search(r"^(miller )?(pon|poner|vuelve|volver|bloquea|bloquear|cierra|cerrar)\b", texto):
            return "BLOQUEAR_ACCESO"
        intencion_iniciativa = self.detectar_intencion_iniciativa(texto)
        if intencion_iniciativa:
            return intencion_iniciativa
        intencion_tecnica = self.detectar_intencion_tecnica(texto)
        if intencion_tecnica:
            return intencion_tecnica
        intencion_utilidad = self.detectar_intencion_utilidades(texto)
        if intencion_utilidad:
            return intencion_utilidad
        if re.search(r"cancion (favorita|preferida)|musica (favorita|preferida)|que (cancion|musica) (me gusta|escucho mas)", texto):
            return "CANCION_FAVORITA"
        if re.search(r"que (has|haz) aprendido|que aprendiste|lo que (has )?aprendido|estadisticas de uso|"
                     r"mis habitos|que sabes de mis (gustos|habitos)|informe de aprendizaje", texto):
            return "RESUMEN_APRENDIZAJE"
        if self.es_orden_memoria(texto):
            return "GUARDAR_MEMORIA"
        if self.es_consulta_memoria_tematica(texto):
            return "BUSCAR_MEMORIA"
        if self.es_consulta_memoria_general(texto):
            return "CONSULTAR_MEMORIA"
        if self.contiene_alguna(texto, ["recuerdas", "te acuerdas de", "te acuerdas", "recuerdas algo"]):
            return "BUSCAR_MEMORIA"
        if self.es_orden_rutina_matutina(texto):
            return "RUTINA_MATUTINA"
        if self.es_saludo(texto):
            return "SALUDO"
        # Descarga de música (antes de volumen: "baja el volumen" no es descargar).
        intencion_descarga = self.detectar_intencion_descarga(texto)
        if intencion_descarga:
            return intencion_descarga
        # Pruebas de módulos (antes de biblioteca: "probar el supervisor").
        intencion_pruebas = self.detectar_intencion_pruebas(texto)
        if intencion_pruebas:
            return intencion_pruebas
        # Supervisor de biblioteca (antes de las reglas de música y de estado).
        intencion_biblioteca = self.detectar_intencion_biblioteca(texto)
        if intencion_biblioteca:
            return intencion_biblioteca
        # Orden explícita de consultar internet: "busca en internet ...", "averigua ...".
        if self.es_orden_internet(texto):
            return "PREGUNTA_INTERNET"
        reglas = [
            ("IDENTIDAD", ["quien eres", "como te llamas", "cual es tu nombre", "dime tu nombre", "que eres", "presentate"]),
            ("HORA", ["que hora es", "dime la hora", "hora actual", "hora tenemos", "hora tienes"]),
            ("FECHA", ["que fecha es", "dime la fecha", "fecha actual", "que dia es", "que dia estamos", "en que fecha estamos"]),
            ("ESTADO", ["como estas", "como te encuentras", "estas funcionando", "estas activo", "estado del sistema", "estado de miller", "como funciona miller", "todo bien miller"]),
            ("QUITAR_SILENCIO", ["quita el silencio", "quitar silencio", "desilenciar", "desmutea", "desmute", "activar sonido", "activa el sonido", "vuelve a activar el sonido"]),
            ("SILENCIAR", ["silencia", "silenciar", "silencio", "quita el sonido", "quita sonido", "mutea", "mute"]),
        ]
        for intencion, palabras in reglas:
            if self.contiene_alguna(texto, palabras):
                return intencion
        if self.es_orden_volumen_numerico(texto):
            return "ESTABLECER_VOLUMEN"
        reglas_musica = [
            ("SUBIR_VOLUMEN", ["sube el volumen", "subir el volumen", "aumenta el volumen", "aumentar el volumen", "sube volumen", "subir volumen", "aumenta volumen", "aumentar volumen", "mas volumen", "sube el audio", "subir el audio", "aumenta el audio", "aumentar el audio", "sube la musica", "subir la musica", "mas alto", "sube el sonido", "subir el sonido"]),
            ("BAJAR_VOLUMEN", ["baja el volumen", "bajar el volumen", "disminuye el volumen", "disminuir el volumen", "reduce el volumen", "reducir el volumen", "baja volumen", "bajar volumen", "menos volumen", "baja el audio", "bajar el audio", "disminuye el audio", "reduce el audio", "baja la musica", "bajar la musica", "mas bajo", "baja el sonido", "bajar el sonido"]),
            ("PAUSAR_MUSICA", ["pausa la musica", "pausar musica", "pausa musica", "pausa la cancion", "pausar la cancion", "pausa", "pausar"]),
            ("REANUDAR_MUSICA", ["reanuda la musica", "reanudar musica", "continua la musica", "continuar musica", "continua la cancion", "reanuda", "continuar", "continua"]),
            ("DETENER_MUSICA", ["deten la musica", "detener musica", "para la musica", "parar musica", "deten la cancion", "para la cancion", "detener", "parar"]),
            ("SIGUIENTE_CANCION", ["siguiente cancion", "cancion siguiente", "siguiente musica", "siguiente", "pasa la cancion", "pasa de cancion", "otra cancion", "pon otra", "siguiente pista", "pista siguiente"]),
            ("ANTERIOR_CANCION", ["cancion anterior", "anterior cancion", "musica anterior", "anterior", "vuelve a la cancion anterior", "pon la anterior", "pista anterior"]),
            ("ALEATORIO_MUSICA", ["activa aleatorio", "activar aleatorio", "modo aleatorio", "reproduccion aleatoria", "musica aleatoria", "pon aleatorio", "aleatorio"]),
            ("REPETIR_AUDIO", ["activa repetir", "activar repetir", "repetir musica", "repetir cancion", "modo repetir", "repeticion"]),
            ("MOSTRAR_COLA_AUDIO", [
                "muestra la lista de reproduccion", "mostrar la lista de reproduccion",
                "ver la lista de reproduccion", "lista de reproduccion",
                "que hay en la lista de reproduccion", "canciones en la lista de reproduccion",
                "muestra la cola", "mostrar cola", "ver cola", "que hay en la cola",
                "canciones en cola", "lista de espera musical",
            ]),
            ("LIMPIAR_COLA_AUDIO", [
                "limpia la lista de reproduccion", "limpiar la lista de reproduccion",
                "vaciar la lista de reproduccion", "vacia la lista de reproduccion",
                "borra la lista de reproduccion", "limpia la cola", "limpiar la cola",
                "vaciar cola", "vacia la cola", "borra la cola",
            ]),
            ("LISTAR_AUDIOS", ["lista las canciones", "listar canciones", "muestra las canciones", "mostrar canciones", "que canciones tengo", "que musica tengo", "lista de canciones", "biblioteca musical"]),
            ("ESTADO_REPRODUCTOR", ["estado de la musica", "estado del reproductor", "que esta sonando", "que cancion esta sonando", "cual es la cancion actual", "que estoy escuchando", "que reproduces", "informacion de la musica"]),
        ]
        verbo_cola = re.search(r"\b(agrega|agregar|anade|añade|anadir|añadir|pon|mete|meter|quita|quitar|elimina|eliminar|"
                               r"borra|borrar|saca|sacar|limpia|limpiar|vacia|vaciar)\b", texto)
        for intencion, palabras in reglas_musica:
            if intencion == "MOSTRAR_COLA_AUDIO" and verbo_cola:
                continue
            if self.contiene_alguna(texto, palabras):
                return intencion
        # Quitar una canción de la cola o lista de reproducción. Solo si la frase nombra la cola (o una posición de la
        # cola): «borra la canción de la papelera» o «quita el silencio» no son de la cola.
        verbo_quitar = r"\b(?:quita|quitar|quitame|elimina|eliminar|saca|sacar|borra|borrar)\b"
        if re.search(verbo_quitar, texto) and (
                re.search(r"\b(?:cola|lista\s+de\s+reproduccion)\b", texto)
                or re.search(r"\b(?:cancion|pista|tema)\s+(?:en\s+la\s+)?(?:posicion|numero)\b", texto)):
            return "QUITAR_COLA_AUDIO"
        if self.es_orden_agregar_cola(texto):
            return "AGREGAR_COLA_AUDIO"
        if self.es_orden_reproducir_cancion(texto):
            return "REPRODUCIR_CANCION"
        if self.contiene_alguna(
            texto,
            ["reproduce musica", "pon musica", "reproducir musica",
             "quiero escuchar musica", "ponme musica", "pon algo de musica",
             "quiero musica", "inicia la musica", "reproduce algo", "pon algo"],
        ):
            return "REPRODUCIR_MUSICA"
        if self.es_orden_abrir_web(texto):
            return "ABRIR_SITIO_WEB"
        if not re.search(r"biblioteca", texto) and re.search(
                r"^(miller )?(lista de |que |cuales son |muestra |muestrame |dime |ver )?(mis |tus )?(comandos|ordenes)"
                r"( disponibles| tengo| hay| de mi (version|plan))?$|\b(que comandos|comandos disponibles|lista de comandos|"
                r"que ordenes|que puedo decir)\b", texto):
            return "AYUDA"
        if self.es_orden_abrir_aplicacion(texto):
            return "ABRIR_APLICACION"
        if self.es_orden_cerrar_aplicacion(texto):
            return "CERRAR_APLICACION"
        reglas_sistema = [
            ("CREAR_CARPETA", ["crea una carpeta", "crear una carpeta", "crea carpeta", "crear carpeta", "haz una carpeta", "hazme una carpeta", "necesito una carpeta"]),
            ("ABRIR_CARPETA", ["abre la carpeta", "abrir la carpeta", "abre carpeta", "abrir carpeta", "quiero abrir la carpeta", "puedes abrir la carpeta"]),
            ("ESTADO_SISTEMA", ["informacion del sistema", "informacion de mi pc", "informacion de mi computadora", "datos de mi computadora", "datos de mi pc", "informacion del ordenador", "datos del sistema", "caracteristicas de mi pc"]),
            ("AYUDA", ["ayuda", "que puedes hacer", "que sabes hacer", "cuales son tus funciones", "que funciones tienes", "como puedes ayudarme", "que puedes hacer por mi"]),
        ]
        for intencion, palabras in reglas_sistema:
            if self.contiene_alguna(texto, palabras):
                return intencion
        # Pregunta general que ninguna regla local resuelve: se consulta en internet.
        if self.es_pregunta_internet(texto):
            return "PREGUNTA_INTERNET"
        return "DESCONOCIDA"
    _RE_INTERROGATIVO = re.compile(
        r"^(?:miller )?(?:oye |dime |sabes |me puedes decir |puedes decirme |quiero saber )?"
        r"(que|quien|quienes|cuando|donde|adonde|cual|cuales|cuanto|cuanta|cuantos|cuantas|como|por que|porque)\b")
    _RE_NO_INTERNET = re.compile(r"\b(cancion|canciones|musica|cola|volumen|carpeta|archivo|memoria|recuerd|biblioteca|"
                                 r"cuarentena|supervisor|prueba|aplicacion)\w*")
    def es_orden_internet(self, texto):
        if self._RE_NO_INTERNET.search(texto):
            return False
        return bool(re.search(r"\b(busca|buscar|buscame|investiga|investigar|averigua|averiguar|consulta|consultar|pregunta)\b"
                              r".*\b(internet|la web|en linea|online|google)\b", texto)
                    or re.match(r"^(?:miller )?(investiga|averigua|averiguame|investigame)\b", texto))
    def es_pregunta_internet(self, texto):
        if self._RE_NO_INTERNET.search(texto) or not self._RE_INTERROGATIVO.search(texto):
            return False
        palabras = [p for p in re.findall(r"\w+", texto) if p != "miller"]
        return len(palabras) >= 3
    def es_orden_rutina_matutina(self, texto):
        texto = self.normalizar_texto(texto).strip()
        if not texto:
            return False
        directos = [
            "rutina", "la rutina", "mi rutina", "rutina matutina",
            "la rutina matutina", "mi rutina matutina", "informe", "el informe",
            "mi informe", "informe de la manana", "el informe de la manana",
            "informe matutino",
        ]
        if texto.strip(" .,!¡¿?") in directos:
            return True
        if not any(p in texto for p in ["rutina", "informe"]):
            return False
        verbos = [
            "inicia", "iniciar", "empieza", "empezar", "comienza", "comenzar",
            "activa", "activar", "ejecuta", "ejecutar", "haz", "hacer",
            "realiza", "realizar", "prepara", "preparar", "genera", "generar",
            "crea", "crear", "dame", "mostrar", "muestrame", "dime", "entrega",
            "presenta",
        ]
        expresiones = [
            "quiero la rutina", "quiero mi rutina", "quiero rutina",
            "quiero el informe", "quiero mi informe", "necesito la rutina",
            "necesito mi rutina", "necesito el informe", "dame la rutina",
            "dame mi rutina", "dame el informe", "muestrame la rutina",
            "muestrame el informe", "prepara la rutina", "prepara el informe",
            "genera la rutina", "genera el informe", "haz la rutina", "haz el informe",
        ]
        return any(v in texto for v in expresiones) or any(
            texto.startswith(v + " ") or f" {v} " in texto for v in verbos
        )
    def es_orden_volumen_numerico(self, texto):
        return bool(re.search(
            r"\b(?:volumen|audio|musica)\b.{0,25}?\b\d{1,3}\s*%?\b|"
            r"\b(?:pon|establece|coloca|ajusta)\s+(?:el\s+)?volumen\s+(?:al|a|en)\s*\d{1,3}",
            texto
        ))
    def extraer_porcentaje_volumen(self, texto):
        texto = self.normalizar_texto(texto).replace("por ciento", "%").replace("porciento", "%")
        match = re.search(r"(?:volumen|audio|musica).{0,35}?(\d{1,3})\s*%?", texto)
        if match:
            return max(0, min(100, int(match.group(1))))
        match = re.search(r"\b(?:al|a|en)\s+(\d{1,3})\s*%?\b", texto)
        return max(0, min(100, int(match.group(1)))) if match else None
    # LISTA DE REPRODUCCIÓN: COMPATIBILIDAD CON LOS NOMBRES INTERNOS ANTIGUOS
    def es_orden_agregar_cola(self, texto):
        texto = self.normalizar_texto(texto)
        verbos = [
            "agrega", "agregar", "anade", "anadir", "pon", "poner",
            "mete", "meter", "introduce", "introducir",
        ]
        destinos = [
            "a la lista de reproduccion", "en la lista de reproduccion",
            "a lista de reproduccion", "en lista de reproduccion",
            "a la cola", "en la cola", "a cola", "en cola", "cola",
        ]
        tiene_verbo = any(texto.startswith(v + " ") or f" {v} " in texto for v in verbos)
        tiene_destino = any(d in texto for d in destinos)
        return tiene_verbo and tiene_destino
    def es_saludo(self, texto):
        patrones = [
            r"^hola$", r"^hola miller$", r"^hey$", r"^hey miller$",
            r"^buenos dias$", r"^buenos dias miller$", r"^buenas tardes$",
            r"^buenas tardes miller$", r"^buenas noches$", r"^buenas noches miller$",
            r"^saludos$", r"^que tal$", r"^hola que tal$",
        ]
        return any(re.search(p, texto) for p in patrones)
    def es_orden_abrir_web(self, texto):
        sitios = [
            "youtube", "google", "bing", "yahoo", "duckduckgo", "netflix",
            "twitch", "prime video", "disney plus", "disney+", "facebook",
            "instagram", "tiktok", "twitter", "reddit", "linkedin", "pinterest",
            "gmail", "google drive", "google maps", "google docs", "google sheets",
            "google meet", "github", "gitlab", "stackoverflow", "npm", "pypi",
            "codepen", "replit", "chatgpt", "claude", "gemini", "perplexity",
            "spotify", "soundcloud", "deezer", "whatsapp", "telegram", "discord",
            "amazon", "mercado libre", "ebay", "wikipedia", "quora", "bbc", "cnn",
            "outlook", "onedrive", "office", "canva", "figma",
        ]
        verbos = [
            "abre", "abrir", "abreme", "abrirme", "puedes abrir",
            "puedes abrirme", "quiero abrir", "quiero entrar", "quiero entrar a",
            "quiero entrar en", "entra a", "entra en", "llevame a", "ir a",
            "ve a", "accede a", "acceder a",
        ]
        return any(s in texto for s in sitios) and any(v in texto for v in verbos)
    _RE_EXCLUIR_PROGRAMA = re.compile(r"\b(carpeta|cancion|canciones|musica|cola|lista|pagina|sitio|web|archivo|prueba|pruebas|"
                                      r"descarga|supervisor|rutina|biblioteca|cuarentena|sesion)\b")
    _PREFIJO = r"^(?:miller )?(?:por favor )?(?:puedes |quiero (?:que )?)?"
    def es_orden_abrir_aplicacion(self, texto):
        """Cualquier programa: "abre spotify", "ejecuta el programa de recortes"..."""
        return bool(re.search(self._PREFIJO + r"(abre|abrir|abreme|abrirme|inicia|iniciar|iniciame|ejecuta|ejecutar|"
                              r"ejecutame|lanza|lanzar|arranca|arrancar)\s+\S", texto)) and not self._RE_EXCLUIR_PROGRAMA.search(texto)
    def es_orden_cerrar_aplicacion(self, texto):
        return bool(re.search(self._PREFIJO + r"(cierra|cerrar|cierrame|termina|terminar|finaliza|finalizar|mata|matar)\s+\S",
                              texto)) and not self._RE_EXCLUIR_PROGRAMA.search(texto) \
            and not re.search(r"(cierra|cerrar|cierrame|termina|terminar|finaliza|finalizar|mata|matar)\s+(a\s+)?miller\b", texto)
    def es_orden_reproducir_cancion(self, texto):
        patrones = [
            "reproduce la cancion ", "reproduce el audio ", "reproduce ",
            "reproducir ", "pon la cancion ", "pon el audio ", "ponme ",
            "pon ", "escucha ", "escuchar ", "quiero escuchar ",
        ]
        for patron in patrones:
            if texto.startswith(patron):
                resto = texto[len(patron):].strip()
                if resto and resto not in ("musica", "algo de musica", "algo", "una cancion", "canciones",):
                    return True
        return False
    def limpiar_nombre_cancion(self, nombre):
        nombre = self.normalizar_texto(nombre).strip(" .,!¡¿?\"'")
        nombre = re.sub(r"\s+(?:a|en)\s+(?:la\s+)?(?:cola|lista de reproduccion)\s*$", "", nombre,)
        nombre = re.sub(r"\s+(?:de|del)\s+la\s+lista de reproduccion\s*$", "", nombre,)
        nombre = re.sub(r"\s+cola\s*$", "", nombre)
        nombre = re.sub(r"^(?:la|el|una|un)\s+", "", nombre)
        return nombre.strip(" .,!¡¿?\"'")
    def es_nombre_cancion_posible(self, texto):
        texto = self.normalizar_texto(texto).strip()
        if not texto or len(texto) > 160:
            return False
        if texto in {
            "si", "no", "cancelar", "cancela", "ninguna", "ninguno",
            "no importa", "olvidalo", "olvidalo miller", "ayuda",
            "pausa", "pausar", "detener", "parar", "siguiente", "anterior",
            "sube el volumen", "baja el volumen",
        }:
            return False
        if self.detectar_intencion(texto) != "DESCONOCIDA":
            return False
        return bool(re.search(r"[a-z0-9]", texto))
    def extraer_nombre_cancion(self, texto):
        texto = self.normalizar_texto(texto).strip()
        patrones_lista = [
            "agrega a la lista de reproduccion",
            "agregar a la lista de reproduccion",
            "anade a la lista de reproduccion",
            "anadir a la lista de reproduccion",
            "agrega en la lista de reproduccion",
            "agregar en la lista de reproduccion",
            "pon en la lista de reproduccion",
            "poner en la lista de reproduccion",
            "mete en la lista de reproduccion",
            "meter en la lista de reproduccion",
            "agrega a la cola", "agregar a la cola", "anade a la cola",
            "anadir a la cola", "agrega en la cola", "agregar en la cola",
            "anade en la cola", "pon en la cola", "poner en la cola",
            "mete en la cola", "meter en la cola",
        ]
        for patron in patrones_lista:
            if texto.startswith(patron):
                nombre = self.limpiar_nombre_cancion(texto[len(patron):])
                if nombre:
                    return nombre
        inicios_lista = [
            "agrega ", "agregar ", "anade ", "anadir ", "pon ",
            "poner ", "mete ", "meter ", "introduce ", "introducir ",
        ]
        for patron in inicios_lista:
            if texto.startswith(patron):
                nombre = self.limpiar_nombre_cancion(texto[len(patron):])
                if nombre and nombre not in ("musica", "algo", "algo de musica"):
                    return nombre
        patrones_cancion = [
            "reproduce la cancion", "reproduce el audio", "reproduce musica de",
            "reproduce", "reproducir la cancion", "reproducir el audio",
            "reproducir", "quiero escuchar", "escucha", "escuchar",
            "pon la cancion", "pon el audio", "ponme", "pon",
        ]
        for patron in patrones_cancion:
            if texto.startswith(patron):
                nombre = self.limpiar_nombre_cancion(texto[len(patron):])
                if nombre and nombre not in ("musica", "algo de musica", "algo"):
                    return nombre
        return None
    def es_orden_memoria(self, texto):
        patrones = [
            "recuerda que", "recuerda mi", "recuerda mis", "recuerda el",
            "recuerda la", "recuerda los", "recuerda las", "recuerda esto",
            "guarda esto", "guarda que", "memoriza esto", "memoriza que",
            "quiero que recuerdes", "quiero que guardes", "no olvides que",
            "ten presente que", "anota que",
        ]
        return self.contiene_alguna(texto, patrones)
    def es_consulta_memoria_general(self, texto):
        if self.es_consulta_memoria_tematica(texto):
            return False
        patrones = [
            "que recuerdas", "que recuerdas de mi", "que sabes de mi",
            "muestrame mi memoria", "muestra mi memoria", "mis recuerdos",
            "dime mis recuerdos", "que tienes guardado", "que tienes en memoria",
            "que sabes sobre mi",
        ]
        return self.contiene_alguna(texto, patrones)
    def es_consulta_memoria_tematica(self, texto):
        patrones = [
            "que recuerdas de ", "que recuerdas sobre ", "que recuerdas acerca de ",
            "te acuerdas de ", "te acuerdas sobre ", "te acuerdas acerca de ",
            "que sabes sobre ", "que sabes de ", "que tienes sobre ", "que tienes de ",
        ]
        return any(p in texto and texto.split(p, 1)[1].strip() for p in patrones)
    # SUPERVISOR DE BIBLIOTECA
    INTENCIONES_BIBLIOTECA = {
        "ESTADO_BIBLIOTECA": "consultar biblioteca",
        "LISTAR_DANADOS_BIBLIOTECA": "listar canciones dañadas",
        "LISTAR_DUPLICADOS_BIBLIOTECA": "listar canciones duplicadas",
        "LISTAR_NO_COMPATIBLES_BIBLIOTECA": "listar formatos no compatibles",
        "LISTAR_CUARENTENA": "listar cuarentena",
        "ESTADO_SUPERVISOR": "consultar supervisor",
        "RESULTADO_LIMPIEZA": "consultar limpieza",
        "AYUDA_BIBLIOTECA": "ayuda de la biblioteca",
        "REVISAR_BIBLIOTECA": "revisar biblioteca",
        "LIMPIAR_BIBLIOTECA": "limpiar biblioteca",
        "CONFIRMAR_LIMPIEZA": "confirmar limpieza",
        "CANCELAR_LIMPIEZA": "cancelar limpieza",
        "RESTAURAR_CUARENTENA": "restaurar de cuarentena",
        "PAUSAR_SUPERVISOR": "pausar supervisor",
        "REANUDAR_SUPERVISOR": "reanudar supervisor",
        "LISTAR_ADULTERADOS": "listar archivos adulterados",
        "PLAN_ELIMINACION": "consultar plan de eliminación",
        "REPARAR_BIBLIOTECA": "reparar biblioteca",
        "VACIAR_CUARENTENA": "vaciar cuarentena",
        "BORRAR_CANCION": "mover canción a la papelera",
        "MUSICA_DEL_DIA": "consultar música del día",
        "BUSCAR_NAVEGADOR": "buscar en el navegador",
        "BUSCAR_ARCHIVO": "buscar archivo",
        "CALCULAR": "calcular",
        "NOTICIAS": "consultar noticias",
        "ALARMA": "gestionar alarma",
        "LISTAR_PAPELERA": "listar papelera",
        "VACIAR_PAPELERA": "vaciar papelera",
        "PREGUNTA_INTERNET": "consultar internet",
        "DESCARGAR_MUSICA": "descargar música",
        "ESTADO_DESCARGA": "consultar descarga",
        "CANCELAR_DESCARGA": "cancelar descarga",
        "BATERIA": "consultar batería",
        "ABRIR_ARCHIVO": "abrir archivo",
        "CERRAR_ARCHIVO": "cerrar archivo",
        "VENTANA": "controlar ventana",
        "ECUALIZADOR": "ajustar ecualizador",
        "ECUALIZADOR_AJUSTE": "ajustar ecualizador",
        "PROBAR_MODULO": "probar módulo",
        "PROBAR_TODOS_MODULOS": "probar todos los módulos",
        "RESULTADO_PRUEBAS": "consultar resultado de las pruebas",
        "LISTAR_PRUEBAS": "listar pruebas",
    }
    _RE_AFIRMA = re.compile(r"^(?:miller )?(si|sí|claro|confirmo|confirmar|confirma|adelante|hazlo|dale|ok|okay|de acuerdo|procede|limpia)\b")
    _RE_NIEGA = re.compile(r"^(?:miller )?(no|cancela|cancelar|olvidalo|mejor no|detente|espera)\b")
    def _anunciar_aprendizaje(self, alias):
        frase = self.normalizar_texto(alias.get("frase", ""))
        print(f"[CEREBRO] 🧠 Aprendí: «{frase}» = «{alias.get('texto')}»")
        if self.iniciativa is not None:
            self.iniciativa.agregar(f"alias:{frase}", f"aprendí que «{frase}» significa «{alias.get('texto')}».",
                                    2, tono="bueno")
        if self.emociones is not None:
            try:
                self.emociones.registrar_evento("orden_aprendida", frase)
            except Exception:
                pass
    _RE_ENSENAR = re.compile(r"^(?:miller )?(?:aprende que|cuando (?:te )?diga) (.+?) (?:significa|quiero decir|es|equivale a) (.+)$")
    def ensenar_orden(self, texto):
        m = self._RE_ENSENAR.match(self.normalizar_texto(texto))
        if not m:
            return "Formato: aprende que <frase> significa <orden>."
        frase, orden = m.group(1).strip(), m.group(2).strip()
        intencion = self.detectar_intencion(orden)
        if intencion in ("DESCONOCIDA", "ENSENAR_ORDEN"):
            return f"Negativo. «{orden}» tampoco la conozco."
        if not self.memoria.aprender_alias(frase, orden, intencion, "enseñanza"):
            return "Negativo. No pude aprenderla."
        return f"Aprendido: «{frase}» = «{orden}»."
    _RE_ENSENAR_SINONIMO = re.compile(r"^(?:miller )?aprende (?!que\b)(.+?) (?:significa|quiere decir|equivale a) (.+)$")
    _RE_OLVIDAR_SINONIMO = re.compile(r"^(?:miller )?olvida (?:el |la )?sinonimo (.+)$")

    def ensenar_sinonimo(self, texto):
        m = self._RE_ENSENAR_SINONIMO.match(self.normalizar_texto(texto))
        if not m:
            return "Formato: aprende <palabra> significa <orden o palabra>."
        aprendido = self.memoria.aprender_sinonimo(m.group(1), m.group(2), None, "enseñanza")
        if not aprendido:
            return "Negativo. No pude aprender ese sinónimo."
        return f"Afirmativo. Aprendido: «{aprendido['original']}» significa «{aprendido['texto']}»."

    def olvidar_sinonimo_orden(self, texto):
        m = self._RE_OLVIDAR_SINONIMO.match(self.normalizar_texto(texto))
        if not m:
            return "Formato: olvida sinónimo <palabra>."
        if self.memoria.olvidar_sinonimo(m.group(1)):
            return f"Afirmativo. Olvidado el sinónimo «{m.group(1).strip()}»."
        return f"«{m.group(1).strip()}» no es un sinónimo que yo haya aprendido."

    def ejecutar_plan_olvido(self):
        r = self.memoria.plan_de_olvido()
        return (f"Afirmativo. Plan de olvido: archivé {r['recuerdos']} recuerdos sin uso, "
                f"{len(r['alias'])} órdenes aprendidas y {len(r['sinonimos'])} sinónimos. "
                "Si quiere recuperar algo, diga «recupera lo olvidado de tema».")

    def recuerdos_olvidados(self):
        lista = self.memoria.olvidados_recientes(5)
        if not lista:
            return "Todavía no he olvidado nada, señor."
        return ("Lo último que olvidé: " + "; ".join(f"«{seguridad.sanear_conocimiento(c, 60)}»" for c in lista)
                + ". Diga «recupera lo olvidado de tema» para volver a tenerlo.")

    def memoria_corto_plazo(self):
        minutos = getattr(configuracion, "MEMORIA_CORTO_MINUTOS", 45)
        dichos = [e.get("contenido", "") for e in self.contexto if e.get("rol") == "usuario"][:-1]
        if not dichos:
            return f"En los últimos {minutos} minutos no me ha dicho nada que yo deba retener, señor."
        ultimos = [seguridad.sanear_conocimiento(d, 50) for d in dichos[-5:]][::-1]
        return (f"En mi memoria a corto plazo, de los últimos {minutos} minutos, lo último que me dijo: "
                + "; ".join(f"«{d}»" for d in ultimos) + ".")

    def memoria_largo_plazo(self):
        r = self.memoria.resumen_largo_plazo()
        temas = ", ".join(f"{t} ({n})" for t, n in r["temas"]) or "ninguno"
        return (f"En mi memoria a largo plazo tengo {r['activos']} recuerdos activos y {r['olvidados']} "
                f"archivados por el plan de olvido. Temas principales: {temas}.")

    def olvidar_tema_orden(self, texto):
        tema = re.sub(r"^(?:miller\s+)?olvida (?:todo )?lo de\s+", "", self.normalizar_texto(texto)).strip()
        n = self.memoria.olvidar_tema(tema)
        return (f"Afirmativo. Archivé {n} recuerdos sobre «{tema}». Puedo recuperarlos." if n
                else f"No tengo recuerdos sobre «{tema}».")

    def recuperar_olvidado_orden(self, texto):
        m = re.match(r"^(?:miller )?recupera (?:lo olvidado|lo que olvidaste|los recuerdos olvidados) (?:de|sobre) (.+)$",
                     self.normalizar_texto(texto))
        tema = m.group(1).strip() if m else ""
        if not tema:
            return "Formato: recupera lo olvidado de <tema>."
        n = self.memoria.recuperar_olvidado(tema)
        return f"Afirmativo. Recuperé {n} recuerdos sobre «{tema}»." if n else f"No tengo nada olvidado sobre «{tema}»."

    def sinonimos_aprendidos(self):
        lista = self.memoria.listar_sinonimos()
        if not lista:
            return "Aún no he aprendido sinónimos."
        partes = [f"«{o}» es «{t}»" + (f" (solo para {a.lower()})" if a else "") for o, t, a in lista[:12]]
        return "Sinónimos aprendidos: " + "; ".join(partes) + "."

    def ordenes_aprendidas(self):
        alias = self.memoria._aprendizaje().get("alias", {}) if hasattr(self.memoria, "_aprendizaje") else {}
        if not alias:
            return "Aún no he aprendido órdenes nuevas."
        ultimas = sorted(alias.items(), key=lambda kv: kv[1].get("desde", ""))[-4:]
        return f"{len(alias)} aprendidas. Últimas: " + "; ".join(f"«{f}» = «{d['texto']}»" for f, d in ultimas) + "."
    _RE_VERBO_ORDEN = re.compile(
        r"^(?:miller )?(?:por favor )?(?:pon|ponme|abre|abrir|abreme|cierra|cerrar|busca|buscar|buscame|encuentra|sube|baja|"
        r"reproduce|reproducir|para|pausa|deten|silencia|suma|resta|multiplica|divide|calcula|dime|crea|borra|quita|"
        r"agrega|anade|descarga|siguiente|anterior|recuerdame|apaga|cancela|muestra|lista|activa|desactiva|revisa|repara|"
        r"restaura|vacia|prueba|probar|cuanto es|que hora|que fecha|programa)\b")
    _RE_SEPARADOR = re.compile(r"\s*,?\s*\b(?:y luego|y despues|luego|despues|y tambien|y ademas|y enseguida)\b\s*")
    def dividir_ordenes(self, texto):
        """"busca netflix en el navegador y luego sube el volumen" -> dos órdenes. Solo divide si cada parte
        empieza por un verbo de orden y MILLER la entiende; "suma 2 y 3" o "a las 9 y 20" no se dividen."""
        t = self.normalizar_texto(texto)
        piezas = [p for p in self._RE_SEPARADOR.split(t) if p.strip()]
        resultado = []
        for pieza in piezas:
            trozos = re.split(r"\s+y\s+(?=(?:miller )?(?:por favor )?\S)", pieza)
            actual = trozos[0]
            for trozo in trozos[1:]:
                if self._RE_VERBO_ORDEN.match(trozo) and self._RE_VERBO_ORDEN.match(actual):
                    resultado.append(actual)
                    actual = trozo
                else:
                    actual = f"{actual} y {trozo}"
            resultado.append(actual)
        if len(resultado) < 2:
            return [texto]
        if any(self.detectar_intencion(p) == "DESCONOCIDA" for p in resultado):
            return [texto]
        return resultado
    _RE_BUSCAR_VERBO = re.compile(r"^(?:miller )?(?:por favor )?(?:busca|buscar|buscame|busque|encuentra|encuentrame|localiza)\b")
    _RE_ARCHIVO = re.compile(r"\b(explorador|mis archivos|archivo|fichero|documento)\b|\b[\w-]+\.[a-z0-9]{2,5}\b|"
                             r"\bpunto (?:txt|pdf|docx?|xlsx?|pptx?|mp3|mp4|jpg|jpeg|png|zip|rar|exe|py|csv|json|wav)\b")
    _RE_EN_NAVEGADOR = re.compile(r"\ben (?:el )?navegador\b|\b(?:en|con) (?:youtube|google|bing)\b|\bbrave\b|\bchrome\b|"
                                  r"\bedge\b|\bfirefox\b|\bopera\b")
    _RE_EXTENSION = re.compile(r"\b[\w\-]+(?:\.| punto )[a-z0-9]{2,4}\b")
    _RE_WEB = re.compile(r"\.(?:com|org|net|es|co|io|tv|app|gov|edu)\b|\b(pagina|sitio|web|navegador|http|www)\b")
    def detectar_intencion_tecnica(self, texto):
        """Ventanas (minimizar, maximizar, restaurar), archivos, batería y ecualizador."""
        t = re.sub(r"^(?:miller\s+)?(?:por favor\s+)?", "", re.sub(r"[?!,¿¡]", " ", texto)).strip()
        t = re.sub(r"\s+", " ", t).strip(" .")
        if re.match(r"(minimiza|minimizar|minimizame|minimizate|esconde|maximiza|maximizar|maximizame|agranda)\b", t) or \
                re.match(r"(restaura|restaurar|muestra|trae)( la| el)? ventana\b", t) or \
                re.match(r"(pon|pone|deja|muestra)\b.+ en pantalla completa$", t):
            return "VENTANA"
        es_archivo = re.search(r"\b(archivo|documento|fichero)\b", t) or (self._RE_EXTENSION.search(t) and not self._RE_WEB.search(t))
        if es_archivo and re.match(r"(abre|abrir|abreme)\b", t):
            return "ABRIR_ARCHIVO"
        if es_archivo and re.match(r"(cierra|cerrar|cierrame)\b", t):
            return "CERRAR_ARCHIVO"
        if re.search(r"\b(bateria|baterias|pila del (equipo|portatil|computador)|nivel de carga|cuanta carga( tiene| queda)?)\b", t):
            return "BATERIA"
        if re.search(r"\b(sube|subir|subele|aumenta|aumentar|baja|bajar|bajale|reduce|reducir|mas|menos)\b(?:\s+\w+){0,3}?\s+"
                     r"(graves|bajos|medios|agudos|brillo)\b", t):
            return "ECUALIZADOR_AJUSTE"
        ecualizador_perfil = bool(re.search(r"\bperfil(es)?\b", t) and re.search(
            r"\b(crea|crear|creame|guarda|guardar|guardame|borra|borrar|elimina|eliminar|lista|que|pon|activa|usa|nuevo)\b", t))
        ecualizador_banda = bool(re.search(r"\b(pon|pone|deja|ajusta|ajustar|fija|fijar)\b.*\b(graves|bajos|medios|agudos|"
                                           r"brillo|altos)\b\s*(en|a|de|al)?\s*-?\d", t))
        ecualizador_modo = bool(re.fullmatch(r"(pon |activa )?(el )?modo (automatico|inteligente)", t))
        if re.search(r"\becualiz", t) or ecualizador_perfil or ecualizador_banda or ecualizador_modo or \
                re.fullmatch(r"(pon |activa )?(el )?(perfil|modo) (graves|agudos|voz|rock|pop|electronica|"
                             r"clasica|acustico|suave|plano)", t):
            return "ECUALIZADOR"
        return None
    def detectar_intencion_utilidades(self, texto):
        """Alarmas, cálculo, búsquedas en el navegador y en el explorador."""
        t = re.sub(r"^miller\s+", "", re.sub(r"[?!.,¿¡]", " ", texto)).strip()
        t = re.sub(r"\s+", " ", t)
        if _alarmas.es_pedido(t):
            return "ALARMA"
        if re.search(r"\b(dime|dame|cuentame|lee|leeme|que)\b.*\b(noticias|titulares)\b|^(ultimas )?noticias$|"
                     r"\bque hay de nuevo\b|\bque esta pasando\b", t):
            return "NOTICIAS"
        if _calculadora.es_operacion(t):
            return "CALCULAR"
        if self._RE_BUSCAR_VERBO.match(t):
            if self._RE_ARCHIVO.search(t) and not re.search(r"\b(cancion|musica|internet|youtube|google)\b", t):
                return "BUSCAR_ARCHIVO"
            if self._RE_EN_NAVEGADOR.search(t):
                return "BUSCAR_NAVEGADOR"
        if re.match(r"^(?:por favor )?(?:abre|abrir|abreme|entra a|entra en|ve a|llevame a)\b", t) and (
                _navegacion.detectar_navegador(t) or re.search(r"\ben (?:el )?navegador\b", t)):
            return "ABRIR_SITIO_WEB"
        return None
    def detectar_intencion_iniciativa(self, texto):
        """Hablar por iniciativa propia y nombre aprendido."""
        t = re.sub(r"[?!.,¿¡]", "", texto).strip()
        t = re.sub(r"^miller\s+", "", t)
        if re.search(r"(formas|maneras|variantes|variaciones) de (tu|su) nombre|nombres? (aprendidos?|que reconoces)|"
                     r"como reconoces tu nombre|que nombres reconoces", t):
            return "NOMBRES_APRENDIDOS"
        if re.match(r"olvida (el nombre|la forma|la variante|la variacion) ", t):
            return "OLVIDAR_NOMBRE"
        if re.search(r"\bno (me )?interrump\w*|no pidas permiso|desactiva (la )?iniciativa|no hables por tu cuenta", t):
            return "PAUSAR_INICIATIVA"
        if re.search(r"activa (la )?iniciativa|puedes (volver a )?(hablar|pedir permiso)|habla cuando (quieras|tengas)", t):
            return "REANUDAR_INICIATIVA"
        valoracion = self.detectar_valoracion(t)
        if valoracion:
            return valoracion
        if re.search(r"(tu|su) equilibrio|tus necesidades|tus (tres )?circulos|como (estan|van) tus (necesidades|circulos)|"
                     r"equilibrio (emocional|interior)|estas equilibrado|que te falta", t):
            return "EQUILIBRIO"
        if re.search(r"\b(conexiones|asociaciones)\b|\bque se relaciona\b|\bque (recuerdos|cosas) (se )?relacion", t):
            return "CONEXIONES"
        if re.search(r"que sabes de ti|conocete|aprende de ti( mismo)?|mirate a ti( mismo)?|tu (cache|cacheo)|"
                     r"que tienes en (cache|memoria cache)|autoconocimiento|cuanto sabes de ti", t):
            return "AUTOCONOCIMIENTO"
        if re.search(r"como te sientes|que sientes|como (te )?(encuentras|estas) de animo|tu (estado de )?animo|"
                     r"estado (emocional|de animo)|tus emociones|estas (feliz|contento|triste|enojado|aburrido|preocupado)|"
                     r"que emocion", t):
            return "EMOCION"
        if re.search(r"tu (personalidad|caracter|forma de ser|temperamento)|como es tu (personalidad|caracter)", t):
            return "PERSONALIDAD"
        if self._RE_ENSENAR.match(t) or self._RE_ENSENAR.match("miller " + t):
            return "ENSENAR_ORDEN"
        if self._RE_ENSENAR_SINONIMO.match(t):
            return "ENSENAR_SINONIMO"
        if re.fullmatch(r"(ejecuta |aplica |haz |lanza )?(el )?plan de olvido", t):
            return "PLAN_OLVIDO"
        if re.search(r"\b(que|cuales?|lo que) (he |has |ha )?olvid(ado|aste)\b", t):
            return "OLVIDADOS"
        if re.search(r"memoria (a |de )?(corto|corta) plazo|que (recuerdas|recuerda) de hoy|de que (hablamos|hablabamos)|"
                     r"que te he dicho", t):
            return "MEMORIA_CORTO"
        if re.search(r"memoria (a |de )?larg[oa] plazo|cuantos recuerdos (tienes|tengo|guardas)", t):
            return "MEMORIA_LARGO"
        if re.match(r"olvida (todo )?lo de ", t):
            return "OLVIDAR_TEMA"
        if re.match(r"recupera (lo olvidado|lo que olvidaste|los recuerdos olvidados) (de|sobre) ", t):
            return "RECUPERAR_OLVIDADO"
        if self._RE_OLVIDAR_SINONIMO.match(t):
            return "OLVIDAR_SINONIMO"
        if re.search(r"(que|cuales) sinonimos (has|tienes|aprendiste)|sinonimos aprendidos", t):
            return "SINONIMOS_APRENDIDOS"
        if re.search(r"(que|cuales) ordenes (has aprendido|aprendiste)|ordenes aprendidas", t):
            return "ORDENES_APRENDIDAS"
        if re.search(r"que (musica|canciones) (escuche|he escuchado|sono|sonaron|oi)|musica (de hoy|de ayer)|"
                     r"(resumen|diario) musical|que escuche (hoy|ayer)", t):
            return "MUSICA_DEL_DIA"
        if re.search(r"cambia(r)? (de |la |tu )?voz|otra voz|usa (la )?voz|pon (la )?voz|voz (mexicana|latina|espanola|de espana)|"
                     r"que voz (tienes|usas)|cual es tu voz", t):
            return "CAMBIAR_VOZ"
        if re.search(r"\b(?:sell|cell)(?:ar|a|ame) (?:(?:el|tu|su|este|mi) )?(?:codigo|programa|sistema)\b|\b(?:sell|cell)alo\b|acepta (?:los )?cambios del codigo", t):
            return "SELLAR_CODIGO"
        if re.search(r"estado de (la )?seguridad|seguridad del sistema|hay (alertas|ataques|amenazas)|informe de seguridad", t):
            return "SEGURIDAD"
        if re.fullmatch(r"que sabes|dime (todo )?lo que sabes|todo lo que sabes|que conoces|que sabes de todo|"
                        r"informe general|reporte general", t):
            return "CONOCIMIENTO_GENERAL"
        if re.fullmatch(r"que (tienes|tiene) (que|para) decir(me)?|tienes algo (que|para) decir(me)?|"
                        r"(alguna |hay |tienes |que )?novedad(es)?|que (me )?querias decir|adelante|diga|digame|siga|"
                        r"hable|habla|proceda|permiso concedido|tiene permiso|tienes permiso", t):
            return "NOVEDADES"
        return None
    _RELLENO_VALORACION = {"miller", "senor", "muy", "pero", "hoy", "hermano", "parcero", "amigo", "eso", "esto",
                           "si", "oye", "bueno", "ya", "otra", "vez", "de", "verdad", "la", "lo", "el", "un", "una",
                           "eres", "estas", "fue", "has", "hiciste", "a", "y", "que", "me", "te", "mucho", "todo"}
    def detectar_valoracion(self, t):
        """Felicitación o regaño SIN otra orden dentro ("muy bien Miller" sí; "muy bien, pon música" no)."""
        try:
            from cerebro.emociones import Emociones
        except Exception:
            return None
        for patron, intencion in ((Emociones._RE_REPROCHE, "REPROCHE"), (Emociones._RE_ELOGIO, "ELOGIO")):
            if patron.search(t):
                resto = [p for p in patron.sub(" ", t).split() if p not in self._RELLENO_VALORACION]
                if len(resto) <= 1:
                    return intencion
        return None
    def responder_valoracion(self, intencion):
        """Respuesta congruente: agradece la felicitación, asume el regaño y pide qué corregir."""
        animo = (self.estado_emocional() or {}).get("emocion", "calma")
        if intencion == "ELOGIO":
            opciones = ["Gracias, señor. Me alegra serle útil.", "Se agradece, señor. Seguiré así.",
                        "Gracias. Eso me sube el ánimo.", "A sus órdenes, señor. Gracias por decírmelo."]
            if animo in ("tristeza", "miedo", "preocupacion"):
                opciones = ["Gracias, señor. Lo necesitaba.", "Gracias. Eso me devuelve algo de luz."]
        else:
            opciones = ["Entendido, señor. Dígame qué corrijo.", "Lo siento, señor. ¿En qué me equivoqué?",
                        "Tomo nota, señor. Indíqueme el error y lo aprendo.", "Disculpe. Lo haré mejor."]
            if animo in ("tristeza", "frustracion"):
                opciones = ["Lo siento, señor. Ya venía mal; dígame qué corrijo.", "Entendido. Intentaré hacerlo mejor."]
        return self.seleccionar_respuesta_contextual(opciones)
    def responder_iniciativa(self, intencion, texto):
        ini, act = self.iniciativa, self.activador
        if intencion == "NOMBRES_APRENDIDOS":
            aprendidas = act.variantes_aprendidas() if act else []
            if not aprendidas:
                return f"Mi nombre es {self.nombre}, fijado al iniciar el programa. No aprendo formas nuevas de oírlo, señor."
            return (f"{len(aprendidas)} {'forma aprendida' if len(aprendidas) == 1 else 'formas aprendidas'}: "
                    f"{', '.join(aprendidas[:6])}.")
        if intencion == "OLVIDAR_NOMBRE":
            variante = re.sub(r"^(?:miller\s+)?olvida (?:el nombre|la forma|la variante|la variacion)\s+", "", texto).strip()
            if act and act.olvidar_variante(variante):
                return f"Afirmativo. «{variante}» olvidado."
            return f"«{variante}» no figura entre las formas aprendidas."
        if intencion == "SEGURIDAD":
            return seguridad.resumen()
        if intencion == "SELLAR_CODIGO":
            return f"Código sellado: {seguridad.sellar_codigo()} archivos. Avisaré si alguno cambia sin que usted lo diga."
        if intencion == "ENSENAR_ORDEN":
            return self.ensenar_orden(texto)
        if intencion == "ENSENAR_SINONIMO":
            return self.ensenar_sinonimo(texto)
        if intencion == "OLVIDAR_SINONIMO":
            return self.olvidar_sinonimo_orden(texto)
        if intencion == "SINONIMOS_APRENDIDOS":
            return self.sinonimos_aprendidos()
        if intencion == "PLAN_OLVIDO":
            return self.ejecutar_plan_olvido()
        if intencion == "OLVIDADOS":
            return self.recuerdos_olvidados()
        if intencion == "MEMORIA_CORTO":
            return self.memoria_corto_plazo()
        if intencion == "MEMORIA_LARGO":
            return self.memoria_largo_plazo()
        if intencion == "OLVIDAR_TEMA":
            return self.olvidar_tema_orden(texto)
        if intencion == "RECUPERAR_OLVIDADO":
            return self.recuperar_olvidado_orden(texto)
        if intencion == "ORDENES_APRENDIDAS":
            return self.ordenes_aprendidas()
        if intencion == "CAMBIAR_VOZ":
            hablador = getattr(self, "hablador", None)
            if hablador is None:
                return "Síntesis de voz fuera de línea."
            if re.search(r"que voz|cual es tu voz", texto):
                return f"Uso la {hablador.voz_actual()}."
            return hablador.cambiar_voz(texto)
        if intencion == "AUTOCONOCIMIENTO":
            return self.autoconocimiento()
        if intencion == "CONEXIONES":
            return self.describir_conexiones(texto)
        if intencion == "EQUILIBRIO":
            if self.necesidades is None:
                return "Módulo de necesidades fuera de línea."
            return self.necesidades.describir()
        if intencion in ("EMOCION", "PERSONALIDAD"):
            if self.emociones is None:
                return "Módulo emocional fuera de línea."
            return self.emociones.describir() if intencion == "EMOCION" else self.emociones.describir_personalidad()
        if ini is None:
            return "Iniciativa fuera de línea."
        if intencion == "PAUSAR_INICIATIVA":
            ini.activa = False
            ini.retirar_peticion()
            return "Entendido. No hablaré por mi cuenta hasta nueva orden."
        if intencion == "REANUDAR_INICIATIVA":
            ini.activa = True
            return "Afirmativo. Pediré permiso cuando tenga algo que informar."
        if intencion == "CONOCIMIENTO_GENERAL":
            return ini.conocimiento_general()
        if intencion == "NOVEDADES":
            return ini.entregar_novedades()
        return None
    def detectar_intencion_descarga(self, texto):
        t = texto
        if not re.search(r"descarg", t) and not re.search(r"\b(baja|bajar|bajame)\b.*\b(cancion|tema|musica|tonada)\b", t):
            return None
        if re.search(r"\b(volumen|carpeta)\b", t):
            return None
        if not re.search(r"descarg", t) and re.search(r"\b(baja|bajar|bajame)\b\s+(?:la |una |esa |esta |mi )?(cancion|tema|musica|tonada)\s*$", t.strip()):
            return None                              # "baja la música" sin nombre es bajar el volumen, no descargar
        if re.search(r"\b(cancela|cancelar|deten|detener|para|parar|aborta|abortar)\b", t):
            return "CANCELAR_DESCARGA"
        if re.search(r"(como va|estado|progreso|avance|termino|ya termino|ya acabo).*descarg|descarg\w* (va|lleva)", t):
            return "ESTADO_DESCARGA"
        return "DESCARGAR_MUSICA"
    def detectar_intencion_pruebas(self, texto):
        """Pruebas de la carpeta test/: "probar voz", "probar todos los módulos"..."""
        t = texto
        if re.search(r"\b(resultado|resultados|resumen|informe)\b.*\bpruebas?\b|"
                     r"como (salieron|fueron|fue|salio|van|va) (las |la )?pruebas?", t):
            return "RESULTADO_PRUEBAS"
        if re.search(r"\b(que|cuales) pruebas\b|lista de (las )?pruebas|pruebas (hay|disponibles|tienes|puedes)", t):
            return "LISTAR_PRUEBAS"
        verbo = re.search(r"\b(prueba|probar|pruebame|pruebalo|pruebala|testea|testear|testeame|diagnostica|diagnosticar)\b", t) \
            or re.search(r"\b(ejecuta|ejecutar|corre|correr|lanza|lanzar|haz|hacer|inicia|iniciar)\b.*\b(prueba|pruebas|test|tests)\b", t)
        if not verbo:
            return None
        if re.search(r"\b(todos|todas|todo|completo|completa|general|cada)\b", t):
            return "PROBAR_TODOS_MODULOS"
        return "PROBAR_MODULO"
    _RE_BORRAR_CANCION = re.compile(
        r"\b(borra|borrar|borrame|borrala|borralo|elimina|eliminar|eliminame|eliminala|eliminalo|suprime|suprimir|"
        r"tira|tirar)\b|\b(manda|mandar|mueve|mover|envia|enviar|quita|quitar|saca|sacar)\b.*\b(papelera|biblioteca)\b")
    _RE_NO_ES_CANCION = re.compile(
        r"\b(cola|lista de reproduccion|cuarentena|recuerdo|recuerdos|memoria|carpeta|historial|descarga|supervisor|"
        r"definitivamente|para siempre)\b|\btod[oa]s? (?:las |los |la |el )?(?:canciones|musica|biblioteca|audios|archivos)\b|duplicad|danad|corrupt|adulterad|compatible|repetid|copias|defectuos")
    def detectar_intencion_papelera(self, t):
        """Papelera de canciones: borrar una, ver qué hay, vaciarla."""
        if "papelera" in t:
            if re.search(r"\b(vacia|vaciar|vaciala|limpia|limpiar)\b", t):
                return "VACIAR_PAPELERA"
            if re.search(r"\b(que hay|que tiene|lista|listar|muestra|mostrar|ver|contenido|cuantas|cuantos|revisa)\b", t):
                return "LISTAR_PAPELERA"
        if self._RE_BORRAR_CANCION.search(t) and not self._RE_NO_ES_CANCION.search(t):
            return "BORRAR_CANCION"
        return None
    def detectar_intencion_biblioteca(self, texto):
        """Devuelve la intención del supervisor de biblioteca o None."""
        t = texto
        if re.search(r"\b(confirma|confirmar|confirmo)\b.*\blimpieza\b", t):
            return "CONFIRMAR_LIMPIEZA"
        if re.search(r"\b(cancela|cancelar)\b.*\blimpieza\b", t):
            return "CANCELAR_LIMPIEZA"
        intencion_papelera = self.detectar_intencion_papelera(t)
        if intencion_papelera:
            return intencion_papelera
        # Ayuda y supervisor
        if re.search(r"\b(ayuda|comandos|que puedes hacer|opciones)\b.*\bbiblioteca\b", t):
            return "AYUDA_BIBLIOTECA"
        if "supervisor" in t:
            if re.search(r"\b(pausa|pausar|pausalo|suspende|suspender|deten|detener|apaga|apagar|desactiva|desactivar)\b", t):
                return "PAUSAR_SUPERVISOR"
            if re.search(r"\b(reanuda|reanudar|continua|continuar|activa|activar|enciende|encender|inicia|iniciar|arranca)\b", t):
                return "REANUDAR_SUPERVISOR"
            return "ESTADO_SUPERVISOR"
        # Restaurar desde cuarentena
        verbo_restaurar = re.search(r"\b(restaura|restaurar|restaurame|recupera|recuperar|devuelve|devolver)\b", t)
        if verbo_restaurar and not self.contiene_alguna(t, ["recuerdo", "memoria"]):
            return "RESTAURAR_CUARENTENA"
        if re.search(r"\b(saca|sacar)\b.*\bcuarentena\b", t):
            return "RESTAURAR_CUARENTENA"
        # Eliminar definitivamente / plan de eliminación (antes que "limpiar")
        borrar = r"\b(elimina|eliminar|eliminame|borra|borrar|borrame|suprime|suprimir|destruye)\b"
        if re.search(r"\b(vacia|vaciar|vacíala|vaciala)\b.*\bcuarentena\b", t) or (
                re.search(borrar, t) and re.search(r"cuarentena|defectuos|definitivamente|para siempre", t)):
            return "VACIAR_CUARENTENA"
        if re.search(r"plan de (eliminacion|borrado)|eliminacion automatica|borrado automatico|"
                     r"que (se va|vas) a (eliminar|borrar)|cuando (se )?(eliminan|borran|elimina|borra|eliminaras|borraras)", t):
            return "PLAN_ELIMINACION"
        if re.search(r"\b(repara|reparar|reparame|arregla|arreglar|arreglame|corrige|corregir)\b", t) and re.search(
                r"biblioteca|archivo|cancion|musica|audio|adulterad|extension|formato", t):
            return "REPARAR_BIBLIOTECA"
        # Resultado de la limpieza / reparación
        if re.search(r"(resultado|resumen|como (fue|salio|quedo)).*\b(reparacion|arreglo)\b|\bque (reparaste|arreglaste)\b", t):
            return "RESULTADO_LIMPIEZA"
        if re.search(r"(resultado|resumen|como (fue|salio|quedo)).*\blimpieza\b|\bque (limpiaste|moviste)\b", t):
            return "RESULTADO_LIMPIEZA"
        objetos = r"(biblioteca|duplicad|repetid|copias|danad|corrupt|ilegible|no (son |es )?compatible|incompatible|adulterad)"
        es_cola = self.contiene_alguna(t, ["cola", "lista de reproduccion"])
        # Limpiar (pide confirmación en Comandos)
        if not es_cola and re.search(
            r"\b(limpia|limpiar|limpiame|elimina|eliminar|borra|borrar|quita|quitar|"
            r"aparta|apartar|mueve|mover|manda|ordena|ordenar|depura|depurar)\b", t
        ) and (re.search(objetos, t) or "cuarentena" in t):
            return "LIMPIAR_BIBLIOTECA"
        # Revisar / escanear
        if re.search(r"\b(revisa|revisar|analiza|analizar|escanea|escanear|examina|examinar|"
                     r"comprueba|comprobar|verifica|verificar)\b", t) and re.search(
                r"\b(biblioteca|mis canciones|la musica|mi musica|los audios|mis audios|archivos de audio)\b", t):
            return "REVISAR_BIBLIOTECA"
        if "cuarentena" in t:
            return "LISTAR_CUARENTENA"
        if re.search(r"adulterad|disfrazad|incongruen|mal etiquetad|extension (falsa|incorrecta|equivocada|mala)|"
                     r"(falsa|incorrecta|equivocada) extension|extensiones (falsas|incorrectas)", t):
            return "LISTAR_ADULTERADOS"
        if re.search(r"danad|corrupt|ilegible|no (se pueden|puedes|puedo) reproducir", t):
            return "LISTAR_DANADOS_BIBLIOTECA"
        if re.search(r"duplicad|(canciones|archivos|audios|pistas) repetid|copias", t):
            return "LISTAR_DUPLICADOS_BIBLIOTECA"
        if re.search(r"no (son |es |sean |)compatible|incompatible|formatos? (raro|desconocido|que no)", t):
            return "LISTAR_NO_COMPATIBLES_BIBLIOTECA"
        if re.search(r"\b(estado|informe|reporte|resumen|salud|como esta|como va)\b.*\bbiblioteca\b", t):
            return "ESTADO_BIBLIOTECA"
        return None
    def generar_respuesta(self, texto, intencion):
        if intencion == "LLAVE_VOZ":
            return acceso.aviso_llave_voz()
        if intencion == "ESTADO_ACCESO":
            return acceso.estado_texto()
        if intencion == "BLOQUEAR_ACCESO":
            return acceso.bloquear()
        aviso_modo = acceso.bloqueo(intencion)          # control de modo: vale para voz y para terminal
        if aviso_modo:
            return aviso_modo
        if intencion in ("NOMBRES_APRENDIDOS", "OLVIDAR_NOMBRE", "PAUSAR_INICIATIVA", "REANUDAR_INICIATIVA",
                         "CONOCIMIENTO_GENERAL", "NOVEDADES", "EMOCION", "PERSONALIDAD", "SEGURIDAD",
                         "CAMBIAR_VOZ", "ENSENAR_ORDEN", "ORDENES_APRENDIDAS", "EQUILIBRIO", "AUTOCONOCIMIENTO",
                         "SELLAR_CODIGO", "ENSENAR_SINONIMO", "OLVIDAR_SINONIMO", "SINONIMOS_APRENDIDOS",
                         "PLAN_OLVIDO", "OLVIDADOS", "MEMORIA_CORTO", "MEMORIA_LARGO", "OLVIDAR_TEMA",
                         "RECUPERAR_OLVIDADO"):
            return self.responder_iniciativa(intencion, texto)
        if intencion in ("ELOGIO", "REPROCHE"):
            return self.responder_valoracion(intencion)
        if intencion == "SALUDO":
            return self.respuesta_saludo()
        if intencion == "RUTINA_MATUTINA":
            self.ultima_accion = "ejecutar rutina matutina"
            self.rutina_matutina_activa = True
            return self.ejecutar_comando(intencion, texto)
        if intencion == "IDENTIDAD":
            return f"Soy {self.nombre}, su sistema de inteligencia artificial. A sus órdenes, señor."
        if intencion == "HORA":
            from utilidades.reloj import frase_hora
            return frase_hora()
        if intencion == "FECHA":
            return f"Hoy es {datetime.now().strftime('%d/%m/%Y')}."
        if intencion == "ESTADO":
            try:
                cantidad = self.memoria.cantidad_recuerdos()
            except Exception:
                cantidad = 0
            animo = (self.estado_emocional() or {}).get("emocion")
            nombres_animo = {"calma": "en calma", "alegria": "contento", "satisfaccion": "satisfecho",
                             "orgullo": "orgulloso", "curiosidad": "curioso", "aburrimiento": "aburrido",
                             "preocupacion": "preocupado", "frustracion": "frustrado", "confusion": "confundido",
                             "tristeza": "algo desanimado", "miedo": "con miedo"}
            extra = f" Ánimo: {nombres_animo.get(animo, animo)}." if animo else ""
            return f"Todos los sistemas operativos. {cantidad} registros en memoria.{extra}"
        if intencion == "RESUMEN_APRENDIZAJE":
            return self.memoria.resumen_aprendizaje(self.INTENCIONES_BIBLIOTECA)
        if intencion == "CANCION_FAVORITA":
            canciones = self.memoria.cancion_favorita()
            if not canciones:
                return "Sin datos suficientes. Siga escuchando música, señor."
            return f"Canción favorita: {canciones[0]}." + (f" Le siguen: {', '.join(canciones[1:])}." if len(canciones) > 1 else "")
        if intencion == "GUARDAR_MEMORIA":
            return self.procesar_guardar_memoria(texto)
        if intencion == "CONSULTAR_MEMORIA":
            return self.procesar_consultar_memoria()
        if intencion == "BUSCAR_MEMORIA":
            return self.procesar_buscar_memoria(texto)
        acciones = {
            "ABRIR_SITIO_WEB": "abrir sitio web",
            "ABRIR_APLICACION": "abrir aplicación",
            "CERRAR_APLICACION": "cerrar aplicación",
            "CREAR_CARPETA": "crear carpeta",
            "ABRIR_CARPETA": "abrir carpeta",
            "ESTADO_SISTEMA": "consultar sistema",
            "REPRODUCIR_MUSICA": "reproducir música",
            "PAUSAR_MUSICA": "pausar música",
            "REANUDAR_MUSICA": "reanudar música",
            "DETENER_MUSICA": "detener música",
            "SIGUIENTE_CANCION": "siguiente canción",
            "ANTERIOR_CANCION": "canción anterior",
            "ALEATORIO_MUSICA": "modo aleatorio",
            "REPETIR_AUDIO": "repetición musical",
            "ESTADO_REPRODUCTOR": "consultar reproductor",
            "LISTAR_AUDIOS": "listar canciones",
            "MOSTRAR_COLA_AUDIO": "mostrar lista de reproducción",
            "LIMPIAR_COLA_AUDIO": "limpiar lista de reproducción",
            "SUBIR_VOLUMEN": "subir volumen",
            "BAJAR_VOLUMEN": "bajar volumen",
            "ESTADO_BIBLIOTECA": "consultar biblioteca",
            "REVISAR_BIBLIOTECA": "revisar biblioteca",
        }
        if intencion in acciones:
            self.ultima_accion = acciones[intencion]
            return self.ejecutar_comando(intencion, texto)
        if intencion == "DESCARGAR_MUSICA":
            self.ultima_entidad = self.comandos.extraer_cancion_descarga(texto) or None
        if intencion == "QUITAR_COLA_AUDIO":              # no está en INTENCIONES_BIBLIOTECA: se enruta aquí
            self.ultima_accion = "quitar canción de la cola"
            return self.ejecutar_comando(intencion, texto)
        if intencion in self.INTENCIONES_BIBLIOTECA:
            self.ultima_accion = self.INTENCIONES_BIBLIOTECA[intencion]
            return self.ejecutar_comando(intencion, texto)
        if intencion in ("REPRODUCIR_CANCION", "AGREGAR_COLA_AUDIO"):
            nombre = self.extraer_nombre_cancion(texto)
            if not nombre:
                if intencion == "AGREGAR_COLA_AUDIO":
                    self.cola_pendiente = True
                    self.cancion_pendiente = False
                    return "¿Qué canción añado a la cola, señor?"
                self.cancion_pendiente = True
                self.cola_pendiente = False
                return "¿Qué canción reproduzco, señor?"
            self.ultima_accion = (
                "reproducir canción"
                if intencion == "REPRODUCIR_CANCION"
                else "agregar canción a la lista de reproducción"
            )
            self.ultima_entidad = nombre
            return self.ejecutar_comando(intencion, nombre)
        if intencion == "ESTABLECER_VOLUMEN":
            volumen = self.extraer_porcentaje_volumen(texto)
            if volumen is None:
                self.volumen_pendiente = True
                return "¿Volumen objetivo, señor? Indique el porcentaje."
            self.ultima_accion, self.ultima_entidad = "establecer volumen", str(volumen)
            return self.ejecutar_comando(intencion, f"volumen {volumen}")
        if intencion in ("SILENCIAR", "QUITAR_SILENCIO"):
            return self.controlar_silencio(intencion)
        if intencion == "AYUDA":
            from utilidades import catalogo
            return catalogo.listado_completo(acceso.modo())
        return self.generar_respuesta_desconocida(texto)
    def ejecutar_comando(self, intencion, texto):
        try:
            respuesta = self.comandos.ejecutar(intencion, texto)
            if not respuesta:
                return "Acción procesada. Sin respuesta del módulo."
            if intencion == "RUTINA_MATUTINA":
                self.rutina_matutina_activa = False
            return respuesta
        except Exception as error:
            print(f"[CEREBRO] Error ejecutando {intencion}: {error}")
            if intencion == "RUTINA_MATUTINA":
                self.rutina_matutina_activa = False
            return "Orden recibida, pero la ejecución falló."
    def controlar_silencio(self, intencion):
        reproductor = getattr(self.comandos, "reproductor", None)
        if reproductor is None:
            return "Reproductor fuera de línea."
        try:
            if intencion == "SILENCIAR":
                if self.volumen_antes_silencio is None:
                    self.volumen_antes_silencio = reproductor.obtener_volumen()
                if reproductor.establecer_volumen(0.0):
                    return "Audio silenciado."
                return "Negativo. No fue posible silenciar el audio."
            if self.volumen_antes_silencio is None:
                return "El audio no está silenciado."
            volumen = max(0, min(100, int(self.volumen_antes_silencio)))
            if reproductor.establecer_volumen(volumen / 100):
                self.volumen_antes_silencio = None
                return f"Audio restablecido. Volumen al {volumen} %."
            return "Negativo. No fue posible restaurar el volumen."
        except Exception as error:
            print(f"[CEREBRO] Error controlando silencio: {error}")
            return "Negativo. No fue posible cambiar el audio."
    def respuesta_saludo(self):
        respuestas = [
            f"{self.nombre} en línea. Todos los sistemas operativos, señor.",
            "A sus órdenes, señor.",
            "Listo para recibir órdenes.",
            "Sistemas en verde. Esperando instrucciones.",
            "En espera, señor. Proceda.",
            f"{self.nombre} operativo. Adelante.",
            "Todo listo. ¿Cuál es la misión?",
            "Atento, señor.",
        ]
        return self.seleccionar_respuesta_contextual(respuestas)
    def generar_respuesta_desconocida(self, texto):
        texto = self.normalizar_texto(texto)
        if self.contiene_alguna(texto, ["abre", "abrir", "abreme", "puedes abrir"]):
            return "¿Qué abro, señor?"
        if self.contiene_alguna(texto, ["cierra", "cerrar", "puedes cerrar"]):
            return "¿Qué aplicación cierro, señor?"
        if self.contiene_alguna(texto, ["crea", "crear", "haz una carpeta", "hazme una carpeta"]):
            return "Indique el nombre de la carpeta."
        if self.contiene_alguna(texto, ["recuerda", "guarda", "memoriza"]):
            return "Indique qué debo registrar en memoria."
        if self.es_pregunta_contextual_corta(texto):
            contexto = self.obtener_contexto_semantico()
            if contexto:
                return f"Entiendo: {contexto}. Precise la consulta."
        if self.ultimo_tema and self.parece_pregunta(texto):
            return f"Tema detectado: {self.ultimo_tema}. Puedo consultarlo en memoria."
        if self.parece_pregunta(texto):
            return self.respuesta_no_entendi_pregunta()
        if self.parece_orden(texto):
            return "Orden no identificada. Repita, señor."
        return self.respuesta_no_entendi_general()
    def respuesta_no_entendi_pregunta(self):
        respuestas = [
            "Pregunta no comprendida. Reformule, señor.",
            "Faltan datos. Precise la pregunta.",
            "No identifico la información requerida.",
            "Consulta ambigua. Repita de otra forma.",
        ]
        return self.seleccionar_respuesta_contextual(respuestas)
    def respuesta_no_entendi_general(self):
        respuestas = [
            "Negativo. Orden no comprendida.",
            "Instrucción no reconocida. Repita, señor.",
            "Información insuficiente para actuar.",
            "Solicitud fuera de mis protocolos actuales.",
            "No puedo determinar la acción. Precise la orden.",
            "Orden ambigua. Necesito más detalle.",
        ]
        return self.seleccionar_respuesta_contextual(respuestas)
    def seleccionar_respuesta_contextual(self, respuestas):
        if not respuestas:
            return "Orden no comprendida."
        disponibles = [r for r in respuestas if r != self.ultima_respuesta] or respuestas
        indice = (len(self.contexto) + len(self.ultima_entrada or "")) % len(disponibles)
        return disponibles[indice]
    def parece_pregunta(self, texto):
        palabras = [
            "que", "como", "cuando", "donde", "porque", "por que", "cual",
            "cuales", "quien", "cuanto", "cuantos", "puedes", "sabes",
        ]
        if "?" in texto:
            return True
        palabras_texto = texto.split()
        return bool(palabras_texto) and palabras_texto[0] in palabras
    def parece_orden(self, texto):
        verbos = [
            "abre", "abrir", "cierra", "cerrar", "crea", "crear", "ejecuta",
            "ejecutar", "inicia", "iniciar", "pon", "reproduce", "reproducir",
            "pausa", "reanuda", "deten", "detener", "siguiente", "anterior",
            "agrega", "agregar", "anade", "meter", "mete", "haz", "hacer",
            "dime", "muestrame", "muestra", "guarda", "recuerda", "sube", "subir",
            "baja", "bajar", "aumenta", "aumentar", "disminuye", "disminuir",
            "reduce", "reducir", "silencia", "silenciar", "empieza", "comienza",
            "activa", "activar", "realiza",
        ]
        return any(texto.startswith(v) or f" {v} " in texto for v in verbos)
    def es_pregunta_contextual_corta(self, texto):
        palabras = texto.split()
        frases = [
            "y para que", "y eso", "y porque", "y por que", "por que", "porque",
            "como", "y como", "y despues", "y luego", "para que", "que pasa",
            "y entonces",
        ]
        return texto in frases or (len(palabras) <= 4 and any(texto.startswith(f) for f in frases))
    def obtener_contexto_semantico(self):
        if self.ultimo_tema:
            return self.ultimo_tema
        for elemento in reversed(self.contexto):
            if elemento.get("rol") == "usuario":
                tema = self.extraer_tema_memoria(elemento.get("contenido", ""))
                if tema:
                    return tema
        return None
    def procesar_guardar_memoria(self, texto):
        contenido = self.extraer_contenido_memoria(texto)
        if not contenido:
            return "¿Qué registro en memoria, señor?"
        if seguridad.es_peligroso(contenido):
            return "Negativo. No registro órdenes de sistema en memoria, por seguridad."
        contenido = seguridad.sanear_conocimiento(contenido, 400)
        tema = self.detectar_tema_memoria(contenido)
        self.ultimo_tema = tema
        try:
            guardado = self.memoria.guardar_recuerdo(contenido, categoria=tema)
        except Exception as error:
            print(f"[CEREBRO] Error guardando memoria: {error}")
            guardado = False
        if not guardado and getattr(self.memoria, "ultimo_error", "") == "disco":
            return "Negativo, señor. No queda espacio en el disco para guardar recuerdos nuevos."
        return (f"Registrado: {contenido}." if guardado else "Negativo. Fallo al guardar en memoria.")
    def extraer_contenido_memoria(self, texto):
        texto = self.normalizar_texto(texto)
        patrones = [
            "quiero que recuerdes", "quiero que guardes", "recuerda que",
            "recuerda mi", "recuerda mis", "recuerda el", "recuerda la",
            "recuerda los", "recuerda las", "recuerda esto", "guarda esto",
            "guarda que", "memoriza esto", "memoriza que", "no olvides que",
            "ten presente que", "anota que",
        ]
        for patron in patrones:
            if texto.startswith(patron):
                texto = texto[len(patron):].strip()
                break
        return texto.lstrip(":,.- ").strip(" .,!¡¿?")
    def detectar_tema_memoria(self, contenido):
        texto = self.normalizar_texto(contenido)
        temas = {
            "proyecto": ["mi proyecto", "el proyecto", "proyecto"],
            "programa": ["mi programa", "el programa", "programa"],
            "aplicacion": ["mi aplicacion", "la aplicacion", "aplicacion"],
            "asistente": ["mi asistente", "el asistente", "asistente"],
            "trabajo": ["mi trabajo", "el trabajo", "trabajo"],
            "estudio": ["mi estudio", "mis estudios", "estudio"],
            "musica": ["mi musica", "musica"],
            "computadora": ["mi computadora", "mi pc", "computadora", "pc"],
        }
        for tema, palabras in temas.items():
            if any(p in texto for p in palabras):
                return tema
        return "general"
    def procesar_consultar_memoria(self):
        try:
            recuerdos = self.memoria.obtener_recuerdos()
        except Exception as error:
            print(f"[CEREBRO] Error consultando memoria: {error}")
            return "Negativo. Memoria no accesible."
        if not recuerdos:
            return "Memoria vacía. Sin registros."
        self.tema_memoria_pendiente = True
        return "¿Qué tema consulto en memoria?"
    def procesar_buscar_memoria(self, texto):
        tema = self.extraer_tema_memoria(texto)
        if tema:
            self.ultimo_tema = tema
            return self.buscar_recuerdos_por_tema(tema)
        if self.es_pregunta_contextual_corta(texto) and self.ultimo_tema:
            return self.buscar_recuerdos_por_tema(self.ultimo_tema)
        consulta = self.extraer_consulta_memoria(texto)
        if not consulta:
            if self.ultimo_tema:
                return self.buscar_recuerdos_por_tema(self.ultimo_tema)
            self.tema_memoria_pendiente = True
            return "¿Qué tema busco en memoria?"
        try:
            resultados = self.memoria.recuperar_relevantes(consulta)
        except Exception:
            try:
                resultados = self.memoria.buscar_recuerdo(consulta)
            except Exception:
                resultados = []
        if not resultados:
            return f"Sin registros sobre '{consulta}'."
        return self.formatear_recuerdos_relevantes(resultados, consulta)
    def extraer_tema_memoria(self, texto):
        texto = self.normalizar_texto(texto)
        patrones = [
            "que recuerdas de ", "que recuerdas sobre ", "que recuerdas acerca de ",
            "te acuerdas de ", "te acuerdas sobre ", "te acuerdas acerca de ",
            "que sabes sobre ", "que sabes de ", "que tienes sobre ", "que tienes de ",
            "sobre ", "acerca de ", "de ",
        ]
        resto = ""
        for patron in patrones:
            if patron in texto:
                partes = texto.split(patron, 1)
                if len(partes) == 2:
                    resto = partes[1].strip()
                    break
        if not resto:
            return None
        eliminar = ["mi", "mis", "el", "la", "los", "las", "un", "una"]
        palabras = [p for p in resto.strip(" .,!¡¿?").split() if p not in eliminar]
        if not palabras:
            return None
        tema = " ".join(palabras)
        equivalencias = {
            "proyecto": "proyecto", "proyectos": "proyecto",
            "programa": "programa", "programas": "programa",
            "aplicacion": "aplicacion", "aplicaciones": "aplicacion",
            "asistente": "asistente", "asistentes": "asistente",
            "trabajo": "trabajo", "estudio": "estudio", "estudios": "estudio",
            "musica": "musica", "computadora": "computadora",
            "computadoras": "computadora", "pc": "computadora",
        }
        return equivalencias.get(tema, tema)
    def interpretar_tema_contextual(self, texto):
        texto = self.normalizar_texto(texto)
        equivalencias = {
            "proyecto": "proyecto", "el proyecto": "proyecto", "mi proyecto": "proyecto",
            "programa": "programa", "el programa": "programa", "mi programa": "programa",
            "aplicacion": "aplicacion", "la aplicacion": "aplicacion", "mi aplicacion": "aplicacion",
            "asistente": "asistente", "el asistente": "asistente", "mi asistente": "asistente",
            "computadora": "computadora", "la computadora": "computadora",
            "mi computadora": "computadora", "mi pc": "computadora", "pc": "computadora",
            "musica": "musica", "la musica": "musica", "mi musica": "musica",
        }
        if texto in equivalencias:
            return equivalencias[texto]
        if self.ultimo_tema and len(texto.split()) <= 3:
            return self.ultimo_tema
        return None
    def buscar_recuerdos_por_tema(self, tema):
        tema = self.normalizar_texto(tema).strip()
        if not tema:
            self.tema_memoria_pendiente = True
            return "¿Qué tema consulto en memoria?"
        self.ultimo_tema = tema
        try:
            resultados = self.memoria.buscar_por_tema(tema)
            if not resultados:
                resultados = self.memoria.buscar_recuerdo(tema)
        except Exception as error:
            print(f"[CEREBRO] Error buscando memoria temática: {error}")
            resultados = []
        if not resultados:
            return f"Sin registros sobre {tema}."
        relevantes = self.seleccionar_recuerdos_relevantes(resultados, tema)
        if not relevantes:
            return f"Sin registros relevantes sobre {tema}."
        contenidos = [
            str(r.get("contenido", "")).strip()
            for r in relevantes[:2]
            if str(r.get("contenido", "")).strip()
        ]
        if not contenidos:
            return f"Sin información útil sobre {tema}."
        return (
            f"Registro: {contenidos[0]}."
            if len(contenidos) == 1
            else f"Registros: {contenidos[0]}; {contenidos[1]}."
        )
    def seleccionar_recuerdos_relevantes(self, recuerdos, tema):
        if not recuerdos:
            return []
        tema = self.normalizar_texto(tema).strip()
        palabras_tema = {p for p in tema.split() if len(p) > 2}
        candidatos = []
        indicadores = [
            "se llama", "es", "esta hecho", "esta desarrollado", "utiliza",
            "usa", "tiene", "consiste", "trabaja con", "funciona con",
        ]
        for recuerdo in recuerdos:
            original = str(recuerdo.get("contenido", "")).strip()
            if not original:
                continue
            contenido = self.normalizar_texto(original)
            puntuacion = 50 if tema and tema in contenido else 0
            puntuacion += len(palabras_tema & {p for p in contenido.split() if len(p) > 2}) * 15
            categoria = self.normalizar_texto(str(recuerdo.get("categoria", "")))
            puntuacion += 40 if categoria == tema else 20 if categoria and categoria in palabras_tema else 0
            puntuacion += 15 if len(original) >= 30 else 8 if len(original) >= 15 else -10 if len(original) < 8 else 0
            puntuacion += sum(5 for indicador in indicadores if indicador in contenido)
            candidatos.append({"recuerdo": recuerdo, "puntuacion": puntuacion})
        if not candidatos:
            return []
        candidatos.sort(
            key=lambda e: (
                e["puntuacion"],
                len(e["recuerdo"].get("contenido", "")),
            ),
            reverse=True,
        )
        mejor = candidatos[0]
        seleccionados = [mejor["recuerdo"]]
        if len(candidatos) > 1:
            segundo = candidatos[1]
            a = self.normalizar_texto(mejor["recuerdo"].get("contenido", ""))
            b = self.normalizar_texto(segundo["recuerdo"].get("contenido", ""))
            if (
                segundo["puntuacion"] >= 45
                and mejor["puntuacion"] - segundo["puntuacion"] <= 20
                and b not in a and a not in b
            ):
                seleccionados.append(segundo["recuerdo"])
        return seleccionados[:2]
    def formatear_recuerdos_relevantes(self, recuerdos, tema=""):
        if not recuerdos:
            return f"Sin registros sobre {tema}." if tema else "Sin registros relevantes."
        if tema:
            recuerdos = self.seleccionar_recuerdos_relevantes(recuerdos, tema)
        contenidos, vistos = [], set()
        for recuerdo in recuerdos[:2]:
            contenido = str(recuerdo.get("contenido", "")).strip()
            clave = self.normalizar_texto(contenido)
            if contenido and clave not in vistos:
                vistos.add(clave)
                contenidos.append(contenido)
        if not contenidos:
            return "Sin información relevante en memoria."
        if len(contenidos) == 1:
            return f"Registro: {contenidos[0]}."
        if tema:
            return f"Sobre {tema}: {contenidos[0]}; {contenidos[1]}."
        return f"Registros: {contenidos[0]}; {contenidos[1]}."
    def extraer_consulta_memoria(self, texto):
        consulta = self.normalizar_texto(texto).strip()
        patrones = [
            "te acuerdas de", "te acuerdas", "recuerdas que", "recuerdas mi",
            "recuerdas mis", "recuerdas el", "recuerdas la", "recuerdas",
            "se acuerda de", "se acuerda del", "se acuerda",
        ]
        for patron in patrones:
            if consulta.startswith(patron):
                consulta = consulta[len(patron):].strip()
                break
        consulta = consulta.strip(" .,!¡¿?")
        consulta = re.sub(r"^(de|sobre|acerca de)\s+", "", consulta)
        return re.sub(r"^(mi|mis|el|la|los|las)\s+", "", consulta)
    def agregar_contexto(self, rol, contenido):
        """Memoria a corto plazo: lo dicho en la última media hora (o el tiempo de configuracion) y como mucho N frases."""
        ahora = datetime.now()
        self.contexto.append({"rol": rol, "contenido": contenido, "momento": ahora.isoformat(),})
        minutos = getattr(configuracion, "MEMORIA_CORTO_MINUTOS", 45)
        self.contexto = [e for e in self.contexto if self._en_corto_plazo(e, ahora, minutos)]
        if len(self.contexto) > self.maximo_contexto:
            self.contexto.pop(0)

    @staticmethod
    def _en_corto_plazo(elemento, ahora, minutos):
        try:
            return (ahora - datetime.fromisoformat(elemento.get("momento", ""))).total_seconds() <= minutos * 60
        except (ValueError, TypeError, AttributeError):
            return True
    def olvidar_contexto(self):
        """Borra la conversación reciente (corto plazo). La memoria a largo plazo no se toca."""
        self.contexto = []
        self.ultima_entrada = self.ultima_respuesta = self.ultima_intencion = None
        self.ultimo_tema = self.ultima_accion = self.ultima_entidad = None
        self._ultima_desconocida = None
        self.__dict__.pop("contexto_ordenes", None)
    def guardar_respuesta(self, respuesta):
        self.ultima_respuesta = respuesta
        self.agregar_contexto("miller", respuesta)
        self.aprender(respuesta)
    def aprender(self, respuesta):
        """Todo lo que pasa (orden, resultado, música, volumen, programas...) alimenta la memoria de aprendizaje."""
        aprender = getattr(self.memoria, "aprender", None)
        if not callable(aprender):
            return
        contexto = {"fuente_internet": " Fuente: " in str(respuesta)}
        reproductor = getattr(self.comandos, "reproductor", None)
        try:
            if reproductor is not None:
                contexto["cancion_actual"] = reproductor.obtener_nombre_actual()
                contexto["volumen"] = reproductor.obtener_volumen()
        except Exception:
            pass
        aprender(self.ultima_entrada, self.ultima_intencion, respuesta, self.ultima_entidad, contexto)
        emociones = getattr(self, "emociones", None)
        if emociones is not None:                       # cada experiencia también se siente
            try:
                fallo = getattr(self.memoria, "_FALLO", None)
                ok = not (fallo and fallo.match(self.memoria.normalizar_texto(respuesta)))
                emociones.registrar_orden(self.ultima_intencion, self.ultima_entrada, respuesta, ok)
            except Exception as error:
                print(f"[CEREBRO] Emociones: {error}")
    def obtener_ultimos_mensajes(self, cantidad=6):
        return self.contexto[-cantidad:] if cantidad > 0 else []
    def obtener_contexto(self):
        return self.contexto.copy()
    def obtener_ultima_intencion(self):
        return self.ultima_intencion
    def obtener_ultima_entrada(self):
        return self.ultima_entrada
    def obtener_ultima_respuesta(self):
        return self.ultima_respuesta
    def rutina_matutina_en_ejecucion(self):
        return self.rutina_matutina_activa
    def debe_cerrar(self):
        return not self.activo
    def debe_salir(self, texto=None):
        return self.debe_cerrar()
    def cerrar(self):
        """Detiene el cerebro y delega el cierre ordenado de los módulos."""
        self.activo = False
        iniciativa, self.iniciativa = getattr(self, "iniciativa", None), None
        if iniciativa is not None:
            try:
                iniciativa.detener()
            except Exception as error:
                print(f"[CEREBRO] Error deteniendo la iniciativa: {error}")
        necesidades = getattr(self, "necesidades", None)
        if necesidades is not None:
            try:
                necesidades.detener()
            except Exception as error:
                print(f"[CEREBRO] Error guardando las necesidades: {error}")
        emociones, self.emociones = getattr(self, "emociones", None), None
        if emociones is not None:
            try:
                emociones.detener()
            except Exception as error:
                print(f"[CEREBRO] Error guardando las emociones: {error}")
        try:
            self.memoria.finalizar_sesion()
        except Exception as error:
            print(f"[CEREBRO] Error guardando el aprendizaje: {error}")
        cerrar_comandos = getattr(self.comandos, "cerrar", None)
        if callable(cerrar_comandos):
            try:
                cerrar_comandos()
            except Exception as error:
                print(f"[CEREBRO] Error cerrando comandos: {error}")
