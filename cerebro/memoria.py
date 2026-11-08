"""MILLER · Sistema de memoria persistente."""
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from difflib import SequenceMatcher
from functools import lru_cache
from utilidades import seguridad

def _ruta_memoria_defecto():
    try:
        from configuracion import RUTA_MEMORIA
        return RUTA_MEMORIA
    except Exception:
        return Path(__file__).resolve().parent.parent / "datos" / "memoria.json"


@lru_cache(maxsize=4096)
def _normalizar(texto):
    texto = unicodedata.normalize("NFD", str(texto).strip().lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = re.sub(r"[.,;:!?¡¿]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()

class Memoria:
    PORCENTAJE_SIMILITUD = 0.85
    MAX_RECUERDOS_RELEVANTES = 5
    MAX_RECUERDOS_GENERALES = 5
    def __init__(self, ruta=None):
        self.ruta = Path(ruta) if ruta else _ruta_memoria_defecto()
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.memoria = []
        self.aprendizaje = self._aprendizaje_vacio()
        self.cargar()
    def cargar(self):
        try:
            if not self.ruta.exists():
                self.memoria = []
                self.guardar_archivo()
                return
            contenido = seguridad.leer_json(self.ruta, None)
            if isinstance(contenido, list):              # formato antiguo: solo recuerdos
                self.memoria = contenido
                self.normalizar_recuerdos_antiguos()
                self.guardar_archivo()
            elif isinstance(contenido, dict):
                self.memoria = [r for r in contenido.get("recuerdos", []) if isinstance(r, dict)]
                self.aprendizaje = contenido.get("aprendizaje")
                self._aprendizaje()
                self.normalizar_recuerdos_antiguos()
            else:
                self.memoria = []
        except Exception as error:
            print(f"[MEMORIA] Error cargando: {error}")
            self.memoria = []
            try:                                          # conserva el archivo dañado en lugar de pisarlo
                if self.ruta.exists():
                    self.ruta.replace(self.ruta.with_name(f"memoria_corrupta_{datetime.now():%Y%m%d_%H%M%S}.json"))
            except OSError:
                pass
    def normalizar_recuerdos_antiguos(self):
        cambios = False
        for recuerdo in self.memoria:
            if "importancia" not in recuerdo:
                recuerdo["importancia"] = 1.0
                cambios = True
            if "frecuencia" not in recuerdo:
                recuerdo["frecuencia"] = 0
                cambios = True
            if "ultimo_acceso" not in recuerdo:
                recuerdo["ultimo_acceso"] = recuerdo.get("fecha", datetime.now().isoformat())
                cambios = True
            if "categoria" not in recuerdo:
                recuerdo["categoria"] = "general"
                cambios = True
        if cambios:
            self.guardar_archivo()
    def guardar_archivo(self):
        try:
            datos = {"version": 2, "recuerdos": self.memoria, "aprendizaje": self._aprendizaje(),
                     "actualizada": datetime.now().isoformat(timespec="seconds")}
            seguridad.escribir_json(self.ruta, datos)
            self._pendientes_guardar = 0
            return True
        except Exception as error:
            print(f"[MEMORIA] Error guardando: {error}")
            return False
    def normalizar_texto(self, texto):
        return _normalizar(texto) if texto is not None else ""
    def obtener_palabras(self, texto):
        texto = self.normalizar_texto(texto)
        return texto.split() if texto else []
    def calcular_similitud(self, texto1, texto2):
        """Devuelve una similitud entre 0.0 y 1.0."""
        texto1, texto2 = self.normalizar_texto(texto1), self.normalizar_texto(texto2)
        if not texto1 or not texto2:
            return 0.0
        if texto1 == texto2:
            return 1.0
        directa = SequenceMatcher(None, texto1, texto2).ratio()
        palabras1, palabras2 = set(self.obtener_palabras(texto1)), set(self.obtener_palabras(texto2))
        similitud_palabras = len(palabras1 & palabras2) / len(palabras1 | palabras2) if palabras1 and palabras2 else 0.0
        return directa * 0.65 + similitud_palabras * 0.35
    def uno_contiene_al_otro(self, texto1, texto2):
        """Detecta si un recuerdo es una versión incompleta del otro."""
        texto1, texto2 = self.normalizar_texto(texto1), self.normalizar_texto(texto2)
        return bool(texto1 and texto2 and (texto1 in texto2 or texto2 in texto1))
    def es_mas_completo(self, nuevo, existente):
        nuevo, existente = self.normalizar_texto(nuevo), self.normalizar_texto(existente)
        palabras_nuevo, palabras_existente = len(nuevo.split()), len(existente.split())
        if palabras_nuevo != palabras_existente:
            return palabras_nuevo > palabras_existente
        return len(nuevo) > len(existente)
    def buscar_similar(self, contenido, categoria="general"):
        contenido, categoria = self.normalizar_texto(contenido), self.normalizar_texto(categoria)
        resultados = []
        for recuerdo in self.memoria:
            existente = recuerdo.get("contenido", "")
            categoria_existente = self.normalizar_texto(recuerdo.get("categoria", "general"))
            if categoria and categoria != "general" and categoria_existente != categoria:
                continue
            similitud = self.calcular_similitud(contenido, existente)
            contiene = self.uno_contiene_al_otro(contenido, existente)
            if similitud >= self.PORCENTAJE_SIMILITUD or contiene:
                resultados.append({"recuerdo": recuerdo, "similitud": similitud})
        return resultados
    def obtener_nuevo_id(self):
        ids = []
        for recuerdo in self.memoria:
            try:
                ids.append(int(recuerdo.get("id", 0)))
            except (ValueError, TypeError):
                pass
        return max(ids) + 1 if ids else 1
    def guardar_recuerdo(self, contenido, categoria="general"):
        self.ultimo_error = ""
        if seguridad.es_peligroso(contenido):
            seguridad.alerta("Recuerdo rechazado: contenía órdenes de sistema.")
            return False
        contenido = seguridad.sanear_conocimiento(contenido, 400)
        categoria = seguridad.sanear_conocimiento(categoria, 40)
        contenido, categoria = self.normalizar_texto(contenido), self.normalizar_texto(categoria)
        if not contenido:
            return False
        if not categoria:
            categoria = "general"
        similares = self.buscar_similar(contenido, categoria)
        if similares:
            similares.sort(key=lambda elemento: elemento["similitud"], reverse=True)
            for elemento in similares:
                existente = elemento["recuerdo"]
                contenido_existente = existente.get("contenido", "")
                if self.es_mas_completo(contenido, contenido_existente):
                    existente["contenido"] = contenido
                    existente["categoria"] = categoria
                    existente["fecha"] = datetime.now().isoformat()
                    existente["importancia"] = max(float(existente.get("importancia", 1.0)), 1.0)
                    print("[MEMORIA] Recuerdo actualizado con información más completa.")
                    return self.guardar_archivo()
                print("[MEMORIA] Recuerdo similar detectado. Se conserva el más completo.")
                return True
        if not self._hay_margen():
            self.ultimo_error = "disco"
            print("[MEMORIA] Sin margen en el disco: no guardo recuerdos nuevos.")
            return False
        ahora = datetime.now().isoformat()
        self.memoria.append({
            "id": self.obtener_nuevo_id(),
            "contenido": contenido,
            "categoria": categoria,
            "fecha": ahora,
            "importancia": 1.0,
            "frecuencia": 0,
            "ultimo_acceso": ahora
        })
        print("[MEMORIA] Nuevo recuerdo guardado.")
        return self.guardar_archivo()
    @staticmethod
    def _hay_margen():
        try:
            from utilidades import cuota
            return cuota.puede_guardar(4096)
        except Exception:
            return True

    def guardar_recuerdo_tema(self, contenido, tema="general"):
        return self.guardar_recuerdo(contenido, tema)
    def registrar_acceso(self, recuerdo):
        if not recuerdo:
            return
        try:
            frecuencia = int(recuerdo.get("frecuencia", 0))
        except (ValueError, TypeError):
            frecuencia = 0
        recuerdo["frecuencia"] = frecuencia + 1
        recuerdo["ultimo_acceso"] = datetime.now().isoformat()
        try:
            importancia = float(recuerdo.get("importancia", 1.0))
        except (ValueError, TypeError):
            importancia = 1.0
        recuerdo["importancia"] = min(importancia + 0.05, 2.0)
    def calcular_recencia(self, recuerdo):
        fecha_texto = recuerdo.get("ultimo_acceso", recuerdo.get("fecha", ""))
        try:
            fecha = datetime.fromisoformat(fecha_texto)
        except (ValueError, TypeError):
            return 0.5
        dias = max((datetime.now() - fecha).total_seconds() / 86400, 0)
        return 1 / (1 + dias / 30)
    def calcular_relevancia(self, recuerdo, consulta=""):
        contenido = self.normalizar_texto(recuerdo.get("contenido", ""))
        consulta = self.normalizar_texto(consulta)
        if consulta:
            similitud = self.calcular_similitud(contenido, consulta)
            palabras_consulta = set(self.obtener_palabras(consulta))
            palabras_contenido = set(self.obtener_palabras(contenido))
            coincidencia = len(palabras_consulta & palabras_contenido) / len(palabras_consulta) if palabras_consulta else 0.0
        else:
            similitud = coincidencia = 0.0
        try:
            importancia = float(recuerdo.get("importancia", 1.0))
        except (ValueError, TypeError):
            importancia = 1.0
        importancia = min(importancia / 2.0, 1.0)
        try:
            frecuencia = int(recuerdo.get("frecuencia", 0))
        except (ValueError, TypeError):
            frecuencia = 0
        frecuencia = min(frecuencia / 10.0, 1.0)
        recencia = self.calcular_recencia(recuerdo)
        if consulta:
            return (similitud * 0.35 + coincidencia * 0.35 +
                    importancia * 0.12 + frecuencia * 0.08 + recencia * 0.10)
        return importancia * 0.45 + frecuencia * 0.25 + recencia * 0.30
    def recuperar_relevantes(self, consulta="", limite=None):
        if limite is None:
            limite = self.MAX_RECUERDOS_RELEVANTES
        try:
            limite = int(limite)
        except (ValueError, TypeError):
            limite = self.MAX_RECUERDOS_RELEVANTES
        limite = max(limite, 1)
        candidatos = [
            {"recuerdo": recuerdo, "relevancia": self.calcular_relevancia(recuerdo, consulta)}
            for recuerdo in self.memoria
        ]
        candidatos.sort(key=lambda elemento: elemento["relevancia"], reverse=True)
        resultados = []
        for elemento in candidatos[:limite]:
            recuerdo = elemento["recuerdo"]
            self.registrar_acceso(recuerdo)
            resultados.append(recuerdo)
        if resultados:
            self.guardar_archivo()
        return resultados
    def recuperar_por_tema(self, tema, limite=None):
        tema = self.normalizar_texto(tema)
        if not tema:
            return []
        if limite is None:
            limite = self.MAX_RECUERDOS_RELEVANTES
        candidatos = []
        for recuerdo in self.memoria:
            categoria = self.normalizar_texto(recuerdo.get("categoria", ""))
            contenido = self.normalizar_texto(recuerdo.get("contenido", ""))
            categoria_exacta = categoria == tema
            if not categoria_exacta and tema not in contenido:
                continue
            puntuacion = self.calcular_relevancia(recuerdo, tema)
            if categoria_exacta:
                puntuacion += 0.25
            candidatos.append({"recuerdo": recuerdo, "relevancia": puntuacion})
        candidatos.sort(key=lambda elemento: elemento["relevancia"], reverse=True)
        resultados = []
        for elemento in candidatos[:limite]:
            recuerdo = elemento["recuerdo"]
            self.registrar_acceso(recuerdo)
            resultados.append(recuerdo)
        if resultados:
            self.guardar_archivo()
        return resultados
    def obtener_recuerdos(self):
        return self.memoria.copy()
    def obtener_por_tema(self, tema):
        tema = self.normalizar_texto(tema)
        if not tema:
            return []
        return [
            recuerdo for recuerdo in self.memoria
            if self.normalizar_texto(recuerdo.get("categoria", "")) == tema
        ]
    def buscar_recuerdo(self, consulta):
        consulta = self.normalizar_texto(consulta)
        if not consulta:
            return []
        return [
            recuerdo for recuerdo in self.memoria
            if consulta in self.normalizar_texto(recuerdo.get("contenido", ""))
            or consulta in self.normalizar_texto(recuerdo.get("categoria", ""))
        ]
    def buscar_por_tema(self, tema):
        tema = self.normalizar_texto(tema)
        if not tema:
            return []
        resultados = [
            recuerdo for recuerdo in self.memoria
            if self.normalizar_texto(recuerdo.get("categoria", "")) == tema
        ]
        if resultados:
            return resultados
        return [
            recuerdo for recuerdo in self.memoria
            if tema in self.normalizar_texto(recuerdo.get("categoria", ""))
            or tema in self.normalizar_texto(recuerdo.get("contenido", ""))
        ]
    def obtener_temas(self):
        temas = []
        for recuerdo in self.memoria:
            categoria = self.normalizar_texto(recuerdo.get("categoria", "general"))
            if categoria and categoria not in temas:
                temas.append(categoria)
        return temas
    def existe_tema(self, tema):
        tema = self.normalizar_texto(tema)
        if not tema:
            return False
        return any(self.normalizar_texto(recuerdo.get("categoria", "")) == tema for recuerdo in self.memoria)
    def formatear_recuerdos(self, recuerdos):
        if not recuerdos:
            return ""
        frases = []
        for recuerdo in recuerdos:
            contenido = str(recuerdo.get("contenido", "")).strip()
            if contenido:
                frases.append(contenido)
        return frases
    def resumen_tema(self, tema):
        recuerdos = self.recuperar_por_tema(tema, self.MAX_RECUERDOS_RELEVANTES)
        if not recuerdos:
            return []
        return self.formatear_recuerdos(recuerdos)
    def cantidad_recuerdos(self):
        return len(self.memoria)
    def cantidad_por_tema(self, tema):
        return len(self.buscar_por_tema(tema))
    def limpiar(self):
        self.memoria = []
        return self.guardar_archivo()
    MAX_HISTORIAL, MAX_LISTA, MAX_FRASES = 150, 30, 8
    _FALLO = re.compile(r"^(negativo|fallo|sin conexion|error|orden no|instruccion no|pregunta no|solicitud fuera|"
                        r"informacion insuficiente|no puedo|no identifico|consulta ambigua|orden ambigua|faltan datos)")
    @staticmethod
    def _aprendizaje_vacio():
        return {"sesiones": {"total": 0, "inicio_actual": None, "ultima_fin": None, "minutos_totales": 0.0},
                "comandos": {}, "horario": {}, "dias": {}, "musica": {"pedidas": {}, "escuchadas": {}, "artistas": {},
                "volumen": {"promedio": None, "muestras": 0}, "descargas": []}, "aplicaciones": {}, "sitios": {},
                "internet": [], "no_entendidas": {}, "errores": [], "historial": [], "alias": {}, "candidatos_alias": {}, "sinonimos": {}, "candidatos_sinonimos": {}, "olvidados": [], "ultimo_olvido": {}}
    def _aprendizaje(self):
        base = self._aprendizaje_vacio()
        datos = getattr(self, "aprendizaje", None)
        if not isinstance(datos, dict):
            self.aprendizaje = base
            return base
        for clave, valor in base.items():             # completa claves que falten (versiones anteriores)
            if not isinstance(datos.get(clave), type(valor)):
                datos[clave] = valor
        for clave, valor in base["musica"].items():
            if not isinstance(datos["musica"].get(clave), type(valor)):
                datos["musica"][clave] = valor
        return datos
    @staticmethod
    def _sumar(diccionario, clave, limite=200):
        clave = str(clave or "").strip()[:120]
        if not clave:
            return
        diccionario[clave] = diccionario.get(clave, 0) + 1
        if len(diccionario) > limite:                 # conserva solo lo más frecuente
            for k, _ in sorted(diccionario.items(), key=lambda x: x[1])[:len(diccionario) - limite]:
                diccionario.pop(k, None)
    def _recortar(self, lista, maximo=None):
        maximo = maximo or self.MAX_LISTA
        del lista[:-maximo]
    def iniciar_sesion(self):
        a = self._aprendizaje()
        a["sesiones"]["total"] += 1
        a["sesiones"]["inicio_actual"] = datetime.now().isoformat(timespec="seconds")
        self.guardar_archivo()
        self._plan_diario()
    def finalizar_sesion(self):
        a = self._aprendizaje()
        ahora = datetime.now()
        inicio = a["sesiones"].get("inicio_actual")
        try:
            a["sesiones"]["minutos_totales"] = round(a["sesiones"].get("minutos_totales", 0)
                                                     + (ahora - datetime.fromisoformat(inicio)).total_seconds() / 60, 1)
        except (TypeError, ValueError):
            pass
        a["sesiones"]["ultima_fin"], a["sesiones"]["inicio_actual"] = ahora.isoformat(timespec="seconds"), None
        self.guardar_archivo()
    def aprender(self, entrada, intencion, respuesta, entidad=None, contexto=None):
        """Registra una interacción completa. contexto: datos del sistema (canción actual, volumen...)."""
        try:
            a, ahora = self._aprendizaje(), datetime.now()
            contexto = contexto or {}
            intencion = str(intencion or "DESCONOCIDA")
            respuesta = str(respuesta or "")
            ok = not self._FALLO.match(self.normalizar_texto(respuesta))
            fecha = ahora.isoformat(timespec="seconds")
            frase = self.normalizar_texto(entrada)[:120]
            c = a["comandos"].setdefault(intencion, {"usos": 0, "fallos": 0, "ultimo": None, "frases": {}})
            c["usos"] += 1
            c["fallos"] += 0 if ok else 1
            c["ultimo"] = fecha
            self._sumar(c["frases"], frase, self.MAX_FRASES)
            self._sumar(a["horario"], f"{ahora.hour:02d}")
            self._sumar(a["dias"], ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"][ahora.weekday()])
            if intencion == "DESCONOCIDA" or not ok and intencion in ("SALUDO", "DESCONOCIDA"):
                self._sumar(a["no_entendidas"], frase, 50)
            elif not ok:
                a["errores"].append({"fecha": fecha, "intencion": intencion, "entrada": frase, "respuesta": respuesta[:160]})
                self._recortar(a["errores"])
            m = a["musica"]
            if intencion in ("REPRODUCIR_CANCION", "AGREGAR_COLA_AUDIO") and entidad and ok:
                self._sumar(m["pedidas"], entidad)
            actual = contexto.get("cancion_actual")
            if actual and intencion in ("REPRODUCIR_CANCION", "REPRODUCIR_MUSICA", "SIGUIENTE_CANCION", "ANTERIOR_CANCION",
                                        "REANUDAR_MUSICA", "AGREGAR_COLA_AUDIO"):
                self._sumar(m["escuchadas"], actual)
                if " - " in actual:
                    self._sumar(m["artistas"], actual.split(" - ")[0].strip())
            volumen = contexto.get("volumen")
            if intencion in ("ESTABLECER_VOLUMEN", "SUBIR_VOLUMEN", "BAJAR_VOLUMEN") and isinstance(volumen, (int, float)) and ok:
                v, n = m["volumen"], m["volumen"]["muestras"]
                v["promedio"] = round(((v["promedio"] or volumen) * n + volumen) / (n + 1), 1)
                v["muestras"] = min(n + 1, 50)         # media móvil: pesa más lo reciente
            if ok and intencion in ("ABRIR_APLICACION", "CERRAR_APLICACION", "ABRIR_SITIO_WEB"):
                objetivo = re.search(r"(?:abriendo|cerrando)\s+(.+?)\.?$", self.normalizar_texto(respuesta))
                if objetivo:
                    self._sumar(a["sitios" if intencion == "ABRIR_SITIO_WEB" else "aplicaciones"], objetivo.group(1))
            if intencion == "PREGUNTA_INTERNET" and ok and contexto.get("fuente_internet"):
                a["internet"] = [x for x in a["internet"] if x.get("pregunta") != frase]
                a["internet"].append({"pregunta": frase, "respuesta": seguridad.sanear_conocimiento(respuesta, 400),
                                      "fecha": fecha})
                self._recortar(a["internet"], 60)
            if intencion == "DESCARGAR_MUSICA" and ok and entidad:
                m["descargas"].append({"consulta": str(entidad)[:120], "fecha": fecha})
                self._recortar(m["descargas"])
            a["historial"].append({"fecha": fecha, "entrada": frase, "intencion": intencion, "ok": ok})
            self._recortar(a["historial"], self.MAX_HISTORIAL)
            self._pendientes_guardar = getattr(self, "_pendientes_guardar", 0) + 1
            if self._pendientes_guardar >= 3 or not ok:
                self.guardar_archivo()
        except Exception as error:                     # aprender nunca debe romper una respuesta
            print(f"[MEMORIA] Error aprendiendo: {error}")
    # ------------------------------------------------ aprendizaje autónomo de órdenes
    _VACIAS = {"el", "la", "los", "las", "un", "una", "de", "del", "a", "al", "en", "y", "o", "que", "me", "mi", "por",
               "favor", "miller", "lo", "le", "se", "con", "para", "esa", "ese", "esta", "este", "algo", "porfa"}
    UMBRAL_SIMILAR, UMBRAL_ALIAS, MAX_ALIAS = 0.84, 0.9, 200

    def _palabras_clave(self, texto):
        return {p for p in self.normalizar_texto(texto).split() if p not in self._VACIAS and len(p) > 2}

    def alias_para(self, frase):
        """Orden aprendida para una frase que MILLER antes no entendía (o None)."""
        frase = self.normalizar_texto(frase)
        alias = self._aprendizaje()["alias"]
        if frase in alias:
            return alias[frase]
        clave = (frase, len(alias))
        cache = self.__dict__.setdefault("_cache_alias", {})
        if clave not in cache:                         # misma frase y mismos alias -> mismo resultado
            mejor, puntos = None, self.UMBRAL_ALIAS
            for conocida in alias:
                m = SequenceMatcher(None, frase, conocida)
                if m.real_quick_ratio() >= puntos and m.quick_ratio() >= puntos and m.ratio() >= puntos:
                    mejor, puntos = conocida, m.ratio()
            if len(cache) > 512:
                cache.clear()
            cache[clave] = mejor
        mejor = cache[clave]
        return alias.get(mejor) if mejor else None

    def similar_conocida(self, frase):
        """Frase ya cumplida antes que se parece mucho a esta: (frase, intención) o None."""
        frase = self.normalizar_texto(frase)
        comandos = self._aprendizaje()["comandos"]
        version = sum(d.get("usos", 0) for d in comandos.values())   # cambia con cada orden aprendida
        cache = self.__dict__.setdefault("_cache_similar", {})
        if (frase, version) in cache:
            return cache[(frase, version)]
        mejor, puntos = None, self.UMBRAL_SIMILAR
        for intencion, datos in comandos.items():
            if intencion in ("DESCONOCIDA", "SALIR") or datos.get("usos", 0) <= datos.get("fallos", 0):
                continue
            for conocida in datos.get("frases", {}):
                if conocida == frase:
                    continue
                m = SequenceMatcher(None, frase, conocida)
                if m.real_quick_ratio() < puntos or m.quick_ratio() < puntos:   # descarte barato
                    continue
                r = m.ratio()
                if r >= puntos:
                    mejor, puntos = (conocida, intencion), r
        if len(cache) > 512:
            cache.clear()
        cache[(frase, version)] = mejor
        return mejor

    def aprender_alias(self, frase, texto, intencion, origen):
        frase, texto = self.normalizar_texto(frase), self.normalizar_texto(texto)
        if not frase or not texto or frase == texto or seguridad.es_peligroso(frase + " " + texto):
            return None
        a = self._aprendizaje()
        if len(a["alias"]) >= self.MAX_ALIAS:
            a["alias"].pop(min(a["alias"], key=lambda k: a["alias"][k].get("usos", 0)), None)
        a["alias"][frase] = {"texto": texto, "intencion": intencion, "origen": origen, "usos": 0,
                             "desde": datetime.now().isoformat(timespec="seconds")}
        a["no_entendidas"].pop(frase, None)
        a["candidatos_alias"].pop(frase, None)
        self.guardar_archivo()
        return a["alias"][frase]

    def patrones_rutina(self):
        """Hábitos: misma orden, misma hora, 3 o más días (cálculo cacheado una hora)."""
        try:
            from cerebro.patrones import Rutinas
        except Exception:
            return []
        rutinas = self.__dict__.setdefault("_rutinas", Rutinas())
        return rutinas.para_ahora(self._aprendizaje().get("historial", []))

    def proponer_alias(self, frase_no_entendida, texto_cumplido, intencion):
        """El usuario dijo algo que no entendí y enseguida lo reformuló con éxito.
        Aprende si comparten palabras clave o si el mismo par se repite."""
        frase = self.normalizar_texto(frase_no_entendida)
        texto = self.normalizar_texto(texto_cumplido)
        if not frase or frase == texto:
            return None
        if self._palabras_clave(frase) & self._palabras_clave(texto):
            return self.aprender_alias(frase, texto, intencion, "reformulación")
        cand = self._aprendizaje()["candidatos_alias"].setdefault(frase, {})
        cand[texto] = cand.get(texto, 0) + 1
        if cand[texto] >= 2:
            return self.aprender_alias(frase, texto, intencion, "reformulación repetida")
        self.guardar_archivo()
        return None

    def usar_alias(self, frase):
        alias = self.alias_para(frase)
        if alias:
            alias["usos"] = alias.get("usos", 0) + 1
            alias["ultimo_uso"] = datetime.now().isoformat(timespec="seconds")
        return alias

    def olvidar_alias(self, frase):
        return self._aprendizaje()["alias"].pop(self.normalizar_texto(frase), None) is not None

    MAX_SINONIMOS = 300
    CONFIRMACIONES_SINONIMO = 2

    @staticmethod
    def _limpiar_sinonimo(texto):
        return " ".join(re.sub(r"[^a-z0-9 ]", " ", str(texto or "")).split())[:60]

    def aprender_sinonimo(self, original, equivalente, ambito=None, origen="enseñanza"):
        """«equal isolar» significa «ecualizador». Sin ámbito vale para todas las órdenes;
        con ámbito (una intención), solo cuando esa orden no se entiende de otra forma."""
        if seguridad.es_peligroso(f"{original} {equivalente}"):          # se mira antes de limpiar
            return None
        original = self._limpiar_sinonimo(self.normalizar_texto(original))
        equivalente = self._limpiar_sinonimo(self.normalizar_texto(equivalente))
        if not original or not equivalente or original == equivalente or len(original) < 2:
            return None
        a = self._aprendizaje()
        sinonimos = a["sinonimos"]
        if original not in sinonimos and len(sinonimos) >= self.MAX_SINONIMOS:
            sinonimos.pop(min(sinonimos, key=lambda k: sinonimos[k].get("usos", 0)), None)
        sinonimos[original] = {"texto": equivalente, "ambito": ambito, "origen": origen, "usos": 0,
                               "desde": datetime.now().isoformat(timespec="seconds")}
        for clave in [k for k in a["candidatos_sinonimos"] if k.startswith(original + "|")]:
            a["candidatos_sinonimos"].pop(clave, None)
        self.guardar_archivo()
        return {"original": original, "texto": equivalente, "ambito": ambito}

    @staticmethod
    def _reemplazar_sinonimos(texto, diccionario):
        usados = []
        for original in sorted(diccionario, key=len, reverse=True):          # la frase más larga primero
            patron = r"(?<![a-z0-9])" + re.escape(original) + r"(?![a-z0-9])"
            if re.search(patron, texto):
                texto = re.sub(patron, diccionario[original]["texto"], texto)
                usados.append(original)
        return re.sub(r"\s+", " ", texto).strip(), usados

    def sinonimos_para(self, texto, ambito=None):
        """Texto con los sinónimos globales (o los de un ámbito) sustituidos. Devuelve (texto, usados)."""
        if not texto:
            return texto, []
        sinonimos = self._aprendizaje()["sinonimos"]
        if ambito:
            dicc = {k: v for k, v in sinonimos.items() if v.get("ambito") == ambito}
        else:
            dicc = {k: v for k, v in sinonimos.items() if not v.get("ambito")}
        if not dicc:
            return texto, []
        nuevo, usados = self._reemplazar_sinonimos(texto, dicc)
        for clave in usados:
            dicc[clave]["usos"] = dicc[clave].get("usos", 0) + 1
            dicc[clave]["ultimo_uso"] = datetime.now().isoformat(timespec="seconds")
        return nuevo, usados

    def sinonimos_de_orden(self, texto):
        """Orden no entendida: si un sinónimo de cierta orden la vuelve una orden conocida, (texto, ámbito, usados)."""
        sinonimos = self._aprendizaje()["sinonimos"]
        for ambito in sorted({v.get("ambito") for v in sinonimos.values() if v.get("ambito")}):
            nuevo, usados = self.sinonimos_para(texto, ambito)
            if usados:
                return nuevo, ambito, usados
        return None

    def observar_sinonimo(self, frase, texto, intencion):
        """Compara lo que no entendió con la reformulación que sí funcionó. Si solo cambia un tramo corto,
        ese tramo es un sinónimo de esa orden: lo aprende tras varias confirmaciones."""
        a_tokens = self.normalizar_texto(frase).split()
        b_tokens = self.normalizar_texto(texto).split()
        if not a_tokens or not b_tokens or a_tokens == b_tokens or intencion in (None, "DESCONOCIDA", "SALIR"):
            return None
        cambios = [op for op in SequenceMatcher(None, a_tokens, b_tokens, autojunk=False).get_opcodes()
                   if op[0] != "equal"]
        if len(cambios) != 1 or cambios[0][0] != "replace":
            return None
        _, i1, i2, j1, j2 = cambios[0]
        if not (1 <= i2 - i1 <= 3 and 1 <= j2 - j1 <= 3):
            return None
        original = self._limpiar_sinonimo(" ".join(a_tokens[i1:i2]))
        equivalente = self._limpiar_sinonimo(" ".join(b_tokens[j1:j2]))
        a = self._aprendizaje()
        if not original or original in a["sinonimos"] or original == equivalente:
            return None
        clave = f"{original}|{equivalente}|{intencion}"
        cand = a["candidatos_sinonimos"]
        cand[clave] = cand.get(clave, 0) + 1
        if len(cand) > 200:
            cand.pop(next(iter(cand)))
        if cand[clave] < self.CONFIRMACIONES_SINONIMO:
            self.guardar_archivo()
            return None
        return self.aprender_sinonimo(original, equivalente, intencion, "aprendido solo")

    def olvidar_sinonimo(self, original):
        clave = self._limpiar_sinonimo(self.normalizar_texto(original))
        if self._aprendizaje()["sinonimos"].pop(clave, None) is None:
            return False
        self.guardar_archivo()
        return True

    def listar_sinonimos(self):
        return [(o, v.get("texto", ""), v.get("ambito")) for o, v in self._aprendizaje()["sinonimos"].items()]

    # ---------------------------------------------------------- memoria a largo plazo y plan de olvido
    MEDIA_VIDA_DIAS = 60          # sin uso, un recuerdo pierde la mitad de su fuerza cada 60 días
    DIAS_MINIMOS_OLVIDO = 60      # nunca se olvida antes de 60 días sin usarlo
    FUERZA_MINIMA = 0.25          # por debajo, el plan de olvido lo archiva
    DIAS_ALIAS_SIN_USO = 90
    DIAS_SINONIMO_SIN_USO = 120
    MAX_OLVIDADOS = 300
    IMPORTANCIA_PROTEGIDA = 1.5   # un recuerdo así nunca se olvida por el paso del tiempo
    FRECUENCIA_PROTEGIDA = 3      # ni uno que MILLER ha usado varias veces
    SIMILITUD_PARECIDOS = 0.9     # con poco espacio solo se quita lo casi idéntico a otro que se queda

    @staticmethod
    def _fecha(texto):
        try:
            return datetime.fromisoformat(str(texto))
        except (ValueError, TypeError):
            return None

    def _dias_sin_uso(self, recuerdo, ahora):
        fecha = self._fecha(recuerdo.get("ultimo_acceso", recuerdo.get("fecha")))
        if fecha is None:
            return 0.0                                  # sin fecha fiable, no se olvida
        return max((ahora - fecha).total_seconds() / 86400, 0.0)

    def fuerza_recuerdo(self, recuerdo, ahora=None):
        """Cuánto lo recuerda MILLER ahora (0 a 1): la importancia y el uso lo sostienen; el tiempo sin usarlo lo apaga."""
        ahora = ahora or datetime.now()
        try:
            importancia = min(max(float(recuerdo.get("importancia", 1.0)), 0.0), 2.0)
        except (ValueError, TypeError):
            importancia = 1.0
        try:
            frecuencia = min(max(int(recuerdo.get("frecuencia", 0)), 0), 10)
        except (ValueError, TypeError):
            frecuencia = 0
        base = 0.4 + importancia / 2.0 * 0.3 + frecuencia / 10.0 * 0.3      # entre 0.4 y 1
        return round(base * 0.5 ** (self._dias_sin_uso(recuerdo, ahora) / self.MEDIA_VIDA_DIAS), 3)

    @staticmethod
    def _olvidar_sin_uso(diccionario, ahora, dias):
        """Quita los alias o sinónimos que llevan «dias» sin usarse. Devuelve sus claves."""
        quitados = []
        for clave, datos in list(diccionario.items()):
            if not isinstance(datos, dict):
                continue
            ultimo = Memoria._fecha(datos.get("ultimo_uso") or datos.get("desde"))
            if ultimo is None or (ahora - ultimo).days < dias:
                continue
            diccionario.pop(clave, None)
            quitados.append(clave)
        return quitados

    def valor_recuerdo(self, recuerdo, ahora=None):
        """Clasifica un recuerdo: «importante» (no se olvida por el tiempo), «util» o «debil» (candidato a olvido)."""
        ahora = ahora or datetime.now()
        try:
            importancia = float(recuerdo.get("importancia", 1.0))
        except (ValueError, TypeError):
            importancia = 1.0
        try:
            frecuencia = int(recuerdo.get("frecuencia", 0))
        except (ValueError, TypeError):
            frecuencia = 0
        if importancia >= self.IMPORTANCIA_PROTEGIDA or frecuencia >= self.FRECUENCIA_PROTEGIDA:
            return "importante"
        return "util" if self.fuerza_recuerdo(recuerdo, ahora) >= self.FUERZA_MINIMA * 2 else "debil"

    def clasificar_recuerdos(self, ahora=None):
        """Marca cada recuerdo con su valor y devuelve cuántos hay de cada clase."""
        ahora = ahora or datetime.now()
        cuenta = {"importante": 0, "util": 0, "debil": 0}
        for recuerdo in self.memoria:
            valor = self.valor_recuerdo(recuerdo, ahora)
            recuerdo["valor"] = valor
            cuenta[valor] += 1
        return cuenta

    def _parecidos_a_olvidar(self, ahora):
        """Recuerdos casi idénticos (similitud ≥ SIMILITUD_PARECIDOS) a otro que se conserva. La red de conexiones
        propone los pares y la similitud decide. Entre dos importantes no se olvida ninguno."""
        from cerebro.conexiones import Conexiones
        sobran, marcados = [], set()
        for ra, rb in Conexiones(self).pares():
            if id(ra) in marcados or id(rb) in marcados:
                continue
            if self.calcular_similitud(ra.get("contenido", ""), rb.get("contenido", "")) < self.SIMILITUD_PARECIDOS:
                continue
            importante_a = self.valor_recuerdo(ra, ahora) == "importante"
            importante_b = self.valor_recuerdo(rb, ahora) == "importante"
            if importante_a and importante_b:
                continue
            if importante_a:
                victima = rb
            elif importante_b:
                victima = ra
            else:
                victima = min((ra, rb), key=lambda r: (self.fuerza_recuerdo(r, ahora),
                                                       len(str(r.get("contenido", "")))))
            sobran.append(victima)
            marcados.add(id(victima))
        return sobran

    @staticmethod
    def _presion_disco():
        try:
            from utilidades import cuota
            return cuota.presion()
        except Exception:
            return "normal"

    def plan_de_olvido(self, ahora=None):
        """Olvida con calma. Con disco normal: archiva lo débil que lleva mucho sin usarse (lo importante nunca).
        Con poco espacio: solo archiva lo casi idéntico a otro recuerdo que se conserva.
        Nada se borra del todo: queda en «olvidados» y se puede recuperar."""
        ahora = ahora or datetime.now()
        presion = self._presion_disco()
        clasificacion = self.clasificar_recuerdos(ahora)
        if presion == "normal":
            archivados = [r for r in self.memoria
                          if self.valor_recuerdo(r, ahora) == "debil"
                          and self._dias_sin_uso(r, ahora) >= self.DIAS_MINIMOS_OLVIDO
                          and self.fuerza_recuerdo(r, ahora) < self.FUERZA_MINIMA]
        else:
            archivados = self._parecidos_a_olvidar(ahora)
        a = self._aprendizaje()
        if archivados:
            ids = {id(r) for r in archivados}
            self.memoria[:] = [r for r in self.memoria if id(r) not in ids]
            hoy = ahora.isoformat(timespec="seconds")
            a["olvidados"] = (a["olvidados"] + [{**r, "olvidado": hoy} for r in archivados])[-self.MAX_OLVIDADOS:]
        resumen = {"fecha": ahora.isoformat(timespec="seconds"), "presion": presion,
                   "recuerdos": len(archivados), "clasificacion": clasificacion,
                   "alias": self._olvidar_sin_uso(a["alias"], ahora, self.DIAS_ALIAS_SIN_USO),
                   "sinonimos": self._olvidar_sin_uso(a["sinonimos"], ahora, self.DIAS_SINONIMO_SIN_USO)}
        a["ultimo_olvido"] = resumen
        self.guardar_archivo()
        return resumen

    def _plan_diario(self):
        """Como mucho un plan de olvido al día, al arrancar. Con poco espacio, se planifica también si hoy
        el último plan se hizo con disco normal."""
        ultimo = self._aprendizaje().get("ultimo_olvido") or {}
        if self._presion_disco() != "normal" and ultimo.get("presion", "normal") == "normal":
            return self.plan_de_olvido()
        if str(ultimo.get("fecha", ""))[:10] != datetime.now().date().isoformat():
            return self.plan_de_olvido()
        return None

    def olvidar_tema(self, tema):
        """Archiva los recuerdos de un tema (palabra o frase del contenido o de la categoría). Devuelve cuántos."""
        clave = self.normalizar_texto(tema).strip()
        if len(clave) < 3:
            return 0
        a = self._aprendizaje()
        archivar = [r for r in self.memoria
                    if clave in self.normalizar_texto(f"{r.get('contenido', '')} {r.get('categoria', '')}")]
        if archivar:
            ids = {id(r) for r in archivar}
            self.memoria[:] = [r for r in self.memoria if id(r) not in ids]
            hoy = datetime.now().isoformat(timespec="seconds")
            a["olvidados"] = (a["olvidados"] + [{**r, "olvidado": hoy} for r in archivar])[-self.MAX_OLVIDADOS:]
            self.guardar_archivo()
        return len(archivar)

    def recuperar_olvidado(self, tema):
        """Devuelve al recuerdo los archivados que tratan de ese tema. Devuelve cuántos."""
        clave = self.normalizar_texto(tema).strip()
        a = self._aprendizaje()
        if len(clave) < 3:
            return 0
        volver = [r for r in a["olvidados"] if clave in self.normalizar_texto(f"{r.get('contenido', '')} {r.get('categoria', '')}")]
        if not volver:
            return 0
        ids = {id(r) for r in volver}
        a["olvidados"] = [r for r in a["olvidados"] if id(r) not in ids]
        ahora = datetime.now().isoformat(timespec="seconds")
        for r in volver:
            recuperado = {k: v for k, v in r.items() if k != "olvidado"}
            recuperado["ultimo_acceso"] = ahora                  # así no vuelve a olvidarse de inmediato
            self.memoria.append(recuperado)
        self.guardar_archivo()
        return len(volver)

    def olvidados_recientes(self, cantidad=5):
        return [r.get("contenido", "") for r in self._aprendizaje()["olvidados"][-cantidad:]][::-1]

    def resumen_largo_plazo(self):
        temas = {}
        for r in self.memoria:
            temas[r.get("categoria", "general")] = temas.get(r.get("categoria", "general"), 0) + 1
        return {"activos": len(self.memoria), "olvidados": len(self._aprendizaje()["olvidados"]),
                "temas": sorted(temas.items(), key=lambda par: par[1], reverse=True)[:5]}

    def registrar_descarga(self, titulo, ok=True):
        a = self._aprendizaje()
        if ok and titulo:
            a["musica"]["descargas"].append({"titulo": str(titulo)[:160], "fecha": datetime.now().isoformat(timespec="seconds")})
            self._recortar(a["musica"]["descargas"])
            self.guardar_archivo()
    def respuesta_aprendida(self, pregunta, umbral=0.82):
        """Respuesta de internet ya aprendida para una pregunta parecida (para usar sin conexión)."""
        frase, mejor = self.normalizar_texto(pregunta), None
        for item in self._aprendizaje()["internet"]:
            similitud = SequenceMatcher(None, frase, item.get("pregunta", "")).ratio()
            if similitud >= umbral and (mejor is None or similitud > mejor[0]):
                mejor = (similitud, item)
        return mejor[1] if mejor else None
    @staticmethod
    def _top(diccionario, n=1):
        return sorted(diccionario.items(), key=lambda x: (-x[1], x[0]))[:n]
    def resumen_aprendizaje(self, nombres_intenciones=None):
        a = self._aprendizaje()
        nombres = nombres_intenciones or {}
        partes = [f"Sesiones: {a['sesiones']['total']}."]
        comandos = {k: v["usos"] for k, v in a["comandos"].items() if k not in ("DESCONOCIDA", "RESUMEN_APRENDIZAJE")}
        if comandos:
            k, n = self._top(comandos)[0]
            partes.append(f"Orden más usada: {nombres.get(k, k.lower().replace('_', ' '))}, {n} veces.")
        if a["horario"]:
            from utilidades.reloj import hora_12_de
            partes.append(f"Mayor actividad: hacia las {hora_12_de(self._top(a['horario'])[0][0])}")
        m = a["musica"]
        favorita = self._top(m["pedidas"]) or self._top(m["escuchadas"])
        if favorita:
            partes.append(f"Canción más pedida: {re.sub(r'[.][a-z0-9]{2,4}$', '', favorita[0][0])}.")
        if m["volumen"]["promedio"] is not None:
            partes.append(f"Volumen preferido: {round(m['volumen']['promedio'])} %.")
        if a["aplicaciones"]:
            partes.append(f"Programa más usado: {self._top(a['aplicaciones'])[0][0]}.")
        if a["internet"]:
            partes.append(f"{len(a['internet'])} respuestas de internet aprendidas.")
        fallos = sum(v["fallos"] for v in a["comandos"].values())
        total = sum(v["usos"] for v in a["comandos"].values())
        if total:
            partes.append(f"Efectividad: {round(100 * (total - fallos) / total)} %.")
        return " ".join(partes) if total else "Sin datos de aprendizaje todavía."
    def cancion_favorita(self, perfil_reproductor=None):
        m = self._aprendizaje()["musica"]
        candidatas = self._top(m["pedidas"], 3) or self._top(m["escuchadas"], 3)
        if not candidatas and isinstance(perfil_reproductor, list):
            candidatas = [(x, 0) for x in perfil_reproductor[:3]]
        return [re.sub(r"[.][a-z0-9]{2,4}$", "", c[0]) for c in candidatas]
