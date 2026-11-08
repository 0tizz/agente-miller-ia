"""MILLER · Probador de módulos."""
import json
import os
import tempfile
import re
import subprocess
import sys
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path
try:
    from configuracion import RUTA_BASE as RAIZ          # funciona también en el .exe
except Exception:
    RAIZ = Path(__file__).resolve().parent.parent
CARPETA_TEST = RAIZ / "test"
CARPETA_RESULTADOS = RAIZ / "datos" / "pruebas"
# Frase que puede decir el usuario -> nombre de la prueba (probar_<nombre>.py)
ALIAS = {
    "voz multiple": "voz_multiple", "varias voces": "voz_multiple", "voces": "voz_multiple",
    "voz": "voz", "hablador": "voz", "sintesis": "voz", "habla": "voz",
    "escuchador": "escuchador", "microfono": "escuchador", "escucha": "escuchador",
    "oido": "escuchador", "reconocimiento": "escuchador",
    "modelo de voz": "modelo_vosk", "modelo vosk": "modelo_vosk", "modelo": "modelo_vosk",
    "vosk": "vosk",
    "activador": "activador", "palabra de activacion": "activador", "activacion": "activador",
    "reproductor": "reproductor", "musica": "reproductor",
    "analizador": "analizador",
    "supervisor": "supervisor", "biblioteca": "supervisor",
    "emociones": "emociones", "emocion": "emociones", "sentimientos": "emociones", "personalidad": "emociones",
    "iniciativa": "iniciativa", "permiso": "iniciativa", "permiso para hablar": "iniciativa",
    "papelera": "papelera", "borrar": "papelera",
    "nombre": "nombre", "aprendizaje del nombre": "nombre",
    "volumen": "volumen", "fundido": "volumen", "fade": "volumen",
    "descargador": "descarga", "descargas": "descarga", "descarga": "descarga",
    "controlador": "controlador",
    "cerebro": "cerebro", "intenciones": "cerebro", "comandos": "cerebro",
    "atenuador": "atenuador", "atenuacion": "atenuador", "ducking": "atenuador",
    "programas": "programas", "aplicaciones": "programas", "catalogo": "programas",
    "memoria": "memoria", "aprendizaje": "memoria",
    "internet": "internet", "busqueda": "internet", "red": "internet",
}

def _normalizar(texto):
    texto = unicodedata.normalize("NFD", str(texto or "").lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", texto)).strip()

class ProbadorModulos:
    TIMEOUT = 120          # segundos por prueba automática
    TIMEOUT_MICROFONO = 45
    def __init__(self, carpeta_test=CARPETA_TEST, carpeta_resultados=CARPETA_RESULTADOS):
        self.carpeta_test = Path(carpeta_test)
        self.carpeta_resultados = Path(carpeta_resultados)
        self._lock = threading.Lock()
        self._hilo = None
        self._proceso = None
        self._resultados = {}
        self._en_curso = None
        self._cancelar = threading.Event()
    def listar(self):
        """{nombre: ruta} de todas las pruebas (test/probar_*.py)."""
        if getattr(sys, "frozen", False) or not self.carpeta_test.is_dir():   # en el .exe no hay Python para lanzarlas
            return {}
        return {p.stem[len("probar_"):]: p for p in sorted(self.carpeta_test.glob("probar_*.py"))}
    @staticmethod
    def nombre_legible(nombre):
        return nombre.replace("_", " ")
    def buscar(self, texto):
        """Devuelve el nombre de la prueba que corresponde al texto, o None."""
        pruebas = self.listar()
        t = _normalizar(texto)
        for nombre in sorted(pruebas, key=len, reverse=True):       # nombre exacto
            if re.search(rf"\b{re.escape(self.nombre_legible(nombre))}\b", t):
                return nombre
        for alias in sorted(ALIAS, key=len, reverse=True):             # alias
            if re.search(rf"\b{re.escape(alias)}\b", t) and ALIAS[alias] in pruebas:
                return ALIAS[alias]
        return None
    def tipo(self, nombre):
        """'vacia' | 'interactiva' | 'microfono' | 'automatica'."""
        ruta = self.listar().get(nombre)
        try:
            codigo = ruta.read_text(encoding="utf-8", errors="replace") if ruta else ""
        except OSError:
            codigo = ""
        if not codigo.strip():
            return "vacia"
        if re.search(r"\binput\s*\(", codigo):
            return "interactiva"
        if re.search(r"\.escuchar\s*\(", codigo):
            return "microfono"
        return "automatica"
    def ejecutar(self, nombre):
        """Ejecuta UNA prueba y espera su resultado (salvo las interactivas)."""
        ruta = self.listar().get(nombre)
        if ruta is None:
            return {"nombre": nombre, "estado": "no_existe"}
        tipo = self.tipo(nombre)
        if tipo == "vacia":
            return self._guardar({"nombre": nombre, "estado": "vacia", "tipo": tipo})
        if tipo == "interactiva":
            return self._abrir_en_ventana(nombre, ruta)
        return self._ejecutar_capturando(nombre, ruta, tipo)
    def ejecutar_todas(self, al_terminar=None):
        """Lanza en segundo plano todas las pruebas automáticas. Devuelve el plan."""
        with self._lock:
            if self._hilo and self._hilo.is_alive():
                return None
            pruebas = self.listar()
            automaticas = [n for n in pruebas if self.tipo(n) in ("automatica", "microfono")]
            omitidas = [n for n in pruebas if n not in automaticas]
            self._cancelar.clear()
            self._resultados = {}
            self._hilo = threading.Thread(target=self._bucle_todas, args=(automaticas, al_terminar),
                                          daemon=True, name="MILLER-Probador")
            self._hilo.start()
        return {"ejecutando": automaticas, "omitidas": omitidas}
    def _bucle_todas(self, nombres, al_terminar):
        for nombre in nombres:
            if self._cancelar.is_set():
                break
            self.ejecutar(nombre)
        with self._lock:
            self._en_curso = None
        if callable(al_terminar):
            try:
                al_terminar(self.resultados())
            except Exception:
                pass
    def en_curso(self):
        with self._lock:
            activo = bool(self._hilo and self._hilo.is_alive())
            return {"activo": activo, "prueba": self._en_curso}
    def resultados(self):
        with self._lock:
            return dict(self._resultados)
    def cancelar(self):
        self._cancelar.set()
        proc = self._proceso
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass
    def cerrar(self):
        self.cancelar()
    def _entorno(self):
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTHONUNBUFFERED="1")
        env["PYTHONPATH"] = str(RAIZ) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        # Las pruebas firman y aíslan en una carpeta temporal: nunca ensucian datos/seguridad.
        env["MILLER_DIR_SEGURIDAD"] = os.path.join(tempfile.gettempdir(), "miller_pruebas_seguridad")
        return env
    def _abrir_en_ventana(self, nombre, ruta):
        if os.name != "nt":
            return self._guardar({"nombre": nombre, "estado": "interactiva", "tipo": "interactiva",
                                  "detalle": f"ejecútala a mano: python {ruta.relative_to(RAIZ)}"})
        try:
            subprocess.Popen([sys.executable, str(ruta)], cwd=str(RAIZ), env=self._entorno(),
                             creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0x10))
            estado = "abierta_en_ventana"
        except OSError as error:
            estado = "error"
            return self._guardar({"nombre": nombre, "estado": estado, "tipo": "interactiva", "detalle": str(error)})
        return self._guardar({"nombre": nombre, "estado": estado, "tipo": "interactiva"})
    def _ejecutar_capturando(self, nombre, ruta, tipo):
        limite = self.TIMEOUT_MICROFONO if tipo == "microfono" else self.TIMEOUT
        with self._lock:
            self._en_curso = nombre
        inicio, lineas = time.monotonic(), []
        print(f"[ TEST {nombre} ] Iniciando {ruta.name}...")
        try:
            proc = subprocess.Popen([sys.executable, str(ruta)], cwd=str(RAIZ), env=self._entorno(),
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace")
        except OSError as error:
            return self._guardar({"nombre": nombre, "estado": "error", "tipo": tipo, "detalle": str(error)})
        self._proceso = proc
        tiempo_agotado = threading.Event()
        def vigilar():
            while proc.poll() is None:
                if time.monotonic() - inicio > limite or self._cancelar.is_set():
                    tiempo_agotado.set()
                    try:
                        proc.kill()
                    except OSError:
                        pass
                    return
                time.sleep(0.2)
        threading.Thread(target=vigilar, daemon=True).start()
        for linea in proc.stdout:
            linea = linea.rstrip()
            lineas.append(linea)
            print(f"[ TEST {nombre} ] {linea}")
        proc.wait()
        self._proceso = None
        duracion = round(time.monotonic() - inicio, 1)
        salida = "\n".join(lineas)
        error = next((l for l in reversed(lineas) if re.match(r"^\w*(Error|Exception)\b", l)), "")
        if tiempo_agotado.is_set():
            estado = "tiempo_agotado"
        elif proc.returncode == 0 and "Traceback (most recent call last)" not in salida:
            estado = "ok"
        else:
            estado = "fallo"
        resultado = {"nombre": nombre, "estado": estado, "tipo": tipo, "codigo": proc.returncode,
                     "duracion": duracion, "error": error[:200],
                     "ultima_linea": next((l for l in reversed(lineas) if l.strip()), "")[:200]}
        self._guardar(resultado, salida)
        print(f"[ TEST {nombre} ] Resultado: {estado} ({duracion} s)")
        return resultado
    def _guardar(self, resultado, salida=None):
        resultado["fecha"] = datetime.now().isoformat(timespec="seconds")
        with self._lock:
            self._resultados[resultado["nombre"]] = resultado
            if self._en_curso == resultado["nombre"]:
                self._en_curso = None
        try:
            self.carpeta_resultados.mkdir(parents=True, exist_ok=True)
            if salida is not None:
                (self.carpeta_resultados / f"{resultado['nombre']}.log").write_text(salida, encoding="utf-8")
            (self.carpeta_resultados / "ultimos_resultados.json").write_text(
                json.dumps(self.resultados(), ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
        return resultado
