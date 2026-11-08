"""MILLER · test.probar_iniciativa: PRUEBA: MILLER pide permiso para hablar y no interrumpe órdenes (cerebro/iniciativa.py)."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent      # carpeta raíz de MILLER
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
import tempfile
import time
from pathlib import Path
from cerebro.iniciativa import Iniciativa, ALTA, BAJA
fallos = []
def comprobar(condicion, mensaje):
    print(("  OK    " if condicion else "  FALLO ") + mensaje)
    if not condicion:
        fallos.append(mensaje)
class ComandosFalsos:
    supervisor = probador = reproductor = None
    tareas = []
    def tareas_en_curso(self):
        return list(self.tareas)
class CerebroFalso:
    comandos = ComandosFalsos()
    memoria = None
    rutina_matutina_activa = False
    cancion_pendiente = cola_pendiente = volumen_pendiente = tema_memoria_pendiente = False
ruta = Path(tempfile.mkdtemp()) / "iniciativa.json"
c = CerebroFalso()
ini = Iniciativa(c, ruta_estado=ruta, intervalo_minimo=0, intervalo_urgente=0, silencio_previo=0,
                 espera_autorizacion=1.0, max_peticiones_hora=100)
print("1. Sin nada que decir, no pide permiso")
comprobar(not ini.debe_pedir_permiso(), "sin asuntos")
ini.agregar("prueba:1", "he aprendido a reconocer «mi lee» como mi nombre.", ALTA)
comprobar(ini.debe_pedir_permiso(), "con un asunto quiere hablar")
print("2. Nunca interrumpe una orden en ejecución")
with ini.ocupado():
    comprobar(not ini.debe_pedir_permiso(), "orden en curso: espera")
c.comandos.tareas = ["descarga"]
comprobar(not ini.debe_pedir_permiso(), "descarga en curso: espera")
c.comandos.tareas = []
ini.silencio_previo = 5
ini.marcar_actividad()
comprobar(not ini.debe_pedir_permiso(), "acaba de oír hablar: espera")
ini.silencio_previo = 0
print("3. Pide permiso y espera autorización")
frase = ini.pedir_permiso()
comprobar(frase == "Permiso para hablar, señor.", f"dice: {frase}")
comprobar(ini.esta_esperando() and not ini.debe_pedir_permiso(), "en espera, no repite la petición")
for t in ("adelante", "Miller, adelante", "diga", "siga", "hable señor", "proceda", "miller diga"):
    comprobar(ini.interpretar(t) == "autoriza", f"'{t}' autoriza")
for t in ("ahora no", "después", "negativo", "más tarde"):
    comprobar(ini.interpretar(t) == "deniega", f"'{t}' deniega")
for t in ("pon la resaca", "permiso para hablar señor", "sube el volumen"):
    comprobar(ini.interpretar(t) is None, f"'{t}' no es respuesta")
texto = ini.entregar()
comprobar("mi lee" in texto and not ini.esta_esperando(), f"autorizado, informa: {texto}")
comprobar(not ini.pendientes(), "asunto entregado")
comprobar(not ini.agregar("prueba:1", "repetido"), "lo dicho no se repite")
print("4. Denegar o no responder lo guarda para más tarde")
ini.agregar("prueba:2", "segundo asunto.", BAJA)
ini.pedir_permiso()
ini.posponer()
comprobar(len(ini.pendientes()) == 1 and not ini.esta_esperando(), "denegado: sigue pendiente")
ini.pedir_permiso()
time.sleep(1.2)
comprobar(not ini.esta_esperando() and len(ini.pendientes()) == 1, "sin respuesta: caduca y sigue pendiente")
ini.pedir_permiso()
ini.retirar_peticion()
comprobar(not ini.esta_esperando() and len(ini.pendientes()) == 1, "otra orden: retira la petición")
print("5. Desactivada no pide permiso")
ini.activa = False
comprobar(not ini.debe_pedir_permiso(), "iniciativa en pausa")
ini.detener()
otra = Iniciativa(c, ruta_estado=ruta)
comprobar(not otra.agregar("prueba:1", "x"), "recuerda lo dicho tras reiniciar")
print()
print("RESULTADO:", "OK" if not fallos else f"FALLO ({len(fallos)})")
if fallos:
    raise SystemExit(1)
