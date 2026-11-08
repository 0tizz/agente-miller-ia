"""MILLER · Prueba de sinónimos: aprende explícito, aprende solo por reformulación, ámbito por orden y olvido."""
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


from cerebro.cerebro import Cerebro
from cerebro.memoria import Memoria

memoria = Memoria(_base / "memoria.json")
cer = Cerebro.__new__(Cerebro)
cer.memoria = memoria

print("1. Enseñanza explícita (vale para todas las órdenes)")
comprobar(cer.detectar_intencion("aprende equal isolar significa ecualizador") == "ENSENAR_SINONIMO",
          "la frase se entiende como enseñanza de sinónimo")
comprobar(cer.detectar_intencion("aprende que hola significa pon musica") == "ENSENAR_ORDEN",
          "«aprende que» sigue siendo una frase completa (no sinónimo)")
r = cer.ensenar_sinonimo("aprende equal isolar significa ecualizador")
comprobar(r.startswith("Afirmativo") and "equal isolar" in r and "ecualizador" in r, "responde: " + r)
texto, usados = memoria.sinonimos_para("pon equal isolar")
comprobar(texto == "pon ecualizador" and usados == ["equal isolar"], "sustituye en la orden: " + texto)
texto, _ = memoria.sinonimos_para("sube equal isolar graves")
comprobar(cer.detectar_intencion(texto) == "ECUALIZADOR_AJUSTE", "y la orden queda detectada: " + texto)
texto, _ = memoria.sinonimos_para("equalizar")
comprobar(texto == "equalizar", "no toca palabras que solo contienen el sinónimo")

print("2. Aprendizaje autónomo por reformulación (por orden)")
memoria.observar_sinonimo("pon equalizar", "pon ecualizador", "ECUALIZADOR")
comprobar("equalizar" not in memoria._aprendizaje()["sinonimos"], "una sola vez no basta")
nuevo = memoria.observar_sinonimo("pon equalizar", "pon ecualizador", "ECUALIZADOR")
comprobar(nuevo and nuevo["original"] == "equalizar" and nuevo["ambito"] == "ECUALIZADOR",
          "tras dos reformulaciones lo aprende solo para ECUALIZADOR")
comprobar(memoria.sinonimos_para("equalizar graves")[1] == [], "no se aplica a todas las órdenes")
candidato = memoria.sinonimos_de_orden("equalizar graves")
comprobar(candidato is not None and candidato[0] == "ecualizador graves" and candidato[1] == "ECUALIZADOR",
          "con la orden de su ámbito sí se aplica: " + str(candidato))
comprobar(memoria.observar_sinonimo("pon equalizar", "pon ecualizador", None) is None,
          "sin intención conocida no aprende nada")
cambios_grandes = memoria.observar_sinonimo("a b c d e f", "x y z", "ECUALIZADOR")
comprobar(cambios_grandes is None, "cambios de más de tres palabras se ignoran")

print("3. Seguridad y límites")
comprobar(memoria.aprender_sinonimo("powershell", "ecualizador") is None, "rechaza órdenes de sistema disfrazadas")
comprobar(memoria.aprender_sinonimo("javascript:", "ecualizador") is None, "rechaza esquemas peligrosos")
comprobar(memoria.aprender_sinonimo("a", "b") is None, "rechaza tramos demasiado cortos")
comprobar(memoria.aprender_sinonimo("igual", "igual") is None, "rechaza sinónimos idénticos")

print("4. Olvido y listado")
r = cer.sinonimos_aprendidos()
comprobar("equal isolar" in r and "equalizar" in r, "lista los sinónimos: " + r[:70])
r = cer.olvidar_sinonimo_orden("olvida sinonimo equal isolar")
comprobar(r.startswith("Afirmativo"), "olvida un sinónimo: " + r)
comprobar(memoria.sinonimos_para("pon equal isolar")[0] == "pon equal isolar", "ya no se aplica")
comprobar(cer.olvidar_sinonimo_orden("olvida sinonimo nada").startswith("«nada»"), "avisa si no existía")
comprobar(cer.detectar_intencion("olvida sinonimo equal isolar") == "OLVIDAR_SINONIMO", "detecta la orden de olvido")
comprobar(cer.detectar_intencion("que sinonimos has aprendido") == "SINONIMOS_APRENDIDOS", "detecta la consulta")

print()
if fallos:
    print(f"FALLOS: {len(fallos)}")
    raise SystemExit(1)
print("TODO OK")
