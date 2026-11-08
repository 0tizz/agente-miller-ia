"""MILLER · Administrador central de comandos. EL CEREBRO DECIDE. COMANDOS DELEGA. LOS MÓDULOS EJECUTAN."""
import os
import re
import time
from pathlib import Path
from utilidades import seguridad
from utilidades import acceso, cuota
from utilidades import navegacion
from utilidades.calculadora import calcular
from utilidades import bateria as _bateria, ventanas as _ventanas
try:
    from utilidades.ecualizador import Ecualizador, PERFILES as _PERFILES_EQ, SINONIMOS_BANDA as _BANDAS_EQ
except Exception as _error_eq:
    Ecualizador, _PERFILES_EQ, _BANDAS_EQ = None, {}, {}
    print(f"[COMANDOS] Ecualizador no disponible: {_error_eq}")
try:
    from utilidades.alarmas import GestorAlarmas
except Exception as _error_alarmas:
    GestorAlarmas = None
    print(f"[COMANDOS] Alarmas no disponibles: {_error_alarmas}")
import configuracion
from configuracion import RUTA_AUDIOS
from utilidades.sistema import Sistema
from audio.reproductor import Reproductor
from utilidades.rutina import RutinaMatutina
try:
    from utilidades.consulta_internet import ConsultorInternet
except Exception as _error_internet:
    ConsultorInternet = None
    print(f"[COMANDOS] Consultas a internet no disponibles: {_error_internet}")
try:
    from utilidades.descargar_musica import descargador_musica
except Exception as _error_descarga:
    descargador_musica = None
    print(f"[COMANDOS] Descarga de música no disponible: {_error_descarga}")
try:
    from utilidades.probador import ProbadorModulos
except Exception as _error_probador:
    ProbadorModulos = None
    print(f"[COMANDOS] Probador de módulos no disponible: {_error_probador}")
try:
    from audio.supervisor_biblioteca import SupervisorBiblioteca, ConfigSupervisor
except Exception as _error_supervisor:  # MILLER sigue funcionando sin supervisor
    SupervisorBiblioteca = ConfigSupervisor = None
    print(f"[COMANDOS] Supervisor de biblioteca no disponible: {_error_supervisor}")

class Comandos:
    """Coordina las acciones de MILLER sin duplicar lógica."""
    ALIAS = {
        **dict.fromkeys((
            "RUTINA", "RUTINA_MANANA", "RUTINA_MAÑANA",
            "RUTINA_MATUTINA", "RUTINA_MATUTINA_COMPLETA",
            "EJECUTAR_RUTINA", "EJECUTAR_RUTINA_MATUTINA",
            "INFORME_MATUTINO", "INFORME_MANANA", "INFORME_MAÑANA",
        ), "RUTINA_MATUTINA"),
        **dict.fromkeys((
            "PAUSAR_MUSICA", "PAUSA_MUSICA", "PAUSA_AUDIO",
            "PAUSAR", "PAUSA",
        ), "PAUSAR_AUDIO"),
        **dict.fromkeys((
            "CONTINUAR_MUSICA", "CONTINUAR", "REANUDAR_AUDIO",
            "REANUDAR_MUSICA", "REANUDAR", "RESUMIR_AUDIO",
            "RESUMIR_MUSICA",
        ), "CONTINUAR_AUDIO"),
        **dict.fromkeys((
            "DETENER_MUSICA", "DETENER", "PARAR_AUDIO",
            "PARAR_MUSICA", "PARAR", "STOP_AUDIO", "STOP",
        ), "DETENER_AUDIO"),
        **dict.fromkeys((
            "SIGUIENTE_MUSICA", "SIGUIENTE_CANCION", "SIGUIENTE",
            "PASAR_CANCION", "PASAR_MUSICA", "SALTAR_CANCION",
            "SALTAR_MUSICA", "SKIP",
        ), "SIGUIENTE_AUDIO"),
        **dict.fromkeys((
            "ANTERIOR_MUSICA", "ANTERIOR_CANCION", "ANTERIOR",
            "CANCION_ANTERIOR", "VOLVER_CANCION", "VOLVER_MUSICA",
        ), "ANTERIOR_AUDIO"),
        **dict.fromkeys((
            "SUBIR_VOLUMEN", "BAJAR_VOLUMEN", "CAMBIAR_VOLUMEN",
            "CONSULTAR_VOLUMEN", "VOLUMEN",
        ), "VOLUMEN_AUDIO"),
        **dict.fromkeys((
            "ESTADO_REPRODUCTOR", "ESTADO_MUSICA",
            "ESTADO_AUDIO", "ESTADO_PLAY",
        ), "ESTADO_AUDIO"),
        **dict.fromkeys((
            "LISTAR_MUSICA", "MOSTRAR_MUSICA", "LISTAR_CANCIONES",
            "MOSTRAR_CANCIONES", "VER_CANCIONES",
        ), "LISTAR_AUDIOS"),
        **dict.fromkeys((
            "AGREGAR_MUSICA_COLA", "AGREGAR_CANCION_COLA",
            "AÑADIR_COLA_AUDIO", "ANADIR_COLA_AUDIO",
            "AÑADIR_MUSICA_COLA", "ANADIR_MUSICA_COLA",
            "AGREGAR_LISTA_REPRODUCCION", "AÑADIR_LISTA_REPRODUCCION",
            "AGREGAR_CANCION_LISTA", "AÑADIR_CANCION_LISTA",
        ), "AGREGAR_COLA_AUDIO"),
        **dict.fromkeys((
            "VER_COLA_AUDIO", "COLA_AUDIO", "MOSTRAR_COLA", "VER_COLA",
            "MOSTRAR_LISTA_REPRODUCCION", "VER_LISTA_REPRODUCCION",
            "LISTAR_LISTA_REPRODUCCION", "MOSTRAR_LISTA",
        ), "MOSTRAR_COLA_AUDIO"),
        **dict.fromkeys((
            "VACIAR_COLA_AUDIO", "LIMPIAR_COLA", "VACIAR_COLA",
            "LIMPIAR_LISTA_REPRODUCCION", "VACIAR_LISTA_REPRODUCCION",
            "BORRAR_LISTA_REPRODUCCION",
        ), "LIMPIAR_COLA_AUDIO"),
        **dict.fromkeys((
            "QUITAR_DE_COLA_AUDIO", "ELIMINAR_DE_COLA_AUDIO",
            "QUITAR_CANCION_COLA", "ELIMINAR_CANCION_COLA",
            "QUITAR_DE_LISTA_REPRODUCCION",
            "ELIMINAR_DE_LISTA_REPRODUCCION",
            "QUITAR_CANCION_LISTA", "ELIMINAR_CANCION_LISTA",
        ), "QUITAR_COLA_AUDIO"),
        **dict.fromkeys((
            "ALEATORIO_MUSICA", "ALEATORIO", "SHUFFLE_AUDIO", "SHUFFLE",
        ), "ALEATORIO_AUDIO"),
        **dict.fromkeys((
            "REPETIR_MUSICA", "REPETIR", "LOOP_AUDIO", "LOOP",
        ), "REPETIR_AUDIO"),
        **dict.fromkeys((
            "REPRODUCIR_CANCION", "REPRODUCIR", "PLAY", "PLAY_AUDIO",
            "PLAY_MUSICA", "PONER_CANCION", "PONER_AUDIO",
        ), "REPRODUCIR_AUDIO"),
        "PONER_MUSICA": "REPRODUCIR_MUSICA",
    }
    SITIOS = {
        "google": "https://www.google.com",
        "bing": "https://www.bing.com",
        "yahoo": "https://www.yahoo.com",
        "duckduckgo": "https://duckduckgo.com",
        "youtube": "https://www.youtube.com",
        "netflix": "https://www.netflix.com",
        "twitch": "https://www.twitch.tv",
        "prime video": "https://www.primevideo.com",
        "disney plus": "https://www.disneyplus.com",
        "disney+": "https://www.disneyplus.com",
        "facebook": "https://www.facebook.com",
        "instagram": "https://www.instagram.com",
        "tiktok": "https://www.tiktok.com",
        "twitter": "https://twitter.com",
        "x": "https://x.com",
        "reddit": "https://www.reddit.com",
        "linkedin": "https://www.linkedin.com",
        "pinterest": "https://www.pinterest.com",
        "gmail": "https://mail.google.com",
        "google drive": "https://drive.google.com",
        "google maps": "https://maps.google.com",
        "google docs": "https://docs.google.com",
        "google sheets": "https://sheets.google.com",
        "google meet": "https://meet.google.com",
        "github": "https://github.com",
        "gitlab": "https://gitlab.com",
        "stackoverflow": "https://stackoverflow.com",
        "npm": "https://www.npmjs.com",
        "pypi": "https://pypi.org",
        "codepen": "https://codepen.io",
        "replit": "https://replit.com",
        "chatgpt": "https://chatgpt.com",
        "claude": "https://claude.ai",
        "gemini": "https://gemini.google.com",
        "perplexity": "https://www.perplexity.ai",
        "spotify": "https://open.spotify.com",
        "soundcloud": "https://soundcloud.com",
        "deezer": "https://www.deezer.com",
        "whatsapp": "https://web.whatsapp.com",
        "telegram": "https://web.telegram.org",
        "discord": "https://discord.com/app",
        "amazon": "https://www.amazon.com",
        "mercado libre": "https://www.mercadolibre.com.co",
        "ebay": "https://www.ebay.com",
        "wikipedia": "https://www.wikipedia.org",
        "quora": "https://www.quora.com",
        "bbc": "https://www.bbc.com",
        "cnn": "https://www.cnn.com",
        "outlook": "https://outlook.live.com",
        "onedrive": "https://onedrive.live.com",
        "office": "https://www.office.com",
        "canva": "https://www.canva.com",
        "figma": "https://www.figma.com",
    }
    APLICACIONES = {
        "calculadora": "calculadora",
        "bloc de notas": "bloc de notas",
        "bloc": "bloc",
        "explorador de archivos": "explorador de archivos",
        "explorador": "explorador",
    }
    PATRONES_CARPETA_CREAR = (
        r"crea una carpeta llamada (.+)", r"crear una carpeta llamada (.+)",
        r"crea carpeta llamada (.+)", r"crear carpeta llamada (.+)",
        r"crea una carpeta (.+)", r"crear una carpeta (.+)",
        r"crea carpeta (.+)", r"crear carpeta (.+)",
    )
    PATRONES_CARPETA_ABRIR = (
        r"abre la carpeta (.+)", r"abrir la carpeta (.+)",
        r"abre carpeta (.+)", r"abrir carpeta (.+)",
    )
    PATRONES_COLA = (
        r"(?:agrega|añade|anade|agregar|añadir|anadir)\s+(?:la\s+)?cancion\s+(.+?)\s+(?:a|en)\s+(?:la\s+)?cola",
        r"(?:agrega|añade|anade|agregar|añadir|anadir)\s+(.+?)\s+(?:a|en)\s+(?:la\s+)?cola",
        r"(?:pon|poner|mete|meter|introduce|introducir)\s+(.+?)\s+(?:en|a)\s+(?:la\s+)?cola",
        r"(?:agrega|añade|anade|agregar|añadir|anadir)\s+(?:a|en)\s+(?:la\s+)?cola\s+(.+)",
        r"(?:pon|poner|mete|meter|introduce|introducir)\s+(?:en|a)\s+(?:la\s+)?cola\s+(.+)",
    )
    PATRONES_AUDIO = (
        r"reproduce la canción (.+)", r"reproduce una canción (.+)",
        r"reproduce el audio (.+)", r"reproduce la música (.+)",
        r"reproduce música de (.+)", r"reproduce (.+)",
        r"reproducir la canción (.+)", r"reproducir una canción (.+)",
        r"reproducir el audio (.+)", r"reproducir la música (.+)",
        r"reproducir música de (.+)", r"reproducir (.+)",
        r"pon la canción (.+)", r"pon una canción (.+)",
        r"pon el audio (.+)", r"pon la música (.+)",
        r"pon música de (.+)", r"pon (.+)",
        r"quiero escuchar la canción (.+)",
        r"quiero escuchar el audio (.+)",
        r"quiero escuchar la música (.+)", r"quiero escuchar (.+)",
        r"escucha (.+)", r"escuchar (.+)",
        r"ponme la canción (.+)", r"ponme una canción (.+)",
        r"ponme música de (.+)", r"ponme (.+)", r"pon música (.+)",
        r"quiero oír (.+)", r"quiero oír la canción (.+)",
    )
    PATRONES_QUITAR_COLA = (
        r"(?:quita|quitar|quitame|elimina|eliminar|borra|borrar|saca|sacar)\s+(?:la\s+|el\s+)?(?:cancion\s+|audio\s+|pista\s+)?(.+?)\s+(?:de|en)\s+(?:la\s+)?(?:cola|lista(?:\s+de\s+reproduccion)?)",
        r"(?:quita|quitar|quitame|elimina|eliminar|borra|borrar|saca|sacar)\s+(?:de|en)\s+(?:la\s+)?(?:cola|lista(?:\s+de\s+reproduccion)?)\s+(.+)",
    )
    NUMEROS = {
        "cero": 0, "uno": 1, "una": 1, "dos": 2, "tres": 3,
        "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
        "ocho": 8, "nueve": 9, "diez": 10, "once": 11,
        "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
        "dieciséis": 16, "dieciseis": 16, "diecisiete": 17,
        "dieciocho": 18, "diecinueve": 19, "veinte": 20,
        "treinta": 30, "cuarenta": 40, "cincuenta": 50,
        "sesenta": 60, "setenta": 70, "ochenta": 80,
        "noventa": 90, "cien": 100,
    }
    FRASES_SUBIR = (
        "sube el volumen", "subir el volumen", "aumenta el volumen",
        "aumentar el volumen", "más volumen", "mas volumen",
        "sube volumen", "subir volumen", "aumenta volumen",
        "aumentar volumen", "sube la música", "subir la música",
        "aumenta la música", "aumentar la música",
    )
    FRASES_BAJAR = (
        "baja el volumen", "bajar el volumen", "disminuye el volumen",
        "disminuir el volumen", "menos volumen", "baja volumen",
        "bajar volumen", "disminuye volumen", "disminuir volumen",
        "baja la música", "bajar la música", "disminuye la música",
        "disminuir la música",
    )
    def __init__(self):
        self.sistema = Sistema()
        # La pista guardada no suena al crearse: principal.py la continúa cuando la ventana ya está abierta.
        self.reproductor = Reproductor(RUTA_AUDIOS, restaurar_pista=not getattr(configuracion, "MUSICA_TRAS_VENTANA", True))
        try:
            self.reproductor.DURACION_FADE_VOLUMEN = max(0.0, float(getattr(configuracion, "VOLUMEN_DURACION_FUNDIDO", 0.9)))
        except (TypeError, ValueError):
            pass
        self.rutina = RutinaMatutina()
        self.ultimo_objetivo = None             # último programa o archivo abierto o nombrado ("ciérralo")
        self.minimizar_propia = None            # lo conecta principal.py: minimiza la ventana de MILLER
        self.ecualizador = None
        if Ecualizador is not None:
            try:
                self.ecualizador = Ecualizador(configuracion.RUTA_DATOS / "ecualizador.json",
                                               configuracion.RUTA_DATOS / "cache" / "ecualizador",
                                               ffmpeg=self.reproductor._ruta_ffmpeg())
                self.reproductor.ecualizador = self.ecualizador
                self.ecualizador.al_listo = lambda original, _copia: self.reproductor.ecualizada_lista(original)
            except Exception as error:
                print(f"[COMANDOS] Ecualizador no disponible: {error}")
                self.ecualizador = None
        self._cerrado = False
        self.supervisor = None
        self._limpieza_por_confirmar = None
        self.probador = ProbadorModulos() if ProbadorModulos else None
        self.internet = ConsultorInternet() if ConsultorInternet else None
        self.alarmas = None
        if GestorAlarmas is not None:
            try:
                self.alarmas = GestorAlarmas(configuracion.RUTA_DATOS / "alarmas.json")
                self.alarmas.iniciar()
            except Exception as error:
                print(f"[COMANDOS] No se pudieron iniciar las alarmas: {error}")
                self.alarmas = None
        self._iniciar_supervisor()
        try:
            from utilidades import acceso
            acceso.al_cambiar_modo(self._supervisor_segun_modo)
        except Exception as error:
            print(f"[COMANDOS] No se pudo seguir el modo de acceso: {error}")
    def _supervisor_segun_modo(self, modo):
        """El supervisor de la biblioteca es PRO: con llave PRO trabaja; en FREE y NIÑOS se detiene."""
        if modo == "pro":
            if getattr(self, "supervisor", None) is None:
                self._iniciar_supervisor()
        else:
            self._detener_supervisor()
    def _iniciar_supervisor(self):
        """Arranca el supervisor en segundo plano (solo en modo PRO). Si falla, MILLER sigue igual."""
        if SupervisorBiblioteca is None or not getattr(configuracion, "SUPERVISOR_ACTIVO", True):
            return
        try:
            from utilidades import acceso
            if acceso.modo() != "pro":
                return
        except Exception:
            return
        try:
            config = ConfigSupervisor(
                modo=getattr(configuracion, "SUPERVISOR_MODO", "observar"),
                intervalo_ciclo=float(getattr(configuracion, "SUPERVISOR_INTERVALO", 300)),
                verificacion_profunda=bool(getattr(configuracion, "SUPERVISOR_VERIFICACION_PROFUNDA", True)),
                reparacion_automatica=bool(getattr(configuracion, "SUPERVISOR_REPARACION_AUTOMATICA", True)),
                ruta_ffmpeg=getattr(configuracion, "SUPERVISOR_FFMPEG", None),
                eliminacion_automatica=bool(getattr(configuracion, "SUPERVISOR_ELIMINACION_AUTOMATICA", False)),
            )
            plan = getattr(configuracion, "SUPERVISOR_PLAN_ELIMINACION", None)
            if isinstance(plan, dict):
                config.plan_eliminacion.update(plan)
            supervisor = SupervisorBiblioteca(self.reproductor, config=config)
            if supervisor.iniciar():
                self.supervisor = supervisor
        except Exception as error:
            print(f"[COMANDOS] No se pudo iniciar el supervisor de biblioteca: {error}")
            self.supervisor = None
    def _detener_supervisor(self):
        supervisor, self.supervisor = getattr(self, "supervisor", None), None
        if supervisor is None:
            return
        try:
            supervisor.detener()
        except Exception as error:
            print(f"[COMANDOS] Error deteniendo el supervisor: {error}")
    MAX_NOMBRES_RESPUESTA = 5
    SEGUNDOS_CONFIRMAR_LIMPIEZA = 90
    NOMBRES_CATEGORIA = {"danados": "dañados", "duplicados": "duplicados", "no_compatibles": "no compatibles",
                         "adulterados": "adulterados"}
    @staticmethod
    def _normalizar_biblioteca(texto):
        import unicodedata
        texto = unicodedata.normalize("NFD", str(texto or "").lower())
        texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9ñ ]+", " ", texto)).strip()
    @staticmethod
    def _n(cantidad, singular, plural):
        return f"{cantidad} {singular if cantidad == 1 else plural}"
    @staticmethod
    def _sin_extension(nombre):
        return re.sub(r"\.[A-Za-z0-9]{2,5}$", "", str(nombre))
    def _enumerar(self, nombres):
        nombres = [self._sin_extension(n) for n in nombres]
        if len(nombres) <= self.MAX_NOMBRES_RESPUESTA:
            return ", ".join(nombres)
        resto = len(nombres) - self.MAX_NOMBRES_RESPUESTA
        return ", ".join(nombres[:self.MAX_NOMBRES_RESPUESTA]) + f" y {resto} más"
    def _sin_supervisor(self):
        if self.supervisor is None:
            return "Supervisor fuera de línea. Diga: activa el supervisor."
        return None
    def _informe_biblioteca(self):
        """Devuelve (informe, mensaje_si_no_hay_informe)."""
        aviso = self._sin_supervisor()
        if aviso:
            return None, aviso
        informe = self.supervisor.obtener_informe()
        if not informe:
            return None, "Primera revisión en curso. Espere unos segundos."
        # Quitar del informe lo que el propio ciclo ya apartó, reparó o eliminó.
        tratados = {a.get("archivo") for a in informe.get("acciones", [])}
        if tratados:
            informe["danados"] = [d for d in informe.get("danados", []) if d.get("archivo") not in tratados]
            grupos = []
            for g in informe.get("duplicados", []):
                restantes = [n for n in g.get("duplicados", []) if n not in tratados]
                if restantes:
                    grupos.append({**g, "duplicados": restantes})
            informe["duplicados"] = grupos
            informe["no_compatibles"] = [n for n in informe.get("no_compatibles", []) if n not in tratados]
        return informe, None
    def _categorias_de_texto(self, texto):
        t = self._normalizar_biblioteca(texto)
        cats = set()
        if re.search(r"danad|corrupt|rot[oa]s?\b|ilegible", t):
            cats.add("danados")
        if re.search(r"duplicad|repetid|copias", t):
            cats.add("duplicados")
        if re.search(r"no (son |es |)compatible|incompatible", t):
            cats.add("no_compatibles")
        if re.search(r"adulterad|disfrazad|falsa|falso|incongruen|extension|mal etiquetad", t):
            cats.add("adulterados")
        return cats or {"danados", "duplicados"}
    def _texto_categorias(self, cats):
        nombres = [self.NOMBRES_CATEGORIA[c] for c in self.supervisor.CATEGORIAS_LIMPIEZA if c in cats]
        return nombres[0] if len(nombres) == 1 else ", ".join(nombres[:-1]) + " y " + nombres[-1]
    def estado_biblioteca(self):
        informe, aviso = self._informe_biblioteca()
        if aviso:
            return aviso
        t = informe.get("totales", {})
        danados = informe.get("danados", [])
        duplicados = informe.get("duplicados", [])
        no_compat = informe.get("no_compatibles", [])
        partes = [f"Biblioteca: {t.get('audio_soportado', 0)} pistas."]
        partes.append(f"{self._n(len(danados), 'dañada', 'dañadas')}." if danados else "Sin daños.")
        if duplicados:
            copias = sum(len(d.get("duplicados", [])) for d in duplicados)
            partes.append(f"{self._n(copias, 'duplicado', 'duplicados')}.")
        adulterados = informe.get("adulterados", [])
        if adulterados:
            partes.append(f"{self._n(len(adulterados), 'adulterado', 'adulterados')}.")
        if informe.get("reparaciones"):
            partes.append(f"{self._n(len(informe['reparaciones']), 'reparado', 'reparados')}.")
        if no_compat:
            partes.append(f"{self._n(len(no_compat), 'no compatible', 'no compatibles')}.")
        if informe.get("advertencias"):
            partes.append(f"{self._n(len(informe['advertencias']), 'advertencia', 'advertencias')}.")
        if t.get("en_cuarentena"):
            partes.append(f"{self._n(t['en_cuarentena'], 'archivo', 'archivos')} en cuarentena.")
        if danados or duplicados:
            partes.append("Recomiendo: limpia la biblioteca.")
        elif adulterados:
            partes.append("Recomiendo: repara la biblioteca.")
        return " ".join(partes)
    def listar_danados_biblioteca(self):
        informe, aviso = self._informe_biblioteca()
        if aviso:
            return aviso
        danados = [d.get("archivo", "") for d in informe.get("danados", [])]
        if not danados:
            return "Sin canciones dañadas."
        return f"{self._n(len(danados), 'dañada', 'dañadas')}: {self._enumerar(danados)}."
    def listar_duplicados_biblioteca(self):
        informe, aviso = self._informe_biblioteca()
        if aviso:
            return aviso
        grupos = informe.get("duplicados", [])
        posibles = informe.get("posibles_duplicados", [])
        if not grupos and not posibles:
            return "Sin duplicados."
        partes = []
        if grupos:
            detalle = "; ".join(
                f"{self._sin_extension(g.get('conservar'))}: copia {self._enumerar(g.get('duplicados', []))}"
                for g in grupos[:self.MAX_NOMBRES_RESPUESTA])
            partes.append(f"{self._n(len(grupos), 'canción duplicada', 'canciones duplicadas')}. {detalle}.")
        if posibles:
            partes.append(f"{self._n(len(posibles), 'título repetido', 'títulos repetidos')} con archivos distintos.")
        return " ".join(partes)
    def listar_no_compatibles_biblioteca(self):
        informe, aviso = self._informe_biblioteca()
        if aviso:
            return aviso
        archivos = informe.get("no_compatibles", [])
        if not archivos:
            return "Todos los formatos son compatibles."
        return f"{self._n(len(archivos), 'no compatible', 'no compatibles')}: {self._enumerar(archivos)}."
    def listar_cuarentena(self):
        aviso = self._sin_supervisor()
        if aviso:
            return aviso
        entradas = self.supervisor.listar_cuarentena()
        if not entradas:
            return "Cuarentena vacía."
        return (f"Cuarentena: {self._n(len(entradas), 'archivo', 'archivos')}. "
                f"{self._enumerar([e.get('nombre', '') for e in entradas])}.")
    def estado_supervisor(self):
        aviso = self._sin_supervisor()
        if aviso:
            return aviso
        e = self.supervisor.obtener_estado()
        if not e.get("activo"):
            return "Supervisor detenido."
        partes = ["Supervisor " + ("en pausa." if e.get("pausado") else "operativo.")]
        partes.append("Modo observación." if e.get("modo") == "observar" else "Modo cuarentena.")
        if e.get("reparacion_automatica"):
            partes.append("Reparación automática activa.")
        partes.append("Eliminación programada activa." if e.get("eliminacion_automatica") else "Eliminación programada inactiva.")
        partes.append(f"{self._n(e.get('ciclos', 0), 'revisión', 'revisiones')}.")
        generado = (self.supervisor.obtener_informe() or {}).get("generado", "")
        if len(generado) >= 16:
            partes.append(f"Última a las {generado[11:16]}.")
        if e.get("en_cuarentena"):
            partes.append(f"{self._n(e['en_cuarentena'], 'archivo', 'archivos')} en cuarentena.")
        return " ".join(partes)
    def resultado_limpieza(self):
        aviso = self._sin_supervisor()
        if aviso:
            return aviso
        r = self.supervisor.obtener_ultima_limpieza()
        if not r:
            return "Sin operaciones en esta sesión."
        if r.get("estado") == "en_curso":
            return "Operación en curso."
        if r.get("estado") == "fallida":
            return "Operación fallida. Reintente en unos segundos."
        acciones = r.get("acciones", [])
        if not acciones:
            texto = "Operación completada. Sin cambios."
        else:
            grupos = {}
            for a in acciones:
                grupos.setdefault(a.get("accion"), []).append(a.get("archivo", ""))
            partes = []
            reparados = grupos.get("convertido", []) + grupos.get("extension_corregida", [])
            if reparados:
                partes.append(f"{self._n(len(reparados), 'reparado', 'reparados')}: {self._enumerar(reparados)}")
            if grupos.get("cuarentena"):
                partes.append(f"{self._n(len(grupos['cuarentena']), 'a cuarentena', 'a cuarentena')}: "
                              f"{self._enumerar(grupos['cuarentena'])}")
            if grupos.get("eliminado"):
                partes.append(f"{self._n(len(grupos['eliminado']), 'eliminado', 'eliminados')} por plan")
            texto = "; ".join(partes) + "."
            texto = texto[0].upper() + texto[1:]
        if r.get("omitidos_por_uso"):
            texto += f" {r['omitidos_por_uso']} omitidos por estar en uso."
        return texto
    def ayuda_biblioteca(self):
        return ("Biblioteca. Consultas: estado, dañadas, duplicadas, adulteradas, no compatibles, "
                "cuarentena, plan de eliminación, estado del supervisor. "
                "Órdenes: revisa, repara, limpia, restaura, vacía la cuarentena, pausa o activa el supervisor. "
                "Papelera: borra una canción, qué hay en la papelera, vacía la papelera.")
    def listar_adulterados(self):
        informe, aviso = self._informe_biblioteca()
        if aviso:
            return aviso
        adulterados = informe.get("adulterados", [])
        reparados = informe.get("reparaciones", [])
        if not adulterados:
            texto = "Sin archivos adulterados."
            if reparados:
                texto += f" {self._n(len(reparados), 'reparado', 'reparados')} en la última revisión."
            return texto
        ejemplo = adulterados[0]
        return (f"{self._n(len(adulterados), 'adulterado', 'adulterados')}: "
                f"{self._enumerar([a['archivo'] for a in adulterados])}. "
                f"Ejemplo: extensión {ejemplo['extension']}, contenido {ejemplo['contenido']}.")
    def reparar_biblioteca(self):
        aviso = self._sin_supervisor()
        if aviso:
            return aviso
        self.supervisor.reanudar()
        if not self.supervisor.solicitar_limpieza({"adulterados"}):
            return "Negativo. Reparación no iniciada."
        return "Afirmativo. Reparación en curso. Originales a cuarentena."
    def plan_eliminacion(self):
        aviso = self._sin_supervisor()
        if aviso:
            return aviso
        plan = self.supervisor.plan_eliminacion()
        if not plan:
            return "Cuarentena vacía. Nada programado."
        programados = [p for p in plan if p["dias_restantes"] is not None]
        nunca = len(plan) - len(programados)
        if not programados:
            return f"{self._n(len(plan), 'archivo', 'archivos')} en cuarentena. Ninguno programado."
        proximo = programados[0]
        dias = proximo["dias_restantes"]
        cuando = "hoy" if dias < 1 else ("mañana" if dias < 2 else f"en {int(dias)} días")
        texto = (f"{self._n(len(programados), 'eliminación programada', 'eliminaciones programadas')}. "
                 f"Próxima: {self._sin_extension(proximo['nombre'])}, {cuando}.")
        if nunca:
            texto += f" {self._n(nunca, 'archivo protegido', 'archivos protegidos')} de borrado automático."
        return texto
    def vaciar_cuarentena(self, texto=""):
        aviso = self._sin_supervisor()
        if aviso:
            return aviso
        entradas = self.supervisor.listar_cuarentena()
        t = self._normalizar_biblioteca(texto)
        cats = None
        if re.search(r"danad|defectuos|corrupt|rot[oa]s?\b", t):
            cats = {"danados"}
        elif re.search(r"duplicad|repetid|copias", t):
            cats = {"duplicados"}
        elif re.search(r"adulterad|originales|reparad", t):
            cats = {"adulterados"}
        elif "papelera" in t:
            cats = {"papelera"}
        if cats:
            entradas = [e for e in entradas if e.get("categoria") in cats]
        if not entradas:
            return "Sin archivos de ese tipo en cuarentena."
        self._limpieza_por_confirmar = ({"tipo": "vaciar", "categorias": cats}, time.monotonic())
        return (f"Eliminación definitiva de {self._n(len(entradas), 'archivo', 'archivos')}. "
                "Irreversible. ¿Confirma, señor?")

    _RE_LIMPIAR_BORRAR = re.compile(
        r"\b(miller|por favor|borra|borrar|borrame|borrala|elimina|eliminar|eliminame|eliminala|suprime|suprimir|"
        r"quita|quitar|quitame|saca|sacar|tira|tirar|manda|mandar|mueve|mover|envia|enviar|"
        r"a la papelera|papelera|de la biblioteca|biblioteca|de mi musica|la cancion|el tema|cancion|tema|pista|"
        r"audio|archivo)\b")
    _RE_ACTUAL = re.compile(r"^(esta|este|esto|la actual|actual|la que suena|lo que suena|la que esta sonando|"
                            r"que esta sonando|que suena|la de ahora|ahora)$")
    SIMILITUD_MINIMA_BORRAR = 0.60
    def _extraer_cancion_borrar(self, texto):
        t = self._RE_LIMPIAR_BORRAR.sub(" ", self._normalizar_biblioteca(texto))
        t = re.sub(r"^(?:la|el|los|las|una|un|de|del)\s+", "", re.sub(r"\s+", " ", t).strip())
        return t.strip()
    def _resolver_cancion_borrar(self, consulta):
        """Devuelve (ruta, motivo_si_no). Exige coincidencia clara: nunca mueve 'la más parecida' a ciegas."""
        rep = self.reproductor
        if not consulta or self._RE_ACTUAL.match(consulta):
            actual = rep.obtener_ruta_actual() if rep else None
            return (actual, None) if actual else (None, "¿Qué canción borro, señor?")
        from difflib import SequenceMatcher
        canciones = rep.obtener_canciones()
        q = self._normalizar_biblioteca(consulta)
        puntuadas = []
        for p in canciones:
            n = self._normalizar_biblioteca(p.stem)
            puntos = 1.0 if n == q else 0.9 if q in n else SequenceMatcher(None, q, n).ratio()
            puntuadas.append((puntos, p))
        puntuadas.sort(key=lambda x: x[0], reverse=True)
        if not puntuadas or puntuadas[0][0] < self.SIMILITUD_MINIMA_BORRAR:
            return None, f"'{consulta}' no está en la biblioteca."
        mejores = [p for puntos, p in puntuadas if puntos >= puntuadas[0][0] - 0.001]
        if len(mejores) > 1 and puntuadas[0][0] < 1.0:
            return None, (f"{len(mejores)} coincidencias: {self._enumerar([p.name for p in mejores])}. "
                          "Precise el nombre, señor.")
        return mejores[0], None
    def _liberar_para_borrar(self, ruta):
        """Si la canción suena o está en cola, la suelta antes de moverla (el reproductor nunca pierde el archivo en…"""
        rep = self.reproductor
        if rep is None:
            return
        try:
            for pista in list(rep.obtener_cola()):
                if Path(pista) == Path(ruta):
                    rep.quitar_de_cola(Path(pista).name)
        except Exception as error:
            print(f"[PAPELERA] No se pudo retirar de la cola: {error}")
        try:
            if rep.obtener_ruta_actual() and Path(rep.obtener_ruta_actual()) == Path(ruta):
                sonaba = rep.esta_reproduciendo()
                otras = [p for p in rep.obtener_canciones() if Path(p) != Path(ruta)]
                if sonaba and otras:
                    rep.siguiente()
                    if rep.obtener_ruta_actual() and Path(rep.obtener_ruta_actual()) == Path(ruta):
                        rep.detener()
                else:
                    rep.detener()
                if rep.obtener_ruta_actual() and Path(rep.obtener_ruta_actual()) == Path(ruta):
                    try:
                        import pygame
                        pygame.mixer.music.unload()       # Windows libera el archivo
                    except Exception:
                        pass
                    rep.cancion_actual = None
        except Exception as error:
            print(f"[PAPELERA] No se pudo soltar la canción actual: {error}")
    def _mover_a_papelera_sin_supervisor(self, ruta):
        destino_dir = Path(RUTA_AUDIOS) / "cuarentena" / "papelera"
        destino_dir.mkdir(parents=True, exist_ok=True)
        destino = destino_dir / f"{time.strftime('%Y%m%d-%H%M%S')}_{Path(ruta).name}"
        os.replace(ruta, destino)
        return {"nombre": Path(ruta).name}
    def borrar_cancion(self, texto=""):
        """Miller, borra La Resaca" -> la canción sale de audios/ y va a audios/cuarentena/papelera/."""
        if self.reproductor is None:
            return "Reproductor fuera de línea."
        consulta = self._extraer_cancion_borrar(texto)
        ruta, aviso = self._resolver_cancion_borrar(consulta)
        if aviso:
            return aviso
        nombre = self._sin_extension(Path(ruta).name)
        self._liberar_para_borrar(ruta)
        entrada = None
        for intento in range(6):                      # el sistema puede tardar en soltar el archivo
            try:
                if self.supervisor is not None:
                    entrada = self.supervisor.mover_a_papelera(ruta)
                else:
                    entrada = self._mover_a_papelera_sin_supervisor(ruta)
            except Exception as error:
                print(f"[PAPELERA] Error moviendo {nombre}: {error}")
                entrada = None
            if entrada or not Path(ruta).exists():
                break
            time.sleep(0.3)
        try:
            self.reproductor.actualizar_lista()
        except Exception:
            pass
        if not entrada:
            return f"Negativo. {nombre} está en uso. Reintente en unos segundos."
        dias = (getattr(configuracion, "SUPERVISOR_PLAN_ELIMINACION", {}) or {}).get("papelera")
        plazo = (f" Recuperable durante {dias} días." if dias and self.supervisor is not None
                 and getattr(configuracion, "SUPERVISOR_ELIMINACION_AUTOMATICA", False) else " Recuperable.")
        return f"Afirmativo. {nombre} a la papelera.{plazo} Para deshacer diga: restaura {nombre}."
    def musica_del_dia(self, texto=""):
        """"¿Qué escuché hoy / ayer?": sección diaria de la memoria musical."""
        cuando = "ayer" if "ayer" in str(texto) else "hoy"
        try:
            r = self.reproductor.resumen_dia(cuando)
        except Exception as error:
            print(f"[COMANDOS] Error leyendo el diario musical: {error}")
            r = None
        if not r:
            return f"Sin música registrada {cuando}, señor."
        texto = (f"{cuando.capitalize()}: {self._n(r['reproducciones'], 'canción', 'canciones')}, "
                 f"{round(r['minutos'])} minutos.")
        if r["top"]:
            texto += f" Más escuchada: {r['top'][0]}."
        if r["saltos"]:
            texto += f" {self._n(r['saltos'], 'salto', 'saltos')}."
        return texto
    # ------------------------------------------------ navegador, explorador, cálculo y alarmas
    _RE_BUSCAR = re.compile(r"^(?:miller\s+)?(?:por favor\s+)?(?:busca|buscar|buscame|busque|encuentra|encuentrame|localiza)\s+")

    def buscar_en_navegador(self, texto=""):
        """"Busca netflix en el navegador", "busca recetas en youtube con brave"."""
        t = navegacion.plano(texto)
        navegador = navegacion.detectar_navegador(t)
        motor = "youtube" if "youtube" in t else "bing" if re.search(r"\ben bing\b", t) else "google"
        consulta = self._RE_BUSCAR.sub("", t)
        consulta = re.sub(r"\s+(?:en|con)\s+(?:youtube|google|bing|internet)\b", " ", consulta)
        consulta = navegacion.quitar_navegador(consulta)
        consulta = re.sub(r"^(?:en (?:el )?navegador|en youtube|en google)\s+", "", consulta).strip()
        if not consulta:
            return "¿Qué busco, señor?"
        if motor == "google" and consulta in self.SITIOS:          # "busca netflix": se abre el sitio
            url = self.SITIOS[consulta]
        else:
            url = navegacion.url_busqueda(consulta, motor)
        ok, nombre = self._abrir_url(url, navegador)
        return f"Buscando {consulta} en {nombre}." if ok else f"Negativo. {nombre.capitalize()}."

    def buscar_archivo(self, texto=""):
        """"Busca en el explorador informe.pdf": lo encuentra y lo muestra seleccionado."""
        t = navegacion.plano(texto)
        nombre = self._RE_BUSCAR.sub("", t)
        nombre = re.sub(r"\b(?:en (?:el|mi) (?:explorador|equipo|pc|computador|computadora|ordenador|disco)(?: de archivos)?|"
                        r"el archivo|un archivo|archivo|el fichero|fichero|el documento|documento|llamado|que se llama)\b",
                        " ", nombre)
        nombre = re.sub(r"\s+", " ", nombre).strip(" .")
        if not nombre:
            return "¿Qué archivo busco, señor?"
        encontrados = navegacion.buscar_archivo(nombre)
        if not encontrados:
            return f"Negativo. «{nombre}» no aparece en sus carpetas."
        navegacion.mostrar_en_explorador(encontrados[0])
        extra = f" Hay {len(encontrados) - 1} coincidencias más." if len(encontrados) > 1 else ""
        return f"Encontrado: {encontrados[0].name}, en {encontrados[0].parent.name}.{extra}"

    def noticias(self):
        """"Miller, dime las noticias": 3 titulares; sin internet, los últimos guardados."""
        try:
            return self.rutina.noticias.obtener_resumen()
        except Exception as error:
            print(f"[COMANDOS] Error con las noticias: {error}")
            return "Negativo. Noticias no disponibles."

    def calcular(self, texto=""):
        return calcular(texto)

    def gestionar_alarma(self, texto=""):
        if self.alarmas is None:
            return "Alarmas fuera de línea."
        from utilidades.alarmas import tipo_pedido
        tipo = tipo_pedido(texto)
        if tipo == "listar":
            return self.alarmas.listar()
        if tipo == "cancelar":
            return self.alarmas.cancelar(texto)
        return self.alarmas.crear(texto)

    def listar_papelera(self):
        aviso = self._sin_supervisor()
        if aviso:
            return aviso
        entradas = [e for e in self.supervisor.listar_cuarentena() if e.get("categoria") == "papelera"]
        if not entradas:
            return "Papelera vacía."
        return (f"Papelera: {self._n(len(entradas), 'canción', 'canciones')}. "
                f"{self._enumerar([e.get('nombre', '') for e in entradas])}.")
    _RE_DESCARGA = re.compile(
        r"^(?:miller\s+)?(?:por favor\s+)?(?:puedes\s+|quiero\s+(?:que\s+)?)?(?:descarga(?:r|me|la)?|bajame|bajar|baja)\s+"
        r"(?:(?:la|el|una|un|esta|este)\s+)?(?:(?:cancion|tema|musica|tonada|audio)\s+)?(?:(?:de|llamada|que se llama)\s+)?", re.I)
    def extraer_cancion_descarga(self, texto):
        consulta = self._RE_DESCARGA.sub("", str(texto or "").strip())
        consulta = re.sub(r"\s+(?:de|en|desde)\s+(?:youtube|internet)\s*$", "", consulta, flags=re.I)
        return consulta.strip(" .,;:") if consulta.strip(" .,;:") not in ("", "musica", "cancion", "una cancion") else ""
    def descargar_cancion(self, texto=""):
        """Descarga en segundo plano (yt-dlp + FFmpeg) a la carpeta audios. Sin red, avisa y sigue."""
        if descargador_musica is None:
            return "Módulo de descarga fuera de línea."
        consulta = self.extraer_cancion_descarga(texto)
        if not consulta:
            return "¿Qué canción descargo, señor?"
        ok_cuota, aviso_cuota = cuota.puede_crecer("archivos", configuracion.CUOTA_DESCARGA_ESTIMADA_MB * 1024 * 1024)
        if not ok_cuota:
            return aviso_cuota
        if self.internet is not None and not self.internet.hay_conexion():
            return "Sin conexión a internet. Descarga no disponible."
        if descargador_musica.obtener_progreso().get("estado") in ("iniciando", "descargando", "convirtiendo"):
            return "Ya hay una descarga en curso. Espere a que termine."
        def al_terminar(resultado):
            self._ultima_descarga = resultado
            if resultado.get("exito"):
                print(f"[DESCARGA] Completada: {resultado.get('titulo')}")
                try:
                    self.reproductor.actualizar_lista()     # la canción queda disponible al instante
                except Exception as error:
                    print(f"[DESCARGA] No se pudo actualizar la biblioteca: {error}")
                registrar = getattr(getattr(self, "memoria", None), "registrar_descarga", None)
                if callable(registrar):
                    registrar(resultado.get("titulo"))
            else:
                print(f"[DESCARGA] Fallida: {resultado.get('mensaje')}")
        self._ultima_descarga = None
        if descargador_musica.descargar_en_hilo(consulta, callback_final=al_terminar) is None:
            return "Ya hay una descarga en curso. Espere a que termine."
        return f"Afirmativo. Descargando {consulta}."
    def estado_descarga(self):
        if descargador_musica is None:
            return "Módulo de descarga fuera de línea."
        p = descargador_musica.obtener_progreso()
        if p.get("estado") in ("iniciando", "descargando", "convirtiendo"):
            titulo = p.get("titulo") or "canción"
            return f"Descarga en curso: {titulo}, {round(p.get('porcentaje') or 0)} %."
        r = getattr(self, "_ultima_descarga", None)
        if not r:
            return "Sin descargas en esta sesión."
        if r.get("exito"):
            return f"Descarga completada: {r.get('titulo')}. Disponible en la biblioteca."
        return f"Descarga fallida. {r.get('mensaje', '')}".strip()
    def cancelar_descarga(self):
        if descargador_musica is None:
            return "Módulo de descarga fuera de línea."
        if descargador_musica.obtener_progreso().get("estado") not in ("iniciando", "descargando", "convirtiendo"):
            return "No hay descarga activa."
        descargador_musica.cancelar()
        return "Descarga cancelada."
    def preguntar_internet(self, texto=""):
        """Respuesta corta desde internet. Sin red, avisa y MILLER sigue operativo."""
        if self.internet is None:
            return "Módulo de internet fuera de línea."
        try:
            r = self.internet.consultar(texto)
        except Exception as error:
            print(f"[COMANDOS] Error consultando internet: {error}")
            return "Fallo en la consulta. Operación abortada."
        if r.get("ok"):
            return f"{r['texto']} Fuente: {r['fuente']}."
        aprendida = getattr(getattr(self, "memoria", None), "respuesta_aprendida", None)
        if r.get("motivo") in ("sin_conexion", "error") and callable(aprendida):
            dato = aprendida(texto)
            if dato:
                return (f"Sin conexión. Dato aprendido el {str(dato.get('fecha', ''))[:10]}: "
                        f"{seguridad.sanear_conocimiento(dato.get('respuesta', ''), 400)}")
        return {"sin_conexion": "Sin conexión a internet. Consulta no disponible, señor.",
                "vacia": "Indique qué consulto en internet.",
                "sin_resultados": "Sin resultados concluyentes en la red."}.get(
                    r.get("motivo"), "Fallo de conexión. Consulta abortada.")
    def _nombres_pruebas(self, nombres):
        return self._enumerar([self.probador.nombre_legible(n) for n in nombres]) if nombres else ""
    def _describir_prueba(self, r):
        nombre = self.probador.nombre_legible(r.get("nombre", ""))
        estado = r.get("estado")
        if estado == "ok":
            return f"Prueba de {nombre}: superada en {r.get('duracion', 0)} segundos."
        if estado == "fallo":
            motivo = r.get("error") or r.get("ultima_linea") or f"terminó con código {r.get('codigo')}"
            return f"Prueba de {nombre}: fallida. {motivo}. Registro en datos/pruebas."
        if estado == "tiempo_agotado":
            extra = " Hable cuando se le indique." if r.get("tipo") == "microfono" else ""
            return f"Prueba de {nombre}: tiempo agotado. Abortada.{extra}"
        if estado == "vacia":
            return f"Prueba de {nombre}: vacía."
        if estado == "abierta_en_ventana":
            return f"Prueba de {nombre} abierta en otra ventana. Requiere su intervención."
        if estado == "interactiva":
            return f"Prueba de {nombre}: interactiva. {r.get('detalle', '')}."
        if estado == "no_existe":
            return f"Prueba de {nombre} inexistente."
        return f"Fallo al lanzar la prueba de {nombre}: {r.get('detalle', 'error desconocido')}."
    def listar_pruebas(self):
        if self.probador is None:
            return "Probador fuera de línea."
        pruebas = self.probador.listar()
        if not pruebas:
            return "Sin pruebas en la carpeta test."
        return (f"{self._n(len(pruebas), 'prueba disponible', 'pruebas disponibles')}: "
                + ", ".join(self.probador.nombre_legible(n) for n in pruebas) + ".")
    def probar_modulo(self, texto=""):
        if self.probador is None:
            return "Probador fuera de línea."
        if self.probador.en_curso()["activo"]:
            return "Pruebas generales en curso. Espere el resultado."
        nombre = self.probador.buscar(texto)
        if nombre is None:
            return "Módulo sin prueba. " + self.listar_pruebas()
        return self._describir_prueba(self.probador.ejecutar(nombre))
    def probar_todos_modulos(self):
        if self.probador is None:
            return "Probador fuera de línea."
        plan = self.probador.ejecutar_todas()
        if plan is None:
            return "Pruebas ya en curso."
        texto = f"Afirmativo. {self._n(len(plan['ejecutando']), 'prueba', 'pruebas')} en curso."
        if plan["omitidas"]:
            texto += f" Omitidas: {self._nombres_pruebas(plan['omitidas'])}."
        return texto + " Pida el resultado de las pruebas."
    def resultado_pruebas(self):
        if self.probador is None:
            return "Probador fuera de línea."
        estado = self.probador.en_curso()
        resultados = self.probador.resultados()
        if estado["activo"]:
            actual = self.probador.nombre_legible(estado["prueba"] or "")
            return (f"En curso. {self._n(len(resultados), 'completada', 'completadas')}"
                    + (f". Probando {actual}." if actual else "."))
        if not resultados:
            return "Sin pruebas ejecutadas."
        bien = [n for n, r in resultados.items() if r.get("estado") == "ok"]
        mal = [r for r in resultados.values() if r.get("estado") in ("fallo", "tiempo_agotado", "error")]
        partes = [f"{self._n(len(bien), 'superada', 'superadas')}."]
        if mal:
            partes.append(f"{self._n(len(mal), 'fallida', 'fallidas')}: {self._nombres_pruebas([r['nombre'] for r in mal])}.")
            partes.append(self._describir_prueba(mal[0]))
        else:
            partes.append("Sin fallos.")
        return " ".join(partes)
    def revisar_biblioteca(self):
        aviso = self._sin_supervisor()
        if aviso:
            return aviso
        self.supervisor.reanudar()
        self.supervisor.escanear_ahora()
        return "Afirmativo. Revisión de biblioteca en curso."
    def limpiar_biblioteca(self, texto=""):
        """Prepara la limpieza y pide confirmación (mueve archivos, aunque sea a cuarentena)."""
        informe, aviso = self._informe_biblioteca()
        if aviso:
            return aviso
        cats = self._categorias_de_texto(texto)
        cuentas = {
            "danados": len(informe.get("danados", [])),
            "duplicados": sum(len(g.get("duplicados", [])) for g in informe.get("duplicados", [])),
            "no_compatibles": len(informe.get("no_compatibles", [])),
            "adulterados": len(informe.get("adulterados", [])),
        }
        cats = {c for c in cats if cuentas[c]}
        if not cats:
            return "Nada que limpiar."
        self._limpieza_por_confirmar = ({"tipo": "limpiar", "categorias": cats}, time.monotonic())
        singular = {"danados": "dañado", "duplicados": "duplicado", "no_compatibles": "no compatible"}
        detalle = ", ".join(self._n(cuentas[c], singular[c], self.NOMBRES_CATEGORIA[c])
                            for c in self.supervisor.CATEGORIAS_LIMPIEZA if c in cats)
        return f"A cuarentena: {detalle}. Reversible. ¿Confirma, señor?"
    # ------------------------------------------------------------ batería
    def bateria(self):
        return _bateria.describir()
    # ------------------------------------------------------------ ecualizador inteligente
    _RE_BANDA_VALOR = re.compile(r"\b(graves|bajos|bajo|grave|medios|medio|voces|agudos|agudo|brillo|altos)\b"
                                 r"\s*(?:en|a|de|al|hasta)?\s*(-?\d+(?:[.,]\d+)?)")

    @staticmethod
    def _nombre_de_perfil_en(t):
        """Lo que sigue a la palabra «perfil»: «crea perfil nocturno con graves 3» -> «nocturno»."""
        m = re.search(r"\bperfil\s+(?:de\s+|llamado\s+|llamada\s+|como\s+|que\s+se\s+llame\s+)?(.+?)"
                      r"(?=\s+(?:con|como|en|a)\s|\s+(?:graves|bajos|medios|agudos|altos|brillo)\b|$)", t)
        nombre = m.group(1).strip() if m else ""
        return "" if nombre in ("con", "como", "de", "en", "a") else nombre

    def _resumen_perfiles_eq(self):
        from utilidades.ecualizador import NOMBRES_PERFIL, PERFILES
        propios = sorted(self.ecualizador.estado.get("propios", {}))
        texto = "Perfiles de fábrica: " + ", ".join(NOMBRES_PERFIL.get(p, p) for p in PERFILES) + "."
        if propios:
            return texto + " Propios: " + ", ".join(propios) + "."
        return texto + " No tiene perfiles propios. Diga «crea perfil nombre con graves 3»."

    def controlar_ecualizador(self, texto):
        """Órdenes del ecualizador: consultar, apagar, perfiles de fábrica y propios, bandas en dB, subir/bajar."""
        eq = self.ecualizador
        if eq is None:
            return "Ecualizador fuera de línea."
        from utilidades.ecualizador import (NOMBRES_PERFIL, PERFILES, BANDAS, MAX_PERFILES_PROPIOS,
                                            formato_db, nombre_perfil, sin_tildes)
        t = re.sub(r"\s+", " ", str(texto or "")).strip()
        actual = self.reproductor.cancion_actual
        propios = eq.estado.get("propios", {})
        # 1. Consultas: cómo está y qué perfiles hay.
        if re.search(r"\b(como esta|estado|que tiene|como suena|que perfil|que ajustes?)\b", t) and \
                not re.search(r"\b(pon|activa|usa|crea|crear|guarda|guardar)\b", t):
            return eq.describir(actual)
        if re.search(r"\b(perfiles|lista de perfiles|que perfiles)\b", t) and \
                not re.search(r"\b(crea|crear|guarda|guardar|borra|borrar|elimina|eliminar)\b", t):
            return self._resumen_perfiles_eq()
        # 2. Apagar: la música suena tal cual.
        if re.search(r"\b(quita|quitar|desactiva|desactivar|apaga|apagar|sin)\b.*\becualiza", t):
            eq.desactivar()
            self.reproductor.reaplicar_ecualizacion()
            return "Ecualizador desactivado. La música suena tal cual."
        # 3. Perfiles propios: crear (con bandas o con la curva que suena) y borrar.
        if re.search(r"\bperfil\b", t) and re.search(r"\b(crea|crear|creame|guarda|guardar|guardame|nuevo|nueva)\b", t):
            crudo = self._nombre_de_perfil_en(t)
            if not crudo:
                return "Dígame el nombre del perfil, señor. Ejemplo: crea perfil nocturno con graves 3, agudos -2."
            if sin_tildes(crudo) in PERFILES:
                return f"Negativo. «{NOMBRES_PERFIL.get(sin_tildes(crudo), crudo)}» es de fábrica. Elija otro nombre."
            nombre = nombre_perfil(crudo)
            if not nombre:
                return "Negativo. Ese nombre no sirve. Use letras y números, y no un nombre reservado."
            if nombre not in propios and len(propios) >= MAX_PERFILES_PROPIOS:
                return f"Negativo. Ya tiene {MAX_PERFILES_PROPIOS} perfiles propios. Borre uno primero."
            valores = {}
            for banda, numero in self._RE_BANDA_VALOR.findall(t):
                valores[_BANDAS_EQ.get(banda, banda)] = float(numero.replace(",", "."))
            creado = eq.crear_perfil(nombre, valores or None, actual)
            if not creado:
                return "Negativo. No pude guardar ese perfil."
            curva = eq.estado["propios"][creado]
            detalle = ", ".join(f"{b} {formato_db(curva[b])}" for b in BANDAS)
            return (f"Afirmativo. Perfil «{creado}» guardado: {detalle}. Ya está en uso; "
                    f"diga «pon perfil {creado}» para volver a usarlo." + self._aplicar_eq_en_vivo())
        if re.search(r"\bperfil\b", t) and re.search(r"\b(borra|borrar|borrame|elimina|eliminar|quita|quitar)\b", t):
            crudo = self._nombre_de_perfil_en(t)
            if not crudo:
                return "¿Qué perfil borro, señor?"
            if sin_tildes(crudo) in PERFILES:
                return "Negativo. Los perfiles de fábrica no se borran."
            nombre = nombre_perfil(crudo)
            if nombre and eq.borrar_perfil(nombre):
                return f"Afirmativo. Perfil «{nombre}» borrado."
            return f"No tengo un perfil propio llamado «{crudo}»."
        # 4. Una banda a un valor exacto: «pon los graves en 3». Las demás no cambian.
        if not re.search(r"\bperfil\b", t) and re.search(r"\b(pon|pone|deja|ajusta|ajustar|fija|fijar)\b", t):
            pares = [(_BANDAS_EQ.get(b, b), float(n.replace(",", "."))) for b, n in self._RE_BANDA_VALOR.findall(t)]
            partes = []
            for banda, valor in pares:
                aplicado = eq.fijar_banda(banda, valor, actual)
                if aplicado is not None:
                    partes.append(f"{banda} en {formato_db(aplicado)}")
            if partes:
                return ("Afirmativo. Ecualizador manual: " + ", ".join(partes) +
                        ". Las demás bandas no cambian." + self._aplicar_eq_en_vivo())
        # 5. Subir o bajar una banda: lo aprende en general y para el artista de la canción.
        m = re.search(r"\b(sube|subir|subele|aumenta|aumentar|mas|baja|bajar|bajale|reduce|reducir|menos|quita)\b"
                      r"(?:\s+\w+){0,3}?\s+(graves|bajos|bajo|grave|medios|medio|voces|agudos|agudo|brillo|altos)\b", t)
        if m:
            direccion = 1 if m.group(1) in ("sube", "subir", "subele", "aumenta", "aumentar", "mas") else -1
            valor = eq.ajustar(m.group(2), direccion, actual)
            banda = _BANDAS_EQ.get(m.group(2), m.group(2))
            preparando = self._aplicar_eq_en_vivo()
            quien = f" para {eq.artista(actual).title()}" if actual and eq.artista(actual) else ""
            return (f"{'Subo' if direccion > 0 else 'Bajo'} los {banda}{quien}: quedan en "
                    f"{'+' if valor > 0 else ''}{valor:g} dB. Lo recordaré.{preparando}")
        # 6. Automático, o un perfil de fábrica o propio.
        if re.search(r"\b(automatico|automatica|inteligente|auto)\b", t):
            eq.poner_automatico()
            return "Ecualizador inteligente activado: mido cada canción y la equilibro." + self._aplicar_eq_en_vivo()
        nombre = eq.buscar_perfil(t)
        if nombre:
            eq.poner_perfil(nombre)
            detalle = ", ".join(f"{b} {formato_db(v)}" for b, v in eq.valores_perfil(nombre).items())
            return (f"Ecualizador en perfil {NOMBRES_PERFIL.get(nombre, nombre)}: {detalle}."
                    + self._aplicar_eq_en_vivo())
        return (eq.describir(actual) + " Diga: «pon perfil rock», «crea perfil nocturno con graves 3», "
                "«pon los graves en 2», «sube los agudos», «ecualizador automático» o «quita el ecualizador».")

    def _aplicar_eq_en_vivo(self):
        if self.reproductor.cancion_actual is None:
            return ""
        antes = self.reproductor.fuente_actual
        self.reproductor.reaplicar_ecualizacion()
        if self.reproductor.fuente_actual == antes and self.ecualizador.ffmpeg:
            return " La canción actual se ecualiza en unos segundos."
        return ""
    def hay_limpieza_pendiente(self):
        pendiente = getattr(self, "_limpieza_por_confirmar", None)
        if not pendiente:
            return False
        if time.monotonic() - pendiente[1] > self.SEGUNDOS_CONFIRMAR_LIMPIEZA:
            self._limpieza_por_confirmar = None
            return False
        return True
    def confirmar_limpieza(self):
        aviso = self._sin_supervisor()
        if aviso:
            return aviso
        if not self.hay_limpieza_pendiente():
            return "Sin operaciones pendientes de confirmación."
        accion, _ = self._limpieza_por_confirmar
        self._limpieza_por_confirmar = None
        if accion["tipo"] == "vaciar":
            n = self.supervisor.eliminar_de_cuarentena(categorias=accion.get("categorias"))
            return (f"Confirmado. {self._n(n, 'archivo eliminado', 'archivos eliminados')}."
                    if n else "Negativo. Nada eliminado.")
        cats = accion["categorias"]
        self.supervisor.reanudar()
        if not self.supervisor.solicitar_limpieza(cats):
            return "Negativo. Limpieza no iniciada."
        return f"Confirmado. Limpieza de {self._texto_categorias(cats)} en curso."
    def cancelar_limpieza(self):
        self._limpieza_por_confirmar = None
        return "Operación cancelada."
    def restaurar_cuarentena(self, texto=""):
        aviso = self._sin_supervisor()
        if aviso:
            return aviso
        entradas = self.supervisor.listar_cuarentena()
        if not entradas:
            return "Cuarentena vacía. Nada que restaurar."
        t = self._normalizar_biblioteca(texto)
        if re.search(r"\b(todo|todos|todas|completa)\b", t):
            ok = sum(1 for e in entradas if self.supervisor.restaurar_de_cuarentena(e["id"]))
            return f"Restaurados {ok} de {len(entradas)}."
        consulta = re.sub(
            r"\b(miller|por favor|restaura|restaurar|restaurame|recupera|recuperar|devuelve|devolver|"
            r"saca|sacar|de|del|la|el|los|las|a|cuarentena|papelera|biblioteca|cancion|archivo|audio|pista)\b",
            " ", t)
        consulta = re.sub(r"\s+", " ", consulta).strip()
        if not consulta:
            return "¿Qué canción restauro, señor?"
        candidatas = [e for e in entradas
                      if consulta in self._normalizar_biblioteca(self._sin_extension(e.get("nombre", "")))]
        if not candidatas:
            return f"'{consulta}' no está en cuarentena."
        if len(candidatas) > 1:
            return (f"{len(candidatas)} coincidencias: "
                    f"{self._enumerar([e['nombre'] for e in candidatas])}. Precise el nombre.")
        e = candidatas[0]
        if self.supervisor.restaurar_de_cuarentena(e["id"]):
            return f"Restaurado: {self._sin_extension(e['nombre'])}."
        return f"Negativo. {self._sin_extension(e['nombre'])} sigue en cuarentena."
    def pausar_supervisor(self):
        aviso = self._sin_supervisor()
        if aviso:
            return aviso
        self.supervisor.pausar()
        return "Supervisor en pausa."
    def reanudar_supervisor(self):
        if self.supervisor is None or not self.supervisor.esta_activo():
            self._detener_supervisor()
            self._iniciar_supervisor()
            return ("Supervisor activado." if self.supervisor else "Negativo. Supervisor no disponible.")
        self.supervisor.reanudar()
        return "Supervisor reanudado."
    def ejecutar(self, intencion, texto=""):
        """Despacha cada intención al método especializado correspondiente."""
        texto = (texto or "").strip()
        intencion = str(intencion or "").upper().strip()
        intencion = self.ALIAS.get(intencion, intencion)
        acciones = {
            "RUTINA_MATUTINA": self.ejecutar_rutina_matutina,
            "ABRIR_SITIO_WEB": lambda: self.abrir_sitio_web(texto),
            "BUSCAR_INTERNET": lambda: self.abrir_sitio_web(texto),
            "ABRIR_APLICACION": lambda: self.abrir_aplicacion(texto),
            "CERRAR_APLICACION": lambda: self.cerrar_aplicacion(texto),
            "CREAR_CARPETA": lambda: self.crear_carpeta(texto),
            "ABRIR_CARPETA": lambda: self.abrir_carpeta(texto),
            "ESTADO_SISTEMA": self.estado_sistema,
            "ESTABLECER_VOLUMEN": lambda: self.controlar_volumen(texto),
            "VOLUMEN_AUDIO": lambda: self.controlar_volumen(texto),
            "REPRODUCIR_MUSICA": lambda: self.reproducir_musica(texto),
            "REPRODUCIR_AUDIO": lambda: self.reproducir_audio(texto),
            "PAUSAR_AUDIO": self.pausar_audio,
            "CONTINUAR_AUDIO": self.continuar_audio,
            "DETENER_AUDIO": self.detener_audio,
            "SIGUIENTE_AUDIO": self.siguiente_audio,
            "ANTERIOR_AUDIO": self.anterior_audio,
            "ESTADO_AUDIO": self.estado_audio,
            "LISTAR_AUDIOS": self.listar_audios,
            "AGREGAR_COLA_AUDIO": lambda: self.agregar_cola_audio(texto),
            "MOSTRAR_COLA_AUDIO": self.mostrar_cola_audio,
            "LIMPIAR_COLA_AUDIO": self.limpiar_cola_audio,
            "QUITAR_COLA_AUDIO": lambda: self.quitar_cola_audio(texto),
            "ALEATORIO_AUDIO": self.aleatorio_audio,
            "REPETIR_AUDIO": self.repetir_audio,
            # Supervisor de biblioteca: información
            "ESTADO_BIBLIOTECA": self.estado_biblioteca,
            "LISTAR_DANADOS_BIBLIOTECA": self.listar_danados_biblioteca,
            "LISTAR_DUPLICADOS_BIBLIOTECA": self.listar_duplicados_biblioteca,
            "LISTAR_NO_COMPATIBLES_BIBLIOTECA": self.listar_no_compatibles_biblioteca,
            "LISTAR_CUARENTENA": self.listar_cuarentena,
            "ESTADO_SUPERVISOR": self.estado_supervisor,
            "RESULTADO_LIMPIEZA": self.resultado_limpieza,
            "AYUDA_BIBLIOTECA": self.ayuda_biblioteca,
            "LISTAR_ADULTERADOS": self.listar_adulterados,
            "PLAN_ELIMINACION": self.plan_eliminacion,
            # Supervisor de biblioteca: acciones
            "REVISAR_BIBLIOTECA": self.revisar_biblioteca,
            "REPARAR_BIBLIOTECA": self.reparar_biblioteca,
            "VACIAR_CUARENTENA": lambda: self.vaciar_cuarentena(texto),
            "LIMPIAR_BIBLIOTECA": lambda: self.limpiar_biblioteca(texto),
            "CONFIRMAR_LIMPIEZA": self.confirmar_limpieza,
            "CANCELAR_LIMPIEZA": self.cancelar_limpieza,
            "RESTAURAR_CUARENTENA": lambda: self.restaurar_cuarentena(texto),
            "MUSICA_DEL_DIA": lambda: self.musica_del_dia(texto),
            "NOTICIAS": self.noticias,
            "BUSCAR_NAVEGADOR": lambda: self.buscar_en_navegador(texto),
            "BUSCAR_ARCHIVO": lambda: self.buscar_archivo(texto),
            "CALCULAR": lambda: self.calcular(texto),
            "ALARMA": lambda: self.gestionar_alarma(texto),
            "BORRAR_CANCION": lambda: self.borrar_cancion(texto),
            "LISTAR_PAPELERA": self.listar_papelera,
            "VACIAR_PAPELERA": lambda: self.vaciar_cuarentena("papelera"),
            "PAUSAR_SUPERVISOR": self.pausar_supervisor,
            "REANUDAR_SUPERVISOR": self.reanudar_supervisor,
            # Pruebas de módulos (carpeta test/)
            "PREGUNTA_INTERNET": lambda: self.preguntar_internet(texto),
            "DESCARGAR_MUSICA": lambda: self.descargar_cancion(texto),
            "ESTADO_DESCARGA": self.estado_descarga,
            "CANCELAR_DESCARGA": self.cancelar_descarga,
            "PROBAR_MODULO": lambda: self.probar_modulo(texto),
            "PROBAR_TODOS_MODULOS": self.probar_todos_modulos,
            "RESULTADO_PRUEBAS": self.resultado_pruebas,
            "LISTAR_PRUEBAS": self.listar_pruebas,
            "BATERIA": self.bateria,
            "ABRIR_ARCHIVO": lambda: self.abrir_archivo(texto),
            "CERRAR_ARCHIVO": lambda: self.cerrar_archivo(texto),
            "VENTANA": lambda: self.controlar_ventana(texto),
            "ECUALIZADOR": lambda: self.controlar_ecualizador(texto),
            "ECUALIZADOR_AJUSTE": lambda: self.controlar_ecualizador(texto),
        }
        accion = acciones.get(intencion)
        if accion:
            try:
                return accion()
            except Exception as error:
                print(f"[COMANDOS] Error en {intencion}: {error}")
                return f"Fallo ejecutando {intencion.lower()}."
        return f"Sin protocolo para {intencion}."
    def ejecutar_rutina_matutina(self):
        try:
            return self.rutina.ejecutar() or "Negativo. Información no disponible."
        except Exception as error:
            print(f"[COMANDOS] Error ejecutando rutina: {error}")
            return "Negativo. Informe incompleto."
    def _reproducir_musica_rutina(self):
        try:
            if not self.reproductor.reproducir():
                return "Biblioteca vacía. Sin canciones."
            cancion = self.reproductor.obtener_nombre_actual()
            return f"Cierre de informe. Reproduciendo {cancion}." if cancion else \
                "Cierre de informe. Música en curso."
        except Exception as error:
            print(f"[COMANDOS] Error reproduciendo música de rutina: {error}")
            return "Negativo. Música de rutina no disponible."
    APPS_ESCRITORIO = ("spotify", "whatsapp", "telegram", "discord", "netflix", "outlook", "teams", "zoom", "steam")
    def _catalogo(self):
        return getattr(self.sistema, "programas", None)

    def _abrir_url(self, url, navegador=None):
        ok, nombre = navegacion.abrir(url, navegador, self._catalogo())
        return ok, nombre

    def abrir_sitio_web(self, texto):
        texto = (texto or "").lower().strip()
        navegador = navegacion.detectar_navegador(texto)
        pide_navegador = bool(navegador) or "navegador" in texto
        if navegador:                                   # "ciérralo" / "minimízalo" se referirán a ese navegador
            self.ultimo_objetivo = _ventanas.limpiar_nombre(navegador if isinstance(navegador, str) else str(navegador))
        if pide_navegador:
            destino = navegacion.quitar_navegador(texto)
            destino = re.sub(r"^(?:miller\s+)?(?:por favor\s+)?(?:abre|abrir|abreme|entra a|entra en|ve a|ir a|llevame a)\s+"
                             r"(?:la pagina de\s+|el sitio de\s+|la web de\s+)?", "", destino).strip()
            url = next((u for n, u in sorted(self.SITIOS.items(), key=lambda x: len(x[0]), reverse=True)
                        if n == destino or n in destino), None)
            if url is None and re.search(r"\.[a-z]{2,6}(/|$)", destino):
                url = "https://" + destino.replace(" ", "")
            if url is None:
                url = navegacion.url_busqueda(destino) if destino else "https://www.google.com"
            ok, nombre = self._abrir_url(url, navegador)
            return f"Afirmativo. {destino.capitalize() or 'Navegador'} en {nombre}." if ok else f"Negativo. {nombre.capitalize()}."
        for app in self.APPS_ESCRITORIO:                 # si el programa está instalado, se prefiere al sitio web
            if re.search(rf"\b{app}\b", texto) and not re.search(r"\b(web|pagina|sitio|navegador)\b", texto):
                try:
                    ok, nombre = self.sistema.abrir_aplicacion(app)
                except Exception:
                    ok = False
                if ok:
                    return f"Afirmativo. Abriendo {nombre}."
        for nombre, url in sorted(self.SITIOS.items(), key=lambda x: len(x[0]), reverse=True):
            if nombre in texto:
                try:
                    ok = self.sistema.abrir_url(url)
                except Exception as error:
                    print(f"[COMANDOS] Error abriendo web: {error}")
                    ok = False
                return f"Afirmativo. Abriendo {nombre}." if ok else f"Negativo. No fue posible abrir {nombre}."
        return "Sitio web no identificado."
    _RE_PROGRAMA = re.compile(
        r"^(?:miller\s+)?(?:por favor\s+)?(?:puedes\s+|quiero\s+(?:que\s+)?)?(?:abre|abrir|abreme|abrirme|inicia|iniciar|iniciame|"
        r"ejecuta|ejecutar|ejecutame|lanza|lanzar|arranca|arrancar|cierra|cerrar|cierrame|termina|terminar|finaliza|finalizar|mata|matar)"
        r"\s+(?:(?:el|la|los|las|un|una|mi)\s+)?(?:(?:programa|aplicacion|app|juego|herramienta)\s+(?:de\s+)?)?", re.I)
    def extraer_programa(self, texto):
        return self._RE_PROGRAMA.sub("", str(texto or "").strip()).strip(" .,;:")
    def _gestionar_aplicacion(self, texto, cerrar=False):
        """Abre o cierra CUALQUIER programa del equipo (catálogo de Windows en utilidades/sistema.py).
        Cerrar va primero por las ventanas (todas las del programa, como pulsar la X); "forzar" termina el proceso."""
        forzar = bool(re.search(r"\b(forzar|forzado|a la fuerza|fuerza|mata|matar)\b", texto or ""))
        nombre = re.sub(r"\b(forzar|forzado|a la fuerza|fuerza)\b", "", self.extraer_programa(texto)).strip()
        if not nombre:
            return f"¿Qué programa {'cierro' if cerrar else 'abro'}, señor?"
        limpio = _ventanas.limpiar_nombre(nombre) or nombre
        self.ultimo_objetivo = limpio
        if cerrar and _ventanas.disponible():
            try:
                cuantas, mostrado = _ventanas.cerrar(limpio, forzar=forzar)
            except Exception as error:
                print(f"[COMANDOS] Error cerrando ventanas: {error}")
                cuantas, mostrado = 0, None
            if cuantas:
                extra = f" ({cuantas} ventanas)" if cuantas > 1 else ""
                return f"Afirmativo. Cerrando {limpio}{extra}." + (" Forzado." if forzar else "")
        nombre = limpio
        try:
            ok, detalle = (self.sistema.cerrar_aplicacion if cerrar else self.sistema.abrir_aplicacion)(nombre)
        except Exception as error:
            print(f"[COMANDOS] Error con aplicación: {error}")
            ok, detalle = False, "error"
        if ok:
            return f"Afirmativo. {'Cerrando' if cerrar else 'Abriendo'} {detalle}."
        if detalle == "no encontrado":
            return f"Programa '{nombre}' no localizado en el equipo."
        if detalle == "no está abierto":
            return f"{nombre.capitalize()} no está abierto."
        return f"Negativo. No fue posible {'cerrar' if cerrar else 'abrir'} {nombre}."
    # ------------------------------------------------------------ archivos y ventanas
    # Por seguridad, "abrir archivo" nunca ejecuta programas ni scripts (para eso está "abre <programa>").
    EXTENSIONES_PELIGROSAS = seguridad.EXTENSIONES_PELIGROSAS
    _RE_ARCHIVO_ABRIR = re.compile(r"^(?:miller\s+)?(?:por favor\s+)?(?:abre|abrir|abreme|cierra|cerrar|cierrame)\s+"
                                   r"(?:el |la |mi )?(?:archivo|documento|fichero|foto|imagen|video|pdf)?\s*(?:de |llamado )?")
    def _nombre_archivo(self, texto):
        nombre = self._RE_ARCHIVO_ABRIR.sub("", str(texto or "")).strip(" .,;:")
        return re.sub(r"\s+punto\s+", ".", nombre)
    def abrir_archivo(self, texto):
        nombre = self._nombre_archivo(texto)
        if not nombre:
            return "¿Qué archivo abro, señor?"
        try:
            encontrados = navegacion.buscar_archivo(nombre, maximo=3)
        except Exception as error:
            print(f"[COMANDOS] Error buscando archivo: {error}")
            encontrados = []
        if not encontrados:
            return f"No encuentro el archivo «{nombre}»."
        ruta = Path(encontrados[0])
        if seguridad.archivo_peligroso(ruta):
            seguridad.alerta(f"Bloqueado abrir como archivo un ejecutable o script: {ruta.name}")
            return f"Por seguridad no abro {ruta.name} como archivo: es un programa o un script."
        try:
            os.startfile(str(ruta))                    # lo abre su programa predeterminado
        except Exception as error:
            print(f"[COMANDOS] Error abriendo archivo: {error}")
            return f"No pude abrir {ruta.name}."
        self.ultimo_objetivo = ruta.name
        return f"Abriendo {ruta.name}."
    def cerrar_archivo(self, texto):
        nombre = self._nombre_archivo(texto) or (self.ultimo_objetivo or "")
        if not nombre:
            return "¿Qué archivo cierro, señor?"
        try:
            cuantas, mostrado = _ventanas.cerrar(nombre)
        except Exception as error:
            print(f"[COMANDOS] Error cerrando archivo: {error}")
            cuantas = 0
        self.ultimo_objetivo = nombre
        return f"Cerrando {nombre}." if cuantas else f"No veo abierto «{nombre}»."
    # Verbos con \b y los más largos primero: antes «minimizar x» se leía como «minimiza» + «r x».
    _RE_VENTANA = re.compile(r"^(?:miller\s+)?(?:por favor\s+)?"
                             r"(minimizame|minimizar|minimiza|esconde|maximizame|maximizar|maximiza|agranda|"
                             r"restaurame|restaurar|restaura|muestra|mostrar|trae)\b\s*"
                             r"(?:la |el |las |los )?(?:ventanas? )?(?:de |del )?")
    _RE_PANTALLA_COMPLETA = re.compile(r"^(?:miller\s+)?(?:por favor\s+)?(?:pon|pone|deja|muestra)\s+(?:la |el )?"
                                       r"(?:ventana (?:de |del )?|programa )?(.+?)\s+en pantalla completa$")
    def controlar_ventana(self, texto):
        """Minimizar, maximizar o restaurar: un programa, un archivo, la ventana activa, todo o la de MILLER."""
        t = str(texto or "")
        if re.search(r"\bminimizate\b|\b(minimiza|esconde)\b.*\b(miller|tu ventana|tu misma|tu mismo)\b", t):
            if callable(self.minimizar_propia):
                self.minimizar_propia()
                return "Me minimizo, señor. Sigo escuchando."
            return "Mi ventana no está abierta."
        pantalla = self._RE_PANTALLA_COMPLETA.match(t)
        if pantalla:                                          # «pon spotify en pantalla completa»
            modo, nombre = "maximizar", _ventanas.limpiar_nombre(pantalla.group(1))
        else:
            m = self._RE_VENTANA.match(t)
            verbo = m.group(1) if m else "minimiza"
            modo = ("minimizar" if verbo.startswith(("minimiza", "esconde")) else
                    "maximizar" if verbo.startswith(("maximiza", "agranda")) else "restaurar")
            nombre = _ventanas.limpiar_nombre(t[m.end():] if m else t)
        if not _ventanas.disponible():
            return "El control de ventanas solo funciona en Windows."
        if modo == "minimizar" and re.fullmatch(r"(todo|todas|todas las ventanas|el escritorio|)", nombre or ""):
            if not nombre and not re.search(r"\b(todo|todas)\b", t):
                titulo = _ventanas.minimizar_activa()
                return f"Minimizando {titulo}." if titulo else "No hay ninguna ventana activa que minimizar."
            _ventanas.minimizar_todo()
            return "Minimizando todas las ventanas."
        if not nombre:
            return "¿Qué ventana, señor?"
        try:
            cuantas, _ = _ventanas.mostrar_como(nombre, modo)
        except Exception as error:
            print(f"[COMANDOS] Error con la ventana: {error}")
            cuantas = 0
        self.ultimo_objetivo = nombre
        if not cuantas:
            return f"No veo abierto {nombre}."
        accion = {"minimizar": "Minimizando", "maximizar": "Maximizando", "restaurar": "Mostrando"}[modo]
        return f"{accion} {nombre}."
    def abrir_aplicacion(self, texto):
        return self._gestionar_aplicacion(texto)
    def cerrar_aplicacion(self, texto):
        return self._gestionar_aplicacion(texto, cerrar=True)
    def crear_carpeta(self, texto):
        nombre = self.extraer_nombre(texto, self.PATRONES_CARPETA_CREAR)
        if not nombre:
            return "Indique el nombre de la carpeta."
        try:
            ok = self.sistema.crear_carpeta(nombre)
        except Exception as error:
            print(f"[COMANDOS] Error creando carpeta: {error}")
            ok = False
        return f"Carpeta '{nombre}' creada." if ok else f"Negativo. No se creó la carpeta '{nombre}'."
    def abrir_carpeta(self, texto):
        nombre = self.extraer_nombre(texto, self.PATRONES_CARPETA_ABRIR)
        if not nombre:
            return "Indique qué carpeta abro."
        try:
            ok = self.sistema.abrir_carpeta(nombre)
        except Exception as error:
            print(f"[COMANDOS] Error abriendo carpeta: {error}")
            ok = False
        return f"Abriendo carpeta '{nombre}'." if ok else f"Carpeta '{nombre}' no localizada."
    def reproducir_musica(self, texto):
        nombre = self.extraer_nombre_audio(texto)
        if nombre:
            return self._reproducir_por_nombre(nombre)
        try:
            if self.reproductor.reproducir():
                cancion = self.reproductor.obtener_nombre_actual()
                return f"Reproduciendo {cancion}." if cancion else "Reproducción en curso."
        except Exception as error:
            print(f"[COMANDOS] Error reproduciendo música: {error}")
            return "Fallo al iniciar la reproducción."
        return "Biblioteca vacía. Sin canciones."
    def reproducir_audio(self, texto):
        nombre = self.extraer_nombre_audio(texto)
        if not nombre:
            # Cerebro puede entregar el nombre ya extraído, sin el verbo.
            nombre = self._limpiar_nombre(texto)
        if not nombre:
            return "¿Qué canción reproduzco, señor?"
        return self._reproducir_por_nombre(nombre)
    def _reproducir_por_nombre(self, nombre):
        nombre = self._limpiar_nombre(nombre)
        if not nombre:
            return "Indique el nombre de la canción."
        try:
            resultados = self.reproductor.buscar_canciones(nombre)
        except Exception as error:
            print(f"[COMANDOS] Error buscando canción: {error}")
            return "Fallo en la búsqueda de la canción."
        if not resultados:
            return f"Sin coincidencias para '{nombre}'."
        cancion = resultados[0]
        try:
            ok = self.reproductor.reproducir(cancion.stem)
        except Exception as error:
            print(f"[COMANDOS] Error reproduciendo canción: {error}")
            ok = False
        return f"Reproduciendo {cancion.stem}." if ok else f"Negativo. No fue posible reproducir {cancion.stem}."
    @staticmethod
    def _limpiar_nombre(texto):
        """Limpia comillas y signos sin alterar el nombre de la canción."""
        return (texto or "").strip().strip("\"'.,!¡¿? ")
    def extraer_nombre_audio(self, texto):
        texto = (texto or "").strip()
        if not texto:
            return None
        for patron in self.PATRONES_AUDIO:
            match = re.search(patron, texto, re.IGNORECASE)
            if match:
                nombre = self._limpiar_nombre(match.group(1))
                if not nombre or nombre.lower() in {
                    "musica", "música", "una musica", "una música",
                    "canciones", "canción", "musica de", "música de",
                    "audio", "un audio", "la musica", "la música",
                }:
                    return None
                return nombre
        return None
    def pausar_audio(self):
        try:
            if self.reproductor.pausar():
                return "Música en pausa."
            if self.reproductor.esta_pausado():
                return "La música ya está en pausa."
        except Exception as error:
            print(f"[COMANDOS] Error pausando audio: {error}")
        return "No hay reproducción activa."
    def continuar_audio(self):
        try:
            if self.reproductor.continuar():
                return "Reanudando."
            if self.reproductor.esta_reproduciendo():
                return "La música ya está en curso."
        except Exception as error:
            print(f"[COMANDOS] Error continuando audio: {error}")
        return "No hay música en pausa."
    def detener_audio(self):
        try:
            if self.reproductor.detener():
                return "Música detenida."
        except Exception as error:
            print(f"[COMANDOS] Error deteniendo audio: {error}")
        return "No había reproducción activa."
    def _cambiar_pista(self, metodo, etiqueta):
        try:
            if getattr(self.reproductor, metodo)():
                cancion = self.reproductor.obtener_nombre_actual()
                return f"Reproduciendo {cancion}." if cancion else "Reproducción en curso."
        except Exception as error:
            print(f"[COMANDOS] Error cambiando pista: {error}")
            return f"Fallo con la canción {etiqueta}."
        return f"Negativo. Sin canción {etiqueta}."
    def siguiente_audio(self):
        return self._cambiar_pista("siguiente", "siguiente")
    def anterior_audio(self):
        return self._cambiar_pista("anterior", "anterior")
    def controlar_volumen(self, texto):
        texto = (texto or "").lower().strip()
        texto = texto.replace("por ciento", "porciento").replace("porcentaje", "porciento")
        porcentaje = self._extraer_porcentaje_volumen(texto)
        if porcentaje is not None:
            porcentaje = max(0, min(100, porcentaje))
            try:
                ok = self.reproductor.establecer_volumen(porcentaje / 100)
                return f"Volumen al {porcentaje} %." if ok else "Negativo. Volumen sin cambios."
            except Exception as error:
                print(f"[COMANDOS] Error estableciendo volumen: {error}")
                return "Negativo. Volumen sin cambios."
        if any(frase in texto for frase in self.FRASES_SUBIR):
            try:
                if self.reproductor.subir_volumen():
                    return f"Volumen al {self.reproductor.obtener_volumen()} %."
            except Exception as error:
                print(f"[COMANDOS] Error subiendo volumen: {error}")
            return "Negativo. Volumen sin cambios."
        if any(frase in texto for frase in self.FRASES_BAJAR):
            try:
                if self.reproductor.bajar_volumen():
                    return f"Volumen al {self.reproductor.obtener_volumen()} %."
            except Exception as error:
                print(f"[COMANDOS] Error bajando volumen: {error}")
            return "Negativo. Volumen sin cambios."
        try:
            volumen = self.reproductor.obtener_volumen()
        except Exception:
            volumen = 0
        return f"Volumen al {volumen} %."
    def _extraer_porcentaje_volumen(self, texto):
        encabezado = r"(?:volumen|audio|música|musica)"
        match = re.search(encabezado + r".{0,30}?(\d{1,3})\s*(?:%|porciento)?", texto, re.I)
        if match:
            return int(match.group(1))
        palabras = "|".join(re.escape(p) for p in sorted(self.NUMEROS, key=len, reverse=True))
        match = re.search(rf"{encabezado}.{{0,30}}?\b({palabras})\b\s*(?:porciento|por\s+ciento)?", texto, re.I)
        return self.NUMEROS.get(match.group(1).lower()) if match else None
    def estado_audio(self):
        try:
            estado = self.reproductor.obtener_estado()
        except Exception as error:
            print(f"[COMANDOS] Error obteniendo estado: {error}")
            return "Negativo. Estado del reproductor no disponible."
        cancion = estado.get("cancion_actual")
        volumen = estado.get("volumen", 0)
        if not cancion:
            return f"Sin reproducción activa. Volumen al {volumen} %."
        situacion = "pausada" if estado.get("pausado") else \
            "reproduciéndose" if estado.get("reproduciendo") else "detenida"
        return f"En curso: {cancion}. Estado: {situacion}. Volumen {volumen} %."
    def listar_audios(self):
        try:
            canciones = self.reproductor.obtener_canciones()
        except Exception as error:
            print(f"[COMANDOS] Error listando audios: {error}")
            return "Negativo. Biblioteca no accesible."
        if not canciones:
            return "Biblioteca vacía. Sin canciones."
        if len(canciones) == 1:
            return f"Una canción disponible: {canciones[0].stem}."
        nombres = ", ".join(c.stem for c in canciones[:5])
        respuesta = f"{len(canciones)} canciones disponibles. Primeras: {nombres}."
        return respuesta
    def agregar_cola_audio(self, texto):
        nombre = self.extraer_nombre(texto, self.PATRONES_COLA)
        if not nombre:
            # Si Cerebro ya extrajo el nombre, llega como texto simple.
            nombre = self._limpiar_nombre(texto)
            nombre = re.sub(
                r"^(?:agrega|agregar|añade|anade|añadir|anadir|pon|poner|mete|meter|introduce|introducir)\s+",
                "", nombre, flags=re.IGNORECASE,
            )
            nombre = re.sub(
                r"\s+(?:a|en)\s+(?:la\s+)?(?:cola|lista(?:\s+de\s+reproduccion)?)$",
                "", nombre, flags=re.IGNORECASE,
            ).strip()
        if not nombre or nombre.lower() in {
            "cancion", "la cancion", "musica", "la musica", "audio",
            "lista", "la lista", "cola", "la cola",
        }:
            return "¿Qué canción añado a la cola, señor?"
        try:
            cola_antes = self.reproductor.obtener_cola()
            cantidad_antes = len(cola_antes)
        except Exception:
            cantidad_antes = -1
        try:
            resultado = self.reproductor.agregar_a_cola(nombre)
            cola = self.reproductor.obtener_cola()
            agregada = len(cola) > cantidad_antes if cantidad_antes >= 0 else bool(resultado)
            if agregada:
                return f"Añadida a la cola: {cola[-1].stem}."
            if resultado and cola:
                return f"Añadida a la cola: {cola[-1].stem}."
            return f"Sin coincidencias para '{nombre}'."
        except Exception as error:
            print(f"[COMANDOS] Error agregando a la lista de reproducción: {error}")
            return "Negativo. No se añadió a la cola."
    def mostrar_cola_audio(self):
        try:
            cola = self.reproductor.obtener_cola()
            if not cola:
                return "Cola vacía."
            nombres = [a.name for a in cola]
            return (f"Cola: {len(nombres)} canciones. " + ", ".join(nombres) + ".")
        except Exception as error:
            print(f"[COMANDOS] Error obteniendo lista de reproducción: {error}")
            return "Negativo. Cola no accesible."
    def limpiar_cola_audio(self):
        try:
            if self.reproductor.limpiar_cola():
                return "Cola despejada."
            try:
                if not self.reproductor.obtener_cola():
                    return "La cola ya está vacía."
            except Exception:
                pass
        except Exception as error:
            print(f"[COMANDOS] Error limpiando lista de reproducción: {error}")
        return "Negativo. Cola sin cambios."
    def quitar_cola_audio(self, texto):
        """Quita una canción de la cola por nombre o por posición (1 = la primera).
        Acepta: «quita beta de la cola», «quita la canción dos de la lista de reproducción»,
        «quita la canción en la posición 2», «quítame la pista número tres»."""
        import unicodedata

        def sin_tildes(valor):
            return "".join(c for c in unicodedata.normalize("NFD", str(valor or "").lower())
                           if unicodedata.category(c) != "Mn").strip()

        t = sin_tildes(texto)
        t = re.sub(r"^miller[\s,]+", "", t)
        t = re.sub(r"^(?:quita|quitar|quitame|elimina|eliminar|borra|borrar|saca|sacar)\s+", "", t)
        limpiezas = (
            (r"\s+(?:de|en)\s+(?:la\s+)?(?:cola|lista(?:\s+de\s+reproduccion)?)(?:\s+de\s+reproduccion)?\s*$", ""),
            (r"^(?:de|en)\s+(?:la\s+)?(?:cola|lista(?:\s+de\s+reproduccion)?)(?:\s+de\s+reproduccion)?(?:\s+|$)", ""),
            (r"^(?:en\s+)?(?:la|el|un|una)\s+", ""),
            (r"^(?:cancion|audio|pista|tema|musica)\s+", ""),
            (r"^(?:en\s+la\s+|la\s+|en\s+)?(?:posicion|numero)\s+", ""),
        )
        for _ in range(2):                         # dos pasadas: «quitar canción de la cola alfa»
            for patron, cambio in limpiezas:
                t = re.sub(patron, cambio, t)
        objetivo = t.strip(" .,!¡¿?")
        if not objetivo or objetivo in ("cancion", "audio", "pista", "tema", "musica", "la cancion", "la pista"):
            return "Indique canción o posición a retirar de la cola."
        try:
            cola = self.reproductor.obtener_cola()
            if not cola:
                return "Cola vacía."
            numero = self.NUMEROS.get(objetivo)
            if numero is None and objetivo.isdigit():
                numero = int(objetivo)
            if numero is not None:
                if numero < 1 or numero > len(cola):
                    return f"Posición {numero} inexistente en la cola."
                nombre = cola[numero - 1].name
                eliminar = getattr(self.reproductor, "eliminar_de_cola", None)
                if callable(eliminar):
                    ok = eliminar(numero)                      # posición 1-based
                else:
                    quitar = getattr(self.reproductor, "quitar_de_cola", None)
                    ok = quitar(numero) if callable(quitar) else False
            else:
                # Primero palabra completa («beta» no es «alpha»); solo si no hay, coincidencia parcial.
                exacta = re.compile(r"\b" + re.escape(objetivo) + r"\b")
                coincidencias = [
                    (i, pista) for i, pista in enumerate(cola)
                    if exacta.search(sin_tildes(pista.name)) or exacta.search(sin_tildes(pista.stem))
                ] or [
                    (i, pista) for i, pista in enumerate(cola)
                    if objetivo in sin_tildes(pista.name) or objetivo in sin_tildes(pista.stem)
                ]
                if not coincidencias:
                    return f"'{objetivo}' no está en la cola."
                indice, pista = coincidencias[0]
                nombre = pista.name
                eliminar = getattr(self.reproductor, "eliminar_de_cola", None)
                if callable(eliminar):
                    ok = eliminar(indice + 1)                  # sale exactamente la pista encontrada
                else:
                    quitar = getattr(self.reproductor, "quitar_de_cola", None)
                    ok = quitar(nombre) if callable(quitar) else False
            if ok:
                return f"Retirada de la cola: {nombre}."
            cola_despues = self.reproductor.obtener_cola()
            if len(cola_despues) < len(cola):
                return f"Retirada de la cola: {nombre}."
            return f"Negativo. '{nombre}' sigue en la cola."
        except Exception as error:
            print(f"[COMANDOS] Error quitando canción de la lista: {error}")
            return "Fallo al modificar la cola."
    def aleatorio_audio(self):
        try:
            activo = self.reproductor.alternar_aleatorio()
            return "Modo aleatorio activado." if activo else "Modo aleatorio desactivado."
        except Exception as error:
            print(f"[COMANDOS] Error alternando aleatorio: {error}")
            return "Negativo. Modo aleatorio sin cambios."
    def repetir_audio(self):
        try:
            activo = self.reproductor.alternar_repetir()
            return "Repetición activada." if activo else "Repetición desactivada."
        except Exception as error:
            print(f"[COMANDOS] Error alternando repetición: {error}")
            return "Negativo. Repetición sin cambios."
    def extraer_nombre(self, texto, patrones):
        texto = (texto or "").strip()
        for patron in patrones:
            match = re.search(patron, texto, re.IGNORECASE)
            if match:
                nombre = self._limpiar_nombre(match.group(1))
                if nombre:
                    return nombre
        return None
    def estado_sistema(self):
        try:
            informacion = self.sistema.obtener_estado()
        except Exception as error:
            print(f"[COMANDOS] Error obteniendo estado del sistema: {error}")
            return "Negativo. Datos del sistema no disponibles."
        if not informacion:
            return "Negativo. Datos del sistema no disponibles."
        sistema = informacion.get("sistema_operativo", "No disponible")
        procesador = informacion.get("procesador", "No disponible")
        arquitectura = informacion.get("arquitectura", "No disponible")
        memoria = informacion.get("memoria", "No disponible")
        return (
            f"Sistema: {sistema}. Procesador: {procesador}. "
            f"Arquitectura: {arquitectura}. Memoria libre: {memoria}."
        )
    def tareas_en_curso(self):
        """Órdenes que siguen ejecutándose en segundo plano (MILLER no interrumpe mientras tanto)."""
        tareas = []
        try:
            if descargador_musica is not None and descargador_musica.obtener_progreso().get("estado") in (
                    "iniciando", "descargando", "convirtiendo"):
                tareas.append("descarga")
        except Exception:
            pass
        try:
            if self.probador is not None and self.probador.en_curso().get("activo"):
                tareas.append("pruebas")
        except Exception:
            pass
        try:
            if self.hay_limpieza_pendiente():
                tareas.append("confirmación pendiente")
            if self.supervisor is not None and self.supervisor.obtener_ultima_limpieza().get("estado") == "en_curso":
                tareas.append("limpieza")
        except Exception:
            pass
        return tareas
    def cerrar(self):
        """Cierra el reproductor una sola vez y libera referencias."""
        if getattr(self, "_cerrado", False):
            return
        self._cerrado = True
        if getattr(self, "ecualizador", None) is not None:
            self.ecualizador.guardar()
        if getattr(self, "alarmas", None) is not None:
            try:
                self.alarmas.detener()
            except Exception:
                pass
        # La descarga, el supervisor y las pruebas se detienen ANTES que el reproductor.
        if descargador_musica is not None:
            try:
                descargador_musica.cancelar()
            except Exception:
                pass
        probador = getattr(self, "probador", None)
        if probador is not None:
            try:
                probador.cerrar()
            except Exception as error:
                print(f"[COMANDOS] Error deteniendo las pruebas: {error}")
        self._detener_supervisor()
        reproductor = getattr(self, "reproductor", None)
        try:
            cerrar = getattr(reproductor, "cerrar", None)
            if callable(cerrar):
                cerrar()
        except Exception as error:
            print(f"[COMANDOS] Error cerrando reproductor: {error}")
        finally:
            self.reproductor = None
            self.rutina = None
            self.sistema = None
