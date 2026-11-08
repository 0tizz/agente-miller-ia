"""MILLER · Módulo meteorológico."""
import json
from urllib.parse import urlencode
from urllib.request import Request
from urllib.request import urlopen
from urllib.error import URLError
from urllib.error import HTTPError

class Clima:
    """Obtiene información meteorológica actual."""
    URL_API = ("https://api.open-meteo.com/v1/forecast")
    CACHE_SEGUNDOS = 900
    def __init__(self, latitud, longitud, ubicacion="mi ubicación"):
        self._cache = (0.0, None)
        self.latitud = float(latitud)
        self.longitud = float(longitud)
        self.ubicacion = (ubicacion)
    def obtener_clima(self):
        """Clima actual; se reutiliza 15 minutos para no repetir peticiones."""
        import time as _t
        marca, valor = self._cache
        if valor is not None and _t.monotonic() - marca < self.CACHE_SEGUNDOS:
            return valor
        valor = self._obtener_clima_red()
        if valor:
            self._cache = (_t.monotonic(), valor)
        return valor
    def _obtener_clima_red(self):
        parametros = {
            "latitude":
                self.latitud,
            "longitude":
                self.longitud,
            "current":
                ",".join(
                    (
                        "temperature_2m",
                        "relative_humidity_2m",
                        "apparent_temperature",
                        "weather_code",
                        "wind_speed_10m",
                    )
                ),
            "hourly":
                ",".join(
                    (
                        "temperature_2m",
                        "precipitation_probability",
                        "weather_code",
                    )
                ),
            "forecast_days":
                1,
            "timezone":
                "auto",
        }
        url = (f"{self.URL_API}?" f"{urlencode(parametros)}")
        solicitud = Request(url, headers={"User-Agent": "MILLER/1.0"})
        try:
            with urlopen(solicitud, timeout=10) as respuesta:
                datos = json.loads(respuesta.read() .decode("utf-8"))
        except HTTPError as error:
            print("[ CLIMA ] " f"Error HTTP: {error.code}")
            return None
        except URLError as error:
            print("[ CLIMA ] " f"Error de conexión: {error.reason}")
            return None
        except TimeoutError:
            print("[ CLIMA ] " "Tiempo de espera agotado.")
            return None
        except Exception as error:
            print("[ CLIMA ] " f"Error inesperado: {error}")
            return None
        return self._procesar_datos(datos)
    def _procesar_datos(self, datos):
        if not datos:
            return None
        actual = datos.get("current", {})
        hourly = datos.get("hourly", {})
        temperatura = actual.get("temperature_2m")
        sensacion = actual.get("apparent_temperature")
        humedad = actual.get("relative_humidity_2m")
        viento = actual.get("wind_speed_10m")
        codigo = actual.get("weather_code")
        descripcion = (self._describir_clima(codigo))
        probabilidad_lluvia = (self._obtener_probabilidad_lluvia(hourly))
        return {
            "ubicacion":
                self.ubicacion,
            "temperatura":
                temperatura,
            "sensacion":
                sensacion,
            "humedad":
                humedad,
            "viento":
                viento,
            "codigo":
                codigo,
            "descripcion":
                descripcion,
            "probabilidad_lluvia":
                probabilidad_lluvia,
        }
    def _obtener_probabilidad_lluvia(self, hourly):
        probabilidades = hourly.get("precipitation_probability", [])
        if not probabilidades:
            return 0
        try:
            valores = [int(valor) for valor in probabilidades[:6] if valor is not None]
            if not valores:
                return 0
            return max(valores)
        except (ValueError, TypeError):
            return 0
    def _describir_clima(self, codigo):
        descripciones = {
            0:
                "cielo despejado",
            1:
                "principalmente despejado",
            2:
                "parcialmente nublado",
            3:
                "nublado",
            45:
                "niebla",
            48:
                "niebla con escarcha",
            51:
                "llovizna ligera",
            53:
                "llovizna moderada",
            55:
                "llovizna intensa",
            56:
                "llovizna helada ligera",
            57:
                "llovizna helada intensa",
            61:
                "lluvia ligera",
            63:
                "lluvia moderada",
            65:
                "lluvia intensa",
            66:
                "lluvia helada ligera",
            67:
                "lluvia helada intensa",
            71:
                "nevadas ligeras",
            73:
                "nevadas moderadas",
            75:
                "nevadas intensas",
            77:
                "granizo de nieve",
            80:
                "chubascos ligeros",
            81:
                "chubascos moderados",
            82:
                "chubascos intensos",
            85:
                "chubascos de nieve ligeros",
            86:
                "chubascos de nieve intensos",
            95:
                "tormenta",
            96:
                "tormenta con granizo ligero",
            99:
                "tormenta con granizo intenso",
        }
        return descripciones.get(codigo, "condiciones meteorológicas desconocidas")
    def obtener_resumen(self):
        clima = self.obtener_clima()
        if not clima:
            return ("No pude obtener " "información meteorológica.")
        temperatura = clima.get("temperatura")
        sensacion = clima.get("sensacion")
        humedad = clima.get("humedad")
        viento = clima.get("viento")
        descripcion = clima.get("descripcion")
        lluvia = clima.get("probabilidad_lluvia", 0)
        partes = []
        if temperatura is not None:
            partes.append(f"{temperatura:.1f} grados")
        if descripcion:
            partes.append(descripcion)
        resumen = ("En " f"{self.ubicacion}, " + ", ".join(partes) + ".")
        if sensacion is not None:
            resumen += (f" Sensación térmica " f"de {sensacion:.1f} grados.")
        if humedad is not None:
            resumen += (f" Humedad del " f"{humedad}%.")
        if viento is not None:
            resumen += (f" Viento de " f"{viento:.1f} kilómetros " f"por hora.")
        resumen += (f" Probabilidad de lluvia " f"durante las próximas horas: " f"{lluvia}%.")
        return resumen
if __name__ == "__main__":
    print()
    print("=" * 60)
    print("MILLER - PRUEBA DEL MÓDULO CLIMA")
    print("=" * 60)
    print()
    clima = Clima(latitud=1.8, longitud=-75.1, ubicacion="mi ubicación")
    print("Consultando información meteorológica...")
    resultado = clima.obtener_clima()
    if resultado:
        print()
        print("Información recibida:")
        print()
        for clave, valor in resultado.items():
            print(f"{clave}: {valor}")
        print()
        print("Resumen:")
        print()
        print(clima.obtener_resumen())
    else:
        print()
        print("No fue posible obtener " "información meteorológica.")
    print()
    print("=" * 60)
