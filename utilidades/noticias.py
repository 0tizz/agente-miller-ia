"""MILLER · Módulo de noticias."""
import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
try:
    from configuracion import RUTA_DATOS as _RUTA_DATOS
except Exception:
    _RUTA_DATOS = None
try:
    from utilidades import seguridad as _seguridad
except Exception:
    _seguridad = None

class Noticias:
    """Administrador de noticias de MILLER."""
    CACHE_SEGUNDOS = 1800
    def __init__(self):
        self._cache = {}
        self.url_base = ("https://news.google.com/rss/search")
    GUARDAR = 3                               # titulares que se guardan para usarlos sin internet
    @property
    def ruta_local(self):
        return (_RUTA_DATOS / "noticias.json") if _RUTA_DATOS else None
    def _guardar_local(self, noticias, tema):
        if not self.ruta_local or _seguridad is None or not noticias:
            return
        limpias = [{"titulo": _seguridad.sanear_conocimiento(n.get("titulo", ""), 200),
                    "fuente": _seguridad.sanear_texto(n.get("fuente", ""), 60)} for n in noticias[:self.GUARDAR]]
        try:
            _seguridad.escribir_json(self.ruta_local, {"tema": tema, "fecha": datetime.now().isoformat(timespec="minutes"),
                                                       "noticias": limpias})
        except Exception as error:
            print(f"[ NOTICIAS ] No se pudieron guardar: {error}")
    def noticias_guardadas(self):
        """Últimas noticias conocidas (sin internet). Cada una lleva 'guardada' con su fecha."""
        if not self.ruta_local or _seguridad is None:
            return []
        datos = _seguridad.leer_json(self.ruta_local, {}) or {}
        fecha = str(datos.get("fecha", ""))
        return [dict(n, guardada=fecha) for n in datos.get("noticias", []) if isinstance(n, dict) and n.get("titulo")]
    def obtener_noticias(self, cantidad=2, tema="Colombia"):
        """Noticias recientes (se reutilizan 30 min). Guarda las 3 últimas; sin internet usa las guardadas."""
        import time as _t
        clave = (cantidad, tema)
        marca, valor = self._cache.get(clave, (0.0, None))
        if valor and _t.monotonic() - marca < self.CACHE_SEGUNDOS:
            return valor
        recientes = self._obtener_noticias_red(max(cantidad, self.GUARDAR), tema)
        if recientes:
            self._guardar_local(recientes, tema)
            valor = recientes[:cantidad]
            self._cache[clave] = (_t.monotonic(), valor)
            return valor
        return self.noticias_guardadas()[:cantidad]
    def _obtener_noticias_red(self, cantidad=2, tema="Colombia"):
        """Obtiene noticias actuales."""
        try:
            consulta = urllib.parse.quote(tema)
            url = (f"{self.url_base}" f"?q={consulta}" f"&hl=es-419" f"&gl=CO" f"&ceid=CO:es-419")
            solicitud = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(solicitud, timeout=10) as respuesta:
                contenido = (respuesta .read() .decode("utf-8"))
            raiz = ET.fromstring(contenido)
            noticias = []
            for item in raiz.findall(".//item"):
                titulo_elemento = (item.find("title"))
                enlace_elemento = (item.find("link"))
                fuente_elemento = (item.find("source"))
                if (titulo_elemento is None or enlace_elemento is None):
                    continue
                titulo = (titulo_elemento.text or "").strip()
                enlace = (enlace_elemento.text or "").strip()
                fuente = "Fuente desconocida"
                if fuente_elemento is not None:
                    fuente = (fuente_elemento.text or "Fuente desconocida").strip()
                if not titulo:
                    continue
                noticias.append({"titulo": titulo, "fuente": fuente, "enlace": enlace})
                if len(noticias) >= cantidad:
                    break
            return noticias
        except Exception as error:
            print("[ NOTICIAS ] " f"Error obteniendo noticias: {error}")
            return []
    def obtener_dos_noticias(self):
        return self.obtener_noticias(cantidad=2, tema="Colombia")
    def obtener_resumen(self):
        noticias = self.obtener_noticias(cantidad=3)
        if not noticias:
            return "Sin conexión y sin noticias guardadas, señor."
        resultado = []
        if noticias[0].get("guardada"):
            resultado.append(f"Sin conexión. Últimas noticias guardadas, {noticias[0]['guardada'][:10]}:")
        for numero, noticia in enumerate(noticias, start=1):
            fuente = f" ({noticia['fuente']})" if noticia.get("fuente") and noticia["fuente"] != "Fuente desconocida" else ""
            resultado.append(f"{numero}. {str(noticia['titulo']).rstrip('.')}{fuente}.")
        return " ".join(resultado)
# PRUEBA DEL MÓDULO
if __name__ == "__main__":
    print()
    print("=" * 60)
    print("MILLER - PRUEBA DEL MÓDULO NOTICIAS")
    print("=" * 60)
    print()
    noticias = Noticias()
    print("Consultando noticias...")
    resultados = (noticias.obtener_dos_noticias())
    print()
    if not resultados:
        print("No se pudieron obtener noticias.")
    else:
        print("Noticias recibidas:")
        print()
        for numero, noticia in enumerate(resultados, start=1):
            print(f"{numero}. {noticia['titulo']}")
            print(f"   Fuente: {noticia['fuente']}")
            print(f"   Enlace: {noticia['enlace']}")
            print()
    print("=" * 60)
