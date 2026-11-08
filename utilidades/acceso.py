"""MILLER · Control de acceso por llaves y modos (free, boy, pro).

- Hay dos llaves: BOY (plan niños) y PRO (plan pro). MILLER guarda solo su huella (PBKDF2-HMAC-SHA256 con sal).
- Las llaves se ponen en la ventana MILLER (una tarjeta por llave) o en la terminal: "acceso <llave>".
- Mientras una llave está puesta, MILLER funciona con su potencia. Con las dos, manda el modo PRO.
  Al retirarla vuelve el modo que quede. Sin llaves puestas, modo FREE.
- Al arrancar no hay llaves puestas: MILLER empieza en FREE.
- Tras varios intentos fallidos se bloquea un rato. El contador se guarda firmado: reiniciar no lo borra.
"""
import hashlib
import hmac
import re
import secrets
import threading
import time

import configuracion
from utilidades import llave_boy, seguridad

MODOS = ("free", "boy", "pro")
RANGO = {"free": 0, "boy": 1, "pro": 2}
NOMBRES = {"free": "FREE", "boy": "NIÑOS (boy)", "pro": "PRO"}
PREFIJO = {"boy": "BOY", "pro": "PRO"}
ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"      # sin 0, O, 1 ni I: fáciles de leer y de escribir
ITERACIONES = 200_000
RUTA = configuracion.RUTA_DATOS / "seguridad" / "acceso.json"

# Nivel mínimo para cada intención. Lo que no aparece aquí es FREE (estándar, completo).
# NIÑOS (boy): funciones secundarias de biblioteca, internet, sistema y aprendizaje.
NIVEL_BOY = (
    "NOMBRES_APRENDIDOS", "OLVIDAR_NOMBRE", "ENSENAR_SINONIMO", "OLVIDAR_SINONIMO", "SINONIMOS_APRENDIDOS",
    "ENSENAR_ORDEN", "ORDENES_APRENDIDAS", "RESUMEN_APRENDIZAJE", "MEMORIA_CORTO", "MEMORIA_LARGO",
    "OLVIDADOS", "OLVIDAR_TEMA", "RECUPERAR_OLVIDADO", "PLAN_OLVIDO",
    "PREGUNTA_INTERNET", "BUSCAR_INTERNET", "BUSCAR_NAVEGADOR", "ABRIR_SITIO_WEB", "BUSCAR_ARCHIVO",
    "ABRIR_ARCHIVO", "CERRAR_ARCHIVO", "ABRIR_APLICACION", "CERRAR_APLICACION", "CREAR_CARPETA", "ABRIR_CARPETA",
    "ESTADO_SISTEMA", "LISTAR_DANADOS_BIBLIOTECA", "LISTAR_DUPLICADOS_BIBLIOTECA",
    "LISTAR_NO_COMPATIBLES_BIBLIOTECA", "LISTAR_CUARENTENA", "LISTAR_ADULTERADOS", "RESTAURAR_CUARENTENA",
    "VACIAR_CUARENTENA", "BORRAR_CANCION", "LISTAR_PAPELERA", "VACIAR_PAPELERA", "AYUDA_BIBLIOTECA",
    "PROBAR_MODULO", "PROBAR_TODOS_MODULOS", "RESULTADO_PRUEBAS", "LISTAR_PRUEBAS", "SEGURIDAD",
    "PAUSAR_INICIATIVA", "REANUDAR_INICIATIVA", "NOVEDADES",
)
# PRO (desbloqueo total): lo más importante. Varios comandos en una frase, el supervisor de la biblioteca,
# el mantenimiento de la biblioteca, las descargas de música y el sellado del código.
NIVEL_PRO = (
    "ORDEN_MULTIPLE", "PAUSAR_SUPERVISOR", "REANUDAR_SUPERVISOR", "ESTADO_SUPERVISOR",
    "REVISAR_BIBLIOTECA", "REPARAR_BIBLIOTECA", "LIMPIAR_BIBLIOTECA", "CONFIRMAR_LIMPIEZA", "CANCELAR_LIMPIEZA",
    "RESULTADO_LIMPIEZA", "PLAN_ELIMINACION", "DESCARGAR_MUSICA", "ESTADO_DESCARGA", "CANCELAR_DESCARGA",
    "SELLAR_CODIGO",
)
REQUIERE = {**{i: "boy" for i in NIVEL_BOY}, **{i: "pro" for i in NIVEL_PRO}}
SIEMPRE = {"LLAVE_VOZ", "ESTADO_ACCESO", "BLOQUEAR_ACCESO"}      # disponibles en cualquier modo
_RE_ORDEN_LLAVE = re.compile(r"^\s*(acceso|llave|clave)\s+(\S.*)$", re.IGNORECASE)

_puestas = set()                                   # llaves puestas ahora: "boy" y/o "pro"
_aviso = {"texto": "Sin llaves puestas: modo FREE, señor."}
_estado_lock = threading.RLock()                   # protege _puestas y _aviso (rápido, sin cálculos)
_archivo_lock = threading.Lock()                   # protege el fichero de llaves y los intentos (hace hashes)
_oyentes_modo = []                                 # funciones que se avisan cuando cambia el modo


def _fijar(texto):
    with _estado_lock:
        _aviso["texto"] = texto
    return texto


def al_cambiar_modo(funcion):
    """Quien lo pida (p. ej. el supervisor de la biblioteca) recibe el modo nuevo cada vez que cambia."""
    _oyentes_modo.append(funcion)


def _avisar_modo():
    actual = modo()
    for funcion in list(_oyentes_modo):
        try:
            funcion(actual)
        except Exception as error:
            print(f"[ACCESO] Aviso de cambio de modo: {error}")


def activas():
    """Llaves puestas ahora (conjunto de "boy" y/o "pro")."""
    with _estado_lock:
        return frozenset(_puestas)


def modo():
    """Modo que manda: PRO si hay llave PRO, NIÑOS si solo hay BOY, FREE si no hay ninguna."""
    with _estado_lock:
        if "pro" in _puestas:
            return "pro"
        if "boy" in _puestas:
            return "boy"
        return "free"


def ultimo_aviso():
    with _estado_lock:
        return _aviso["texto"]


def canonica(texto):
    """Quita espacios, guiones y signos, y pasa a mayúsculas: "boy-ab3c…" equivale a "BOYAB3C…"."""
    return re.sub(r"[^A-Za-z0-9]", "", str(texto or "")).upper()


def _huella(llave_canonica, sal):
    return hashlib.pbkdf2_hmac("sha256", llave_canonica.encode("utf-8"), sal, ITERACIONES).hex()


def _cargar():
    datos = seguridad.leer_json(RUTA, None) or {}
    datos.setdefault("llaves", {})
    datos.setdefault("fallos", 0)
    datos.setdefault("bloqueado_hasta", 0)
    return datos


def _guardar(datos):
    seguridad.escribir_json(RUTA, datos, indent=2, sincronizar=True)


def generar_llaves(forzar=False):
    """Crea la llave PRO y guarda solo su huella. La llave BOY no se genera: es la del código abierto y se obtiene
    (ver llave_boy). Devuelve la llave PRO en claro: se muestra una sola vez."""
    with _archivo_lock:
        datos = _cargar()
        if datos["llaves"] and not forzar:
            raise RuntimeError("Ya existen llaves. Use forzar=True para sustituirlas.")
        nuevas, claros = {}, {}
        for plan in ("pro",):
            cuerpo = "".join(secrets.choice(ALFABETO) for _ in range(12))
            llave = f"{PREFIJO[plan]}-{cuerpo[:4]}-{cuerpo[4:8]}-{cuerpo[8:]}"
            sal = secrets.token_bytes(16)
            nuevas[plan] = {"sal": sal.hex(), "huella": _huella(canonica(llave), sal)}
            claros[plan] = llave
        datos["llaves"] = nuevas
        datos["fallos"], datos["bloqueado_hasta"] = 0, 0
        _guardar(datos)
        return claros


def _verificar(texto):
    """(plan, aviso): plan es "boy" o "pro" si la llave vale; None si no vale o hay bloqueo."""
    with _archivo_lock:
        datos = _cargar()
        ahora = time.time()
        if datos["bloqueado_hasta"] > ahora:
            minutos = int((datos["bloqueado_hasta"] - ahora) // 60) + 1
            return None, f"Acceso bloqueado tras varios intentos fallidos. Espere {minutos} minuto(s), señor."
        intento = canonica(texto)
        entrada = datos["llaves"].get("pro")
        if entrada and hmac.compare_digest(_huella(intento, bytes.fromhex(entrada["sal"])), entrada["huella"]):
            plan = "pro"
        elif llave_boy.verificar(texto):
            plan = "boy"
            try:
                llave_boy.marcar_conocida()            # puesta en la tarjeta: no hace falta que MILLER la descubra
            except Exception:
                pass
        else:
            plan = None
        if plan:
            if datos["fallos"]:
                datos["fallos"] = 0
                _guardar(datos)
            return plan, ""
        datos["fallos"] += 1
        if datos["fallos"] >= configuracion.ACCESO_INTENTOS_MAX:
            datos["bloqueado_hasta"] = ahora + configuracion.ACCESO_BLOQUEO_MINUTOS * 60
            datos["fallos"] = 0
            _guardar(datos)
            return None, (f"Negativo. Llave no válida. Acceso bloqueado "
                          f"{configuracion.ACCESO_BLOQUEO_MINUTOS} minutos, señor.")
        _guardar(datos)
        return None, "Negativo. Llave no válida, señor."


def poner(plan, texto):
    """Pone una llave en su casilla ("boy" o "pro") o, si plan es None (terminal), en la que corresponda.
    Texto vacío = retirar la llave de la casilla. Devuelve el aviso. La llave nunca se guarda en claro."""
    if plan is not None and plan not in PREFIJO:
        return _fijar("Casilla no válida, señor.")
    if not canonica(texto):
        return quitar(plan)
    encontrada, aviso = _verificar(texto)
    if encontrada is None:
        return _fijar(aviso)
    if plan is not None and encontrada != plan:
        return _fijar(f"Negativo. Esa llave es del modo {NOMBRES[encontrada]}: no va en esta casilla, señor.")
    with _estado_lock:
        _puestas.add(encontrada)
    _avisar_modo()
    return _fijar(f"Afirmativo. Llave {PREFIJO[encontrada]} puesta: modo {NOMBRES[modo()]} activo, señor.")


def introducir(texto):
    """Llave escrita en la TERMINAL con "acceso <llave>"."""
    return poner(None, texto)


def quitar(plan=None):
    """Retira una llave ("boy" o "pro") o, sin plan, todas. Vuelve el modo que quede."""
    with _estado_lock:
        if plan is None:
            _puestas.clear()
            texto = "Llaves retiradas. Modo FREE, señor."
        elif plan in _puestas:
            _puestas.discard(plan)
            texto = f"Llave {PREFIJO[plan]} retirada. Modo {NOMBRES[modo()]}, señor."
        else:
            texto = f"No hay llave {PREFIJO.get(plan, plan)} puesta, señor."
    _avisar_modo()
    return _fijar(texto)


def bloquear():
    """Pon modo free: retira todas las llaves."""
    return quitar(None)


def orden_llave(texto):
    """Si lo escrito en la TERMINAL es "acceso <llave>", devuelve la llave; si no, None."""
    m = _RE_ORDEN_LLAVE.match(texto or "")
    return m.group(2) if m else None


def bloqueo(intencion):
    """None si el modo actual permite la intención; si no, el aviso que MILLER dice."""
    if not getattr(configuracion, "ACCESO_ACTIVO", True) or intencion in SIEMPRE:
        return None
    nivel = REQUIERE.get(intencion, "free")
    if RANGO[modo()] >= RANGO[nivel]:
        return None
    return (f"Esa función es del modo {NOMBRES[nivel]}, señor. "
            "Para activarla ponga su llave en la ventana MILLER o escriba: acceso <llave>.")


def aviso_llave_voz():
    return ("Por seguridad, las llaves no se dicen en voz alta. "
            "Póngalas en la ventana MILLER o en la terminal, señor.")


def estado_texto():
    from utilidades import cuota
    return f"Modo actual: {NOMBRES[modo()]}, señor. {cuota.resumen()}"
