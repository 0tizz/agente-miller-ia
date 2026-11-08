"""MILLER · Descargador de musica."""
import json
import logging
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from utilidades import seguridad
# RUTAS ABSOLUTAS DEL PROYECTO
try:
    from configuracion import RUTA_BASE as RAIZ          # funciona también en el .exe
except Exception:
    RAIZ = Path(__file__).resolve().parent.parent
CARPETA_MODELOS = RAIZ / "modelos"
CARPETA_FFMPEG = CARPETA_MODELOS / "ffmpeg-master-gpl"
CARPETA_BIN = CARPETA_FFMPEG / "bin"
AUDIOS = RAIZ / "audios"
DATOS = RAIZ / "datos"
HISTORIAL = DATOS / "historial_descargas.json"
for carpeta in (AUDIOS, DATOS):
    carpeta.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger("MILLER.DescargadorMusica")
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO)

def buscar_ejecutable(nombre):
    """Busca un .exe primero en la ruta configurada, luego en modelos y PATH."""
    nombre = nombre if nombre.lower().endswith(".exe") else nombre + ".exe"
    candidatos = [CARPETA_BIN / nombre, CARPETA_FFMPEG / nombre, CARPETA_MODELOS / nombre,]
    for ruta in candidatos:
        try:
            if ruta.is_file():
                return ruta.resolve()
        except OSError:
            logger.debug("No se pudo comprobar %s", ruta, exc_info=True)
    if CARPETA_MODELOS.is_dir():
        try:
            for ruta in CARPETA_MODELOS.rglob(nombre):
                try:
                    if ruta.is_file():
                        return ruta.resolve()
                except OSError:
                    continue
        except (OSError, PermissionError):
            logger.warning("No se pudo recorrer completamente %s", CARPETA_MODELOS)
    encontrado = shutil.which(nombre) or shutil.which(nombre.removesuffix(".exe"))
    if encontrado:
        try:
            ruta = Path(encontrado).resolve()
            if ruta.is_file():
                return ruta
        except (OSError, RuntimeError):
            logger.debug("Ruta de PATH inválida: %s", encontrado, exc_info=True)
    return None

def comprobar_ejecutable(ruta, timeout=8):
    """Ejecuta --version para distinguir un archivo válido de un .exe defectuoso."""
    if not ruta:
        return {"disponible": False, "funciona": False, "version": None, "error": "Ejecutable no encontrado."}
    ruta = Path(ruta)
    if not ruta.is_file():
        return {"disponible": False, "funciona": False, "version": None,
                "error": f"No existe el archivo: {ruta}"}
    try:
        resultado = subprocess.run(
            [str(ruta), "-version"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        salida = (resultado.stdout or resultado.stderr or "").strip()
        primera_linea = salida.splitlines()[0] if salida else ""
        funciona = resultado.returncode == 0 and bool(salida)
        return {
            "disponible": True,
            "funciona": funciona,
            "version": primera_linea[:300],
            "codigo_salida": resultado.returncode,
            "error": None if funciona else (salida[:500] or "El ejecutable no devolvió versión."),
        }
    except subprocess.TimeoutExpired:
        return {"disponible": True, "funciona": False, "version": None,
                "error": f"El ejecutable tardó más de {timeout} segundos."}
    except (OSError, ValueError) as error:
        return {"disponible": True, "funciona": False, "version": None, "error": str(error)}

class DescargadorMusica:
    """Descargador con validación, reintentos, cancelación y registro local."""
    def __init__(self):
        self.raiz = RAIZ
        self.carpeta = AUDIOS
        self.archivo_historial = HISTORIAL
        self.ffmpeg = buscar_ejecutable("ffmpeg.exe")
        self.ffprobe = buscar_ejecutable("ffprobe.exe")
        self._bloqueo = threading.RLock()
        self._cancelacion = threading.Event()
        self._descarga_activa = False
        self._hilo = None
        self._ultima_error = None
        self._progreso = {"estado": "inactivo", "porcentaje": 0.0, "mensaje": "Preparado", "titulo": "",}
    def estado(self, comprobar_binarios=False):
        try:
            import yt_dlp
            yt_dlp_disponible = True
            version_yt_dlp = getattr(yt_dlp.version, "__version__", "disponible")
        except ImportError:
            yt_dlp_disponible = False
            version_yt_dlp = None
        # Refresca rutas por si el usuario añadió FFmpeg después de iniciar MILLER.
        self.ffmpeg = buscar_ejecutable("ffmpeg.exe")
        self.ffprobe = buscar_ejecutable("ffprobe.exe")
        ffmpeg_info = comprobar_ejecutable(self.ffmpeg) if comprobar_binarios else None
        ffprobe_info = comprobar_ejecutable(self.ffprobe) if comprobar_binarios else None
        with self._bloqueo:
            progreso = dict(self._progreso)
            activa = self._descarga_activa
        resultado = {
            "archivo_modulo": str(Path(__file__).resolve()),
            "carpeta_raiz": str(RAIZ),
            "carpeta_modelos": str(CARPETA_MODELOS),
            "carpeta_ffmpeg_esperada": str(CARPETA_FFMPEG),
            "carpeta_bin_esperada": str(CARPETA_BIN),
            "carpeta_audios": str(self.carpeta),
            "carpeta_existe": self.carpeta.is_dir(),
            "carpeta_modelos_existe": CARPETA_MODELOS.is_dir(),
            "carpeta_bin_existe": CARPETA_BIN.is_dir(),
            "ffmpeg": str(self.ffmpeg) if self.ffmpeg else "NO ENCONTRADO",
            "ffprobe": str(self.ffprobe) if self.ffprobe else "NO ENCONTRADO",
            "ffmpeg_disponible": bool(self.ffmpeg and self.ffmpeg.is_file()),
            "ffprobe_disponible": bool(self.ffprobe and self.ffprobe.is_file()),
            "yt_dlp_disponible": yt_dlp_disponible,
            "version_yt_dlp": version_yt_dlp,
            "descarga_activa": activa,
            "progreso": progreso,
            "ultima_error": self._ultima_error,
            "historial": str(self.archivo_historial),
        }
        if comprobar_binarios:
            resultado["prueba_ffmpeg"] = ffmpeg_info
            resultado["prueba_ffprobe"] = ffprobe_info
        return resultado
    def obtener_progreso(self):
        with self._bloqueo:
            return dict(self._progreso)
    def _actualizar(self, estado=None, porcentaje=None, mensaje=None, titulo=None):
        with self._bloqueo:
            if estado is not None:
                self._progreso["estado"] = str(estado)
            if porcentaje is not None:
                try:
                    self._progreso["porcentaje"] = round(max(0.0, min(100.0, float(porcentaje))), 1)
                except (TypeError, ValueError):
                    pass
            if mensaje is not None:
                self._progreso["mensaje"] = str(mensaje)
            if titulo is not None:
                self._progreso["titulo"] = str(titulo)
    def _informar(self, callback, estado=None, porcentaje=None, mensaje=None, titulo=None):
        self._actualizar(estado, porcentaje, mensaje, titulo)
        if callback:
            try:
                callback(self.obtener_progreso())
            except Exception:
                logger.exception("El callback de progreso produjo un error; la descarga continúa.")
    def _leer_historial(self):
        if not self.archivo_historial.is_file():
            return []
        try:
            with self.archivo_historial.open("r", encoding="utf-8-sig") as archivo:
                datos = json.load(archivo)
            if isinstance(datos, dict):
                datos = datos.get("descargas", [])
            if not isinstance(datos, list):
                logger.warning("El formato del historial no es una lista. Se inicia vacío.")
                return []
            return [item for item in datos if isinstance(item, dict)]
        except json.JSONDecodeError:
            # Conserva el archivo dañado para permitir recuperación manual.
            respaldo = self.archivo_historial.with_name(
                f"historial_descargas_danado_{datetime.now():%Y%m%d_%H%M%S}.json"
            )
            try:
                shutil.copy2(self.archivo_historial, respaldo)
                logger.error("Historial JSON inválido. Copia de respaldo: %s", respaldo)
            except OSError:
                logger.exception("No se pudo respaldar el historial dañado.")
            return []
        except OSError:
            logger.exception("No se pudo leer el historial.")
            return []
    def _guardar_historial(self, registro):
        """Escritura atómica para reducir riesgo de perder el JSON."""
        with self._bloqueo:
            historial = self._leer_historial()
            historial.append(registro)
            historial = historial[-500:]
            temporal = self.archivo_historial.with_suffix(".tmp")
            try:
                with temporal.open("w", encoding="utf-8") as archivo:
                    json.dump({"descargas": historial}, archivo, ensure_ascii=False, indent=2,)
                    archivo.flush()
                    os.fsync(archivo.fileno())
                temporal.replace(self.archivo_historial)
                return True
            except (OSError, TypeError, ValueError):
                logger.exception("No se pudo guardar el historial.")
                try:
                    temporal.unlink(missing_ok=True)
                except OSError:
                    pass
                return False
    def obtener_historial(self, limite=20):
        try:
            limite = max(1, min(500, int(limite)))
        except (TypeError, ValueError):
            limite = 20
        return self._leer_historial()[-limite:]
    def limpiar_historial(self, conservar_respaldo=True):
        """Limpia el historial opcionalmente conservando una copia."""
        with self._bloqueo:
            try:
                if conservar_respaldo and self.archivo_historial.is_file():
                    respaldo = self.archivo_historial.with_name(
                        f"historial_descargas_respaldo_{datetime.now():%Y%m%d_%H%M%S}.json"
                    )
                    shutil.copy2(self.archivo_historial, respaldo)
                temporal = self.archivo_historial.with_suffix(".tmp")
                temporal.write_text('{"descargas": []}', encoding="utf-8")
                temporal.replace(self.archivo_historial)
                return True, "Historial limpiado."
            except OSError as error:
                logger.exception("No se pudo limpiar el historial.")
                return False, f"No se pudo limpiar el historial: {error}"
    @staticmethod
    def _es_url(texto):
        try:
            partes = urlparse(str(texto).strip())
            if not (partes.scheme.lower() in ("http", "https") and bool(partes.netloc)):
                return False
            if not seguridad.url_segura(texto, seguridad.DOMINIOS_DESCARGA):
                raise ValueError("dominio de descarga no permitido")
            return True
        except (AttributeError, TypeError):
            return False
    @staticmethod
    def _limpiar_consulta(consulta):
        texto = str(consulta or "").strip()
        prefijos = (
            "miller descargar canción ", "miller descargar cancion ",
            "miller descargar música ", "miller descargar musica ",
            "miller descargar ", "descargar canción ", "descargar cancion ",
            "descargar música ", "descargar musica ", "descargar ",
        )
        texto_minusculas = texto.casefold()
        for prefijo in prefijos:
            if texto_minusculas.startswith(prefijo):
                texto = texto[len(prefijo):].strip()
                break
        return texto.strip(" \t\r\n\"'")
    @staticmethod
    def clasificar_error(error):
        texto = str(error or "").lower()
        if isinstance(error, PermissionError) or "permission denied" in texto or "acceso denegado" in texto:
            return "Windows denegó el acceso. Comprueba permisos y que el archivo no esté bloqueado."
        if isinstance(error, FileNotFoundError):
            return "No se encontró un archivo necesario. Revisa FFmpeg, la ruta y la fuente."
        if isinstance(error, TimeoutError) or any(x in texto for x in ("timed out", "timeout", "tiempo de espera")):
            return "Se agotó el tiempo de espera. Comprueba la conexión e inténtalo de nuevo."
        if any(x in texto for x in ("getaddrinfo", "name or service not known", "dns", "temporary failure in name resolution")):
            return "No se pudo resolver el servidor. Comprueba internet o la dirección de la fuente."
        if any(x in texto for x in ("connection refused", "connection reset", "network is unreachable", "urlopen error")):
            return "Falló la conexión con la fuente. Revisa internet, firewall o proxy."
        if "429" in texto or "too many requests" in texto:
            return "La fuente limitó las solicitudes (HTTP 429). Espera antes de reintentar."
        if "403" in texto or "forbidden" in texto:
            return "La fuente denegó el acceso (HTTP 403). El contenido puede requerir permisos."
        if "404" in texto or "not found" in texto:
            return "No se encontró el contenido (HTTP 404). Comprueba la URL o el título."
        if any(x in texto for x in ("unsupported url", "no suitable extractor", "not a valid url")):
            return "La URL no es compatible con yt-dlp o está mal escrita."
        if any(x in texto for x in ("private video", "video unavailable", "is not available", "unavailable")):
            return "El contenido no está disponible, es privado o no tienes permiso de acceso."
        if "ffmpeg" in texto or "ffprobe" in texto or "postprocessing" in texto or "post-processing" in texto:
            return "Falló la conversión multimedia. Comprueba que ffmpeg.exe funcione y que haya espacio en disco."
        if "no space left" in texto or "disk full" in texto:
            return "No hay espacio suficiente en el disco para guardar el audio."
        if "read-only" in texto or "readonly" in texto:
            return "La carpeta de destino es de solo lectura."
        if "cancelad" in texto or "cancelled" in texto or "canceled" in texto:
            return "Descarga cancelada."
        if "no module named" in texto or "yt_dlp" in texto and "import" in texto:
            return "Falta yt-dlp en el Python actual. Instálalo usando el mismo Python de MILLER."
        if "no se encontró ffmpeg.exe" in texto:
            return str(error)
        if "no se encontró ningún resultado" in texto or "no results" in texto:
            return "No se encontraron resultados para esa búsqueda."
        if isinstance(error, ValueError):
            return str(error) or "La consulta proporcionada no es válida."
        return f"No se pudo completar la descarga: {str(error)[:700]}"
    def cancelar(self):
        with self._bloqueo:
            if not self._descarga_activa:
                return "No hay ninguna descarga activa."
            self._cancelacion.set()
        return "Cancelación solicitada. Se detendrá cuando yt-dlp responda al aviso."
    def _comprobar_carpetas(self):
        try:
            self.carpeta.mkdir(parents=True, exist_ok=True)
            self.archivo_historial.parent.mkdir(parents=True, exist_ok=True)
            prueba = self.carpeta / ".miller_prueba_escritura.tmp"
            prueba.write_text("prueba", encoding="utf-8")
            prueba.unlink(missing_ok=True)
        except OSError as error:
            raise RuntimeError(
                f"No se puede escribir en la carpeta de audios: {self.carpeta}. "
                f"Detalle: {error}"
            ) from error
    def _encontrar_mp3(self, existentes, id_audio, candidata=None):
        """Localiza el resultado aunque yt-dlp cambie el nombre final."""
        if candidata:
            try:
                if candidata.is_file() and candidata.stat().st_size > 0:
                    return candidata.resolve()
            except OSError:
                pass
        try:
            mp3s = [p for p in self.carpeta.glob("*.mp3") if p.is_file()]
            if id_audio:
                coincidencias = [p for p in mp3s if f"[{id_audio}]" in p.name]
                if coincidencias:
                    return max(coincidencias, key=lambda p: p.stat().st_mtime).resolve()
            nuevos = [p for p in mp3s if p.resolve() not in existentes]
            if nuevos:
                return max(nuevos, key=lambda p: p.stat().st_mtime).resolve()
        except OSError:
            logger.exception("No se pudo comprobar el archivo final.")
        return None
    def descargar(self, consulta, callback_progreso=None):
        with self._bloqueo:
            if self._descarga_activa:
                return {
                    "exito": False,
                    "mensaje": "Ya hay una descarga activa.",
                    "archivo": None,
                    "titulo": "",
                    "codigo_error": "DESCARGA_OCUPADA",
                }
            self._descarga_activa = True
            self._cancelacion.clear()
            self._ultima_error = None
        fecha = datetime.now().isoformat(timespec="seconds")
        consulta_original = str(consulta or "").strip()
        consulta_limpia = self._limpiar_consulta(consulta_original)
        titulo = ""
        fuente = ""
        ruta_final = None
        codigo_error = None
        try:
            if not consulta_limpia:
                raise ValueError("Indica el nombre de la canción o una URL.")
            try:
                import yt_dlp
            except ImportError as error:
                codigo_error = "DEPENDENCIA_YT_DLP"
                raise RuntimeError(
                    "Falta yt-dlp. Instala con: "
                    "py -3.13 -m pip install -U yt-dlp"
                ) from error
            self._comprobar_carpetas()
            # Buscar de nuevo por si se añadieron los binarios tras iniciar MILLER.
            self.ffmpeg = buscar_ejecutable("ffmpeg.exe")
            self.ffprobe = buscar_ejecutable("ffprobe.exe")
            if not self.ffmpeg:
                codigo_error = "FFMPEG_NO_ENCONTRADO"
                raise RuntimeError(
                    "No se encontró ffmpeg.exe. Se buscó en:\n"
                    f"  {CARPETA_BIN}\n  {CARPETA_MODELOS} y sus subcarpetas."
                )
            prueba_ffmpeg = comprobar_ejecutable(self.ffmpeg)
            if not prueba_ffmpeg["funciona"]:
                codigo_error = "FFMPEG_NO_FUNCIONAL"
                raise RuntimeError(
                    f"El archivo FFmpeg existe, pero no funciona: {self.ffmpeg}. "
                    f"Detalle: {prueba_ffmpeg.get('error')}"
                )
            if self._cancelacion.is_set():
                codigo_error = "CANCELADA"
                raise RuntimeError("Descarga cancelada.")
            fuente = consulta_limpia if self._es_url(consulta_limpia) else f"ytsearch1:{consulta_limpia}"
            existentes = {p.resolve() for p in self.carpeta.glob("*.mp3") if p.is_file()}
            self._informar(
                callback_progreso,
                estado="iniciando",
                porcentaje=0,
                mensaje=f"FFmpeg verificado: {self.ffmpeg.name}",
                titulo=consulta_limpia,
            )
            def hook(datos):
                if self._cancelacion.is_set():
                    raise RuntimeError("Descarga cancelada.")
                estado_hook = datos.get("status")
                info_hook = datos.get("info_dict") or {}
                titulo_hook = info_hook.get("title") or titulo or consulta_limpia
                if estado_hook == "downloading":
                    total = datos.get("total_bytes") or datos.get("total_bytes_estimate")
                    descargado = datos.get("downloaded_bytes", 0)
                    porcentaje = (descargado / total * 85) if total else 0
                    velocidad = datos.get("_speed_str", "")
                    restante = datos.get("_eta_str", "")
                    mensaje = "Descargando contenido"
                    if velocidad:
                        mensaje += f" | {velocidad}"
                    if restante:
                        mensaje += f" | restante {restante}"
                    self._informar(
                        callback_progreso, estado="descargando",
                        porcentaje=porcentaje, mensaje=mensaje, titulo=titulo_hook,
                    )
                elif estado_hook == "finished":
                    self._informar(
                        callback_progreso, estado="convirtiendo",
                        porcentaje=90, mensaje="Convirtiendo a MP3 con FFmpeg...",
                        titulo=titulo_hook,
                    )
            opciones = {
                "format": "bestaudio/best",
                "outtmpl": str(self.carpeta / "%(title).160B [%(id)s].%(ext)s"),
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "ignoreerrors": False,
                "retries": 3,
                "fragment_retries": 3,
                "extractor_retries": 2,
                "file_access_retries": 3,
                "socket_timeout": 30,
                "continuedl": True,
                "windowsfilenames": True,
                "overwrites": False,
                "progress_hooks": [hook],
                "ffmpeg_location": str(self.ffmpeg.parent),
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            }
            with yt_dlp.YoutubeDL(opciones) as ydl:
                info = ydl.extract_info(fuente, download=True)
                if not info:
                    codigo_error = "SIN_RESULTADOS"
                    raise RuntimeError("La fuente no devolvió información.")
                if info.get("entries") is not None:
                    info = next((item for item in info["entries"] if item), None)
                if not info:
                    codigo_error = "SIN_RESULTADOS"
                    raise RuntimeError("No se encontró ningún resultado.")
                titulo = info.get("title") or consulta_limpia
                id_audio = str(info.get("id") or "")
                try:
                    candidata = Path(ydl.prepare_filename(info)).with_suffix(".mp3")
                except Exception:
                    candidata = None
                    logger.debug("No se pudo calcular el nombre del MP3.", exc_info=True)
            if self._cancelacion.is_set():
                codigo_error = "CANCELADA"
                raise RuntimeError("Descarga cancelada.")
            ruta_final = self._encontrar_mp3(existentes, id_audio, candidata)
            if not ruta_final:
                codigo_error = "MP3_NO_ENCONTRADO"
                raise RuntimeError("La descarga terminó, pero no se localizó el MP3 en la carpeta audios.")
            try:
                tamano = ruta_final.stat().st_size
            except OSError as error:
                codigo_error = "ARCHIVO_ILEGIBLE"
                raise RuntimeError(f"No se pudo leer el archivo final: {error}") from error
            if tamano <= 0:
                codigo_error = "MP3_VACIO"
                raise RuntimeError("El archivo MP3 está vacío.")
            # Si ffprobe existe, verifica que el archivo pueda inspeccionarse.
            if self.ffprobe:
                prueba = subprocess.run(
                    [str(self.ffprobe), "-v", "error", "-show_entries",
                     "format=format_name,duration", "-of", "default=noprint_wrappers=1",
                     str(ruta_final)],
                    capture_output=True, text=True, timeout=15, check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if prueba.returncode != 0:
                    logger.warning(
                        "ffprobe no pudo validar el archivo %s: %s",
                        ruta_final, (prueba.stderr or "")[:500],
                    )
            resultado = {
                "exito": True,
                "mensaje": "Descarga y conversión completadas.",
                "archivo": str(ruta_final),
                "titulo": titulo,
                "codigo_error": None,
                "tamano_bytes": tamano,
            }
            self._informar(
                callback_progreso, estado="completado", porcentaje=100,
                mensaje=resultado["mensaje"], titulo=titulo,
            )
            self._guardar_historial({
                "fecha": fecha, "consulta": consulta_original, "fuente": fuente,
                "titulo": titulo, "archivo": str(ruta_final), "estado": "completado",
                "mensaje": resultado["mensaje"], "tamano_bytes": tamano,
            })
            return resultado
        except Exception as error:
            mensaje = self.clasificar_error(error)
            cancelada = self._cancelacion.is_set() or "cancelad" in str(error).lower()
            if cancelada:
                codigo_error = "CANCELADA"
            codigo_error = codigo_error or "ERROR_DESCARGA"
            self._ultima_error = {
                "codigo": codigo_error,
                "mensaje": mensaje,
                "tipo": type(error).__name__,
                "fecha": fecha,
            }
            self._informar(
                callback_progreso,
                estado="cancelado" if cancelada else "error",
                mensaje=mensaje,
                titulo=titulo or consulta_original,
            )
            self._guardar_historial({
                "fecha": fecha, "consulta": consulta_original, "fuente": fuente,
                "titulo": titulo, "archivo": None,
                "estado": "cancelado" if cancelada else "error",
                "mensaje": mensaje, "codigo_error": codigo_error,
                "tipo_error": type(error).__name__,
            })
            logger.error("[%s] %s", codigo_error, mensaje, exc_info=logger.isEnabledFor(logging.DEBUG))
            return {
                "exito": False, "mensaje": mensaje, "archivo": None,
                "titulo": titulo, "codigo_error": codigo_error,
                "tipo_error": type(error).__name__,
            }
        finally:
            with self._bloqueo:
                self._descarga_activa = False
    def descargar_en_hilo(self, consulta, callback_final=None, callback_progreso=None):
        """Inicia la descarga en segundo plano sin bloquear el asistente."""
        with self._bloqueo:
            if self._descarga_activa:
                return None
        def trabajo():
            resultado = self.descargar(consulta, callback_progreso)
            if callback_final:
                try:
                    callback_final(resultado)
                except Exception:
                    logger.exception("El callback final produjo un error.")
        hilo = threading.Thread(target=trabajo, name="MILLER-DescargaMusica", daemon=True)
        hilo.start()
        self._hilo = hilo
        return hilo
# API PUBLICA COMPATIBLE CON MILLER
descargador_musica = DescargadorMusica()

def descargar_musica(consulta, callback_progreso=None):
    """Mantiene la firma pública que usa el módulo de comandos."""
    return descargador_musica.descargar(consulta, callback_progreso)
