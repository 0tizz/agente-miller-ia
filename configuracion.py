"""MILLER · v0.1 · Configuración general. Edite los valores; validar() corrige los que estén fuera de rango."""
import sys
import unicodedata
from pathlib import Path

# IDENTIDAD
NOMBRE_ASISTENTE = "MILLER"
VERSION = "0.1.0"
DESCRIPCION = "Sistema de Inteligencia Artificial de asistencia táctica"
PYTHON_MINIMO = (3, 10)
PYTHON_RECOMENDADO = (3, 13)          # PyAudio aún no publica instalador para 3.14


def _ruta_base():
    """Carpeta de MILLER. En el .exe: la carpeta (o una superior) que contiene modelos/ o audios/."""
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent
    carpeta = Path(sys.executable).resolve().parent
    for candidata in (carpeta, *list(carpeta.parents)[:3]):
        if (candidata / "modelos").is_dir() or (candidata / "audios").is_dir():
            return candidata
    return carpeta


# RUTAS
EJECUTABLE = bool(getattr(sys, "frozen", False))
RUTA_BASE = _ruta_base()
RUTA_DATOS = RUTA_BASE / "datos"
RUTA_MEMORIA = RUTA_DATOS / "memoria.json"
RUTA_MODELOS = RUTA_BASE / "modelos"
RUTA_MODELO_VOZ = RUTA_MODELOS / "voz" / "vosk-model-small-es-0.42"
RUTA_VOCES = RUTA_MODELOS / "voces"
RUTA_AUDIOS = RUTA_BASE / "audios"
ICONO_MILLER = RUTA_BASE / "miller_icono.ico"       # ventana, barra de tareas y el .exe
RUTA_NOMBRE_ASISTENTE = RUTA_DATOS / "nombre_asistente.json"   # el nombre que se pone al iniciar
RUTA_EMOCIONES = RUTA_DATOS / "emociones.json"

# VOZ
MODO_VOZ = True                       # False = modo texto (teclado)
HABLAR_RESPUESTAS = True
# La palabra de activación es el nombre del asistente, que se pone al iniciar (utilidades/nombre.py).
USAR_PALABRA_ACTIVACION = True
IDIOMA_VOZ = "es-CO"
VOZ_MOTOR = "neural"                  # "neural" (voz de modelos/voces) | "sapi5" (voz de Windows)
VOZ_NEURAL = "es_ES-davefx-medium"    # voz predeterminada: masculina española
VOZ_GENERO = "masculino"              # para la voz de Windows: "masculino" | "femenino"
VOZ_VELOCIDAD = 185                   # palabras por minuto
VOZ_SILENCIO_FIN_FRASE = 0.6          # s de silencio que cierran una frase (más bajo = más ágil)
VOZ_FACTOR_SOBRE_MUSICA = 1.2         # sin música: la voz suena un 20 % más que el volumen actual
VOZ_DB_SOBRE_MUSICA = 1.0             # con música: la voz suena 1 dB sobre la canción a su volumen normal
VOZ_VOLUMEN_MINIMO = 0.06             # audible aunque la música esté casi en silencio
VOZ_VOLUMEN_MAXIMO = 1.0              # la voz puede llegar al máximo si la música está muy alta
VOZ_SUAVIZADO = True                  # iguala la voz al nivel de la música, sin picos ásperos

# CONVERSACIÓN (como una llamada)
CONVERSACION_ACTIVA = True
CONVERSACION_VENTANA = 8              # s tras cada respuesta para seguir hablando sin decir "Miller"
CONVERSACION_FIN_INACTIVIDAD = 90     # s de silencio que cuelgan el modo llamada

# NOMBRE DEL ASISTENTE
# Se pone al iniciar el programa, una sola vez (PURGAR lo borra). Es la palabra de activación.
# No aprende formas nuevas de oírlo.
NOMBRE_PREDETERMINADO = "Miller"       # si no se pone otro (Enter, o sin consola)
NOMBRE_LONGITUD_MINIMA = 3
NOMBRE_LONGITUD_MAXIMA = 20

# AUDIO
ATENUACION_ACTIVA = True              # la música baja mientras MILLER habla
ATENUACION_FACTOR = 0.40              # mientras habla, la música baja al 40 % (atenuación marcada)
VOLUMEN_DURACION_FUNDIDO = 0.9        # s del fundido al subir/bajar volumen (0 = de golpe)

# SUPERVISOR DE BIBLIOTECA Y PAPELERA
SUPERVISOR_ACTIVO = True
SUPERVISOR_MODO = "cuarentena"        # "observar" | "cuarentena"
SUPERVISOR_INTERVALO = 300            # s entre revisiones completas
SUPERVISOR_VERIFICACION_PROFUNDA = True
SUPERVISOR_REPARACION_AUTOMATICA = True
SUPERVISOR_FFMPEG = None              # None = buscar en modelos/ y en el PATH
SUPERVISOR_ELIMINACION_AUTOMATICA = True
SUPERVISOR_PLAN_ELIMINACION = {       # días en cuarentena antes de borrar (None = nunca solo)
    "danados": 15,
    "duplicados": 7,
    "adulterados_reparados": 7,
    "adulterados": None,
    "papelera": 30,                   # "Miller, borra <canción>"
    "no_compatibles": None,
}

# INICIATIVA (habla solo con permiso)
INICIATIVA_ACTIVA = True
INICIATIVA_FRASES_PERMISO = ["Permiso para hablar, señor."]
INICIATIVA_SILENCIO_PREVIO = 20
INICIATIVA_ESPERA_AUTORIZACION = 25
INICIATIVA_INTERVALO_MINIMO = 900
INICIATIVA_INTERVALO_URGENTE = 60
INICIATIVA_MAX_PETICIONES_HORA = 4
INICIATIVA_AUTORIZAR_SIN_NOMBRE = True

# EMOCIONES
EMOCIONES_ACTIVAS = True

# INTERFAZ: ventana con la esencia de MILLER
INTERFAZ_ACTIVA = True                # cascada de palabras y círculo de su ánimo
MUSICA_AL_INICIAR = True              # al arrancar, la música sigue donde quedó (siempre sonando)
MUSICA_TRAS_VENTANA = True            # ...pero solo después de que se abra la ventana de MILLER
INTERFAZ_ANCHO = 720                  # px (ancho fijo de la ventana)
INTERFAZ_ALTO_PANEL = 520             # px de la zona fija: cascada y páginas (TERMINAL, MILLER con su sección INSTALACIÓN, ENTORNO); 0 = sin panel
INTERFAZ_INACTIVIDAD_S = 120           # segundos sin tocar la ventana para cerrar la página y volver al fondo; 0 = nunca
INTERFAZ_SIEMPRE_ENCIMA = True

# CEREBRO Y MENSAJES
MAXIMO_CONTEXTO = 20
MEMORIA_CORTO_MINUTOS = 45          # memoria a corto plazo: cuánto tiempo recuerda lo dicho en la sesión
MENSAJE_INICIO = "Sistemas en línea."
MENSAJE_NUCLEO = "Núcleo operativo."
MENSAJE_ESPERA = "A la espera de órdenes, señor."
MENSAJE_DESPEDIDA = "Sistemas en reposo. Hasta pronto, señor."
MENSAJE_SALUDO_PRIMERA_VEZ = ("Buenas, señor. Soy MILLER, su asistente. Póngame un nombre en la sección INSTALACIÓN de la página MILLER; "
                              "si lo deja vacío, me quedo como Miller.")
MENSAJE_DESPEDIDA_PURGA = "Hasta luego, señor. Procedo con la purga."
MENSAJE_COMANDO_DESCONOCIDO = "Orden no comprendida."
COMANDOS_SALIDA = ["salir", "exit", "cerrar", "cerrar miller", "apagar", "apagate", "apagar miller",
                   "apagar sistema", "terminar", "adios", "adios miller"]

# UBICACIÓN (clima)
LATITUD = 1.8
LONGITUD = -75.1
NOMBRE_UBICACION = "mi ubicación"

AVISOS_CONFIGURACION = []


def _plano(texto):
    texto = unicodedata.normalize("NFD", str(texto or "").lower().strip())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return " ".join(texto.strip(" .,;:!?¡¿").split())


def es_comando_salida(texto):
    """True si el usuario pide cerrar MILLER ("salir", "Miller, apágate", "adiós"...)."""
    return bool(texto) and _plano(texto) in {_plano(c) for c in COMANDOS_SALIDA}


def _rango(nombre, minimo, maximo, tipo=float):
    valor = globals()[nombre]
    try:
        corregido = min(maximo, max(minimo, tipo(valor)))
    except (TypeError, ValueError):
        corregido = tipo(minimo)
    if corregido != valor:
        AVISOS_CONFIGURACION.append(f"{nombre}={valor!r} fuera de rango; se usa {corregido!r}.")
        globals()[nombre] = corregido


def validar():
    """Corrige valores imposibles y crea las carpetas. Los avisos quedan en AVISOS_CONFIGURACION."""
    AVISOS_CONFIGURACION.clear()
    if sys.version_info < PYTHON_MINIMO:
        AVISOS_CONFIGURACION.append(f"Python {sys.version.split()[0]} es antiguo; se requiere 3.10 o superior.")
    elif sys.version_info[:2] > PYTHON_RECOMENDADO:
        AVISOS_CONFIGURACION.append(f"Python {sys.version.split()[0]}: PyAudio puede no instalarse; use Python 3.13.")
    for nombre, minimo, maximo, tipo in (
            ("VOZ_VELOCIDAD", 80, 350, int), ("VOZ_SILENCIO_FIN_FRASE", 0.3, 3.0, float),
            ("CONVERSACION_VENTANA", 0, 60, float), ("CONVERSACION_FIN_INACTIVIDAD", 15, 3600, float),
            ("ATENUACION_FACTOR", 0.0, 1.0, float),
            ("VOZ_FACTOR_SOBRE_MUSICA", 1.0, 3.0, float), ("VOZ_DB_SOBRE_MUSICA", 0.0, 12.0, float), ("VOZ_VOLUMEN_MINIMO", 0.0, 1.0, float),
            ("VOZ_VOLUMEN_MAXIMO", 0.1, 1.0, float), ("INTERFAZ_ANCHO", 200, 900, int), ("INTERFAZ_ALTO_PANEL", 0, 600, int),
            ("INTERFAZ_INACTIVIDAD_S", 0, 3600, float),
            ("VOLUMEN_DURACION_FUNDIDO", 0.0, 5.0, float), ("SUPERVISOR_INTERVALO", 30, 86400, float),
            ("INICIATIVA_SILENCIO_PREVIO", 0, 600, float), ("INICIATIVA_ESPERA_AUTORIZACION", 5, 120, float),
            ("INICIATIVA_INTERVALO_MINIMO", 30, 86400, float), ("INICIATIVA_INTERVALO_URGENTE", 0, 3600, float),
            ("INICIATIVA_MAX_PETICIONES_HORA", 1, 60, int), ("MAXIMO_CONTEXTO", 2, 200, int),
            ("LATITUD", -90.0, 90.0, float), ("LONGITUD", -180.0, 180.0, float)):
        _rango(nombre, minimo, maximo, tipo)
    global SUPERVISOR_MODO, VOZ_GENERO, INICIATIVA_FRASES_PERMISO
    if SUPERVISOR_MODO not in ("observar", "cuarentena"):
        AVISOS_CONFIGURACION.append(f"SUPERVISOR_MODO={SUPERVISOR_MODO!r} no válido; se usa 'observar'.")
        SUPERVISOR_MODO = "observar"
    if str(VOZ_GENERO).lower() not in ("masculino", "femenino"):
        VOZ_GENERO = "masculino"
    if not isinstance(INICIATIVA_FRASES_PERMISO, (list, tuple)) or not INICIATIVA_FRASES_PERMISO:
        INICIATIVA_FRASES_PERMISO = ["Permiso para hablar, señor."]
    if not isinstance(SUPERVISOR_PLAN_ELIMINACION, dict):
        AVISOS_CONFIGURACION.append("SUPERVISOR_PLAN_ELIMINACION debe ser un diccionario; se ignora.")
        globals()["SUPERVISOR_PLAN_ELIMINACION"] = {}
    for carpeta in (RUTA_DATOS, RUTA_AUDIOS, RUTA_MODELOS):
        carpeta.mkdir(parents=True, exist_ok=True)
    if MODO_VOZ and not RUTA_MODELO_VOZ.is_dir():
        AVISOS_CONFIGURACION.append(f"No se encontró el modelo de voz en {RUTA_MODELO_VOZ}.")
    return AVISOS_CONFIGURACION


# ====== ACCESO, MODOS Y CUOTAS ======
ACCESO_ACTIVO = True                  # False desactiva los modos: todo disponible (solo para depurar)
ACCESO_INTENTOS_MAX = 5               # llaves erróneas seguidas antes de bloquear el acceso
ACCESO_BLOQUEO_MINUTOS = 15           # cuánto dura el bloqueo tras los intentos fallidos
CUOTA_ACTIVA = True                   # limita cuánto puede ocupar MILLER en disco
CUOTA_RESERVA_DISCO_MB = 1024         # espacio libre del disco que nunca se toca
CUOTA_FREE_ASISTENTE_MB = 1024        # FREE: tope del asistente (código, modelos, memorias)
CUOTA_FREE_ARCHIVOS_MB = 1024         # FREE: tope de archivos (canciones)
CUOTA_BOY_ASISTENTE_MB = 2048         # NIÑOS: tope del asistente
CUOTA_BOY_ARCHIVOS_MB = 8192          # NIÑOS: tope de archivos
CUOTA_PRO_DISCO = 0.90                # PRO: puede usar hasta este % del espacio libre del disco
CUOTA_PRO_REPARTO_ASISTENTE = 0.30    # PRO: parte para el asistente; el resto para archivos
CUOTA_DESCARGA_ESTIMADA_MB = 20       # espacio que se reserva antes de descargar una canción
CUOTA_AVISO_DISCO_PCT = 0.05          # disco con menos de este % libre: presión baja (MILLER avisa y poda con cuidado)
CUOTA_CRITICA_DISCO_PCT = 0.02        # menos de este % libre: presión crítica (no se descarga nada)
CUOTA_ESCRITURA_MINIMA_MB = 16        # por debajo de este margen no se guardan recuerdos nuevos

validar()
