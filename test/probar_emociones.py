"""MILLER · test.probar_emociones: PRUEBA: emociones de MILLER en segundo plano (cerebro/emociones.py) y su efecto en la iniciativa."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent      # carpeta raíz de MILLER
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
import tempfile
import time
from pathlib import Path
from cerebro.emociones import Emociones
from cerebro.iniciativa import Iniciativa
fallos = []


def comprobar(condicion, mensaje):
    print(("  OK    " if condicion else "  FALLO ") + mensaje)
    if not condicion:
        fallos.append(mensaje)


carpeta = Path(tempfile.mkdtemp())
e = Emociones(ruta=carpeta / "emociones.json")
print("1. Empieza en calma")
comprobar(e.estado()["emocion"] == "calma", f"estado inicial: {e.describir()}")
print("2. Órdenes cumplidas -> satisfacción")
for _ in range(6):
    e.registrar_orden("REPRODUCIR_MUSICA", "pon musica", "Reproduciendo Flaca.")
comprobar(e.estado()["emocion"] == "satisfaccion", f"{e.describir()}")
print("3. Fallos seguidos -> frustración")
for _ in range(4):
    e.registrar_orden("PREGUNTA_INTERNET", "quien gano", "Fallo de conexión. Consulta abortada.", ok=False)
comprobar(e.estado()["emocion"] == "frustracion", f"{e.describir()}")
deseo = e.algo_que_expresar()
comprobar(deseo is not None and "micrófono" in deseo[1], f"quiere expresarlo: {deseo and deseo[1]}")
comprobar(e.algo_que_expresar() is None, "no repite la misma emoción enseguida")
print("4. Un elogio -> alegría")
for _ in range(2):
    e.registrar_orden("DESCONOCIDA", "gracias miller bien hecho", "Orden no comprendida.", ok=True)
comprobar(e.estado()["emocion"] in ("alegria", "orgullo"), f"{e.describir()}")
print("5. Las emociones se desvanecen solas hacia la calma")
futuro = time.monotonic() + 6 * 3600
e._ultima_orden = futuro                     # simula que hubo órdenes (sin aburrimiento)
e.tick(futuro)
comprobar(e.estado()["emocion"] == "calma", f"6 horas después: {e.describir()}")
print("5b. Sin órdenes durante mucho rato -> aburrimiento, con tope")
b = Emociones()
b._ultima_orden -= 3600
for paso in range(1, 200):
    b.tick(b._ultimo_tick + 10)
comprobar(b.estado()["emocion"] == "aburrimiento" and b.intensidad["aburrimiento"] <= 0.65,
          f"{b.describir()} ({round(b.intensidad['aburrimiento'], 2)})")
print("6. Experiencias del programa")
e.registrar_evento("pruebas_fallo", "voz")
comprobar(e.estado()["emocion"] == "preocupacion", f"pruebas fallidas: {e.describir()}")
print("7. La personalidad cambia despacio y se guarda")
antes = dict(e.rasgos)
for _ in range(30):
    e.registrar_orden("SIGUIENTE_CANCION", "siguiente", "Reproduciendo Flaca.")
comprobar(e.rasgos["confianza"] > antes["confianza"], f"confianza {antes['confianza']} -> {round(e.rasgos['confianza'], 3)}")
comprobar(e.rasgos["confianza"] - antes["confianza"] < 0.1, "el cambio es lento")
e.guardar()
otra = Emociones(ruta=carpeta / "emociones.json")
comprobar(abs(otra.rasgos["confianza"] - e.rasgos["confianza"]) < 0.001, "personalidad recordada al reiniciar")
print("8. El estado emocional modula la iniciativa (siempre con permiso)")


class CerebroFalso:
    comandos = None
    memoria = None
    emociones = Emociones()


c = CerebroFalso()
ini = Iniciativa(c, intervalo_minimo=100, silencio_previo=0, espera_autorizacion=5)
base = c.emociones.factor_iniciativa()
for _ in range(3):
    c.emociones.registrar_evento("nombre_aprendido", "mi lee")
comprobar(c.emociones.factor_iniciativa() < base, f"con curiosidad tiene más ganas de hablar ({base} -> {c.emociones.factor_iniciativa()})")
ini.agregar("x", "prueba de tono.", 2)
ini.pedir_permiso()
texto = ini.entregar()
comprobar(texto.startswith(("Señor, he notado algo", "Observación, señor")), f"tono según la emoción: {texto}")
futuro = time.monotonic() + 6 * 3600
c.emociones._ultima_orden = futuro
c.emociones.tick(futuro)
for _ in range(3):
    ini.agregar(f"y{_}", "otro asunto.", 1)
    ini.pedir_permiso()
    ini.posponer()
c.emociones.contadores["permisos_concedidos"] = 1
comprobar(c.emociones.factor_iniciativa() > 1.0, f"tras varias negativas es más prudente ({c.emociones.factor_iniciativa()})")
comprobar(ini.pedir_permiso() == "Permiso para hablar, señor.", "la frase de permiso no cambia")
print()
print("RESULTADO:", "OK" if not fallos else f"FALLO ({len(fallos)})")
if fallos:
    raise SystemExit(1)
