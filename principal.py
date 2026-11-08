"""MILLER · v0.1 · Punto de entrada: arranque, bucle de voz/texto y cierre ordenado."""
import os
import queue
import re
import sys
import threading
import time
from contextlib import nullcontext
import configuracion
from utilidades import acceso
from utilidades import entorno
if __name__ == "__main__" and "--instalar" in sys.argv:
    # Equipo nuevo (clon del repositorio): baja librerías, modelos de voz y ffmpeg, y termina.
    from utilidades import instalador
    sys.exit(0 if instalador.instalar_todo(print) else 1)
if __name__ == "__main__" and not entorno.comprobar():
    sys.exit(1)
if __name__ == "__main__":
    from utilidades import instalador
    if not instalador.todo_listo():
        print("[INSTALADOR] Faltan modelos (voz, ffmpeg). Ejecute una vez: python principal.py --instalar")
from cerebro.cerebro import Cerebro
from voz.activador import Activador
from voz.conversacion import Conversacion
from configuracion import USAR_PALABRA_ACTIVACION, MODO_VOZ, HABLAR_RESPUESTAS
from utilidades import nombre
sys.setswitchinterval(0.002)                      # reparte mejor el tiempo entre hilos: la ventana no se traba


def _registrar_error_hilo(info):
    """Un fallo en un hilo de fondo se registra y MILLER sigue funcionando."""
    try:
        print(f"[MILLER] Error en {info.thread.name if info.thread else 'hilo'}: {info.exc_value}")
        from utilidades import seguridad
        seguridad.anexar_log(configuracion.RUTA_DATOS / "errores.log",
                             f"{time.strftime('%Y-%m-%d %H:%M:%S')} {info.thread.name if info.thread else ''}: "
                             f"{info.exc_type.__name__}: {info.exc_value}")
    except Exception:
        pass


threading.excepthook = _registrar_error_hilo
try:
    from voz.escuchador import Escuchador
except Exception as _error_escuchador:            # sin vosk/pyaudio: MILLER funciona en modo texto
    Escuchador = None
    print(f"[MILLER] Reconocimiento de voz no disponible: {_error_escuchador}")
try:
    from voz.hablador import Hablador
except Exception as _error_hablador:              # sin pyttsx3: responde solo por pantalla
    Hablador = None
    print(f"[MILLER] Síntesis de voz no disponible: {_error_hablador}")

def mostrar_encabezado():
    print(f"\n{'=' * 60}\n                     M I L L E R\n{'=' * 60}\n      Asistente Personal de Inteligencia Artificial\n{'=' * 60}\n")

def crear_componentes():
    print("[MILLER] Inicializando cerebro...")
    cerebro = Cerebro()
    print("[MILLER] Cerebro preparado.")
    escuchador = None
    if MODO_VOZ:
        try:
            print("[MILLER] Inicializando reconocimiento de voz...")
            if Escuchador is None:
                raise RuntimeError("faltan vosk o PyAudio")
            escuchador = Escuchador()
            print("MILLER: Micrófono preparado." if getattr(escuchador, "microfono_disponible", False) else "MILLER: Micrófono no disponible.")
        except Exception as error:
            print(f"MILLER: Error inicializando el reconocimiento de voz.\n[VOZ] {error}")
            escuchador = None
    hablador = None
    if HABLAR_RESPUESTAS:
        try:
            print("[MILLER] Inicializando síntesis de voz...")
            if Hablador is None:
                raise RuntimeError("falta pyttsx3")
            hablador = Hablador()
            print("MILLER: Síntesis de voz preparada." if getattr(hablador, "disponible", False) else "MILLER: Síntesis de voz no disponible.")
        except Exception as error:
            print(f"MILLER: Error inicializando síntesis de voz.\n[VOZ] {error}")
            hablador = None
        if hablador is not None:
            conectar_atenuador(hablador, cerebro)
            cerebro.hablador = hablador
    activador = None
    if USAR_PALABRA_ACTIVACION:
        try:
            print("[MILLER] Inicializando activador...")
            activador = Activador(nombre.clave(), aprender=False)     # la palabra de activación es el nombre
            cerebro.activador = activador
            try:
                palabra = activador.obtener_palabra()
            except Exception:
                palabra = nombre.clave()
            print(f"MILLER: Palabra de activación: '{palabra}'.")
        except Exception as error:
            print(f"MILLER: Error inicializando el activador.\n[ACTIVADOR] {error}")
            activador = None
    return cerebro, escuchador, hablador, activador
# ATENUACIÓN: la música baja mientras MILLER habla y la voz sigue al volumen

def conectar_atenuador(hablador, cerebro):
    if not getattr(configuracion, "ATENUACION_ACTIVA", True):
        return
    try:
        from audio.atenuador import AtenuadorVoz
        reproductor = getattr(getattr(cerebro, "comandos", None), "reproductor", None)
        if reproductor is None:
            return
        hablador.conectar_atenuador(AtenuadorVoz(
            reproductor, factor=getattr(configuracion, "ATENUACION_FACTOR", 0.40),
            factor_voz=getattr(configuracion, "VOZ_FACTOR_SOBRE_MUSICA", 1.2),
            minimo_voz=getattr(configuracion, "VOZ_VOLUMEN_MINIMO", 0.06),
            maximo_voz=getattr(configuracion, "VOZ_VOLUMEN_MAXIMO", 1.0),
            db_sobre_musica=getattr(configuracion, "VOZ_DB_SOBRE_MUSICA", 1.0)))
        print("[MILLER] Atenuación de música al hablar: activa.")
    except Exception as error:
        print(f"[VOZ] Atenuación no disponible: {error}")

INTERFAZ = None                                  # ventana de la esencia (si está abierta)
CIERRE = threading.Event()                       # se activa al cerrar la ventana: apaga MILLER
HABLA = threading.RLock()                        # una sola voz a la vez (respuestas y alarmas)
TERMINADO = threading.Event()
ORDEN = threading.RLock()                         # voz, consola y TERMINAL nunca procesan dos órdenes a la vez
ORDENES_ESCRITAS = queue.Queue()                 # lo que se escribe en la TERMINAL de la ventana


def interfaz(metodo, *argumentos):
    """Avisa a la ventana sin que un fallo gráfico afecte a MILLER."""
    if INTERFAZ is not None:
        try:
            getattr(INTERFAZ, metodo)(*argumentos)
        except Exception:
            pass


def abrir_interfaz(cerebro):
    global INTERFAZ
    if not getattr(configuracion, "INTERFAZ_ACTIVA", True):
        return
    try:
        from interfaz import esencia
        INTERFAZ = esencia.crear(cerebro, getattr(configuracion, "INTERFAZ_ANCHO", 300),
                                 getattr(configuracion, "INTERFAZ_SIEMPRE_ENCIMA", True),
                                 al_cerrar=CIERRE.set, ruta_movimiento=configuracion.RUTA_DATOS / "movimiento.json",
                                 alto_panel=getattr(configuracion, "INTERFAZ_ALTO_PANEL", 210),
                                 al_escribir=ORDENES_ESCRITAS.put, ruta_programa=configuracion.RUTA_BASE)
        if INTERFAZ is not None:
            INTERFAZ.al_purgar = CIERRE.set              # PURGAR: que MILLER se despida antes de cerrar la ventana
            print("[MILLER] Ventana de la esencia abierta.")
            try:
                cerebro.comandos.minimizar_propia = INTERFAZ.minimizar      # "Miller, minimízate"
            except Exception:
                pass
    except Exception as error:
        print(f"[INTERFAZ] No disponible: {error}")


def iniciar_musica(cerebro):
    """La música continúa normal al arrancar, pero solo cuando la ventana de MILLER ya se abrió."""
    if not getattr(configuracion, "MUSICA_AL_INICIAR", True):
        return
    reproductor = getattr(getattr(cerebro, "comandos", None), "reproductor", None)
    if reproductor is None or not hasattr(reproductor, "continuar_al_iniciar"):
        return

    def arrancar():
        if INTERFAZ is not None:                     # la ventana ya está en pantalla: un instante y suena
            time.sleep(0.8)
        try:
            if reproductor.continuar_al_iniciar():
                print("[MILLER] La música continúa.")
        except Exception as error:
            print(f"[AUDIO] No se pudo continuar la música: {error}")
    threading.Thread(target=arrancar, daemon=True, name="MILLER-MusicaInicio").start()


def responder(hablador, respuesta, en_terminal=None):
    """Dice la respuesta. En la terminal sale lo mismo, o «en_terminal» si se pide algo más (la clave BOY).
    Si la respuesta trae una versión corta para voz (catalogo.Respuesta), en voz se dice solo esa."""
    if respuesta is None:
        return
    voz = getattr(respuesta, "voz", None)
    respuesta = str(respuesta).strip()
    if not respuesta:
        return
    hablado = str(voz).strip() if voz else respuesta
    with HABLA:
        print(f"\nMILLER: {respuesta}")
        interfaz("registrar", "MILLER", f"{respuesta} {en_terminal}" if en_terminal else respuesta)
        interfaz("publicar", hablado, "miller")
        interfaz("modo", "hablando")
        if HABLAR_RESPUESTAS and hablador is not None:
            try:
                if getattr(hablador, "disponible", True):
                    hablador.hablar(hablado)
            except Exception as error:
                print(f"[VOZ] No fue posible reproducir la respuesta:\n[VOZ] {error}")
        interfaz("modo", "escuchando")
        print()


def gestor_alarmas(cerebro):
    return getattr(getattr(cerebro, "comandos", None), "alarmas", None)


def anunciar_alarmas(cerebro, hablador):
    """Suena el tono y MILLER avisa. Las alarmas las pidió el usuario: no piden permiso."""
    gestor = gestor_alarmas(cerebro)
    if gestor is None or not gestor.hay_vencidas():
        return False
    from utilidades.alarmas import sonar_tono
    for alarma in gestor.tomar_vencidas():
        with HABLA:
            try:
                volumen = cerebro.comandos.reproductor.volumen
            except Exception:
                volumen = 0.5
            sonar_tono(max(0.3, volumen * 1.2))
            responder(hablador, gestor.anunciar(alarma))
    return True

def reiniciar_activador(activador):
    if activador is None:
        return
    try:
        activador.desactivar()
    except Exception:
        pass

def obtener_palabra_activacion(activador):
    if activador is not None:
        try:
            palabra = activador.obtener_palabra()
            if palabra:
                return str(palabra).strip().lower()
        except Exception:
            pass
    return str(nombre.clave()).strip().lower()
# INICIATIVA: MILLER pide permiso para hablar y solo habla si se le autoriza

def pedir_permiso_para_hablar(iniciativa, hablador, escuchador=None):
    frase = iniciativa.pedir_permiso()
    responder(hablador, frase)
    interfaz("modo", "permiso")
    descartar_eco(escuchador)
    print("✋ MILLER espera su autorización (adelante / diga / siga / ahora no).")


def descartar_eco(escuchador):
    """Evita que MILLER se oiga a sí mismo justo después de hablar."""
    metodo = getattr(escuchador, "descartar_eco", None)
    if callable(metodo):
        try:
            metodo()
        except Exception:
            pass


def atender_permiso(iniciativa, hablador, escuchador, decision):
    if decision == "autoriza":
        print("✅ MILLER: permiso concedido.")
        texto = iniciativa.entregar()
        responder(hablador, texto, en_terminal=iniciativa.adjunto_terminal())
    else:
        print("⛔ MILLER: permiso denegado. Queda para más tarde.")
        responder(hablador, iniciativa.posponer())
    descartar_eco(escuchador)


def decidir_permiso(iniciativa, activado, orden, entrada):
    """Durante la espera: ¿la frase autoriza, deniega o es otra orden?"""
    if not iniciativa.esta_esperando():
        return None
    if activado and not orden:
        return "autoriza"                       # "Miller." a secas = "dígame"
    if activado:
        return iniciativa.interpretar(orden)
    if getattr(configuracion, "INICIATIVA_AUTORIZAR_SIN_NOMBRE", True):
        return iniciativa.interpretar(entrada)
    return None


def espera_respuesta(cerebro):
    """MILLER acaba de preguntar algo ("¿qué canción reproduzco?") y espera la respuesta."""
    pendiente = any(getattr(cerebro, a, False) for a in ("cancion_pendiente", "cola_pendiente",
                                                         "volumen_pendiente", "tema_memoria_pendiente"))
    try:
        return pendiente or bool(cerebro.comandos.hay_limpieza_pendiente())
    except Exception:
        return pendiente


def _comando_de_terminal(cerebro, orden):
    """Órdenes que actúan sobre la propia TERMINAL («limpiar terminal»). Devuelve True si las atendió.
    Vacían el texto Y reinician la conversación reciente; la memoria a largo plazo no se toca."""
    import unicodedata
    texto = "".join(c for c in unicodedata.normalize("NFD", str(orden or "").lower())
                    if unicodedata.category(c) != "Mn").strip(" .,!¡¿?")
    texto = re.sub(r"^miller[\s,]+", "", texto)
    if not re.fullmatch(r"(?:limpia|limpiar|limpiame|borra|borrar|vacia|vaciar|reinicia|reiniciar)\s+"
                        r"(?:la\s+|de\s+la\s+)?(?:terminal|pantalla|consola)(?:\s+de\s+miller)?", texto):
        return False
    try:
        cerebro.olvidar_contexto()
    except Exception as error:
        print(f"[TERMINAL] No pude reiniciar el contexto: {error}")
    interfaz("limpiar_terminal")
    interfaz("registrar", "MILLER", "Afirmativo, señor. Terminal limpia y conversación reiniciada.")
    return True


def ejecutar_orden(cerebro, hablador, orden, iniciativa=None):
    """Ejecuta una orden sin que la iniciativa pueda interrumpirla."""
    if _comando_de_terminal(cerebro, orden):
        return
    interfaz("publicar", orden, "usuario")
    interfaz("registrar", "Tú", orden)
    interfaz("modo", "pensando")
    with ORDEN, (iniciativa.ocupado() if iniciativa is not None else nullcontext()):
        try:
            respuesta = cerebro.procesar(orden)
        except Exception as error:
            print(f"[CEREBRO] Error procesando la orden:\n[CEREBRO] {error}")
            respuesta = "Se produjo un error inesperado al procesar la instrucción."
        responder(hablador, respuesta, en_terminal=iniciativa.adjunto_terminal() if iniciativa is not None else None)

def procesar_voz(cerebro, escuchador, hablador, activador):
    if escuchador is None:
        print("MILLER: El reconocimiento de voz no está disponible.")
        return
    try:
        disponible = escuchador.esta_disponible()
    except Exception as error:
        print(f"MILLER: No se pudo comprobar el reconocimiento de voz.\n[VOZ] {error}")
        return
    if not disponible:
        print("MILLER: El sistema de reconocimiento local no está disponible.")
        error_voz = getattr(escuchador, "error", None)
        if error_voz:
            print(f"[VOZ] {error_voz}")
        return
    if USAR_PALABRA_ACTIVACION and activador is None:
        print("MILLER: El activador no está disponible.")
        return
    palabra = obtener_palabra_activacion(activador)
    reiniciar_activador(activador)
    print(f"\nMILLER: Estoy esperando la palabra '{palabra}'." if USAR_PALABRA_ACTIVACION else "\nMILLER: Estoy escuchando.")
    if USAR_PALABRA_ACTIVACION:
        print("MILLER: Las frases sin la palabra de activación serán ignoradas.")
    print()
    iniciativa = getattr(cerebro, "iniciativa", None)
    conversacion = Conversacion(ventana=getattr(configuracion, "CONVERSACION_VENTANA", 8),
                                fin_inactividad=getattr(configuracion, "CONVERSACION_FIN_INACTIVIDAD", 90),
                                activa=getattr(configuracion, "CONVERSACION_ACTIVA", True))

    def quiere_hablar():
        return iniciativa is not None and iniciativa.debe_pedir_permiso()

    alarmas = gestor_alarmas(cerebro)

    def hay_evento():
        return (CIERRE.is_set() or conversacion.debe_caducar() or quiere_hablar()
                or (alarmas is not None and alarmas.hay_vencidas()))

    def hablar(texto, seguir=True):
        responder(hablador, texto)
        descartar_eco(escuchador)                  # no oírse a sí mismo (importante sin nombre)
        if seguir:
            conversacion.abrir_seguimiento()
    while True:
        try:
            entrada = escuchador.escuchar(interrumpir=hay_evento)
        except KeyboardInterrupt:
            print("\nMILLER: Escucha interrumpida.")
            break
        except Exception as error:
            print(f"[VOZ] Error escuchando: {error}")
            reiniciar_activador(activador)
            continue
        entrada = str(entrada or "").strip()
        if CIERRE.is_set():
            print("\nMILLER: Ventana cerrada. Apagando.")
            break
        if not entrada:
            if anunciar_alarmas(cerebro, hablador):
                descartar_eco(escuchador)
                continue
            if conversacion.llamada_caducada():
                hablar("Llamada finalizada por inactividad, señor.", seguir=False)
                continue
            # La escucha se pausó porque MILLER tiene algo que decir y nadie está hablando.
            if quiere_hablar():
                pedir_permiso_para_hablar(iniciativa, hablador, escuchador)
            continue
        print(f"🎙️ Detectado: {entrada}")
        conversacion.oido()
        if iniciativa is not None:
            iniciativa.marcar_actividad()          # alguien habla: no interrumpir
        if USAR_PALABRA_ACTIVACION:
            try:
                resultado = activador.procesar(entrada)
            except Exception as error:
                print(f"[ACTIVADOR] Error procesando frase: {error}")
                reiniciar_activador(activador)
                continue
            if not isinstance(resultado, dict):
                print("[ACTIVADOR] Resultado inválido.")
                reiniciar_activador(activador)
                continue
            activado = bool(resultado.get("activado", False))
            orden = resultado.get("orden", "")
            orden = "" if orden is None else str(orden).strip()
        else:
            activado, orden = True, entrada
        # ¿Es la respuesta a "Permiso para hablar, señor"?
        if iniciativa is not None:
            decision = decidir_permiso(iniciativa, activado, orden, entrada)
            if decision:
                atender_permiso(iniciativa, hablador, escuchador, decision)
                reiniciar_activador(activador)
                continue
            if (activado and orden or conversacion.acepta_sin_nombre()) and iniciativa.esta_esperando():
                iniciativa.retirar_peticion()      # llegó otra orden: la orden manda
                print("✋ MILLER retira su petición de palabra: hay una orden.")
        # Conversación fluida: modo llamada y seguimiento sin repetir el nombre.
        frase = orden if activado else entrada
        if activado or conversacion.acepta_sin_nombre():
            if conversacion.es_inicio(frase):
                conversacion.iniciar_llamada()
                print("📞 MILLER: modo llamada activo.")
                hablar("En línea, señor. Le escucho. Para terminar diga: fin de la llamada.")
                interfaz("modo", "llamada")
                reiniciar_activador(activador)
                continue
            if conversacion.en_llamada() and conversacion.es_fin(frase):
                conversacion.terminar_llamada()
                print("📞 MILLER: llamada finalizada.")
                hablar("Llamada finalizada, señor.", seguir=False)
                reiniciar_activador(activador)
                continue
        if not activado and conversacion.acepta_sin_nombre():
            if (conversacion.en_seguimiento() and not espera_respuesta(cerebro)
                    and cerebro.detectar_intencion(entrada) == "DESCONOCIDA"):
                print("💬 MILLER: frase ignorada (no parece una orden para mí).")
                conversacion.cerrar_seguimiento()
                reiniciar_activador(activador)
                continue
            activado, orden = True, entrada
            print("💬 MILLER: " + ("en llamada." if conversacion.en_llamada() else "seguimiento sin nombre."))
        if USAR_PALABRA_ACTIVACION:
            if not activado:
                print("🔒 MILLER: frase ignorada (sin palabra activadora).")
                reiniciar_activador(activador)
                continue
            print("🔓 MILLER: palabra activadora detectada.")
            if not orden:
                print("🔓 MILLER: activación sin comando.")
                hablar("Sí. Estoy escuchando.")
                reiniciar_activador(activador)
                print("🔒 MILLER volvió a ESPERA.")
                continue
            print(f"🔓 Comando autorizado: {orden}")
        orden = str(orden).strip()
        if not orden:
            reiniciar_activador(activador)
            continue
        ejecutar_orden(cerebro, hablador, orden, iniciativa)
        descartar_eco(escuchador)
        conversacion.abrir_seguimiento()
        if USAR_PALABRA_ACTIVACION:
            reiniciar_activador(activador)
            print("🔒 MILLER volvió a ESPERA.")
        try:
            if cerebro.debe_cerrar():
                break
        except Exception as error:
            print(f"[CEREBRO] Error comprobando salida: {error}")
            continue

def procesar_texto(cerebro, hablador):
    print("MILLER: Modo texto activado.")
    print("MILLER: Escribe 'salir' para cerrar.\n")
    iniciativa = getattr(cerebro, "iniciativa", None)

    def vigilar_alarmas():                       # en modo texto input() bloquea: las alarmas avisan desde aquí
        while not TERMINADO.is_set():
            time.sleep(1.0)
            ocupado = iniciativa is not None and iniciativa.estado().get("ocupado")
            if not ocupado:
                anunciar_alarmas(cerebro, hablador)
    threading.Thread(target=vigilar_alarmas, daemon=True, name="MILLER-AvisoAlarmas").start()
    while True:
        if iniciativa is not None and iniciativa.debe_pedir_permiso():
            pedir_permiso_para_hablar(iniciativa, hablador)
        try:
            entrada = input("Tú: ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break
        if not entrada:
            continue
        if iniciativa is not None:
            iniciativa.marcar_actividad()
            sin_miller = re.sub(r"^\s*miller\b[\s,.:]*", "", entrada, flags=re.I).strip()
            nombrado = sin_miller != entrada
            decision = decidir_permiso(iniciativa, nombrado or not sin_miller, sin_miller, entrada)
            if decision:
                atender_permiso(iniciativa, hablador, None, decision)
                continue
            iniciativa.retirar_peticion()
        ejecutar_orden(cerebro, hablador, entrada, iniciativa)
        try:
            if cerebro.debe_cerrar():
                break
        except Exception as error:
            print(f"[CEREBRO] Error comprobando salida: {error}")

def atender_terminal(cerebro, hablador):
    """Hilo de la TERMINAL de la ventana: ejecuta lo escrito, aunque MILLER esté en modo voz."""
    iniciativa = getattr(cerebro, "iniciativa", None)
    while not TERMINADO.is_set():
        try:
            entrada = ORDENES_ESCRITAS.get(timeout=0.5).strip()
        except queue.Empty:
            continue
        if not entrada:
            continue
        llave = acceso.orden_llave(entrada)
        if llave is not None:                       # la llave no pasa a la memoria ni a la cascada
            aviso = acceso.introducir(llave)
            print(f"MILLER: {aviso}")
            interfaz("registrar", "MILLER", aviso)
            continue
        try:
            if iniciativa is not None:
                iniciativa.marcar_actividad()
                sin_miller = re.sub(r"^\s*miller\b[\s,.:]*", "", entrada, flags=re.I).strip()
                nombrado = sin_miller != entrada
                decision = decidir_permiso(iniciativa, nombrado or not sin_miller, sin_miller, entrada)
                if decision:
                    interfaz("registrar", "Tú", entrada)
                    atender_permiso(iniciativa, hablador, None, decision)
                    continue
                iniciativa.retirar_peticion()
            ejecutar_orden(cerebro, hablador, entrada, iniciativa)
            if cerebro.debe_cerrar():
                CIERRE.set()                     # "salir" escrito en la terminal apaga MILLER
        except Exception as error:
            print(f"[TERMINAL] Error: {error}")


def _fundir_musica(cerebro):
    """Antes de cerrar por una purga: la música baja hasta el silencio y se espera a que acabe el fundido."""
    reproductor = getattr(getattr(cerebro, "comandos", None), "reproductor", None)
    if reproductor is None:
        return
    try:
        reproductor.fundir_salida()
    except Exception as error:
        print(f"[PURGA] No se pudo fundir la música: {error}")


def cerrar_miller(escuchador, hablador, activador=None, cerebro=None):
    print(f"\n{'=' * 60}\nMILLER: Cerrando sistema...")
    # 1. Desactivar la palabra de activación.
    if activador is not None:
        try:
            activador.desactivar()
        except Exception as error:
            print(f"[ACTIVADOR] Error cerrando activador: {error}")
    # 2. Detener la escucha para impedir nuevas órdenes.
    if escuchador is not None:
        try:
            escuchador.detener()
        except Exception as error:
            print(f"[VOZ] Error cerrando escuchador: {error}")
    # 3. Si se pidió PURGAR, MILLER se despide (en voz alta si la voz está activa) antes de borrar nada.
    try:
        from utilidades import purga
        pedida = purga.pedida()
    except Exception:
        pedida = False
    if pedida:
        try:
            responder(hablador, configuracion.MENSAJE_DESPEDIDA_PURGA)     # espera a que termine de hablar
        except Exception as error:
            print(f"[PURGA] No se pudo despedir: {error}")
    # Al cerrar (purga o ventana): primero termina de hablar y la música se funde hasta el silencio.
    _fundir_musica(cerebro)
    # 4. Cerrar la ventana (ya se ha despedido y ha fundido el sonido).
    interfaz("cerrar")
    # 5. Cerrar el cerebro y esperar al cierre del reproductor.
    if cerebro is not None:
        try:
            cerebro.cerrar()
        except Exception as error:
            print(f"[CIERRE] Error cerrando cerebro: {error}")
    # 6. Detener el hablador después del cierre ordenado.
    if hablador is not None:
        try:
            hablador.detener()
        except Exception as error:
            print(f"[VOZ] Error cerrando hablador: {error}")
    # 7. Si se pidió PURGAR en la ventana MILLER, se borran recuerdos y cachés ahora que todo está parado.
    try:
        from utilidades import purga
        purga.ejecutar_si_pedida()
    except Exception as error:
        print(f"[PURGA] Error: {error}")
    print(f"MILLER: {configuracion.MENSAJE_DESPEDIDA}\n{'=' * 60}")

def revisar_seguridad_al_iniciar():
    """En segundo plano: limpia copias viejas y comprueba que el código de MILLER no cambió a escondidas."""
    def revisar():
        from utilidades import seguridad
        try:
            seguridad.limpiar_antiguos(30)
            cambiados = seguridad.integridad_codigo()
            if cambiados:
                print(f"[SEGURIDAD] ⚠ {len(cambiados)} archivos de código cambiaron desde el sello: "
                      f"{', '.join(sorted(cambiados)[:5])}. Si fue usted: «Miller, sella tu código».")
        except Exception as error:
            print(f"[SEGURIDAD] Revisión inicial: {error}")
    threading.Thread(target=revisar, daemon=True, name="MILLER-Seguridad").start()


def esperar_nombre_en_ventana():
    """Primera vez: la ventana pone el nombre (página INSTALACIÓN). Devuelve False si la ventana se cierra antes."""
    while not nombre.esperar_fijado(0.5):
        if CIERRE.is_set():
            return False
    return True


def aplicar_nombre(cerebro, activador):
    """Con el nombre ya puesto (ventana o consola), Cerebro y el activador de voz lo usan. Devuelve el activador."""
    nombre_final = nombre.clave()
    if cerebro is not None:
        cerebro.nombre = nombre_final
    if USAR_PALABRA_ACTIVACION:
        try:
            activador = Activador(nombre_final, aprender=False)      # la palabra de activación es el nombre
            if cerebro is not None:
                cerebro.activador = activador
        except Exception as error:
            activador = None
            print(f"MILLER: Error inicializando el activador.\n[ACTIVADOR] {error}")
    return activador


def _identidad_barra_tareas():
    """Windows muestra el icono de MILLER (y no el de Python) en la barra de tareas."""
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MILLER.Asistente")
    except Exception:
        pass


def main():
    _identidad_barra_tareas()
    mostrar_encabezado()
    revisar_seguridad_al_iniciar()
    try:
        cerebro, escuchador, hablador, activador = crear_componentes()
    except Exception as error:
        print(f"\nMILLER: No se pudo iniciar.\n[INICIO] {error}")
        return
    abrir_interfaz(cerebro)
    if INTERFAZ is not None:
        if not nombre.fijado():                       # primera vez: el nombre se pone en la ventana, no en la consola
            print(f"\nMILLER: {configuracion.MENSAJE_SALUDO_PRIMERA_VEZ}")
            if not esperar_nombre_en_ventana():       # la ventana se cerró antes de ponerlo
                TERMINADO.set()
                cerrar_miller(escuchador, hablador, activador, cerebro)
                return
    else:
        nombre.configurar_al_iniciar()                # sin ventana: el nombre se pregunta en la consola
    activador = aplicar_nombre(cerebro, activador)
    iniciar_musica(cerebro)
    if INTERFAZ is not None:
        threading.Thread(target=atender_terminal, args=(cerebro, hablador), daemon=True,
                         name="MILLER-Terminal").start()

    def vigilar_cierre():
        """En modo texto input() no se puede interrumpir: al cerrar la ventana se apaga de forma ordenada."""
        CIERRE.wait()
        time.sleep(2.0)
        if not TERMINADO.is_set():
            TERMINADO.set()
            print("\nMILLER: Ventana cerrada. Apagando.")
            cerrar_miller(escuchador, hablador, activador, cerebro)
            os._exit(0)
    threading.Thread(target=vigilar_cierre, daemon=True, name="MILLER-Cierre").start()
    print(f"\nMILLER: {configuracion.MENSAJE_INICIO}")
    print(f"MILLER: {configuracion.MENSAJE_NUCLEO}")
    if MODO_VOZ:
        print("MILLER: Reconocimiento de voz LOCAL activado." if escuchador is not None else "MILLER: Reconocimiento de voz no disponible.")
    else:
        print("MILLER: Modo texto activado.")
    if MODO_VOZ and USAR_PALABRA_ACTIVACION:
        palabra = obtener_palabra_activacion(activador)
        print(f"MILLER: Palabra de activación obligatoria: '{palabra}'.")
        print("MILLER: Las variaciones reconocidas por el activador también son válidas.")
    if getattr(cerebro, "iniciativa", None) is not None:
        print("MILLER: Iniciativa activa: pediré permiso para hablar ('Miller, adelante' para autorizar).")
    print(f"MILLER: {configuracion.MENSAJE_ESPERA}\n")
    try:
        if MODO_VOZ and escuchador is not None:
            procesar_voz(cerebro, escuchador, hablador, activador)
        else:
            if MODO_VOZ:
                print("MILLER: Cambiando automáticamente a modo texto.\n")
            procesar_texto(cerebro, hablador)
    except KeyboardInterrupt:
        print("\nMILLER: Interrupción detectada.")
    except Exception as error:
        print(f"\nMILLER: Error general.\n[PRINCIPAL] {error}")
    finally:
        if not TERMINADO.is_set():
            TERMINADO.set()                      # el cierre ya está en curso: el vigilante no lo repite
            cerrar_miller(escuchador, hablador, activador, cerebro)
if __name__ == "__main__":
    main()
