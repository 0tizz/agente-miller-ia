"""MILLER · Prueba de perfiles propios, bandas en dB exactos y órdenes claras del ecualizador (sin audio)."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
import os
import tempfile
from pathlib import Path

_base = Path(tempfile.mkdtemp())
os.environ["MILLER_DIR_SEGURIDAD"] = str(_base / "seguridad")
fallos = []


def comprobar(condicion, mensaje):
    print(("  OK    " if condicion else "  FALLO ") + mensaje)
    if not condicion:
        fallos.append(mensaje)


from utilidades.ecualizador import Ecualizador, BANDAS
from cerebro.comandos import Comandos


class _Reproductor:
    cancion_actual = None
    fuente_actual = None

    def reaplicar_ecualizacion(self):
        pass


def nuevo_comandos(ruta):
    eq = Ecualizador(ruta, _base / "cache", ffmpeg=None)
    cmd = Comandos.__new__(Comandos)
    cmd.ecualizador = eq
    cmd.reproductor = _Reproductor()
    return cmd, eq


ruta = _base / "ecualizador.json"
cmd, eq = nuevo_comandos(ruta)

print("1. Crear un perfil propio con bandas")
r = cmd.controlar_ecualizador("crea perfil nocturno con graves 3 agudos -2")
comprobar(eq.estado["propios"].get("nocturno") == {"graves": 3.0, "medios": 0.0, "agudos": -2.0},
          "guarda graves 3, medios 0 y agudos -2")
comprobar("«nocturno» guardado" in r and "graves +3 dB" in r, "confirma con los valores: " + r[:70])

print("2. Ponerlo en uso")
r = cmd.controlar_ecualizador("pon perfil nocturno")
comprobar(eq.estado["modo"] == "perfil" and eq.estado["perfil"] == "nocturno", "pone el perfil propio en uso")
comprobar(eq.ganancias(None) == {"graves": 3.0, "medios": 0.0, "agudos": -2.0}, "las ganancias son las del perfil")

print("3. Persistencia: al reiniciar sigue el perfil")
cmd2, eq2 = nuevo_comandos(ruta)
comprobar("nocturno" in eq2.estado.get("propios", {}) and eq2.estado["perfil"] == "nocturno",
          "el perfil y su curva se recuperan del archivo firmado")

print("4. Nombres que no sirven")
comprobar("de fábrica" in cmd.controlar_ecualizador("crea perfil rock con graves 1"), "no pisa un perfil de fábrica")
comprobar(cmd.controlar_ecualizador("crea perfil automatico").startswith("Negativo"), "no admite nombres reservados")
comprobar(cmd.controlar_ecualizador("crea perfil con graves 3").startswith("Dígame"), "pide el nombre si falta")
r = cmd.controlar_ecualizador("crea perfil Mañanera con graves 1")
comprobar("mananera" in eq.estado["propios"], "quita tildes del nombre: " + r[:50])

print("5. Bandas en un valor exacto (modo manual)")
cmd.controlar_ecualizador("pon perfil plano")
r = cmd.controlar_ecualizador("pon los graves en 4")
g = eq.ganancias(None)
comprobar(eq.estado["modo"] == "manual" and g["graves"] == 4.0 and g["agudos"] == 0.0 and g["medios"] == 0.0,
          "graves a 4 dB y las demás bandas igual: " + str(g))
comprobar("manual" in eq.describir(None), "describe el modo manual")
r = cmd.controlar_ecualizador("pon agudos en 10")
comprobar(eq.ganancias(None)["agudos"] == 6.0 and "+6 dB" in r, "el máximo es ±6 dB y lo dice")

print("6. Subir y bajar siguen funcionando")
cmd.controlar_ecualizador("pon perfil plano")
r = cmd.controlar_ecualizador("sube los graves")
comprobar(eq.estado["preferencias"]["global"]["graves"] == 2.0 and r.startswith("Subo"), "sube 2 dB lo aprendido")
cmd.controlar_ecualizador("baja los graves")
comprobar(eq.estado["preferencias"]["global"]["graves"] == 0.0, "baja y vuelve a 0")

print("7. Borrar perfiles")
r = cmd.controlar_ecualizador("borra perfil nocturno")
comprobar("nocturno" not in eq.estado["propios"] and r.startswith("Afirmativo"), "borra el perfil propio")
comprobar(eq.estado["perfil"] == "plano", "si estaba en uso, vuelve a plano")
comprobar("de fábrica" in cmd.controlar_ecualizador("borra perfil rock"), "no borra perfiles de fábrica")
comprobar("No tengo" in cmd.controlar_ecualizador("borra perfil fantasma"), "avisa si no existe")

print("8. Lista y límite")
lista = cmd.controlar_ecualizador("lista de perfiles")
comprobar("rock" in lista and "Propios: mananera" in lista, "lista perfiles de fábrica y propios: " + lista[-40:])
for n in range(len(eq.estado["propios"]), 20):
    cmd.controlar_ecualizador(f"crea perfil prueba{n} con graves 1")
comprobar(len(eq.estado["propios"]) == 20, "hasta 20 perfiles propios")
comprobar(cmd.controlar_ecualizador("crea perfil uno mas con graves 1").startswith("Negativo"), "el 21 se rechaza")

print("9. Automático y perfiles de fábrica")
r = cmd.controlar_ecualizador("ecualizador automatico")
comprobar(eq.estado["modo"] == "automatico", "pasa a automático")
r = cmd.controlar_ecualizador("pon perfil rock")
comprobar(eq.estado["perfil"] == "rock" and "rock" in r, "perfil de fábrica rock: " + r[:60])
comprobar(eq.buscar_perfil("pon el perfil de rock") == "rock", "encuentra el perfil dentro de una frase")

print()
if fallos:
    print(f"FALLOS: {len(fallos)}")
    raise SystemExit(1)
print("TODO OK")
