"""MILLER · Reproductor de audio 3.6."""
from pathlib import Path
from difflib import SequenceMatcher
from collections import Counter
import json, math, os, random, re, threading, time, unicodedata
import pygame
from functools import lru_cache
from .fade_controller import FadeController
try:
    from utilidades import seguridad
except Exception:
    seguridad = None
class Reproductor:
    EXTENSIONES_AUDIO = {".mp3", ".wav", ".ogg", ".flac"}
    VOLUMEN_MINIMO, VOLUMEN_MAXIMO, VOLUMEN_INICIAL = 0.0, 1.0, 0.8
    INCREMENTO_VOLUMEN = 0.10
    MAX_HISTORIAL, CANCIONES_RECIENTES_A_EVITAR = 20, 5
    INTERVALO_MONITOR, UMBRAL_BUSQUEDA_APROXIMADA = 0.25, 0.45
    DURACION_FADE_IN, DURACION_FADE_OUT = 2.0, 1.2
    DURACION_FADE_VOLUMEN = 0.9          # subir / bajar volumen con fundido
    VERSION_MEMORIA_MUSICAL, MAX_CANCIONES_RECIENTES = 4, 50
    ENTRADAS_RED, NEURONAS_OCULTAS = 8, 12
    TASA_APRENDIZAJE, DECAY_ADAM, DECAY_ADAM_CUADRADO, EPSILON_ADAM = 0.008, 0.9, 0.999, 1e-8
    ESPERA_COPIA_INICIO = 3.0                    # al empezar una canción cuya copia ecualizada aún se crea (máx. s)

    def __init__(self, carpeta_audios, ruta_memoria=None, restaurar_pista=True):
        self.carpeta = Path(carpeta_audios)
        self.canciones, self.cola, self.historial = [], [], []
        self.cancion_actual, self.indice_actual, self._indice_historial = None, -1, -1
        self.reproduciendo = self.pausado = False
        self.volumen = self.VOLUMEN_INICIAL
        self._volumen_antes_silencio = self.VOLUMEN_INICIAL
        self.modo_aleatorio = self.modo_repetir = False
        self.tiempo_inicio, self.tiempo_acumulado = None, 0.0
        self.inicializado = self.cerrado = False
        self._lock = threading.RLock()
        self._lock_disco = threading.Lock()
        self._monitor_activo, self._monitor_hilo = False, None
        self._procesando_fin, self._inicio_monotono = False, None
        self.ruta_memoria = Path(ruta_memoria) if ruta_memoria else self.carpeta.parent / "datos" / "memoriamusical.json"
        self.memoria_musical = self._cargar_memoria_musical()
        self._cambios_memoria = 0
        self._estado_guardado = self.memoria_musical.get("estado_reproductor", {})
        self._pista_pendiente = None             # restauración aplazada hasta continuar_al_iniciar()
        self.ecualizador = None                  # utilidades/ecualizador.py (lo conecta Comandos)
        self.fuente_actual = None                # archivo que suena de verdad (original o copia ecualizada)
        self._cambios_pedidos = set()            # canciones cuyo cambio de ecualización pidió el usuario
        self._restaurar_pista_al_crear = bool(restaurar_pista)
        self._inicializar_audio()
        self.fade_controller = FadeController(pygame.mixer.music.get_volume, pygame.mixer.music.set_volume)
        self.actualizar_lista()
        self._restaurar_estado()
        if self.inicializado:
            self._iniciar_monitor()
    @staticmethod
    def _numero(valor, defecto=0.0):
        try:
            n = float(valor)
            return n if math.isfinite(n) else defecto
        except (TypeError, ValueError):
            return defecto
    @classmethod
    def _modelo_nuevo(cls):
        rng = random.Random(7341)
        h, n = cls.NEURONAS_OCULTAS, cls.ENTRADAS_RED
        return {
            "arquitectura": [n, h, 1],
            "wi": [[rng.uniform(-.18, .18) for _ in range(n)] for _ in range(h)],
            "bh": [0.0] * h,
            "wo": [rng.uniform(-.18, .18) for _ in range(h)],
            "bo": 0.0, "pasos": 0,
            "adam": {
                "m_wi": [[0.0] * n for _ in range(h)],
                "v_wi": [[0.0] * n for _ in range(h)],
                "m_bh": [0.0] * h, "v_bh": [0.0] * h,
                "m_wo": [0.0] * h, "v_wo": [0.0] * h,
                "m_bo": 0.0, "v_bo": 0.0
            }
        }
    def _memoria_base(self):
        return {
            "version": self.VERSION_MEMORIA_MUSICAL, "canciones": {},
            "artistas": {}, "generos": {}, "recientes": [],
            "preferencias": {"likes": 0, "dislikes": 0}, "sesiones": 0,
            "modelo": self._modelo_nuevo(), "estado_reproductor": {},
            "actualizada": time.time()
        }
    @classmethod
    def _modelo_valido(cls, m):
        try:
            h, n, a = cls.NEURONAS_OCULTAS, cls.ENTRADAS_RED, m["adam"]
            return (
                len(m["wi"]) == h and all(len(r) == n for r in m["wi"])
                and len(m["bh"]) == h and len(m["wo"]) == h
                and all(len(a[k]) == h for k in ("m_bh", "v_bh", "m_wo", "v_wo"))
                and len(a["m_wi"]) == h and len(a["v_wi"]) == h
                and all(len(r) == n for r in a["m_wi"] + a["v_wi"])
            )
        except (TypeError, KeyError, IndexError):
            return False
    def _cargar_memoria_musical(self):
        base = self._memoria_base()
        try:
            if not self.ruta_memoria.exists():
                return base
            if seguridad is not None:
                datos = seguridad.leer_json(self.ruta_memoria, None)
            else:
                with self.ruta_memoria.open(encoding="utf-8") as f:
                    datos = json.load(f)
            if not isinstance(datos, dict):
                return base
            datos = datos.get("memoria_musical", datos)
            if not isinstance(datos, dict):
                return base
            base.update(datos)
            for k in ("canciones", "artistas", "generos", "preferencias"):
                if not isinstance(base.get(k), dict):
                    base[k] = {}
            if not isinstance(base.get("recientes"), list):
                base["recientes"] = []
            base["recientes"] = base["recientes"][-self.MAX_CANCIONES_RECIENTES:]
            if not isinstance(base.get("estado_reproductor"), dict):
                base["estado_reproductor"] = {}
            base.pop("eventos", None)
            if not self._modelo_valido(base.get("modelo")):
                base["modelo"] = self._modelo_nuevo()
            for r in base["canciones"].values():
                if isinstance(r, dict):
                    r.pop("tokens", None)
                    r.pop("ruta", None)
            base["version"] = self.VERSION_MEMORIA_MUSICAL
            return base
        except (OSError, json.JSONDecodeError, TypeError) as e:
            print(f"[ AUDIO/IA ] No se pudo leer memoria musical: {e}")
            return base
    def _crear_estado_persistente(self):
        pendiente = getattr(self, "_pista_pendiente", None)
        if pendiente and self.cancion_actual is None:      # se cerró antes de continuar: no perder la canción
            return dict(self._estado_guardado or {}, cancion_actual=str(Path(pendiente[0]).resolve()),
                        posicion_segundos=round(pendiente[1], 2), guardado=int(time.time()))
        return {
            "cancion_actual": str(self.cancion_actual.resolve()) if self.cancion_actual else None,
            "posicion_segundos": round(self._calcular_tiempo_actual(), 2),
            "reproduciendo": bool(self.reproduciendo), "pausado": bool(self.pausado),
            "volumen": round(float(self.volumen), 4),
            "volumen_antes_silencio": round(float(getattr(self, "_volumen_antes_silencio", self.VOLUMEN_INICIAL)), 4),
            "aleatorio": bool(self.modo_aleatorio), "repetir": bool(self.modo_repetir),
            "cola": [str(p.resolve()) for p in self.cola],
            "historial": [str(p.resolve()) for p in self.historial[-self.MAX_HISTORIAL:]],
            "indice_historial": self._indice_historial, "guardado": int(time.time())
        }
    RETRASO_GUARDADO = 4.0               # s: varios cambios seguidos (cambio de canción) = una sola escritura
    def guardar_memoria_musical(self, inmediato=False):
        """Guarda la memoria musical SIN frenar la reproducción: se agrupa y se escribe en segundo plano."""
        if inmediato:
            return self._guardar_ahora()
        with self._lock:
            self._cambios_memoria = getattr(self, "_cambios_memoria", 0) + 1
            if getattr(self, "_guardado_programado", False):
                return True
            self._guardado_programado = True
        def diferido():
            time.sleep(self.RETRASO_GUARDADO)
            self._guardado_programado = False
            if not self.cerrado:
                self._guardar_ahora()
        threading.Thread(target=diferido, daemon=True, name="MILLER-GuardarMusica").start()
        return True
    def _guardar_ahora(self):
        with self._lock:                                  # bajo el candado solo se toma una copia (rápido)
            temporal = None
            try:
                self.ruta_memoria.parent.mkdir(parents=True, exist_ok=True)
                self.memoria_musical["actualizada"] = int(time.time())
                self.memoria_musical["recientes"] = self.memoria_musical.get("recientes", [])[-self.MAX_CANCIONES_RECIENTES:]
                self.memoria_musical.pop("eventos", None)
                self.memoria_musical["estado_reproductor"] = self._crear_estado_persistente()
                copia = json.loads(json.dumps(self.memoria_musical, allow_nan=False)) if seguridad is not None else None
                self._cambios_memoria = 0
            except (OSError, TypeError, ValueError) as e:
                print(f"[ AUDIO ] Error preparando la memoria musical: {e}")
                return False
        if copia is not None:                             # el disco (firma, fsync) fuera del candado
            try:
                with self._lock_disco:
                    return bool(seguridad.escribir_json(self.ruta_memoria, copia, sincronizar=True))
            except (OSError, TypeError, ValueError) as e:
                print(f"[ AUDIO ] Error guardando memoria musical: {e}")
                return False
        with self._lock:
            try:
                temporal = self.ruta_memoria.with_name(self.ruta_memoria.name + ".tmp")
                with temporal.open("w", encoding="utf-8") as f:
                    json.dump(self.memoria_musical, f, ensure_ascii=False, indent=2, allow_nan=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temporal, self.ruta_memoria)
                self._cambios_memoria = 0
                return True
            except (OSError, TypeError, ValueError) as e:
                print(f"[ AUDIO ] Error guardando memoria musical: {e}")
                try:
                    if temporal and temporal.exists():
                        temporal.unlink()
                except OSError:
                    pass
                return False
    @staticmethod
    def _clave_archivo(archivo):
        try:
            return str(Path(archivo).resolve()).casefold()
        except (OSError, TypeError):
            return str(archivo).casefold()
    @staticmethod
    @lru_cache(maxsize=4096)
    def _texto_busqueda(texto):
        s = unicodedata.normalize("NFKD", str(texto or "").casefold())
        s = "".join(c for c in s if not unicodedata.combining(c))
        return " ".join(re.sub(r"[_.()\[\]{}-]+", " ", s).split())
    def _metadatos_archivo(self, archivo):
        nombre = self._texto_busqueda(Path(archivo).stem)
        palabras = [p for p in nombre.split() if len(p) > 1]
        ignorar = {"official", "video", "audio", "lyrics", "letra", "visualizer", "remix", "live", "version", "hd", "4k"}
        limpias = [p for p in palabras if p not in ignorar]
        return {"nombre": Path(archivo).stem, "artista_estimado": limpias[0] if len(limpias) > 1 else "desconocido"}
    def _restaurar_estado(self):
        e = self._estado_guardado
        if not isinstance(e, dict):
            return
        self.volumen = max(0.0, min(1.0, self._numero(e.get("volumen"), self.VOLUMEN_INICIAL)))
        self._volumen_antes_silencio = max(0.01, min(1.0, self._numero(e.get("volumen_antes_silencio"), self.volumen or self.VOLUMEN_INICIAL)))
        self.modo_aleatorio, self.modo_repetir = bool(e.get("aleatorio", False)), bool(e.get("repetir", False))
        self.cola = [Path(p) for p in e.get("cola", []) if isinstance(p, str) and Path(p).is_file() and Path(p).suffix.lower() in self.EXTENSIONES_AUDIO]
        self.historial = [Path(p) for p in e.get("historial", []) if isinstance(p, str) and Path(p).is_file()][-self.MAX_HISTORIAL:]
        try:
            self._indice_historial = max(-1, min(len(self.historial) - 1, int(e.get("indice_historial", len(self.historial) - 1))))
        except (TypeError, ValueError):
            self._indice_historial = len(self.historial) - 1
        ruta = e.get("cancion_actual")
        archivo = Path(ruta) if isinstance(ruta, str) else None
        if (archivo and archivo.is_file() and archivo.suffix.lower() in self.EXTENSIONES_AUDIO and self.inicializado
                and not self._restaurar_pista_al_crear):
            self._pista_pendiente = (archivo, max(0.0, self._numero(e.get("posicion_segundos"))))
            try:
                pygame.mixer.music.set_volume(0.0)
            except pygame.error:
                pass
        elif archivo and archivo.is_file() and archivo.suffix.lower() in self.EXTENSIONES_AUDIO and self.inicializado:
            self._restaurar_pista(archivo, max(0.0, self._numero(e.get("posicion_segundos"))), bool(e.get("reproduciendo")), bool(e.get("pausado")))
        else:
            try:
                pygame.mixer.music.set_volume(0.0)
            except pygame.error:
                pass
    def _restaurar_pista(self, archivo, posicion, estaba_reproduciendo, estaba_pausado):
        try:
            self.fade_controller.cancelar()
            pygame.mixer.music.stop()
            fuente = self._fuente(archivo)
            pygame.mixer.music.load(str(fuente))
            self.fuente_actual = fuente
            pygame.mixer.music.set_volume(0.0)
            pygame.mixer.music.play()
            if posicion > 0:
                try:
                    pygame.mixer.music.set_pos(posicion)
                except (pygame.error, AttributeError):
                    pygame.mixer.music.stop()
                    pygame.mixer.music.play(start=posicion)
            self.cancion_actual = archivo
            try:
                self.indice_actual = self.canciones.index(archivo)
            except ValueError:
                self.indice_actual = -1
            self.tiempo_acumulado = posicion
            self._inicio_monotono = time.monotonic()
            activa = bool(estaba_reproduciendo and not estaba_pausado)
            self.tiempo_inicio = time.time() if activa else None
            self.reproduciendo, self.pausado = bool(estaba_reproduciendo or estaba_pausado), not activa
            if self.pausado:
                pygame.mixer.music.pause()
            else:
                self.fade_controller.fade_in(self.volumen, self.DURACION_FADE_IN)
            print(f"[ AUDIO ] ♻ Estado restaurado: {archivo.name} ({int(posicion)} s).")
            return True
        except Exception as e:
            self.cancion_actual = None
            self.reproduciendo = self.pausado = False
            self.tiempo_inicio, self.tiempo_acumulado = None, 0.0
            try:
                pygame.mixer.music.stop()
                pygame.mixer.music.set_volume(self.volumen)
            except Exception:
                pass
            print(f"[ AUDIO ] No se pudo restaurar la pista: {e}")
            return False
    @staticmethod
    def _sigmoide(v):
        v = max(-30.0, min(30.0, float(v)))
        return 1.0 / (1.0 + math.exp(-v))
    def _caracteristicas_musicales(self, r):
        rep = max(0, self._numero(r.get("reproducciones")))
        fin, saltos, inter = (max(0, self._numero(r.get(k))) for k in ("terminadas", "saltos", "interrupciones"))
        escuchados, puntos = max(0, self._numero(r.get("segundos_escuchados"))), self._numero(r.get("puntuacion"))
        total = max(1, fin + saltos + inter)
        pref = str(r.get("preferencia_explicita", ""))
        like = 1 if pref in {"me gusta", "like", "favorita", "favorito"} else -1 if pref in {"no me gusta", "dislike", "rechazo"} else 0
        ultima = max(0, self._numero(r.get("ultima_reproduccion")))
        dias = max(0, time.time() - ultima) / 86400 if ultima else 365
        return [min(1, math.log1p(rep) / 6), min(1, fin / total), min(1, saltos / total),
                min(1, inter / total), min(1, math.log1p(escuchados) / 11),
                max(-1, min(1, puntos / 12)), like, min(1, dias / 90)]
    def _pasada_red(self, registro, modelo=None):
        m = modelo or self.memoria_musical["modelo"]
        x = self._caracteristicas_musicales(registro)
        h = [math.tanh(sum(w * v for w, v in zip(fila, x)) + b) for fila, b in zip(m["wi"], m["bh"])]
        return x, h, self._sigmoide(sum(w * v for w, v in zip(m["wo"], h)) + m["bo"])
    def _predecir_afinidad_red(self, registro):
        m = self.memoria_musical.get("modelo")
        if not self._modelo_valido(m):
            m = self.memoria_musical["modelo"] = self._modelo_nuevo()
        return max(-1, min(1, (self._pasada_red(registro, m)[2] - .5) * 2))
    def _entrenar_red(self, registro, tipo):
        objetivos = {"terminada": (.88, 1), "reproduccion": (.58, .25), "salto": (.12, .8),
                     "interrupcion": (.32, .35), "me gusta": (.98, 1), "like": (.98, 1),
                     "favorita": (.98, 1), "favorito": (.98, 1), "no me gusta": (.02, 1),
                     "dislike": (.02, 1), "rechazo": (.02, 1)}
        if tipo not in objetivos:
            return
        m = self.memoria_musical["modelo"]
        if not self._modelo_valido(m):
            m = self.memoria_musical["modelo"] = self._modelo_nuevo()
        x, h, y = self._pasada_red(registro, m)
        objetivo, confianza = objetivos[tipo]
        error = max(-1, min(1, (objetivo - y) * confianza))
        wo, gwo, gbo = m["wo"][:], [], error
        gwo = [error * v for v in h]
        gh = [error * wo[i] * (1 - h[i] * h[i]) for i in range(len(h))]
        gwi = [[gh[i] * x[j] for j in range(len(x))] for i in range(len(h))]
        grad = gwo + [gbo] + gh + [v for fila in gwi for v in fila]
        norma = math.sqrt(sum(v * v for v in grad)) or 1
        escala = min(1, 2 / norma)
        gwi = [[v * escala for v in fila] for fila in gwi]
        gh, gwo, gbo = [v * escala for v in gh], [v * escala for v in gwo], gbo * escala
        a, paso = m["adam"], int(m.get("pasos", 0)) + 1
        b1, b2 = self.DECAY_ADAM, self.DECAY_ADAM_CUADRADO
        def upd(p, g, mk, vk, idx=None):
            if idx is None:
                oldm, oldv = a[mk], a[vk]
            elif isinstance(idx, tuple):
                oldm, oldv = a[mk][idx[0]][idx[1]], a[vk][idx[0]][idx[1]]
            else:
                oldm, oldv = a[mk][idx], a[vk][idx]
            mm, vv = b1 * oldm + (1 - b1) * g, b2 * oldv + (1 - b2) * g * g
            if idx is None:
                a[mk], a[vk] = mm, vv
            elif isinstance(idx, tuple):
                a[mk][idx[0]][idx[1]], a[vk][idx[0]][idx[1]] = mm, vv
            else:
                a[mk][idx], a[vk][idx] = mm, vv
            mc, vc = mm / (1 - b1 ** paso), vv / (1 - b2 ** paso)
            return max(-5, min(5, p + self.TASA_APRENDIZAJE * mc / (math.sqrt(vc) + self.EPSILON_ADAM)))
        for i in range(self.NEURONAS_OCULTAS):
            for j in range(self.ENTRADAS_RED):
                m["wi"][i][j] = upd(m["wi"][i][j], gwi[i][j], "m_wi", "v_wi", (i, j))
            m["bh"][i] = upd(m["bh"][i], gh[i], "m_bh", "v_bh", i)
            m["wo"][i] = upd(m["wo"][i], gwo[i], "m_wo", "v_wo", i)
        m["bo"] = upd(m["bo"], gbo, "m_bo", "v_bo")
        m["pasos"] = paso
    def _registro_cancion(self, archivo):
        clave = self._clave_archivo(archivo)
        canciones = self.memoria_musical.setdefault("canciones", {})
        r = canciones.setdefault(clave, {
            "nombre": Path(archivo).name, "reproducciones": 0, "terminadas": 0,
            "saltos": 0, "interrupciones": 0, "segundos_escuchados": 0.0,
            "segundos_ultima_sesion": 0.0, "ultima_reproduccion": 0,
            "ultima_interaccion": 0,
            "artista_estimado": self._metadatos_archivo(archivo)["artista_estimado"],
            "puntuacion": 0.0
        })
        for k in ("reproducciones", "terminadas", "saltos", "interrupciones", "segundos_escuchados", "puntuacion"):
            r.setdefault(k, 0)
        r.setdefault("artista_estimado", self._metadatos_archivo(archivo)["artista_estimado"])
        return r
    def _registrar_evento(self, tipo, archivo=None, segundos=0):
        if archivo is None:
            return
        with self._lock:
            r, ahora = self._registro_cancion(archivo), time.time()
            segundos = max(0, self._numero(segundos))
            r["ultima_interaccion"], r["segundos_ultima_sesion"] = ahora, segundos
            r["segundos_escuchados"] = self._numero(r.get("segundos_escuchados")) + segundos
            if tipo == "reproduccion":
                r["reproducciones"] += 1
                r["ultima_reproduccion"] = ahora
            elif tipo in {"terminada", "salto", "interrupcion"}:
                r[{"terminada": "terminadas", "salto": "saltos", "interrupcion": "interrupciones"}[tipo]] += 1
            pesos = {"reproduccion": .15, "terminada": 1, "salto": -1.25, "interrupcion": -.25}
            r["puntuacion"] = max(-20, min(100, self._numero(r.get("puntuacion")) + pesos.get(tipo, 0)))
            artista = r.get("artista_estimado", "desconocido")
            ar = self.memoria_musical.setdefault("artistas", {}).setdefault(artista, {"reproducciones": 0, "terminadas": 0, "saltos": 0, "puntuacion": 0})
            for campo, ev in (("reproducciones", "reproduccion"), ("terminadas", "terminada"), ("saltos", "salto")):
                if tipo == ev:
                    ar[campo] = int(ar.get(campo, 0)) + 1
            ar["puntuacion"] = max(-100, min(500, self._numero(ar.get("puntuacion")) + pesos.get(tipo, 0)))
            if tipo == "reproduccion":
                rec = self.memoria_musical.setdefault("recientes", [])
                rec.append({"ruta": self._clave_archivo(archivo), "nombre": Path(archivo).name, "tiempo": int(ahora)})
                del rec[:-self.MAX_CANCIONES_RECIENTES]
            self._registrar_diario(tipo, archivo, segundos, artista)
            self._entrenar_red(r, tipo)
            self.guardar_memoria_musical()
    NIVEL_POR_DEFECTO = 0.15                     # RMS típico de una canción si aún no se ha medido
    def nivel_cancion_actual(self):
        """Volumen real (RMS 0-1) de la canción que suena, medido una vez y guardado en la memoria musical."""
        actual = self.cancion_actual
        if actual is None:
            return None
        r = (self.memoria_musical.get("canciones") or {}).get(self._clave_archivo(actual)) or {}
        try:
            return float(r["rms"])
        except (KeyError, TypeError, ValueError):
            return None
    def _ruta_ffmpeg(self):
        if getattr(self, "_ffmpeg", "?") != "?":
            return self._ffmpeg
        import shutil
        candidatos = [self.carpeta.parent / "modelos" / "ffmpeg-master-gpl" / "bin" / "ffmpeg.exe", shutil.which("ffmpeg")]
        self._ffmpeg = next((str(c) for c in candidatos if c and Path(c).is_file()), None)
        return self._ffmpeg
    def _medir_nivel(self, archivo):
        """En segundo plano y solo una vez por canción: ffmpeg volumedetect sobre 60 s del tema."""
        if self.nivel_cancion_actual() is not None or not self._ruta_ffmpeg():
            return
        def medir():
            import subprocess
            try:
                extra = {"creationflags": 0x08000000 | 0x00004000} if os.name == "nt" else {}   # sin ventana y con prioridad baja
                r = subprocess.run([self._ffmpeg, "-hide_banner", "-nostats", "-ss", "30", "-t", "60", "-i", str(archivo),
                                    "-af", "volumedetect", "-vn", "-f", "null", "-"], capture_output=True, text=True,
                                   timeout=60, stdin=subprocess.DEVNULL, **extra)
                m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", r.stderr or "")
                if not m:
                    return
                rms = round(10 ** (float(m.group(1)) / 20), 4)
                with self._lock:
                    self._registro_cancion(archivo)["rms"] = rms
                print(f"[ AUDIO ] Nivel medido: {Path(archivo).stem} = {m.group(1)} dB")
            except Exception as e:
                print(f"[ AUDIO ] No se pudo medir el nivel: {e}")
        threading.Thread(target=medir, daemon=True, name="MILLER-NivelCancion").start()
    DIAS_DIARIO = 90
    def _registrar_diario(self, tipo, archivo, segundos, artista):
        """Memoria musical por secciones diarias: qué sonó, cuánto y qué se saltó cada día."""
        hoy = time.strftime("%Y-%m-%d")
        diario = self.memoria_musical.setdefault("diario", {})
        dia = diario.setdefault(hoy, {"reproducciones": 0, "terminadas": 0, "saltos": 0, "minutos": 0.0,
                                      "canciones": {}, "artistas": {}, "primera": time.strftime("%H:%M"), "ultima": ""})
        nombre = Path(archivo).stem
        dia["minutos"] = round(self._numero(dia.get("minutos")) + segundos / 60.0, 1)
        dia["ultima"] = time.strftime("%H:%M")
        if tipo == "reproduccion":
            dia["reproducciones"] += 1
            dia["canciones"][nombre] = int(dia["canciones"].get(nombre, 0)) + 1
            dia["artistas"][artista] = int(dia["artistas"].get(artista, 0)) + 1
        elif tipo in ("terminada", "salto"):
            dia[{"terminada": "terminadas", "salto": "saltos"}[tipo]] += 1
        for viejo in sorted(diario)[:-self.DIAS_DIARIO]:          # conserva los últimos 90 días
            diario.pop(viejo, None)
    def resumen_dia(self, fecha=None):
        """Resumen corto de la música de un día ("hoy", "ayer" o AAAA-MM-DD)."""
        import datetime as _dt
        hoy = _dt.date.today()
        fecha = {"hoy": hoy, "ayer": hoy - _dt.timedelta(days=1), None: hoy}.get(fecha, fecha)
        clave = fecha.isoformat() if hasattr(fecha, "isoformat") else str(fecha)
        with self._lock:
            dia = dict((self.memoria_musical.get("diario") or {}).get(clave) or {})
        if not dia or not dia.get("reproducciones"):
            return None
        top = sorted(dia.get("canciones", {}).items(), key=lambda x: -x[1])[:3]
        return {"fecha": clave, "reproducciones": dia["reproducciones"], "minutos": dia.get("minutos", 0),
                "saltos": dia.get("saltos", 0), "top": [n for n, _ in top]}
    def _registrar_fin_actual(self, tipo):
        if self.cancion_actual:
            self._registrar_evento(tipo, self.cancion_actual, self._calcular_tiempo_actual())
    def registrar_interaccion(self, tipo, nombre=None):
        archivo = self.buscar_cancion(nombre) if nombre else self.cancion_actual
        if archivo is None:
            return False
        tipo = self._texto_busqueda(tipo)
        pesos = {"me gusta": 2, "like": 2, "favorita": 2, "favorito": 2, "no me gusta": -3, "dislike": -3, "rechazo": -3}
        with self._lock:
            r = self._registro_cancion(archivo)
            if tipo in pesos:
                r["puntuacion"] = max(-20, min(100, self._numero(r.get("puntuacion")) + pesos[tipo]))
                r["ultima_interaccion"], r["preferencia_explicita"] = time.time(), tipo
                clave = "likes" if pesos[tipo] > 0 else "dislikes"
                pref = self.memoria_musical.setdefault("preferencias", {})
                pref[clave] = int(pref.get(clave, 0)) + 1
                self._entrenar_red(r, tipo)
            elif tipo in {"busqueda", "buscar"}:
                r["busquedas"] = int(r.get("busquedas", 0)) + 1
            else:
                return False
            return self.guardar_memoria_musical()
    def recomendar_canciones(self, limite=10, excluir_actual=False):
        try:
            limite = max(1, int(limite))
        except (TypeError, ValueError):
            limite = 10
        with self._lock:
            biblioteca = self.actualizar_lista()
            actual = self._clave_archivo(self.cancion_actual) if self.cancion_actual else None
            recientes = Counter(x.get("ruta") for x in self.memoria_musical.get("recientes", []) if isinstance(x, dict))
            valores = []
            for p in biblioteca:
                clave = self._clave_archivo(p)
                if excluir_actual and clave == actual:
                    continue
                r = self.memoria_musical.get("canciones", {}).get(clave, {})
                art = r.get("artista_estimado", self._metadatos_archivo(p)["artista_estimado"])
                ar = self.memoria_musical.get("artistas", {}).get(art, {})
                rep, fin, saltos = (self._numero(r.get(k)) for k in ("reproducciones", "terminadas", "saltos"))
                v = self._numero(r.get("puntuacion")) + .15 * self._numero(ar.get("puntuacion"))
                v += 2 * self._predecir_afinidad_red(r) + min(1.5, fin * .25) - min(2, saltos * .65)
                v += 1.5 / math.sqrt(1 + rep) - min(3, recientes[clave] * .8)
                if rep == 0:
                    v += .5
                valores.append((v + random.uniform(-.15, .15), p))
            valores.sort(reverse=True, key=lambda x: x[0])
            return [p for _, p in valores[:limite]]
    def obtener_perfil_musical(self):
        with self._lock:
            canciones = self.memoria_musical.get("canciones", {})
            fav = sorted(canciones.values(), key=lambda r: self._numero(r.get("puntuacion")), reverse=True)[:10]
            arts = sorted(self.memoria_musical.get("artistas", {}).items(), key=lambda x: self._numero(x[1].get("puntuacion")), reverse=True)[:10]
            return {
                "canciones_aprendidas": len(canciones),
                "canciones_recientes": len(self.memoria_musical.get("recientes", [])),
                "entrenamientos_red": int(self.memoria_musical.get("modelo", {}).get("pasos", 0)),
                "canciones_favoritas": [{"nombre": r.get("nombre"), "puntuacion": round(self._numero(r.get("puntuacion")), 2),
                    "reproducciones": r.get("reproducciones", 0), "terminadas": r.get("terminadas", 0), "saltos": r.get("saltos", 0)} for r in fav],
                "artistas_estimados": [{"nombre": n, "puntuacion": round(self._numero(r.get("puntuacion")), 2)} for n, r in arts],
                "ruta_memoria": str(self.ruta_memoria)
            }
    def _inicializar_audio(self):
        with self._lock:
            try:
                if self.cerrado:
                    return False
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
                self.inicializado, self.cerrado = True, False
                pygame.mixer.music.set_volume(self.volumen)
                print(f"[ AUDIO ] Motor 3.6 inicializado. Volumen: {self.obtener_volumen()}%")
                return True
            except Exception as e:
                self.inicializado = False
                print(f"[ AUDIO ] Error inicializando pygame: {e}")
                return False
    def asegurar_carpeta(self):
        try:
            self.carpeta.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            print(f"[ AUDIO ] Error creando carpeta: {e}")
            return False
    def actualizar_lista(self):
        with self._lock:
            if not self.asegurar_carpeta():
                self.canciones, self.indice_actual = [], -1
                return []
            try:
                # Caché: solo se vuelve a leer el disco si la carpeta cambió (alta, baja o renombrado).
                firma = self.carpeta.stat().st_mtime_ns
                if firma != getattr(self, "_firma_biblioteca", None) or not self.canciones:
                    self.canciones = sorted((p for p in self.carpeta.iterdir() if p.is_file() and p.suffix.lower() in self.EXTENSIONES_AUDIO), key=lambda p: p.name.lower())
                    self._firma_biblioteca = firma
                if self.cancion_actual is not None:
                    try:
                        self.indice_actual = self.canciones.index(self.cancion_actual)
                    except ValueError:
                        self.indice_actual = -1
                return self.canciones.copy()
            except Exception as e:
                print(f"[ AUDIO ] Error actualizando biblioteca: {e}")
                self.canciones, self.indice_actual = [], -1
                return []
    def obtener_canciones(self):
        return self.actualizar_lista()
    def cantidad_canciones(self):
        with self._lock:
            return len(self.canciones)
    def obtener_nombre_actual(self):
        with self._lock:
            return self.cancion_actual.name if self.cancion_actual else None
    def obtener_ruta_actual(self):
        with self._lock:
            return self.cancion_actual
    def esta_reproduciendo(self):
        with self._lock:
            return self.reproduciendo and not self.pausado
    def esta_pausado(self):
        with self._lock:
            return self.pausado
    def _normalizar_texto(self, texto):
        return self._texto_busqueda(texto)
    def buscar_cancion(self, nombre):
        q = self._normalizar_texto(nombre)
        if not q:
            return None
        self.actualizar_lista()
        for p in self.canciones:
            if self._normalizar_texto(p.name) == q or self._normalizar_texto(p.stem) == q:
                return p
        candidatas = [p for p in self.canciones if q in self._normalizar_texto(p.stem)]
        if candidatas:
            return candidatas[0]
        mejor = max(self.canciones, key=lambda p: SequenceMatcher(None, q, self._normalizar_texto(p.stem)).ratio(), default=None)
        return mejor if mejor and SequenceMatcher(None, q, self._normalizar_texto(mejor.stem)).ratio() >= self.UMBRAL_BUSQUEDA_APROXIMADA else None
    def buscar_canciones(self, consulta):
        q = self._normalizar_texto(consulta)
        if not q:
            return []
        self.actualizar_lista()
        r = [(1 if (n := self._normalizar_texto(p.stem)) == q else .9 if q in n else SequenceMatcher(None, q, n).ratio(), p) for p in self.canciones]
        return [p for score, p in sorted(r, key=lambda x: x[0], reverse=True) if score >= .35]
    def _seleccionar_automatica(self):
        if self.cola:
            return self.cola[0]
        if self.modo_aleatorio:
            return self._seleccionar_aleatoria()
        if self.indice_actual >= 0 and self.canciones:
            return self.canciones[(self.indice_actual + 1) % len(self.canciones)]
        return self.canciones[0] if self.canciones else None
    def _seleccionar_aleatoria(self):
        if not self.canciones:
            return None
        disp = [p for p in self.canciones if p != self.cancion_actual] or self.canciones.copy()
        recientes = Counter(x.get("ruta") for x in self.memoria_musical.get("recientes", []) if isinstance(x, dict))
        locales = {self._clave_archivo(p) for p in self.historial[-self.CANCIONES_RECIENTES_A_EVITAR:]}
        artistas = Counter(self._metadatos_archivo(x.get("nombre", "")).get("artista_estimado", "desconocido")
                           for x in self.memoria_musical.get("recientes", [])[-15:] if isinstance(x, dict))
        vals = []
        for p in disp:
            k = self._clave_archivo(p)
            r = self.memoria_musical.get("canciones", {}).get(k, {})
            art = r.get("artista_estimado", self._metadatos_archivo(p)["artista_estimado"])
            rep, fin, saltos, inter = (max(0, self._numero(r.get(x))) for x in ("reproducciones", "terminadas", "saltos", "interrupciones"))
            v = .42 * self._numero(r.get("puntuacion")) + 1.8 * self._predecir_afinidad_red(r)
            v += min(1.3, fin * .22) - min(2.2, saltos * .65) - min(.8, inter * .12) + 1.65 / math.sqrt(1 + rep)
            if rep == 0:
                v += .45
            v -= min(3, recientes[k] * .9) + (1.2 if k in locales else 0) + min(1.4, artistas[art] * .35)
            ultima = self._numero(r.get("ultima_reproduccion"))
            if ultima:
                v += min(.8, math.log1p(max(0, time.time() - ultima) / 86400) / 5)
            vals.append((v + random.uniform(-.18, .18), p))
        mx = max(v for v, _ in vals)
        pesos = [math.exp(max(-20, min(0, (v - mx) / 1.35)) ) for v, _ in vals]
        try:
            return random.choices([p for _, p in vals], weights=pesos, k=1)[0]
        except (ValueError, IndexError, OverflowError):
            return random.choice(disp)
    def fundir_salida(self, duracion=None):
        """Desvanece la música hasta el silencio y espera a que acabe (se usa antes de cerrar por una purga)."""
        return self._fundir_salida(duracion)

    def _fundir_salida(self, duracion=None):
        """Fundido de salida síncrono: no permite detener/cambiar antes de acabar."""
        duracion = self.DURACION_FADE_OUT if duracion is None else max(0.0, float(duracion))
        try:
            if not self.inicializado or not pygame.mixer.get_init():
                return False
            if self.pausado or not self.reproduciendo or not pygame.mixer.music.get_busy():
                return True
            if duracion <= 0:
                pygame.mixer.music.set_volume(0.0)
                return True
            # FadeController realiza la transición de volumen.
            self.fade_controller.fade_out(duracion)
            # Salvaguarda: esperar al volumen cero aunque el controlador
            limite = time.monotonic() + duracion + 0.75
            while time.monotonic() < limite:
                if not pygame.mixer.get_init():
                    return False
                if pygame.mixer.music.get_volume() <= 0.005:
                    break
                time.sleep(0.02)
            pygame.mixer.music.set_volume(0.0)
            return True
        except Exception as e:
            print(f"[ AUDIO ] Error en fade-out: {e}")
            try:
                if pygame.mixer.get_init():
                    pygame.mixer.music.set_volume(0.0)
            except Exception:
                pass
            return False
    def _reproducir_archivo(self, archivo, registrar_historial=True):
        if archivo is None:
            return False
        archivo = Path(archivo)
        if not archivo.is_file() or archivo.suffix.lower() not in self.EXTENSIONES_AUDIO or not self.inicializado or self.cerrado:
            print(f"[ AUDIO ] Archivo no disponible o formato incompatible: {archivo}")
            return False
        with self._lock:
            anterior = self.cancion_actual
            estaba_sonando = bool(anterior is not None and self.reproduciendo and not self.pausado)
            # Registrar el salto antes de modificar la pista actual.
            if anterior is not None and self.reproduciendo and anterior != archivo:
                self._registrar_fin_actual("salto")
            try:
                # NO cancelar el controlador antes del fade-out.
                if estaba_sonando:
                    self._fundir_salida(self.DURACION_FADE_OUT)
                else:
                    self.fade_controller.cancelar()
                pygame.mixer.music.stop()
                fuente = self._fuente_al_empezar(archivo)
                pygame.mixer.music.load(str(fuente))
                self.fuente_actual = fuente
                pygame.mixer.music.set_volume(0.0)
                pygame.mixer.music.play()
                self.cancion_actual = archivo
                self._preparar_siguiente()
                self._medir_nivel(archivo)
                try:
                    self.indice_actual = self.canciones.index(archivo)
                except ValueError:
                    self.indice_actual = -1
                self.reproduciendo, self.pausado = True, False
                self.tiempo_inicio, self.tiempo_acumulado = time.time(), 0
                self._inicio_monotono = time.monotonic()
                if registrar_historial:
                    self._agregar_historial(archivo)
                self._registrar_evento("reproduccion", archivo, 0)
                # El fundido de entrada comienza desde volumen cero.
                self.fade_controller.fade_in(self.volumen, self.DURACION_FADE_IN)
                self.guardar_memoria_musical()
                print(f"[ AUDIO ] ▶ Reproduciendo: {archivo.name}")
                return True
            except Exception as e:
                print(f"[ AUDIO ] Error reproduciendo {archivo.name}: {e}")
                self.reproduciendo = self.pausado = False
                self.tiempo_inicio, self.tiempo_acumulado = None, 0
                return False
    def reproducir(self, nombre=None):
        with self._lock:
            if self.cerrado or not self.inicializado:
                print("[ AUDIO ] Reproductor cerrado o motor no inicializado.")
                return False
            self.actualizar_lista()
            if not self.canciones:
                print("[ AUDIO ] No hay canciones.")
                return False
            if nombre:
                archivo = self.buscar_cancion(nombre)
                if archivo is None:
                    print(f"[ AUDIO ] No encontré: {nombre}")
                    return False
                return self._reproducir_archivo(archivo)
            # La reproducción automática utiliza el mismo flujo que "siguiente":
            return self.siguiente()
    def continuar_al_iniciar(self):
        """Arranque de MILLER (con la ventana ya abierta): la música sigue donde quedó y sonando.
        Si no había canción guardada, empieza la biblioteca. Devuelve True si suena."""
        with self._lock:
            if self.cerrado or not self.inicializado:
                return False
            pendiente, self._pista_pendiente = self._pista_pendiente, None
            if pendiente and Path(pendiente[0]).is_file():
                return bool(self._restaurar_pista(pendiente[0], pendiente[1], True, False))
            if self.reproduciendo and self.pausado:
                return self.continuar()
            if self.reproduciendo:
                return True
        return self.reproducir()
    def pausar(self):
        with self._lock:
            if not self.inicializado or self.cerrado or not self.reproduciendo or self.pausado:
                return False
            try:
                self.tiempo_acumulado = self._calcular_tiempo_actual()
                # Primero termina el fundido; después se pausa el canal en silencio.
                self._fundir_salida(self.DURACION_FADE_OUT)
                self.fade_controller.cancelar()
                pygame.mixer.music.set_volume(0.0)
                pygame.mixer.music.pause()
                self.tiempo_inicio, self.pausado = None, True
                self.guardar_memoria_musical()
                print("[ AUDIO ] ⏸ Pausado.")
                return True
            except Exception as e:
                print(f"[ AUDIO ] Error pausando: {e}")
                return False
    def continuar(self):
        with self._lock:
            if not self.inicializado or self.cerrado or not self.reproduciendo or not self.pausado:
                return False
            try:
                self.fade_controller.cancelar()
                pygame.mixer.music.set_volume(0.0)
                pygame.mixer.music.unpause()
                self.tiempo_inicio, self.pausado = time.time(), False
                self.fade_controller.fade_in(self.volumen, self.DURACION_FADE_IN)
                self.guardar_memoria_musical()
                print("[ AUDIO ] ▶ Continuando.")
                return True
            except Exception as e:
                print(f"[ AUDIO ] Error continuando: {e}")
                return False
    def detener(self):
        with self._lock:
            if not self.inicializado or self.cerrado:
                return False
            try:
                if self.reproduciendo and not self.pausado:
                    self._registrar_fin_actual("interrupcion")
                    self._fundir_salida(self.DURACION_FADE_OUT)
                self.fade_controller.cancelar()
                pygame.mixer.music.stop()
                pygame.mixer.music.set_volume(self.volumen)
                self.reproduciendo = self.pausado = False
                self.tiempo_inicio, self.tiempo_acumulado = None, 0
                self.guardar_memoria_musical()
                print("[ AUDIO ] ⏹ Detenido.")
                return True
            except Exception as e:
                print(f"[ AUDIO ] Error deteniendo: {e}")
                return False
    def siguiente(self):
        """Avanza respetando estrictamente la prioridad y recuperando fallos."""
        with self._lock:
            if not self.inicializado or self.cerrado:
                return False
            self.actualizar_lista()
            if not self.canciones:
                return False
            intentadas = set()
            # 1. FIFO: no se consulta ningún otro modo mientras quede cola.
            while self.cola:
                pista = self.cola.pop(0)
                self.guardar_memoria_musical()
                clave = self._clave_archivo(pista)
                if clave in intentadas:
                    continue
                intentadas.add(clave)
                if pista.is_file() and pista.suffix.lower() in self.EXTENSIONES_AUDIO:
                    if self._reproducir_archivo(pista):
                        self.guardar_memoria_musical()
                        return True
                print(f"[ AUDIO ] Pista de cola omitida: {pista.name}")
            # 2. Repetir solo después de agotar la cola.
            if self.modo_repetir and self.cancion_actual:
                pista = self.cancion_actual
                clave = self._clave_archivo(pista)
                if clave not in intentadas and pista.is_file():
                    intentadas.add(clave)
                    if self._reproducir_archivo(pista):
                        self.guardar_memoria_musical()
                        return True
            # 3. Construir candidatos sin duplicar intentos fallidos.
            disponibles = [p for p in self.canciones if p.is_file()
                           and p.suffix.lower() in self.EXTENSIONES_AUDIO
                           and self._clave_archivo(p) not in intentadas]
            if self.modo_aleatorio:
                if disponibles:
                    candidata = self._seleccionar_aleatoria()
                    if candidata in disponibles:
                        disponibles.remove(candidata)
                        disponibles.insert(0, candidata)
                    if len(disponibles) > 1:
                        resto = disponibles[1:]
                        random.shuffle(resto)
                        disponibles = disponibles[:1] + resto
            else:
                disponibles.sort(key=lambda p: p.name.casefold())
                if self.indice_actual >= 0 and self.canciones:
                    siguiente_indice = self.indice_actual + 1
                    orden = self.canciones[siguiente_indice:] + self.canciones[:siguiente_indice]
                    posiciones = {self._clave_archivo(p): i for i, p in enumerate(orden)}
                    disponibles.sort(key=lambda p: posiciones.get(self._clave_archivo(p), len(orden)))
            # 4. Si falla una pista, probar la siguiente alternativa.
            for pista in disponibles:
                if self.cerrado or not self.inicializado:
                    return False
                if self._reproducir_archivo(pista):
                    self.guardar_memoria_musical()
                    return True
                print(f"[ AUDIO ] Pista omitida por error: {pista.name}")
            # 5. No quedan pistas reproducibles.
            self.reproduciendo = self.pausado = False
            self.tiempo_inicio, self.tiempo_acumulado = None, 0.0
            try:
                if pygame.mixer.get_init():
                    self.fade_controller.cancelar()
                    pygame.mixer.music.stop()
                    pygame.mixer.music.set_volume(self.volumen)
            except Exception as e:
                print(f"[ AUDIO ] Error recuperando el motor: {e}")
            self.guardar_memoria_musical()
            print("[ AUDIO ] No quedan pistas reproducibles.")
            return False
    def anterior(self):
        with self._lock:
            if not self.inicializado or self.cerrado or len(self.historial) < 2:
                return False
            nuevo = len(self.historial) - 2 if self._indice_historial >= len(self.historial) - 1 else self._indice_historial - 1
            self._indice_historial = max(0, nuevo)
            p = self.historial[self._indice_historial]
            if not p.exists():
                print(f"[ AUDIO ] La canción del historial ya no existe: {p.name}")
                return False
            return self._reproducir_archivo(p, registrar_historial=False)
    def agregar_a_cola(self, nombre):
        if not nombre:
            return False
        p = self.buscar_cancion(nombre)
        if p is None:
            print(f"[ AUDIO ] No encontré: {nombre}")
            return False
        return self.agregar_archivo_a_cola(p)
    def agregar_archivo_a_cola(self, archivo):
        if archivo is None:
            return False
        p = Path(archivo)
        if not p.is_file() or p.suffix.lower() not in self.EXTENSIONES_AUDIO:
            return False
        with self._lock:
            if self.cerrado:
                return False
            self.cola.append(p)
            if not self.guardar_memoria_musical():
                self.cola.pop()
                return False
            print(f"[ AUDIO ] ➕ Cola ({len(self.cola)}): {p.name}")
            return True
    def eliminar_de_cola(self, posicion):
        try:
            i = int(posicion) - 1
        except (TypeError, ValueError):
            return False
        with self._lock:
            if not 0 <= i < len(self.cola):
                return False
            p = self.cola.pop(i)
            if not self.guardar_memoria_musical():
                self.cola.insert(i, p)
                return False
            print(f"[ AUDIO ] ❌ Eliminada de cola: {p.name}")
            return True
    def quitar_de_cola(self, nombre_o_posicion):
        if nombre_o_posicion is None:
            return False
        texto = str(nombre_o_posicion).strip()
        if texto.isdigit():
            return self.eliminar_de_cola(int(texto))
        q = self._normalizar_texto(texto)
        if not q:
            return False
        with self._lock:
            indice = next((i for i, p in enumerate(self.cola)
                           if q == self._normalizar_texto(p.name)
                           or q == self._normalizar_texto(p.stem)
                           or q in self._normalizar_texto(p.stem)), None)
            if indice is None:
                return False
            p = self.cola.pop(indice)
            if not self.guardar_memoria_musical():
                self.cola.insert(indice, p)
                return False
            print(f"[ AUDIO ] ❌ Eliminada de cola: {p.name}")
            return True
    def limpiar_cola(self):
        with self._lock:
            anterior = self.cola.copy()
            self.cola.clear()
            if not self.guardar_memoria_musical():
                self.cola = anterior
                return False
            print(f"[ AUDIO ] 🧹 Cola limpiada: {len(anterior)} canciones.")
            return True
    def obtener_cola(self):
        with self._lock:
            return self.cola.copy()
    def cantidad_en_cola(self):
        with self._lock:
            return len(self.cola)
    def alternar_aleatorio(self):
        with self._lock:
            self.modo_aleatorio = not self.modo_aleatorio
            activo = self.modo_aleatorio
            self.guardar_memoria_musical()
        print(f"[ AUDIO ] 🔀 Aleatorio {'activado' if activo else 'desactivado'}.")
        return activo
    def establecer_aleatorio(self, activo):
        with self._lock:
            self.modo_aleatorio = bool(activo)
            self.guardar_memoria_musical()
            return self.modo_aleatorio
    def alternar_repetir(self):
        with self._lock:
            self.modo_repetir = not self.modo_repetir
            activo = self.modo_repetir
            self.guardar_memoria_musical()
        print(f"[ AUDIO ] 🔁 Repetición {'activada' if activo else 'desactivada'}.")
        return activo
    def establecer_repetir(self, activo):
        with self._lock:
            self.modo_repetir = bool(activo)
            self.guardar_memoria_musical()
            return self.modo_repetir
    def _agregar_historial(self, archivo):
        if archivo is None:
            return
        p = Path(archivo)
        if self._indice_historial >= 0 and self._indice_historial < len(self.historial) - 1:
            self.historial = self.historial[:self._indice_historial + 1]
        if self.historial and self.historial[-1] == p:
            self._indice_historial = len(self.historial) - 1
            return
        self.historial.append(p)
        self.historial = self.historial[-self.MAX_HISTORIAL:]
        self._indice_historial = len(self.historial) - 1
    def obtener_historial(self):
        with self._lock:
            return self.historial.copy()
    def limpiar_historial(self):
        with self._lock:
            self.historial.clear()
            self._indice_historial = -1
            self.guardar_memoria_musical()
        return True
    def establecer_volumen(self, volumen):
        try:
            v = max(0.0, min(1.0, float(volumen)))
        except (TypeError, ValueError):
            return False
        with self._lock:
            anterior = self.volumen
            if v == 0.0 and anterior > 0.0:
                self._volumen_antes_silencio = anterior
            elif v > 0.0:
                self._volumen_antes_silencio = v
            self.volumen = v
            try:
                if self.inicializado and not self.cerrado:
                    if v == 0.0 and self.reproduciendo and not self.pausado:
                        self._fundir_salida(self.DURACION_FADE_OUT)
                    elif v > 0.0 and self.reproduciendo and not self.pausado and anterior == 0.0:
                        self.fade_controller.cancelar()
                        pygame.mixer.music.set_volume(0.0)
                        self._fundido_volumen(v, self.DURACION_FADE_IN)
                    elif self.reproduciendo and not self.pausado:
                        # Subir / bajar: transición suave desde el nivel actual, nunca de golpe.
                        self._fundido_volumen(v, self.DURACION_FADE_VOLUMEN)
                    else:
                        self.fade_controller.cancelar()
                        pygame.mixer.music.set_volume(v if not self.pausado else 0.0)
                return self.guardar_memoria_musical()
            except Exception as e:
                print(f"[ AUDIO ] Error volumen: {e}")
                return False
    def _fundido_volumen(self, objetivo, duracion):
        """Lanza la transición de volumen en segundo plano (no bloquea el lock ni la respuesta)."""
        fade = self.fade_controller
        def tarea():
            try:
                fade.transicionar(objetivo, duracion)
            except Exception as e:
                print(f"[ AUDIO ] Error en fundido de volumen: {e}")
                try:
                    pygame.mixer.music.set_volume(objetivo)
                except Exception:
                    pass
        threading.Thread(target=tarea, daemon=True, name="MILLER-FundidoVolumen").start()
        return True
    def silenciar(self):
        """Silencia con fundido y conserva el último volumen audible."""
        return self.establecer_volumen(0.0)
    def restaurar_volumen(self):
        """Recupera el volumen anterior al silencio mediante fundido de entrada."""
        with self._lock:
            objetivo = max(0.01, min(1.0, self._numero(getattr(self, "_volumen_antes_silencio", self.VOLUMEN_INICIAL), self.VOLUMEN_INICIAL)))
        return self.establecer_volumen(objetivo)
    def establecer_volumen_porcentaje(self, porcentaje):
        try:
            return self.establecer_volumen(max(0, min(100, float(porcentaje))) / 100)
        except (TypeError, ValueError):
            return False
    def subir_volumen(self, cantidad=None):
        try:
            cantidad = self.INCREMENTO_VOLUMEN if cantidad is None else float(cantidad)
        except (TypeError, ValueError):
            return False
        return self.establecer_volumen(self.volumen + cantidad)
    def bajar_volumen(self, cantidad=None):
        try:
            cantidad = self.INCREMENTO_VOLUMEN if cantidad is None else float(cantidad)
        except (TypeError, ValueError):
            return False
        return self.establecer_volumen(self.volumen - cantidad)
    def subir_volumen_porcentaje(self, porcentaje=10):
        try:
            return self.establecer_volumen_porcentaje(self.obtener_volumen() + float(porcentaje))
        except (TypeError, ValueError):
            return False
    def bajar_volumen_porcentaje(self, porcentaje=10):
        try:
            return self.establecer_volumen_porcentaje(self.obtener_volumen() - float(porcentaje))
        except (TypeError, ValueError):
            return False
    def obtener_volumen(self):
        with self._lock:
            return round(self.volumen * 100)
    # ------------------------------------------------------------ ecualizador
    def _fuente(self, archivo):
        """Qué cargar: la copia ecualizada si está lista; si no, el original."""
        if self.ecualizador is None:
            return Path(archivo)
        try:
            return Path(self.ecualizador.fuente_para(archivo))
        except Exception as e:
            print(f"[ AUDIO ] Ecualizador: {e}")
            return Path(archivo)
    def _preparar_siguiente(self):
        """Deja ecualizada de antemano la siguiente de la cola (así suena ya ecualizada desde el inicio)."""
        if self.ecualizador is not None and self.cola:
            try:
                self.ecualizador.preparar(self.cola[0], avisar=False)
            except Exception:
                pass
    def cambiar_fuente_en_vivo(self, original, nueva=None):
        """La copia ecualizada de la canción que suena ya está lista: se pasa a ella en el mismo segundo."""
        with self._lock:
            if self.cerrado or not self.inicializado or self.cancion_actual is None:
                return False
            if Path(original) != Path(self.cancion_actual):
                return False
            nueva = Path(nueva) if nueva else self._fuente(self.cancion_actual)
            if self.fuente_actual is not None and Path(self.fuente_actual) == nueva:
                return False
            posicion = self._calcular_tiempo_actual()
            sonando = self.reproduciendo and not self.pausado
            try:
                if sonando:
                    self._fundir_salida(0.08)
                pygame.mixer.music.stop()
                pygame.mixer.music.load(str(nueva))
                pygame.mixer.music.set_volume(0.0)
                pygame.mixer.music.play(start=posicion)
                self.fuente_actual = nueva
                self.tiempo_acumulado, self._inicio_monotono = posicion, time.monotonic()
                self.tiempo_inicio = time.time() if sonando else None
                if sonando:
                    self.fade_controller.fade_in(self.volumen, 0.2)
                else:
                    pygame.mixer.music.pause()
                print(f"[ AUDIO ] 🎚 Ecualizada: {Path(original).name}")
                return True
            except Exception as e:
                print(f"[ AUDIO ] No se pudo aplicar la ecualización: {e}")
                return False
    def _fuente_al_empezar(self, archivo):
        """Al empezar una canción: si su copia ecualizada se está creando, espera un poco (máx. ESPERA_COPIA_INICIO)
        para sonar ya ecualizada desde el primer segundo. Si no llega a tiempo, suena la original."""
        fuente = self._fuente(archivo)
        eq = self.ecualizador
        if eq is None or Path(fuente) != Path(archivo) or not eq.preparando(archivo):
            return fuente
        limite = time.monotonic() + self.ESPERA_COPIA_INICIO
        while time.monotonic() < limite and eq.preparando(archivo):
            time.sleep(0.1)
            lista = Path(eq.fuente_para(archivo, preparar=False))
            if lista != Path(archivo):
                return lista
        return Path(eq.fuente_para(archivo, preparar=False))

    def reaplicar_ecualizacion(self):
        """Cambio pedido por el usuario: suena ya si la copia existe; si se está creando, cambia en cuanto esté lista."""
        actual = self.cancion_actual
        if self.ecualizador is None or actual is None:
            return False
        ruta, eq = Path(actual), self.ecualizador
        if eq.sin_efecto(ruta):
            return self.cambiar_fuente_en_vivo(actual, ruta)
        destino = Path(eq.fuente_para(ruta))
        if destino != ruta:
            return self.cambiar_fuente_en_vivo(actual, destino)
        self._cambios_pedidos.add(ruta)              # aún creándose: el aviso la cambiará, sin cortes antes
        return True

    def ecualizada_lista(self, original):
        """Aviso de una copia terminada en segundo plano. Solo cambia si el usuario acaba de pedir ese cambio:
        nunca cambia sola a mitad de canción (eso sonaba a bajón de volumen)."""
        ruta = Path(original)
        if ruta not in self._cambios_pedidos:
            return False
        self._cambios_pedidos.discard(ruta)
        return self.cambiar_fuente_en_vivo(ruta)
    def _calcular_tiempo_actual(self):
        return max(0, self.tiempo_acumulado + (time.time() - self.tiempo_inicio if self.tiempo_inicio is not None else 0))
    def obtener_tiempo_reproduccion(self):
        with self._lock:
            return int(self._calcular_tiempo_actual()) if self.cancion_actual else 0
    def _iniciar_monitor(self):
        with self._lock:
            if self._monitor_activo or self.cerrado or not self.inicializado:
                return
            self._monitor_activo = True
            self._monitor_hilo = threading.Thread(target=self._monitor_reproduccion, daemon=True, name="MILLER-AudioMonitor")
            self._monitor_hilo.start()
        print("[ AUDIO ] Monitor automático iniciado.")
    def _monitor_reproduccion(self):
        while self._monitor_activo:
            try:
                with self._lock:
                    if self.cerrado:
                        break
                    if self.inicializado and self.reproduciendo and not self.pausado and not pygame.mixer.music.get_busy():
                        self._manejar_fin_cancion()
                    elif self.reproduciendo and not self.pausado:
                        self._guardar_estado_silencioso()
            except Exception as e:
                print(f"[ AUDIO ] Error monitor: {e}")
            time.sleep(self.INTERVALO_MONITOR)
    def _guardar_estado_silencioso(self):
        ahora = time.monotonic()
        if not hasattr(self, "_ultimo_guardado_estado"):
            self._ultimo_guardado_estado = 0
        if ahora - self._ultimo_guardado_estado >= 15:          # menos escrituras a disco (firma y respaldo)
            self._ultimo_guardado_estado = ahora
            self.guardar_memoria_musical()
    def _manejar_fin_cancion(self):
        """Gestiona el fin de pista y mantiene la reproducción continua."""
        with self._lock:
            if self.cerrado or not self.reproduciendo or self._procesando_fin:
                return
            # No interpretar una carga reciente como un final real.
            if self._inicio_monotono is not None:
                if time.monotonic() - self._inicio_monotono < 1.0:
                    return
            self._procesando_fin = True
            try:
                actual = self.cancion_actual
                print(f"[ AUDIO ] ✓ Terminó: {self.obtener_nombre_actual()}")
                # Registrar el final una sola vez.
                if actual is not None:
                    self._registrar_fin_actual("terminada")
                self.reproduciendo = False
                self.pausado = False
                self.tiempo_inicio = None
                self.tiempo_acumulado = 0.0
                # siguiente() prioriza la cola, luego repetir,
                if not self.siguiente():
                    print("[ AUDIO ] No se pudo reproducir la siguiente pista.")
            except Exception as e:
                print(f"[ AUDIO ] Error gestionando fin de canción: {e}")
            finally:
                self._procesando_fin = False
    def obtener_estado(self):
        with self._lock:
            ruta = self.cancion_actual
            return {
                "inicializado": self.inicializado, "cerrado": self.cerrado,
                "reproduciendo": self.reproduciendo, "pausado": self.pausado,
                "cancion_actual": self.obtener_nombre_actual(), "ruta_actual": str(ruta) if ruta else None,
                "indice_actual": self.indice_actual, "cantidad_canciones": len(self.canciones),
                "cantidad_en_cola": len(self.cola), "volumen": self.obtener_volumen(),
                "aleatorio": self.modo_aleatorio, "repetir": self.modo_repetir,
                "tiempo_reproduccion": self.obtener_tiempo_reproduccion(),
                "historial": [p.name for p in self.historial], "indice_historial": self._indice_historial,
                "cola": [p.name for p in self.cola], "fade": self.fade_controller.obtener_estado(),
                "memoria_musical": self.obtener_perfil_musical()
            }
    def cerrar(self):
        """Guarda, espera al monitor, desvanece el audio y libera pygame."""
        with self._lock:
            if self.cerrado:
                return
            print("[ AUDIO ] Guardando estado y cerrando reproductor...")
            try:
                if self.reproduciendo and not self.pausado:
                    self.tiempo_acumulado = self._calcular_tiempo_actual()
                self.tiempo_inicio = None
                self.guardar_memoria_musical(inmediato=True)
            except Exception as e:
                print(f"[ AUDIO ] Error guardando memoria musical: {e}")
            self._monitor_activo = False
            monitor = self._monitor_hilo
        # Esperar fuera del bloqueo para no bloquear el hilo del monitor.
        try:
            if monitor and monitor.is_alive() and monitor is not threading.current_thread():
                monitor.join(timeout=3.0)
                if monitor.is_alive():
                    print("[ AUDIO ] Aviso: el monitor sigue activo.")
        except Exception as e:
            print(f"[ AUDIO ] Error esperando al monitor: {e}")
        # El reproductor sigue marcado como abierto durante el fade-out.
        try:
            if self.inicializado and pygame.mixer.get_init() and self.reproduciendo and not self.pausado and pygame.mixer.music.get_busy():
                self._fundir_salida(self.DURACION_FADE_OUT)
        except Exception as e:
            print(f"[ AUDIO ] Error durante fade-out de cierre: {e}")
        # Marcar cerrado solamente después del fundido.
        with self._lock:
            self.cerrado = True
        try:
            if getattr(self, "fade_controller", None) is not None:
                self.fade_controller.cerrar()
        except Exception as e:
            print(f"[ AUDIO ] Error cerrando FadeController: {e}")
        try:
            if self.inicializado and pygame.mixer.get_init():
                pygame.mixer.music.stop()
                pygame.mixer.quit()
        except Exception as e:
            print(f"[ AUDIO ] Error cerrando pygame: {e}")
        with self._lock:
            self.reproduciendo = self.pausado = False
            self.inicializado = False
            self._procesando_fin = False
            self._monitor_hilo = None
        print("[ AUDIO ] Reproductor cerrado correctamente.")
