"""MILLER · Alarmas y recordatorios: "pon alarma a las 9 y 20", "en media hora", "en 1 hora 36 minutos"."""
import re
import threading
import time
import uuid
from datetime import datetime, timedelta

from utilidades.numeros import palabras_a_numeros, plano
from utilidades.reloj import hora_12

_RE_PEDIR = re.compile(r"\b(alarma|alarmas|despiertame|despertador|recuerdame|recordatorio|avisame|temporizador)\b")
_RE_TEMPORIZADOR = re.compile(r"\btemporizador\b")
_RE_LISTAR = re.compile(r"\b(que|cuales|cuantas|lista|listar|muestra|mostrar|ver|tengo)\b.*\b(alarmas?|recordatorios?)\b")
_RE_CANCELAR = re.compile(r"\b(cancela|cancelar|quita|quitar|borra|borrar|elimina|eliminar|apaga|apagar|desactiva)\b.*"
                          r"\b(alarmas?|recordatorios?|temporizador)\b")


def es_pedido(texto):
    t = plano(texto)
    return bool(_RE_PEDIR.search(t)) and (" a las " in f" {t} " or " en " in f" {t} " or " para las " in f" {t} "
                                         or bool(_RE_TEMPORIZADOR.search(t))
                                         or bool(_RE_LISTAR.search(t)) or bool(_RE_CANCELAR.search(t))
                                         or bool(re.search(r"\b(a la|las) \d|\b\d{1,2}:\d{2}", palabras_a_numeros(t))))


def tipo_pedido(texto):
    t = plano(texto)
    if _RE_CANCELAR.search(t):
        return "cancelar"
    if _RE_LISTAR.search(t) and not re.search(r"\b(pon|crea|programa|configura|ponme)\b", t):
        return "listar"
    return "crear"


def interpretar_momento(texto, ahora=None):
    """Devuelve (datetime, descripción) o None. Entiende relativos ("en media hora") y horas ("a las 9 y 20")."""
    ahora = ahora or datetime.now()
    t = palabras_a_numeros(plano(texto), unir_y=False)
    relativo = palabras_a_numeros(plano(texto), unir_y=True)
    # --- Relativo: "en media hora", "en 1 hora y 36 minutos", "en 10 minutos", "temporizador de 5 minutos"
    m = re.search(r"\bdentro de|\ben\b|\btemporizador(?: de| por)?\b", relativo)
    if m:
        resto = relativo[m.end():]
        horas = minutos = segundos = 0
        if re.match(r"\s*(?:una )?media hora", resto):
            minutos = 30
        elif re.match(r"\s*(?:un |1 )?cuarto de hora", resto):
            minutos = 15
        hh = re.search(r"(\d+(?:\.\d+)?) horas?(?: y media)?", resto)
        if hh:
            horas = float(hh.group(1)) + (0.5 if "y media" in hh.group(0) else 0)
        mm = re.search(r"(\d+) (?:minutos?|min)\b", resto)
        if mm:
            minutos += int(mm.group(1))
        elif hh and re.search(r"horas? y (\d+)\b", resto):        # "1 hora y 36"
            minutos += int(re.search(r"horas? y (\d+)\b", resto).group(1))
        ss = re.search(r"(\d+) segundos?", resto)
        if ss:
            segundos = int(ss.group(1))
        total = timedelta(hours=horas, minutes=minutos, seconds=segundos)
        if total.total_seconds() > 0:
            return ahora + total, _describir_relativo(total)
    # --- Hora concreta: "a las 9 y 20", "a las 21:30", "a las 7 de la mañana", "a las 9 y media", "menos cuarto"
    t = re.sub(r"\b([2-5]0) y ([1-9])\b", lambda x: str(int(x.group(1)) + int(x.group(2))), t)   # "9 y 30 y 5"
    m = re.search(r"\b(?:a las|a la|para las|las)\s+(\d{1,2})(?::(\d{2}))?(?:\s+y\s+(media|cuarto|\d{1,2}))?"
                  r"(?:\s+menos\s+(cuarto|\d{1,2}))?(?:\s+(?:minutos?))?"
                  r"(?:\s+(de la manana|de la tarde|de la noche|de la madrugada|am|pm|a m|p m))?", t)
    if not m:
        return None
    hora = int(m.group(1))
    minuto = int(m.group(2)) if m.group(2) else 0
    if m.group(3):
        minuto = {"media": 30, "cuarto": 15}.get(m.group(3), None) or int(m.group(3))
    if m.group(4):
        hora -= 1
        minuto = 60 - ({"cuarto": 15}.get(m.group(4), None) or int(m.group(4)))
    periodo = (m.group(5) or "").replace(" ", "")
    if hora > 23 or minuto > 59:
        return None
    if periodo in ("delatarde", "delanoche", "pm") and hora < 12:
        hora += 12
    elif periodo in ("delamanana", "delamadrugada", "am") and hora == 12:
        hora = 0
    momento = ahora.replace(hour=hora % 24, minute=minuto, second=0, microsecond=0)
    if not periodo and hora <= 12:
        # Sin "mañana/tarde": la más próxima de las dos (9:20 o 21:20).
        candidatas = [momento + timedelta(hours=h) for h in (0, 12, 24, 36)]
        momento = next(c for c in candidatas if c > ahora)
    elif momento <= ahora:
        momento += timedelta(days=1)
    return momento, f"{'a la' if momento.hour % 12 == 1 else 'a las'} {hora_12(momento)}"


def _describir_relativo(delta):
    total = int(delta.total_seconds())
    h, resto = divmod(total, 3600)
    m, s = divmod(resto, 60)
    partes = []
    if h:
        partes.append(f"{h} {'hora' if h == 1 else 'horas'}")
    if m:
        partes.append(f"{m} {'minuto' if m == 1 else 'minutos'}")
    if s and not h:
        partes.append(f"{s} {'segundo' if s == 1 else 'segundos'}")
    return "en " + " y ".join(partes)


def extraer_motivo(texto):
    """'recuérdame llamar a mamá en 10 minutos' -> 'llamar a mamá'."""
    t = plano(texto)
    m = re.search(r"\b(?:recuerdame|avisame|alarma para|recordatorio (?:de|para))\s+(?:que\s+)?(.+?)"
                  r"\s+(?:en|dentro de|a las|a la|para las)\s", t + " ")
    motivo = (m.group(1).strip() if m else "")
    return "" if re.fullmatch(r"(?:una?|la|el)?\s*(?:alarma)?", motivo) else motivo[:80]


class GestorAlarmas:
    """Guarda las alarmas firmadas en datos/alarmas.json y avisa cuando vencen."""

    def __init__(self, ruta=None, al_sonar=None):
        self.ruta = ruta
        self.al_sonar = al_sonar
        self._lock = threading.Lock()
        self._alarmas = self._cargar()
        self._vencidas = []
        self._stop = threading.Event()
        self._hilo = threading.Thread(target=self._bucle, daemon=True, name="MILLER-Alarmas")

    def _cargar(self):
        try:
            from utilidades import seguridad
            datos = seguridad.leer_json(self.ruta, {}) if self.ruta else {}
        except Exception:
            datos = {}
        alarmas = []
        for a in (datos or {}).get("alarmas", []):
            try:
                alarmas.append({"id": str(a["id"]), "cuando": datetime.fromisoformat(a["cuando"]),
                                "motivo": str(a.get("motivo", ""))[:80]})
            except (KeyError, TypeError, ValueError):
                continue
        return alarmas

    def _guardar(self):
        if not self.ruta:
            return
        try:
            from utilidades import seguridad
            with self._lock:
                datos = {"alarmas": [{"id": a["id"], "cuando": a["cuando"].isoformat(timespec="seconds"),
                                      "motivo": a["motivo"]} for a in self._alarmas]}
            seguridad.escribir_json(self.ruta, datos)
        except Exception as error:
            print(f"[ALARMAS] No se pudieron guardar: {error}")

    def iniciar(self):
        self._hilo.start()
        return True

    def detener(self):
        self._stop.set()
        self._guardar()

    def _bucle(self):
        while not self._stop.wait(1.0):
            ahora = datetime.now()
            with self._lock:
                vencidas = [a for a in self._alarmas if a["cuando"] <= ahora]
                self._alarmas = [a for a in self._alarmas if a["cuando"] > ahora]
                self._vencidas.extend(vencidas)
            if vencidas:
                self._guardar()
                if callable(self.al_sonar):
                    try:
                        self.al_sonar()
                    except Exception:
                        pass

    # ------------------------------------------------------------ uso
    def hay_vencidas(self):
        return bool(self._vencidas)

    def tomar_vencidas(self):
        with self._lock:
            vencidas, self._vencidas = self._vencidas, []
        return vencidas

    def crear(self, texto, ahora=None):
        resultado = interpretar_momento(texto, ahora)
        if not resultado:
            return "¿A qué hora, señor? Por ejemplo: a las 9 y 20, o en media hora."
        cuando, descripcion = resultado
        if (cuando - (ahora or datetime.now())).days > 7:
            return "Negativo. Solo programo alarmas para los próximos 7 días."
        motivo = extraer_motivo(texto)
        with self._lock:
            if len(self._alarmas) >= 50:
                return "Negativo. Demasiadas alarmas activas."
            self._alarmas.append({"id": uuid.uuid4().hex[:6], "cuando": cuando, "motivo": motivo})
            self._alarmas.sort(key=lambda a: a["cuando"])
        self._guardar()
        extra = f" para {motivo}" if motivo else ""
        hora = f" ({hora_12(cuando)})" if descripcion.startswith("en ") else ""
        return f"Alarma{extra} {descripcion}{hora}.".replace("m..", "m.")

    def listar(self):
        with self._lock:
            alarmas = list(self._alarmas)
        if not alarmas:
            return "Sin alarmas activas."
        hoy = datetime.now().date()
        partes = [f"{'' if a['cuando'].date() == hoy else 'mañana '}{hora_12(a['cuando'])}"
                  + (f" {a['motivo']}" if a["motivo"] else "") for a in alarmas[:5]]
        return (f"{len(alarmas)} {'alarma' if len(alarmas) == 1 else 'alarmas'}: " + ", ".join(partes) + ".").replace("m..", "m.")

    def cancelar(self, texto=""):
        t = palabras_a_numeros(plano(texto), unir_y=False)
        with self._lock:
            if not self._alarmas:
                return "Sin alarmas activas."
            if re.search(r"\b(todas|todos|toda)\b", t):
                n, self._alarmas = len(self._alarmas), []
            else:
                momento = interpretar_momento(t)
                objetivo = None
                if momento:
                    objetivo = next((a for a in self._alarmas if a["cuando"].strftime("%H:%M") == momento[0].strftime("%H:%M")), None)
                objetivo = objetivo or self._alarmas[0]
                self._alarmas.remove(objetivo)
                n = 1
        self._guardar()
        return f"{n} {'alarma cancelada' if n == 1 else 'alarmas canceladas'}."

    @staticmethod
    def anunciar(alarma):
        motivo = f" {alarma['motivo'][0].upper()}{alarma['motivo'][1:]}." if alarma.get("motivo") else ""
        from utilidades.reloj import frase_hora
        return f"Alarma, señor. {frase_hora()}{motivo}"


def sonar_tono(volumen=0.5):
    """Tres pitidos cortos (pygame) antes de anunciar la alarma. Si no hay audio, no pasa nada."""
    try:
        import array
        import math as _m
        import pygame
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        frecuencia, canales = pygame.mixer.get_init()[0], pygame.mixer.get_init()[2]
        muestras = array.array("h")
        for pitido in range(3):
            for i in range(int(frecuencia * 0.18)):
                envolvente = min(1.0, i / 400, (frecuencia * 0.18 - i) / 400)
                valor = int(9000 * envolvente * _m.sin(2 * _m.pi * 880 * i / frecuencia))
                muestras.extend([valor] * canales)
            muestras.extend([0] * int(frecuencia * 0.12) * canales)
        sonido = pygame.mixer.Sound(buffer=muestras.tobytes())
        sonido.set_volume(max(0.1, min(1.0, volumen)))
        canal = sonido.play()
        limite = time.monotonic() + 2.5
        while canal is not None and canal.get_busy() and time.monotonic() < limite:
            time.sleep(0.02)
    except Exception:
        pass
