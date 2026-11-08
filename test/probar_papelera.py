"""MILLER · test.probar_papelera: PRUEBA: "Miller, borra <canción>" la mueve a cuarentena/papelera y se puede restaurar."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent      # carpeta raíz de MILLER
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
import tempfile
import wave
from pathlib import Path
try:
    import pygame  # noqa: F401
except ImportError:                       # entorno sin pygame: módulo simulado
    import types
    class _M:
        def __getattr__(self, n):
            return lambda *a, **k: None
    pygame = types.ModuleType("pygame"); pygame.mixer = _M(); pygame.mixer.music = _M(); pygame.init = lambda *a, **k: None
    _sys.modules["pygame"] = pygame
from audio.supervisor_biblioteca import ConfigSupervisor, SupervisorBiblioteca
from cerebro.comandos import Comandos
from cerebro.cerebro import Cerebro
fallos = []
def comprobar(condicion, mensaje):
    print(("  OK    " if condicion else "  FALLO ") + mensaje)
    if not condicion:
        fallos.append(mensaje)
base = Path(tempfile.mkdtemp())
audios = base / "audios"; audios.mkdir(); (base / "datos").mkdir()
def wav(nombre):
    with wave.open(str(audios / nombre), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(b"\0\0" * 8000)
    return audios / nombre
for n in ("La Resaca.wav", "Amorfoda.wav", "Soy Peor.wav", "Flaca.wav"):
    wav(n)
class ReproductorFalso:
    EXTENSIONES_AUDIO = {".wav", ".mp3"}
    def __init__(self):
        self.carpeta, self.ruta_memoria = audios, base / "datos" / "memoriamusical.json"
        self.cancion_actual, self.cola, self.historial = None, [], []
        self.cerrado, self.memoria_musical, self.sonando = False, {}, False
    def obtener_canciones(self):
        return sorted(p for p in audios.iterdir() if p.is_file())
    def actualizar_lista(self):
        return self.obtener_canciones()
    def obtener_ruta_actual(self):
        return self.cancion_actual
    def obtener_cola(self):
        return list(self.cola)
    def quitar_de_cola(self, nombre):
        self.cola = [p for p in self.cola if p.name != nombre]
        return True
    def esta_reproduciendo(self):
        return self.sonando
    def siguiente(self):
        if self.cancion_actual:
            self.historial.append(self.cancion_actual)
        otras = [p for p in self.obtener_canciones() if p != self.cancion_actual]
        self.cancion_actual = otras[0] if otras else None
        return True
    def detener(self):
        self.sonando = False
        return True
rep = ReproductorFalso()
sup = SupervisorBiblioteca(rep, config=ConfigSupervisor(modo="observar", eliminacion_automatica=True))
com = object.__new__(Comandos)
com.reproductor, com.supervisor, com._limpieza_por_confirmar = rep, sup, None
print("1. Reconoce la orden")
cer = object.__new__(Cerebro)
for frase, esperada in (("borra la resaca", "BORRAR_CANCION"), ("miller elimina la cancion amorfoda", "BORRAR_CANCION"),
                        ("manda soy peor a la papelera", "BORRAR_CANCION"), ("borra esta cancion", "BORRAR_CANCION"),
                        ("que hay en la papelera", "LISTAR_PAPELERA"), ("vacia la papelera", "VACIAR_PAPELERA"),
                        ("quita la resaca de la cola", "QUITAR_COLA_AUDIO"), ("borra los duplicados", "LIMPIAR_BIBLIOTECA"),
                        ("vacia la cuarentena", "VACIAR_CUARENTENA"), ("restaura la resaca", "RESTAURAR_CUARENTENA")):
    obtenida = cer.detectar_intencion(frase)
    comprobar(obtenida == esperada, f"'{frase}' -> {obtenida}")
print("2. Mueve la canción a cuarentena/papelera")
r = com.borrar_cancion("borra la resaca")
comprobar(not (audios / "La Resaca.wav").exists(), f"sale de la biblioteca ({r})")
comprobar(any(p.name.endswith("La Resaca.wav") for p in (audios / "cuarentena" / "papelera").iterdir()), "está en cuarentena/papelera")
comprobar("La Resaca" in com.listar_papelera(), "aparece en la papelera")
print("3. Canción sonando o en cola: se suelta antes de moverla")
rep.cancion_actual, rep.sonando = audios / "Amorfoda.wav", True
rep.cola = [audios / "Soy Peor.wav"]
r = com.borrar_cancion("borra esta cancion")
comprobar(not (audios / "Amorfoda.wav").exists() and rep.cancion_actual != audios / "Amorfoda.wav", f"la actual pasa a la siguiente y se borra ({r})")
r = com.borrar_cancion("borra soy peor")
comprobar(not (audios / "Soy Peor.wav").exists() and not rep.cola, f"retirada de la cola y borrada ({r})")
print("4. No borra a ciegas")
r = com.borrar_cancion("borra la cancion despacito")
comprobar((audios / "Flaca.wav").exists() and "no está" in r, f"nombre inexistente: {r}")
print("5. Restaurar y plan de eliminación")
comprobar(sup.restaurar_de_cuarentena(next(e["id"] for e in sup.listar_cuarentena() if e["nombre"] == "La Resaca.wav")),
          "restaurada")
comprobar((audios / "La Resaca.wav").exists(), "vuelve a la biblioteca")
plan = [p for p in sup.plan_eliminacion() if p["categoria"] == "papelera"]
comprobar(plan and all(29 <= p["dias_restantes"] <= 30 for p in plan), "papelera: se borra sola a los 30 días")
sup.detener()
print()
print("RESULTADO:", "OK" if not fallos else f"FALLO ({len(fallos)})")
if fallos:
    raise SystemExit(1)
