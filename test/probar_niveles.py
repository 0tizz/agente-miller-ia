"""Prueba no interactiva: niveles FREE / NIÑOS / PRO, llave BOY (huella y cascada) y supervisor PRO.
Trabaja en una carpeta temporal; nunca toca audios/ ni datos reales."""
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

TEMPORAL = Path(tempfile.mkdtemp(prefix="miller_niveles_"))
import os  # noqa: E402
os.environ["MILLER_DIR_SEGURIDAD"] = str(TEMPORAL / "seguridad")
import configuracion  # noqa: E402

configuracion.RUTA_DATOS = TEMPORAL / "datos"
configuracion.RUTA_BASE = TEMPORAL / "miller"
from utilidades import acceso, llave_boy  # noqa: E402
import ayuda_llave_boy  # noqa: E402
import ayuda_llave_pro  # noqa: E402

acceso.RUTA = TEMPORAL / "acceso.json"
llave_boy.RUTA = TEMPORAL / "llave_boy.json"
fallos = 0


def comprobar(nombre, condicion, detalle=""):
    global fallos
    if condicion:
        print(f"  OK    {nombre}")
    else:
        fallos += 1
        print(f"  FALLO {nombre} {detalle}")


print("1. Llave BOY: huella y descubrimiento en la cascada")
comprobar("una llave BOY falsa no vale", not llave_boy.verificar("BOY-AAAA-BBBB-CCCC"))
llave = ayuda_llave_boy.preparar()
comprobar("la llave BOY vale aunque MILLER no la haya descubierto",
          llave_boy.verificar(llave) and llave_boy.progreso() == 0)
comprobar("la llave BOY vale escrita sin guiones y en minúsculas", llave_boy.verificar(llave.replace("-", "").lower()))
fragmentos = list(llave_boy._fragmentos())
comprobar("sin fragmentos, MILLER tiene uno pendiente para dejar caer", llave_boy.fragmento_pendiente() in fragmentos)
estado, _ = llave_boy.observar("hola")
comprobar("una palabra ajena no es fragmento", estado is None)
estado, _ = llave_boy.observar(fragmentos[0])
comprobar("un fragmento nuevo se guarda", estado == "pieza" and llave_boy.progreso() == 1)
estado, _ = llave_boy.observar("BOY-" + fragmentos[0])
comprobar("un fragmento repetido no cuenta otra vez", estado == "repetida" and llave_boy.progreso() == 1)
llave_boy.observar(fragmentos[1])
comprobar("con dos fragmentos aún no hay llave encontrada", llave_boy.progreso() == 2 and not llave_boy.completado())
comprobar("con dos fragmentos el pendiente es el último", llave_boy.fragmento_pendiente() == fragmentos[2])
estado, texto = llave_boy.observar(fragmentos[2])
comprobar("con los tres fragmentos MILLER encuentra la llave", estado == "encontrada" and texto == llave
          and llave_boy.completado())
comprobar("ya encontrada, no quedan fragmentos que dejar caer", llave_boy.fragmento_pendiente() is None)
llave_boy._guardar({})
llave_boy.marcar_conocida()
comprobar("la llave puesta en la tarjeta no da aviso de descubrimiento",
          llave_boy.completado() and llave_boy.observar(fragmentos[0])[0] == "repetida")
llave_boy._guardar({})
print("2. Acceso con la llave BOY")
acceso.quitar(None)
claros = {"pro": ayuda_llave_pro.preparar()}
comprobar("la llave PRO de prueba se prepara; la BOY no", set(claros) == {"pro"})
comprobar("la llave BOY pone el modo NIÑOS", acceso.poner("boy", llave).startswith("Afirmativo") and acceso.modo() == "boy")
acceso.quitar(None)
comprobar("una llave PRO no va en la casilla BOY", "no va en esta casilla" in acceso.poner("boy", claros["pro"]))
acceso.poner("pro", claros["pro"])
comprobar("la llave PRO manda sobre NIÑOS", acceso.modo() == "pro")
print("3. Qué pide cada nivel")
acceso.quitar(None)
comprobar("FREE: buscar en internet es NIÑOS", acceso.bloqueo("BUSCAR_INTERNET") is not None)
comprobar("FREE: estado de la biblioteca es estándar", acceso.bloqueo("ESTADO_BIBLIOTECA") is None)
comprobar("FREE: reproducir y el ecualizador son estándar", acceso.bloqueo("REPRODUCIR_CANCION") is None)
comprobar("FREE: varios comandos en una frase es PRO", acceso.bloqueo("ORDEN_MULTIPLE") is not None)
comprobar("FREE: reparar la biblioteca es PRO", acceso.bloqueo("REPARAR_BIBLIOTECA") is not None)
acceso.poner("boy", llave)
comprobar("NIÑOS: buscar en internet se permite", acceso.bloqueo("BUSCAR_INTERNET") is None)
comprobar("NIÑOS: reparar la biblioteca sigue siendo PRO", acceso.bloqueo("REPARAR_BIBLIOTECA") is not None)
acceso.poner("pro", claros["pro"])
comprobar("PRO: varios comandos en una frase se permiten", acceso.bloqueo("ORDEN_MULTIPLE") is None)
comprobar("PRO: el supervisor se puede pausar", acceso.bloqueo("PAUSAR_SUPERVISOR") is None)
print("4. El supervisor sigue al modo PRO")
from cerebro.comandos import Comandos  # noqa: E402
acceso.quitar(None)
registro = []
comandos = Comandos.__new__(Comandos)
comandos.supervisor = None
comandos._iniciar_supervisor = lambda: registro.append("arranca")
comandos._detener_supervisor = lambda: registro.append("para")
comandos._supervisor_segun_modo("pro")
comprobar("con modo PRO el supervisor arranca", registro == ["arranca"], str(registro))
registro.clear()
comandos._supervisor_segun_modo("boy")
comprobar("con modo NIÑOS el supervisor se para", registro == ["para"], str(registro))
registro.clear()
acceso.al_cambiar_modo(comandos._supervisor_segun_modo)
acceso.poner("pro", claros["pro"])
comprobar("al poner la llave PRO se avisa al supervisor", "arranca" in registro, str(registro))
registro.clear()
acceso.quitar(None)
comprobar("al retirar la llave PRO el supervisor se para", "para" in registro, str(registro))
print(f"Resultado: {'todo correcto' if not fallos else str(fallos) + ' fallo(s)'}")
raise SystemExit(1 if fallos else 0)
