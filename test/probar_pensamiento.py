"""MILLER · Prueba del pensamiento de la cascada: percibir, ordenar, soltar a su velocidad y decidir si juega."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
import random
fallos = []


def comprobar(condicion, mensaje):
    print(("  OK    " if condicion else "  FALLO ") + mensaje)
    if not condicion:
        fallos.append(mensaje)


from interfaz.frases import JuegoFrases
from interfaz.pensamiento import Percepcion, Pensador


def col(palabra, x, y, vel=2.0, **extra):
    c = {"palabra": palabra, "x": x, "y": y, "vel": vel, "n": len(palabra)}
    c.update(extra)
    return c


print("1. Percepción de la cascada")
p = Percepcion()
cascada = [col("CASA", 100, 50, vel=3.0), col("LUZ", 110, 300, vel=3.0), col("MAR", 300, 60, vel=1.0),
           col("SOL", 105, 80, vel=3.0, frase=True), col("RIO", 95, 40, vel=3.0, reservada=True)]
cerca = p.cercanas(cascada, (100, 60))
comprobar(cerca == ["CASA"], "solo ve las libres cerca del orbe: " + str(cerca))
comprobar(p.percibir(cascada, (100, 60), alto=400) == ["CASA", "MAR", "LUZ"],
          "con poco cerca, percibe lo que hay en pantalla de arriba abajo: " + str(p.percibir(cascada, (100, 60), alto=400)))
comprobar(p.percibir(cascada, (100, 60), alto=200) == ["CASA", "MAR"],
          "no percibe lo que cae por debajo de la ventana")
p.observar(cascada)
comprobar(abs(p.velocidad() - 2.333) < 0.01 and p.ritmo() == "normal", "mide la velocidad de las libres: %.2f" % p.velocidad())
rapidas = [col("A" * 3, i * 15, 10, vel=4.0) for i in range(8)]
for _ in range(5):
    p.observar(rapidas)
comprobar(p.ritmo() == "rápido", "con la cascada rápida lo percibe como rápido")
comprobar(1.6 <= p.velocidad_para_frase() <= 3.4, "suelta la frase a un ritmo razonable")
comprobar(Percepcion().ritmo() == "desconocido", "sin mirar, no dice nada del ritmo")

print("2. Ordenar: sigue lo que aprendió")
juego = JuegoFrases(azar=random.Random(1))
juego.aprender(["CIELO", "AZUL", "PROFUNDO"])
juego.aprender(["CIELO", "AZUL", "CLARO"])
juego.aprender(["MAR", "AZUL"])
pensador = Pensador(juego, azar=random.Random(2))
orden = pensador.ordenar(["PROFUNDO", "CIELO", "AZUL"])
comprobar(orden == ["CIELO", "AZUL", "PROFUNDO"], "pone CIELO AZUL PROFUNDO en su orden: " + str(orden))
comprobar(pensador.ordenar(["X1", "Y2"]) == ["X1", "Y2"] and pensador.ordenar(["SOLA"]) == ["SOLA"],
          "sin datos mantiene el orden de llegada")
comprobar(pensador.ordenar(["AZUL", "AZUL", "CIELO"]) == ["CIELO", "AZUL"], "no repite palabras")

print("3. Elegir: lo que ve o lo que sabe")
frase = pensador.elegir(["PROFUNDO", "CIELO", "AZUL", "NUBE"])
comprobar(sorted(frase) == sorted(["PROFUNDO", "CIELO", "AZUL", "NUBE"]) and pensador.ordenadas == 1,
          "con cuatro palabras a la vista, las ordena: " + str(frase))
frase = pensador.elegir(["SOLO"])
comprobar(isinstance(frase, list) and len(frase) >= 1 and all(isinstance(x, str) for x in frase),
          "con una sola palabra recurre a lo que sabe: " + str(frase))

print("4. Decidir si juega")
pensador = Pensador(juego, azar=random.Random(3))
oportunidades = [pensador.decidir_jugar(100.0 + i, ocupado=False, placer=0.2) for i in range(50)]
comprobar(any(oportunidades) and not all(oportunidades), "con poco placer a veces juega, no siempre")
comprobar(not any(pensador.decidir_jugar(100.0, ocupado=True, placer=0.1) for _ in range(20)),
          "nunca juega mientras está ocupado")
pensador.marcar_juego(200.0)
comprobar(not any(pensador.decidir_jugar(205.0, ocupado=False, placer=0.1) for _ in range(20)),
          "espera entre dos juegos")
sin_ganas = Pensador(juego, azar=random.Random(4))
comprobar(not any(sin_ganas.decidir_jugar(500.0, ocupado=False, placer=0.9, silencio=5.0) for _ in range(30)),
          "con el placer alto y sin silencio no tiene ganas")
con_silencio = Pensador(juego, azar=random.Random(5))
comprobar(any(con_silencio.decidir_jugar(500.0, ocupado=False, placer=0.9, silencio=200.0) for _ in range(30)),
          "tras mucho silencio sí le apetece jugar")

print("5. Integración en la cascada del orbe (sin ventana)")
import threading
from interfaz.esencia import VentanaEsencia


class _Lienzo:
    def itemconfigure(self, *a, **k):
        pass


class _Equilibrio:
    def __init__(self, placer):
        self.niveles = {"placer": placer}
        self.llamadas = []

    def alimentar(self, necesidad, cantidad):
        self.llamadas.append((necesidad, cantidad))


def _ventana(modo="espera", placer=0.1):
    v = object.__new__(VentanaEsencia)
    juego = JuegoFrases(azar=random.Random(7))
    juego.aprender(["CIELO", "AZUL", "PROFUNDO"])
    juego.aprender(["CIELO", "AZUL", "CLARO"])
    v.juego = juego
    v.percepcion = Percepcion()
    v.pensador = Pensador(juego, azar=random.Random(11))
    v.pos = [100.0, 100.0]
    v.alto, v.ancho = 400, 330
    v.equilibrio = _Equilibrio(placer)
    v._modo = modo
    v._lock = threading.Lock()
    v.lienzo = _Lienzo()
    v._frase_activa, v._proxima_frase = None, 0.0
    v._ultimo_pensamiento = -1000.0
    columnas = []
    for k, (palabra, x, y) in enumerate([("PROFUNDO", 100, 110), ("CIELO", 112, 96), ("AZUL", 88, 120)]):
        columnas.append({"item": k, "cabeza": k, "x": x, "y": y, "vel": 2.0, "n": len(palabra), "palabra": palabra})
    for k, palabra in enumerate(["LUZ", "MAR", "SAL", "PAZ", "SOL", "RIO", "FLOR"]):
        columnas.append({"item": 10 + k, "cabeza": 10 + k, "x": 300 - 5 * k, "y": 350 + 5 * k, "vel": 2.0,
                         "n": len(palabra), "palabra": palabra})
    v.columnas = columnas
    return v


v = _ventana(modo="hablando")
for ahora in range(200, 260, 4):
    v._jugar_frases(float(ahora))
comprobar(v._frase_activa is None, "mientras habla no se pone a jugar con las palabras")

v = _ventana(modo="espera", placer=0.1)
ahora, intentos = 300.0, 0
while v._frase_activa is None and intentos < 60:
    v._jugar_frases(ahora)
    ahora += 5.0
    intentos += 1
comprobar(v._frase_activa is not None, "con poco placer, en espera, empieza a jugar tras unos intentos")
if v._frase_activa is not None:
    comprobar(v._frase_activa["palabras"] == ["CIELO", "AZUL", "PROFUNDO"],
              "la frase que suelta es lo que ve caer, ordenado: " + str(v._frase_activa["palabras"]))
    comprobar(v.equilibrio.llamadas == [("placer", 0.02)], "jugar le da algo de placer")
    cols = v._frase_activa["columnas"]
    for c in cols:
        c["espera"] = True                                # ya terminaron de caer
    v._jugar_frases(ahora)
    comprobar(v._frase_activa["suelta"] is True, "cuando las columnas están listas, suelta la frase")
    vels = {round(c["vel"], 3) for c in cols}
    comprobar(len(vels) == 1 and 1.6 <= next(iter(vels)) <= 3.4,
              "la frase cae a la velocidad de la cascada: " + str(vels))
    comprobar([c.get("palabra") for c in cols] == v._frase_activa["palabras"],
              "lo que cae queda guardado en cada columna")
    for c in cols:
        c["frase"] = False                                # la frase se fue de pantalla
    v._frase_activa = None
    v._modo = "pensando"
    for k in range(20):
        v._jugar_frases(ahora + 100.0 + 5 * k)
    comprobar(v._frase_activa is None, "pensando no suelta frases nuevas")

print()
if fallos:
    print(f"FALLOS: {len(fallos)}")
    raise SystemExit(1)
print("TODO OK")
