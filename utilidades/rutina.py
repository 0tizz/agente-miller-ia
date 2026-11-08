"""MILLER · Informe contextual"""
from utilidades.reloj import Reloj
from utilidades.clima import Clima
from utilidades.noticias import Noticias
from configuracion import (LATITUD, LONGITUD, NOMBRE_UBICACION)

class RutinaMatutina:
    """Coordinador del informe contextual de MILLER."""
    def __init__(self):
        self.reloj = Reloj()
        self.clima = Clima(latitud=LATITUD, longitud=LONGITUD, ubicacion=NOMBRE_UBICACION)
        self.noticias = Noticias()
    def obtener_informacion_reloj(self):
        try:
            informacion = (self.reloj .obtener_informacion())
            return informacion
        except Exception as error:
            print("[RUTINA] Error obteniendo reloj: " f"{error}")
            return None
    def obtener_informacion_clima(self):
        try:
            informacion = (self.clima .obtener_clima())
            return informacion
        except Exception as error:
            print("[RUTINA] Error obteniendo clima: " f"{error}")
            return None
    def obtener_informacion_noticias(self, cantidad=1):
        try:
            noticias = (self.noticias .obtener_noticias(cantidad=cantidad))
        except TypeError:
            # Compatibilidad con Noticias antiguo.
            try:
                noticias = (self.noticias .obtener_noticias())
            except Exception as error:
                print("[RUTINA] Error obteniendo noticias: " f"{error}")
                return []
        except Exception as error:
            print("[RUTINA] Error obteniendo noticias: " f"{error}")
            return []
        if not noticias:
            return []
        return list(noticias[:cantidad])
    def obtener_periodo(self, informacion_reloj=None):
        """mañana tarde noche"""
        # Intentar utilizar el periodo del reloj
        if informacion_reloj:
            periodo = informacion_reloj.get("periodo")
            if periodo:
                periodo = str(periodo).strip().lower()
                if periodo in ("mañana", "tarde", "noche"):
                    return periodo
        hora = None
        if informacion_reloj:
            hora = informacion_reloj.get("hora_24") or informacion_reloj.get("hora")
        # Intentar convertir la hora
        try:
            if isinstance(hora, str):
                # Ejemplo:
                hora = hora.strip()
                if ":" in hora:
                    hora = hora.split(":")[0]
                hora = int(hora)
            else:
                hora = int(hora)
        except Exception:
            hora = None
        if hora is None:
            return "mañana"
        if 0 <= hora < 12:
            return "mañana"
        if 12 <= hora < 19:
            return "tarde"
        return "noche"
    def generar_saludo(self, informacion_reloj):
        """Genera automáticamente el saludo según el momento actual."""
        periodo = self.obtener_periodo(informacion_reloj)
        if periodo == "mañana":
            return ("Buenos días, señor.")
        if periodo == "tarde":
            return ("Buenas tardes, señor.")
        if periodo == "noche":
            return ("Buenas noches, señor.")
        return ("Saludos, señor.")
    # HORA Y FECHA (una frase)
    def generar_hora(self, informacion_reloj):
        if not informacion_reloj:
            return ""
        hora, fecha, dia = (informacion_reloj.get(c) for c in ("hora", "fecha", "dia"))
        if not hora:
            return ""
        articulo = "Es la" if str(hora).startswith("1:") else "Son las"
        return f"{articulo} {hora}, {dia}." if dia else f"{articulo} {hora}"
    # CLIMA (una frase)
    def generar_clima(self, informacion_clima):
        if not informacion_clima:
            return "Clima: sin datos."
        temperatura = informacion_clima.get("temperatura")
        descripcion = informacion_clima.get("descripcion")
        lluvia = informacion_clima.get("probabilidad_lluvia")
        partes = []
        if temperatura is not None:
            try:
                partes.append(f"{round(float(temperatura))} grados")
            except (TypeError, ValueError):
                partes.append(f"{temperatura} grados")
        if descripcion:
            partes.append(str(descripcion))
        if lluvia:
            partes.append(f"lluvia {lluvia} %")
        return "Clima: " + (", ".join(partes) if partes else "sin datos") + "."
    # NOTICIAS (solo una)
    def generar_noticias(self, noticias):
        if not noticias:
            return "Noticias: sin conexión."
        noticia = noticias[0]
        if isinstance(noticia, dict):
            titulo = noticia.get("titulo", noticia.get("title", ""))
            fuente = noticia.get("fuente", noticia.get("source", ""))
        else:
            titulo = getattr(noticia, "titulo", getattr(noticia, "title", ""))
            fuente = getattr(noticia, "fuente", getattr(noticia, "source", ""))
        if not titulo:
            return "Noticias: sin titulares."
        guardada = noticia.get("guardada") if isinstance(noticia, dict) else None
        previo = f"Sin conexión. Último titular guardado ({guardada[:10]}): " if guardada else "Titular: "
        return f"{previo}{str(titulo).rstrip('.')}." + (f" Fuente: {fuente}." if fuente else "")
    # CONSTRUIR INFORME (corto: saludo, hora, clima y una noticia)
    def construir_rutina(self):
        informacion_reloj = self.obtener_informacion_reloj()
        partes = [self.generar_saludo(informacion_reloj), self.generar_hora(informacion_reloj),
                  self.generar_clima(self.obtener_informacion_clima()),
                  self.generar_noticias(self.obtener_informacion_noticias(cantidad=1))]
        return " ".join(p.strip() for p in partes if p and p.strip())
    def obtener_datos(self):
        informacion_reloj = self.obtener_informacion_reloj()
        return {"reloj": informacion_reloj, "clima": self.obtener_informacion_clima(),
                "noticias": self.obtener_informacion_noticias(cantidad=1),
                "periodo": self.obtener_periodo(informacion_reloj)}
    def ejecutar(self):
        """Punto de entrada principal."""
        return self.construir_rutina()
