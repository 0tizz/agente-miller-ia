"""MILLER · Ecualizador inteligente.

pygame no puede ecualizar en vivo, así que MILLER prepara con ffmpeg (en segundo plano y con prioridad
baja) una copia ecualizada de cada canción y la guarda en una caché. Cuando está lista, cambia a ella
en el mismo segundo de la canción, con un fundido muy corto.

  - AUTOMÁTICO (inteligente): mide cada canción (graves, medios y agudos) y corrige lo que le sobra
    o le falta para que todas suenen equilibradas.
  - PERFILES: plano, graves, agudos, voz, rock, pop, electrónica, clásica, acústico, suave, y los propios
    que usted crea (hasta 20, con sus tres bandas).
  - MANUAL: «pon los graves en 3» fija una banda en ese valor y deja las demás como están.
  - APRENDE: "sube los graves" / "baja los agudos" ajustan ±2 dB; lo recuerda en general y para
    el artista de la canción, y lo aplica en adelante.
"""
import hashlib
import os
import re
import subprocess
import threading

from utilidades import acceso, cuota
import time
import unicodedata
from pathlib import Path

BANDAS = ("graves", "medios", "agudos")
PERFILES = {                                   # (graves, medios, agudos) en dB
    "plano": (0, 0, 0), "graves": (5, 0, -1), "agudos": (-1, 0, 4), "voz": (-2, 3, 1),
    "rock": (4, -1, 3), "pop": (1, 2, 1), "electronica": (5, -1, 3), "clasica": (1, -1, 2),
    "acustico": (2, 1, 1), "suave": (-1, 0, -3),
}
NOMBRES_PERFIL = {"electronica": "electrónica", "clasica": "clásica", "acustico": "acústico"}
RESERVADOS = {"automatico", "automatica", "inteligente", "auto", "manual", "perfil", "modo", "todo"}
MAX_PERFILES_PROPIOS = 20
SINONIMOS_BANDA = {"graves": "graves", "bajos": "graves", "bajo": "graves", "grave": "graves",
                   "medios": "medios", "medio": "medios", "voces": "medios",
                   "agudos": "agudos", "agudo": "agudos", "brillo": "agudos", "altos": "agudos"}
REFERENCIA = {"graves": -4.0, "medios": -7.0, "agudos": -13.0}    # dB respecto al total (mezcla equilibrada)
LIMITE_DB, PASO_AJUSTE = 6.0, 2.0
MAX_CACHE_MB = 1500
SIN_VENTANA = (0x08000000 | 0x00004000) if os.name == "nt" else 0   # sin ventana y prioridad baja


def _limitar(v, a=-LIMITE_DB, b=LIMITE_DB):
    return max(a, min(b, v))


def sin_tildes(texto):
    """Minúsculas, sin tildes ni símbolos, con espacios simples."""
    t = unicodedata.normalize("NFD", str(texto or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", t)).strip()


def nombre_perfil(texto):
    """Nombre válido para un perfil propio, o "" si no sirve (muy corto, de fábrica o reservado)."""
    t = sin_tildes(texto)[:24].strip()
    return "" if len(t) < 2 or t in PERFILES or t in RESERVADOS else t


def _bandas_validas(datos):
    """Graves, medios y agudos en dB, acotados y sin valores raros."""
    salida = {}
    for b in BANDAS:
        try:
            salida[b] = round(_limitar(float((datos or {}).get(b, 0.0))), 1)
        except (TypeError, ValueError, AttributeError):
            salida[b] = 0.0
    return salida


def formato_db(g):
    """«+3 dB», «-2 dB», «0 dB»."""
    return f"{'+' if g > 0 else ''}{g:g} dB"


class Ecualizador:
    def __init__(self, ruta_estado, carpeta_cache, ffmpeg=None):
        self.ruta_estado = Path(ruta_estado)
        self.cache = Path(carpeta_cache)
        self.ffmpeg = ffmpeg
        self._lock = threading.RLock()
        self._preparando = set()
        self.al_listo = None                       # callback(original, ecualizada): la usa el reproductor
        self.estado = {"modo": "automatico", "perfil": "plano", "activo": True,
                       "preferencias": {"global": {b: 0.0 for b in BANDAS}, "artistas": {}}, "analisis": {}, "propios": {}, "manual": None}
        self._cargar()

    # ------------------------------------------------------------ persistencia
    def _cargar(self):
        try:
            from utilidades import seguridad
            datos = seguridad.leer_json(self.ruta_estado, None)
        except Exception:
            datos = None
        if isinstance(datos, dict):
            for clave in ("modo", "perfil", "activo"):
                if clave in datos:
                    self.estado[clave] = datos[clave]
            pref = datos.get("preferencias") or {}
            self.estado["preferencias"]["global"].update({b: float(v) for b, v in (pref.get("global") or {}).items() if b in BANDAS})
            self.estado["preferencias"]["artistas"] = {a: {b: float(v) for b, v in d.items() if b in BANDAS}
                                                       for a, d in (pref.get("artistas") or {}).items() if isinstance(d, dict)}
            self.estado["analisis"] = {k: v for k, v in (datos.get("analisis") or {}).items() if isinstance(v, dict)}
        if isinstance(datos, dict):
            propios = datos.get("propios") if isinstance(datos.get("propios"), dict) else {}
            self.estado["propios"] = {str(n): _bandas_validas(v) for n, v in propios.items()
                                      if isinstance(v, dict)}
            if isinstance(datos.get("manual"), dict):
                self.estado["manual"] = _bandas_validas(datos["manual"])
        if self.estado.get("perfil") not in self.todos_los_perfiles():
            self.estado["perfil"] = "plano"

    def guardar(self):
        try:
            from utilidades import seguridad
            with self._lock:
                analisis = dict(list(self.estado["analisis"].items())[-800:])     # no crece sin fin
                self.estado["analisis"] = analisis
                copia = {**self.estado, "analisis": dict(analisis)}
            seguridad.escribir_json(self.ruta_estado, copia)
        except Exception as error:
            print(f"[ECUALIZADOR] No se pudo guardar: {error}")

    # ------------------------------------------------------------ cálculo de la curva
    @staticmethod
    def artista(archivo):
        nombre = Path(archivo).stem
        return nombre.split(" - ")[0].strip().lower() if " - " in nombre else ""

    @staticmethod
    def _clave_archivo(archivo):
        archivo = Path(archivo)
        try:
            st = archivo.stat()
            base = f"{archivo.resolve()}|{st.st_size}|{int(st.st_mtime)}"
        except OSError:
            base = str(archivo)
        return hashlib.sha1(base.encode("utf-8", "replace")).hexdigest()[:16]

    def _curva_base(self, archivo):
        """Lo que pide el modo, sin lo aprendido: manual, perfil o la medida automática."""
        if self.estado["modo"] == "manual" and self.estado.get("manual"):
            return dict(self.estado["manual"])
        if self.estado["modo"] in ("perfil", "manual"):
            return self.valores_perfil(self.estado["perfil"])
        medida = self.estado["analisis"].get(self._clave_archivo(archivo)) if archivo else None
        base = {b: 0.0 for b in BANDAS}
        if medida:                               # inteligente: corrige solo la mitad de la diferencia
            for b in BANDAS:
                if b in medida:
                    base[b] = _limitar((REFERENCIA[b] - medida[b]) * 0.5, -3.0, 3.0)
        return base

    def valores_perfil(self, nombre):
        """Graves, medios y agudos de un perfil de fábrica o propio."""
        if nombre in PERFILES:
            return dict(zip(BANDAS, PERFILES[nombre]))
        return dict(self.estado.get("propios", {}).get(nombre) or _bandas_validas({}))

    def todos_los_perfiles(self):
        return list(PERFILES) + sorted(self.estado.get("propios", {}))

    def buscar_perfil(self, texto):
        """Perfil (de fábrica o propio) que aparece en el texto, o None. Gana el nombre más largo."""
        t = f" {sin_tildes(texto)} "
        for nombre in sorted(self.todos_los_perfiles(), key=len, reverse=True):
            if f" {nombre} " in t:
                return nombre
        return None

    def crear_perfil(self, nombre, valores=None, archivo=None):
        """Guarda un perfil propio con esos valores, o con la curva que suena ahora, y lo pone en uso.
        Devuelve el nombre guardado o None si no se pudo."""
        nombre = nombre_perfil(nombre)
        propios = self.estado.setdefault("propios", {})
        if not nombre or (nombre not in propios and len(propios) >= MAX_PERFILES_PROPIOS):
            return None
        curva = _bandas_validas(valores) if valores is not None else _bandas_validas(self.ganancias(archivo))
        with self._lock:
            propios[nombre] = curva
            self.estado.update(modo="perfil", perfil=nombre, activo=True)
        self.guardar()
        return nombre

    def borrar_perfil(self, nombre):
        """Borra un perfil propio. Devuelve True si existía."""
        with self._lock:
            propios = self.estado.get("propios", {})
            if nombre not in propios:
                return False
            del propios[nombre]
            if self.estado.get("perfil") == nombre:
                self.estado.update(modo="perfil", perfil="plano")
        self.guardar()
        return True

    def fijar_banda(self, banda, valor, archivo=None):
        """Pone una banda en un valor exacto (dB, máximo ±6); las demás no cambian. Devuelve el valor que suena."""
        banda = SINONIMOS_BANDA.get(banda, banda)
        if banda not in BANDAS:
            return None
        with self._lock:
            base = self._curva_base(archivo)
            pref = self.estado["preferencias"]
            artista = pref["artistas"].get(self.artista(archivo), {}) if archivo else {}
            extra = pref["global"].get(banda, 0.0) + artista.get(banda, 0.0)
            base[banda] = float(valor) - extra
            self.estado.update(modo="manual", manual=_bandas_validas(base), activo=True)
        self.guardar()
        return self.ganancias(archivo)[banda]

    def ganancias(self, archivo=None):
        """dB de graves, medios y agudos que tocan para esta canción: lo que pide el modo más lo aprendido."""
        with self._lock:
            if not self.estado.get("activo", True):
                return {b: 0.0 for b in BANDAS}
            base = self._curva_base(archivo)
            pref = self.estado["preferencias"]
            artista = pref["artistas"].get(self.artista(archivo), {}) if archivo else {}
            return {b: round(_limitar(base[b] + pref["global"].get(b, 0.0) + artista.get(b, 0.0)), 1) for b in BANDAS}

    @staticmethod
    def filtro(g):
        """Cadena de filtros de ffmpeg. Lo que se sube se compensa para no saturar."""
        if all(abs(g[b]) < 0.5 for b in BANDAS):
            return ""
        partes = []
        if abs(g["graves"]) >= 0.5:
            partes.append(f"bass=g={g['graves']}:f=110:w=0.7")
        if abs(g["medios"]) >= 0.5:
            partes.append(f"equalizer=f=1500:t=o:w=2:g={g['medios']}")
        if abs(g["agudos"]) >= 0.5:
            partes.append(f"treble=g={g['agudos']}:f=5000:w=0.7")
        maximo = max(0.0, *g.values())
        if maximo > 0:
            partes.append(f"volume=-{round(maximo * 0.6, 1)}dB")
        partes.append("alimiter=limit=0.95:level=disabled")
        return ",".join(partes)

    # ------------------------------------------------------------ análisis y caché
    def _ffmpeg(self, argumentos, timeout=180):
        return subprocess.run([self.ffmpeg, "-hide_banner", "-nostats", *argumentos], capture_output=True, text=True,
                              timeout=timeout, stdin=subprocess.DEVNULL, creationflags=SIN_VENTANA)

    def _nivel(self, archivo, filtro):
        r = self._ffmpeg(["-ss", "20", "-t", "40", "-i", str(archivo), "-af", f"{filtro}volumedetect", "-vn",
                          "-f", "null", "-"], timeout=90)
        m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", r.stderr or "")
        return float(m.group(1)) if m else None

    def analizar(self, archivo):
        """Mide graves (<250 Hz), medios (250-4000) y agudos (>4000) respecto al total de la canción."""
        clave = self._clave_archivo(archivo)
        with self._lock:
            if clave in self.estado["analisis"]:
                return self.estado["analisis"][clave]
        if not self.ffmpeg:
            return None
        total = self._nivel(archivo, "")
        if total is None:
            return None
        bandas = {"graves": "lowpass=f=250,", "medios": "highpass=f=250,lowpass=f=4000,", "agudos": "highpass=f=4000,"}
        medida = {}
        for banda, f in bandas.items():
            n = self._nivel(archivo, f)
            if n is not None:
                medida[banda] = round(n - total, 1)
        with self._lock:
            self.estado["analisis"][clave] = medida
        return medida

    def sin_efecto(self, archivo):
        """True si debe sonar la canción original tal cual (ecualizador apagado, sin ffmpeg o curva plana)."""
        if not self.ffmpeg or not self.estado.get("activo", True):
            return True
        if self.estado["modo"] == "automatico" and self._clave_archivo(archivo) not in self.estado["analisis"]:
            return False                             # aún falta medirla: está pendiente, no es plana
        return not self.filtro(self.ganancias(archivo))

    def preparando(self, archivo):
        """True mientras se crea una copia de esta canción (en cualquier curva)."""
        with self._lock:
            return any(clave[0] == str(archivo) for clave in self._preparando)

    def ruta_cache(self, archivo, filtro):
        firma = hashlib.sha1(f"{self._clave_archivo(archivo)}|{filtro}".encode()).hexdigest()[:20]
        return self.cache / f"{firma}.ogg"

    def fuente_para(self, archivo, preparar=True):
        """Lo que debe sonar: la copia ecualizada si ya está lista; si no, el original (y la prepara)."""
        if not self.ffmpeg or not self.estado.get("activo", True):
            return Path(archivo)
        if self.estado["modo"] == "automatico" and self._clave_archivo(archivo) not in self.estado["analisis"]:
            if preparar:
                self.preparar(archivo)
            return Path(archivo)
        filtro = self.filtro(self.ganancias(archivo))
        if not filtro:
            return Path(archivo)
        destino = self.ruta_cache(archivo, filtro)
        if destino.is_file() and destino.stat().st_size > 1024:
            try:
                os.utime(destino, None)                  # para la caché: usada recientemente
            except OSError:
                pass
            return destino
        if preparar:
            self.preparar(archivo)
        return Path(archivo)

    def preparar(self, archivo, avisar=True):
        """Analiza y crea la copia ecualizada en segundo plano (una sola vez por canción y curva)."""
        if not self.ffmpeg or acceso.bloqueo("ECUALIZADOR") is not None:   # en FREE la música suena tal cual
            return False
        clave = (str(archivo), self.estado["modo"], self.estado["perfil"],
                 tuple(sorted(self.ganancias(archivo).items())))
        with self._lock:
            if clave in self._preparando:
                return True
            self._preparando.add(clave)

        def trabajo():
            try:
                if self.estado["modo"] == "automatico":
                    self.analizar(archivo)
                filtro = self.filtro(self.ganancias(archivo))
                if not filtro:
                    return
                destino = self.ruta_cache(archivo, filtro)
                if not destino.is_file():
                    ok_cuota, aviso = cuota.puede_crecer("asistente", Path(archivo).stat().st_size)
                    if not ok_cuota:
                        print(f"[ECUALIZADOR] {aviso}")
                        return
                    self.cache.mkdir(parents=True, exist_ok=True)
                    temporal = destino.with_suffix(".tmp.ogg")
                    r = self._ffmpeg(["-y", "-i", str(archivo), "-vn", "-af", filtro, "-c:a", "libvorbis",
                                      "-q:a", "6", str(temporal)], timeout=600)
                    if r.returncode != 0 or not temporal.is_file():
                        print(f"[ECUALIZADOR] ffmpeg no pudo ecualizar {Path(archivo).name}")
                        temporal.unlink(missing_ok=True)
                        return
                    os.replace(temporal, destino)
                    self._limpiar_cache()
                self.guardar()
                if avisar and callable(self.al_listo):
                    self.al_listo(Path(archivo), destino)
            except Exception as error:
                print(f"[ECUALIZADOR] {error}")
            finally:
                with self._lock:
                    self._preparando.discard(clave)
        threading.Thread(target=trabajo, daemon=True, name="MILLER-Ecualizador").start()
        return True

    def _limpiar_cache(self):
        """Si la caché pasa del límite, borra las copias usadas hace más tiempo."""
        try:
            archivos = sorted(self.cache.glob("*.ogg"), key=lambda p: p.stat().st_mtime)
            total = sum(p.stat().st_size for p in archivos)
            while archivos and total > MAX_CACHE_MB * 1024 * 1024:
                viejo = archivos.pop(0)
                total -= viejo.stat().st_size
                viejo.unlink(missing_ok=True)
        except OSError:
            pass

    # ------------------------------------------------------------ órdenes
    def poner_perfil(self, perfil):
        with self._lock:
            self.estado.update(modo="perfil", perfil=perfil, activo=True)
        self.guardar()

    def poner_automatico(self):
        with self._lock:
            self.estado.update(modo="automatico", activo=True)
        self.guardar()

    def desactivar(self):
        with self._lock:
            self.estado["activo"] = False
        self.guardar()

    def ajustar(self, banda, direccion, archivo=None):
        """Sube o baja una banda: lo aprende en general y, si suena algo, para su artista."""
        banda = SINONIMOS_BANDA.get(banda, banda)
        if banda not in BANDAS:
            return None
        paso = PASO_AJUSTE * (1 if direccion > 0 else -1)
        with self._lock:
            self.estado["activo"] = True
            pref = self.estado["preferencias"]
            artista = self.artista(archivo) if archivo else ""
            # Con artista conocido, mitad general y mitad para ese artista; si no, todo general.
            pref["global"][banda] = round(_limitar(pref["global"].get(banda, 0.0) + (paso * 0.5 if artista else paso)), 1)
            if artista:
                d = pref["artistas"].setdefault(artista, {b: 0.0 for b in BANDAS})
                d[banda] = round(_limitar(d.get(banda, 0.0) + paso * 0.5), 1)
        self.guardar()
        return self.ganancias(archivo)[banda] if archivo else pref["global"][banda]

    def describir(self, archivo=None):
        e = self.estado
        if not e.get("activo", True):
            return "Ecualizador desactivado: la música suena tal cual."
        if e["modo"] == "automatico":
            modo = "automático (inteligente)"
        elif e["modo"] == "manual":
            modo = "manual (bandas a su valor)"
        else:
            modo = f"perfil {NOMBRES_PERFIL.get(e['perfil'], e['perfil'])}"
        texto = f"Ecualizador en modo {modo}."
        if archivo:
            g = self.ganancias(archivo)
            texto += " Ahora: " + ", ".join(f"{b} {'+' if g[b] > 0 else ''}{g[b]:g} dB" for b in BANDAS) + "."
        if not self.ffmpeg:
            texto += " Falta ffmpeg en modelos/: sin él no puedo ecualizar."
        return texto
