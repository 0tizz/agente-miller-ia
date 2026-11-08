"""MILLER · Contexto de las órdenes: entiende lo que se dice "por referencia" a la orden anterior.

  "otra vez" / "de nuevo" / "repítelo"        -> repite la última orden
  "más" / "un poco más" / "menos"             -> sigue con lo último (volumen, graves, agudos...)
  "ciérralo" / "minimízalo" / "maximízalo"    -> sobre el último programa o archivo abierto o nombrado
  "y en brave" / "ahora en firefox"           -> repite la última búsqueda o página en otro navegador
  "y los agudos" (tras subir los graves)      -> misma acción sobre otra banda del ecualizador
"""
import re
import time

NO_REPETIR = {"SALIR", "BORRAR_CANCION", "VACIAR_PAPELERA", "VACIAR_CUARENTENA", "CONFIRMAR_LIMPIEZA",
              "OLVIDAR_NOMBRE", "DESCONOCIDA", "ELOGIO", "REPROCHE", "CERRAR_APLICACION", "CERRAR_ARCHIVO"}
VIGENCIA = 300.0                                     # s: pasado ese tiempo ya no se da por supuesto el contexto
_NAVEGADORES = r"(chrome|google chrome|edge|microsoft edge|firefox|brave|opera)"
_BANDA = r"(graves|bajos|medios|agudos|brillo)"
_PRONOMBRE = r"(?:lo|la|los|las)"


class ContextoOrdenes:
    def __init__(self):
        self.ultima = None                           # {"frase", "intencion", "momento"}
        self.objetivo = None                         # último programa o archivo abierto / nombrado
        self.historial = []

    def registrar(self, intencion, frase, **entidades):
        if not intencion or intencion == "DESCONOCIDA":
            return
        self.ultima = {"frase": frase, "intencion": intencion, "momento": time.monotonic()}
        self.historial = (self.historial + [self.ultima])[-10:]
        if entidades.get("objetivo"):
            self.objetivo = entidades["objetivo"]

    def _vigente(self):
        return self.ultima if self.ultima and time.monotonic() - self.ultima["momento"] < VIGENCIA else None

    def resolver(self, frase):
        """La frase completa a la que se refiere, o None si la frase ya es una orden por sí misma."""
        t = re.sub(r"[?!.,¿¡]", "", str(frase or "")).strip()
        t = re.sub(r"^miller\s+", "", t)
        ultima = self._vigente()
        objetivo = self.objetivo if ultima else None
        if objetivo:
            if re.fullmatch(rf"(cierra{_PRONOMBRE}|cierra eso|cierra esa ventana|ya cierra{_PRONOMBRE})", t):
                return f"cierra {objetivo}"
            if re.fullmatch(rf"(minimiza{_PRONOMBRE}|minimiza eso|esconde{_PRONOMBRE})", t):
                return f"minimiza {objetivo}"
            if re.fullmatch(rf"(maximiza{_PRONOMBRE}|agranda{_PRONOMBRE}|pon{_PRONOMBRE} en grande)", t):
                return f"maximiza {objetivo}"
            if re.fullmatch(rf"(restaura{_PRONOMBRE}|muestra{_PRONOMBRE}|trae{_PRONOMBRE}|vuelve a mostrar{_PRONOMBRE})", t):
                return f"restaura la ventana de {objetivo}"
        if not ultima:
            return None
        intencion, anterior = ultima["intencion"], ultima["frase"]
        if re.fullmatch(r"(otra vez|de nuevo|repitelo|repite eso|hazlo otra vez|hazlo de nuevo|una vez mas|"
                        r"vuelve a hacerlo|lo mismo)", t):
            return None if intencion in NO_REPETIR else anterior
        if re.fullmatch(r"(mas|un poco mas|otro poco|aun mas|todavia mas|mas fuerte|sube mas)", t):
            if intencion in ("SUBIR_VOLUMEN", "ECUALIZADOR_AJUSTE"):
                return anterior if not re.search(r"\b(baja|reduce|disminuye|menos)\b", anterior) else None
            if intencion == "BAJAR_VOLUMEN":
                return "sube el volumen"
        if re.fullmatch(r"(menos|un poco menos|mas bajo|mas suave|baja mas)", t):
            if intencion in ("BAJAR_VOLUMEN", "SUBIR_VOLUMEN"):
                return "baja el volumen"
            if intencion == "ECUALIZADOR_AJUSTE":
                return re.sub(r"\b(sube|aumenta|mas)\b", "baja", anterior)
        m = re.fullmatch(r"(?:y|ahora|mejor)?\s*(?:en|con)?\s*(?:el )?(?:navegador )?" + _NAVEGADORES, t)
        if m and intencion in ("BUSCAR_NAVEGADOR", "ABRIR_SITIO_WEB"):
            sin_nav = re.sub(r"\s*(?:en|con)\s+(?:el\s+)?(?:navegador\s+)?" + _NAVEGADORES + r"\b", "", anterior)
            sin_nav = re.sub(r"\s*en (?:el )?navegador\b", "", sin_nav)
            return f"{sin_nav} en {m.group(1)}"
        m = re.fullmatch(r"(?:y|ahora)\s+(?:los |el |la )?" + _BANDA, t)
        if m and intencion == "ECUALIZADOR_AJUSTE":
            return re.sub(_BANDA, m.group(1), anterior)
        return None
