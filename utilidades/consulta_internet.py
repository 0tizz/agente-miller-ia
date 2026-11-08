"""MILLER · Consultas rápidas a internet (solo biblioteca estándar)."""
import html
import json
import re
import socket
import threading
import time
import unicodedata
from html.parser import HTMLParser
from urllib.parse import quote, urlencode, urlparse, parse_qs, unquote
from urllib.request import Request, urlopen
from utilidades import seguridad
AGENTE = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
_RE_DEFINICION = re.compile(r"^(quien es|quien fue|quienes son|que es|que son|que fue|que significa|significado de|definicion de)\b")
_RELLENO = re.compile(
    r"^(?:miller[\s,]*)?(?:(?:por favor|oye|dime|me puedes decir|puedes decirme|sabes|quiero saber|"
    r"busca(?:me)?|buscar|investiga(?:r)?|averigua(?:r)?|consulta(?:r)?|pregunta(?:le)?)\s+)*"
    r"(?:(?:en|a)\s+(?:internet|la web|google|linea)\s+)?(?:(?:sobre|acerca de|de)\s+)?", re.I)

def _plano(texto):
    texto = unicodedata.normalize("NFD", str(texto or "").lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")

class _ParserDuck(HTMLParser):
    """Extrae título, enlace y fragmento de html.duckduckgo.com."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.resultados, self._campo, self._nivel = [], None, 0
    def handle_starttag(self, tag, attrs):
        if self._campo:
            self._nivel += 1
            return
        attrs = dict(attrs)
        clases = (attrs.get("class") or "").split()
        if "result__a" in clases:
            self.resultados.append({"titulo": "", "url": attrs.get("href", ""), "fragmento": ""})
            self._campo, self._nivel = "titulo", 1
        elif "result__snippet" in clases and self.resultados:
            self._campo, self._nivel = "fragmento", 1
    def handle_endtag(self, tag):
        if self._campo:
            self._nivel -= 1
            if self._nivel <= 0:
                self._campo = None
    def handle_data(self, data):
        if self._campo and self.resultados:
            self.resultados[-1][self._campo] += data

class ConsultorInternet:
    TIEMPO_ESPERA = 5.0
    TIEMPO_CONEXION = 1.5
    MAX_CARACTERES = 240
    CACHE_SEGUNDOS = 600
    def __init__(self):
        self._cache, self._conexion = {}, (0.0, False)
        self._lock = threading.Lock()
    def hay_conexion(self):
        """True si hay salida a internet. Resultado válido 20 s."""
        ahora = time.monotonic()
        if ahora - self._conexion[0] < 20:
            return self._conexion[1]
        ok = False
        for destino in (("1.1.1.1", 443), ("8.8.8.8", 53), ("duckduckgo.com", 443)):
            try:
                socket.create_connection(destino, timeout=self.TIEMPO_CONEXION).close()
                ok = True
                break
            except OSError:
                continue
        self._conexion = (ahora, ok)
        return ok
    def _leer(self, url, datos=None):
        cuerpo = urlencode(datos).encode("utf-8") if datos else None
        peticion = Request(url, data=cuerpo, headers={"User-Agent": AGENTE, "Accept-Language": "es-CO,es;q=0.9"})
        with urlopen(peticion, timeout=self.TIEMPO_ESPERA) as r:
            return r.read(600_000).decode("utf-8", errors="replace")
    @staticmethod
    def limpiar_pregunta(texto):
        texto = re.sub(r"[¿?¡!]", " ", str(texto or ""))
        texto = _RELLENO.sub("", texto.strip())
        return re.sub(r"\s+", " ", texto).strip(" .,;:")
    def _acortar(self, texto):
        texto = re.sub(r"\s+", " ", html.unescape(texto or "")).strip()
        texto = re.sub(r"\s*\([^)]{0,80}\)", "", texto)              # quita paréntesis largos (pronunciación...)
        frases, salida = re.split(r"(?<=[.!?])\s+", texto), ""
        for frase in frases:
            if salida and len(salida) + len(frase) + 1 > self.MAX_CARACTERES:
                break
            salida = f"{salida} {frase}".strip()
        if len(salida) > self.MAX_CARACTERES:
            salida = salida[:self.MAX_CARACTERES].rsplit(" ", 1)[0].rstrip(",;:") + "…"
        return salida
    @staticmethod
    def _dominio(url):
        if "uddg=" in url:
            url = unquote(parse_qs(urlparse(url).query).get("uddg", [url])[0])
        host = urlparse(url if "//" in url else "https:" + url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    def _duckduckgo(self, consulta):
        pagina = self._leer("https://html.duckduckgo.com/html/", {"q": consulta, "kl": "co-es"})
        parser = _ParserDuck()
        parser.feed(pagina)
        for r in parser.resultados[:6]:
            fragmento = self._acortar(r["fragmento"])
            if len(fragmento) >= 40 and "duckduckgo.com/y.js" not in r["url"]:     # sin anuncios
                return fragmento, self._dominio(r["url"])
        return None
    def _wikipedia(self, consulta):
        busqueda = json.loads(self._leer("https://es.wikipedia.org/w/api.php?" + urlencode(
            {"action": "query", "list": "search", "srsearch": consulta, "srlimit": 1, "format": "json"})))
        aciertos = busqueda.get("query", {}).get("search", [])
        if not aciertos:
            return None
        titulo = aciertos[0]["title"]
        resumen = json.loads(self._leer("https://es.wikipedia.org/api/rest_v1/page/summary/" + quote(titulo.replace(" ", "_"))))
        texto = self._acortar(resumen.get("extract", ""))
        return (texto, "Wikipedia") if texto else None
    def consultar(self, pregunta):
        """Devuelve {"ok", "texto", "fuente"} o {"ok": False, "motivo": "sin_conexion" | "sin_resultados" | ...}."""
        consulta = self.limpiar_pregunta(pregunta)
        if len(consulta) < 3:
            return {"ok": False, "motivo": "vacia"}
        clave = _plano(consulta)
        with self._lock:
            guardado = self._cache.get(clave)
        if guardado and time.monotonic() - guardado[0] < self.CACHE_SEGUNDOS:
            return guardado[1]
        if not self.hay_conexion():
            return {"ok": False, "motivo": "sin_conexion"}
        definicion = bool(_RE_DEFINICION.match(clave))
        fuentes = (self._wikipedia, self._duckduckgo) if definicion else (self._duckduckgo, self._wikipedia)
        ultimo_error = None
        for fuente in fuentes:
            try:
                encontrado = fuente(_RE_DEFINICION.sub("", clave).strip() if fuente == self._wikipedia else consulta)
            except Exception as error:          # red caída a mitad, página cambiada, JSON inválido...
                ultimo_error = error
                continue
            if encontrado:
                texto = seguridad.sanear_conocimiento(encontrado[0], self.MAX_CARACTERES + 20)
                fuente_web = seguridad.sanear_texto(encontrado[1], 60)
                if not texto:
                    continue
                resultado = {"ok": True, "texto": texto, "fuente": fuente_web, "consulta": consulta}
                with self._lock:
                    if len(self._cache) >= 200:                       # caché acotada: no crece sin fin
                        self._cache.pop(min(self._cache, key=lambda k: self._cache[k][0]), None)
                    self._cache[clave] = (time.monotonic(), resultado)
                return resultado
        if ultimo_error is not None:
            print(f"[INTERNET] {ultimo_error}")
            self._conexion = (0.0, False)
            return {"ok": False, "motivo": "error"}
        return {"ok": False, "motivo": "sin_resultados"}
