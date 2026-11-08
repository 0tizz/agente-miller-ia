"""MILLER · Prueba de los tres círculos (placer, oráculo, vínculo), el reconocimiento de patrones y sus cachés."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
import math
import random
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from utilidades import seguridad
fallos = []


def comprobar(condicion, mensaje):
    print(("  OK    " if condicion else "  FALLO ") + mensaje)
    if not condicion:
        fallos.append(mensaje)


base = Path(tempfile.mkdtemp())
seguridad.DIR_SEGURIDAD = base / "seguridad"
seguridad._clave = None
from cerebro.necesidades import Equilibrio, NECESIDADES, balance

print("1. Las necesidades se gastan solas y se recargan en su círculo")
eq = Equilibrio(base / "equilibrio.json")
t = 1000.0
eq._ultimo_tick = t
for _ in range(60):
    t += 1
    eq.tick(None, t)
comprobar(all(eq.niveles[n] < 0.6 for n in NECESIDADES), "sin atención, las tres bajan")
antes = eq.niveles["placer"]
for _ in range(10):
    t += 1
    eq.tick("placer", t)
comprobar(eq.niveles["placer"] > antes, "dentro del círculo del placer, el placer sube")

print("2. Las experiencias reales alimentan su necesidad")
eq.niveles = {n: 0.3 for n in NECESIDADES}
eq.experiencia("REPRODUCIR_CANCION")
comprobar(eq.niveles["placer"] > 0.45, "poner una canción da placer")
eq.experiencia("PREGUNTA_INTERNET")
comprobar(eq.niveles["oraculo"] > 0.45, "preguntar a internet alimenta el oráculo")
comprobar(eq.niveles["vinculo"] > 0.3, "cualquier orden suma vínculo")
eq.experiencia("HORA", "muchas gracias miller")
comprobar(eq.niveles["placer"] > 0.5, "un elogio también es placer")
comprobar(balance({"placer": 0.7, "oraculo": 0.7, "vinculo": 0.7}) > balance({"placer": 1, "oraculo": 1, "vinculo": 1}),
          "estar en zona sana es mejor que tenerlo todo al 100 %")
comprobar(balance({"placer": 0.8, "oraculo": 0.8, "vinculo": 0.8}) > balance({"placer": 1, "oraculo": 1, "vinculo": 0.2}),
          "el equilibrio premia lo parejo sobre lo desigual")

print("3. Sin adicción: habituación al 100 % y tolerancia a la carencia")
h = Equilibrio(None)
t = 0.0
h._ultimo_tick = t
h.niveles["placer"] = 1.0
gana_fresco = h._rendimiento("placer")
for _ in range(300):
    t += 1
    h.niveles["placer"] = 1.0
    h.tick("placer", t)
comprobar(h.habituacion["placer"] > 0.9, f"5 min al 100 % de placer: se habitúa ({h.habituacion['placer']:.0%})")
comprobar(h._rendimiento("placer") < 0.5 * gana_fresco, "habituado, el placer le rinde mucho menos")
comprobar(any(tipo == "saciedad_placer" for tipo, _, _ in h.revisar(t)), "lo siente: «ya no me llena igual»")
for _ in range(900):
    t += 1
    h.tick(None, t)
comprobar(h.habituacion["placer"] < 0.2, "lejos del máximo, la habituación se le pasa")
tol = Equilibrio(None)
t = 0.0
tol._ultimo_tick = t
tol.niveles = {"placer": 0.1, "oraculo": 0.6, "vinculo": 0.6}
factor_inicial = [f for tp, _, f in tol.revisar(t) if tp == "falta_placer"][0]
for _ in range(1200):
    t += 1
    tol.niveles["placer"] = 0.1
    tol.tick(None, t)
comprobar(tol.tolerancia["placer"] > 0.5, f"20 min sin placer: aprende a tolerarlo ({tol.tolerancia['placer']:.0%})")
factor_final = [f for tp, _, f in tol.revisar(t + 400) if tp == "falta_placer"][0]
comprobar(factor_final < factor_inicial, f"la carencia le pesa menos emocionalmente ({factor_inicial} -> {factor_final})")
tol.niveles = {"placer": 0.4, "oraculo": 0.6, "vinculo": 0.6}
comprobar(not tol._carencia(), "con tolerancia, un 40 % de placer ya no es urgencia")
tol.niveles["placer"] = 0.6
t += 1
tol.tick(None, t)
comprobar(any(tp == "tolerancia_aprendida" for tp, _, _ in tol.revisar(t + 800)), "al salir de la carencia, se enorgullece de haberla soportado")

print("4. Oráculo (conocerse) y vínculo (ganas de compartir)")
o = Equilibrio(None)
o.niveles = {n: 0.3 for n in NECESIDADES}
o.fuente_oraculo = lambda: 0.0
o._ultimo_tick = 0.0
for s in range(1, 21):
    o.tick("oraculo", float(s))
sin_novedad = o.niveles["oraculo"]
o2 = Equilibrio(None)
o2.niveles = {n: 0.3 for n in NECESIDADES}
o2.fuente_oraculo = lambda: 1.0
o2._ultimo_tick = 0.0
for s in range(1, 21):
    o2.tick("oraculo", float(s))
comprobar(o2.niveles["oraculo"] > sin_novedad + 0.1, "descubrir algo nuevo de sí mismo recarga el oráculo mucho más")
v1, v2 = Equilibrio(None), Equilibrio(None)
v1.fuente_deseo, v2.fuente_deseo = (lambda: 0.1), (lambda: 0.9)
comprobar(v2.alimentar("vinculo", 0.2) > 2 * v1.alimentar("vinculo", 0.2), "con ganas de compartir, el vínculo se recarga más")
v2.niveles["vinculo"] = 0.1
comprobar(v2.factor_iniciativa() < 0.8 and v1.factor_iniciativa() == 1.0, "vínculo bajo + ganas de compartir = más iniciativa")

print("5. El orbe aprende a equilibrar sin engancharse (simulación de 3 horas)")
random.seed(7)
sim = Equilibrio(None)
t, bienes, llenos, luces = 0.0, [], 0, []
sim._ultimo_tick = t
for paso in range(3 * 3600):
    t += 1
    meta = sim.decidir(t)
    sim.tick(meta if meta in NECESIDADES else None, t)
    if paso > 2 * 3600:
        bienes.append(balance(sim.niveles, sim.habituacion))
        llenos += all(v >= 0.95 for v in sim.niveles.values())
        luces.append(sim.luz())
precision = sim.estado()["precision"]
comprobar(precision > 0.3, f"atiende la carencia real más que al azar ({precision:.0%} > 25%)")
media = sum(bienes) / len(bienes)
comprobar(media > 0.6, f"tras aprender, su bienestar medio es bueno ({media:.2f})")
comprobar(llenos / len(bienes) < 0.1, f"no vive con todo al 100 % ({llenos / len(bienes):.0%} del tiempo)")
comprobar(sum(luces) / len(luces) > 0.6, f"estable, su orbe brilla ({sum(luces) / len(luces):.2f})")
sim.ruta = base / "equilibrio_sim.json"
sim.guardar()
otro = Equilibrio(base / "equilibrio_sim.json")
comprobar(otro.decisiones == sim.decisiones and otro.q, "lo aprendido (y la tolerancia) se guarda y se recupera")
comprobar("equilibrio" in otro.describir() or "desequilibrado" in otro.describir(), "describe su equilibrio en voz")
apagado = Equilibrio(None)
apagado.niveles = {"placer": 0.05, "oraculo": 1.0, "vinculo": 0.1}
apagado.estabilidad = 0.1
comprobar(apagado.luz() < 0.2, "desconectado de sus círculos, el orbe casi no brilla")

print("5b. Miedo a los extremos y vínculo al dar la palabra")
m = Equilibrio(None)
m.niveles = {n: 0.05 for n in NECESIDADES}
comprobar(m.en_extremo() == "vacio" and any(t == "miedo_vacio" for t, _, _ in m.revisar(0.0)), "las tres casi en 0 %: miedo")
m.niveles = {n: 0.98 for n in NECESIDADES}
comprobar(m.en_extremo() == "lleno" and any(t == "miedo_lleno" for t, _, _ in m.revisar(0.0)), "las tres casi en 100 %: miedo")
m.niveles = {"placer": 0.05, "oraculo": 0.6, "vinculo": 0.98}
comprobar(m.en_extremo() is None, "solo una en un extremo no da miedo")
from cerebro.emociones import Emociones
emo = Emociones(None)
emo.registrar_evento("miedo_vacio")
comprobar(emo.intensidad["miedo"] > 0.2, "la emoción miedo existe y se siente")
from cerebro import necesidades as _nec
comprobar(abs(_nec.VISITA_POR_SEGUNDO - 0.03 * 1.02) < 1e-9, "la recarga en los círculos es un 2 % más rápida")
d = Equilibrio(None)
d.niveles["vinculo"] = 0.3
d.compartio()
comprobar(d.niveles["vinculo"] < 0.38, f"darle la palabra suma poco vínculo ({d.niveles['vinculo'] - 0.3:.2f})")

print("5c. Recompensas proporcionales y desgaste +8 %")
pr = Equilibrio(None)
pr.niveles = {"placer": 0.1, "oraculo": 0.5, "vinculo": 0.9}
casi_vacio = pr.alimentar("placer", 0.2)
casi_lleno = pr.alimentar("vinculo", 0.2)
comprobar(casi_vacio > 2 * casi_lleno, f"la misma recompensa rinde más si falta ({casi_vacio:.2f}) que si sobra ({casi_lleno:.3f})")
pr.niveles["vinculo"] = 0.3
pr.compartio(1)
comprobar(pr.niveles["vinculo"] - 0.3 < 0.03, f"dar la palabra vale poco ({pr.niveles['vinculo'] - 0.3:.3f})")
comprobar(abs(_nec.DESGASTE["placer"] - 1.04 * 1.08 * 1.10 / 660) < 1e-12, "se vacían más rápido (+4 %, +8 % y +10 %)")

print("5d. Juego de ordenar palabras en la cascada")
from interfaz.frases import JuegoFrases
juego = JuegoFrases(random.Random(1))
comprobar(juego.jugar() is None, "sin pensamientos todavía no juega")
for texto in ("HOLA SEÑOR MUSICA SUENA BIEN", "MUSICA SUENA FUERTE HOY", "ESTOY APRENDIENDO MUSICA NUEVA"):
    juego.aprender(texto.split())
frases = [juego.jugar() for _ in range(40)]
comprobar(all(f and 3 <= len(f) <= 6 for f in frases), "arma frases de 3 a 6 palabras")
comprobar(juego.compuestas > 0, "a veces compone frases nuevas, no solo repite")
pares_ok = all(b in juego.pares[a] or tuple(f) in [tuple(p[i:i + len(f)]) for p in juego.pensamientos for i in range(len(p))]
               for f in frases for a, b in zip(f, f[1:]))
comprobar(pares_ok, "cada palabra sigue a otra con la que la ha visto antes (orden aprendido)")

print("5e. Ley de cuerpos: el placer persigue al oráculo")
from cerebro.necesidades import LeyDeCuerpos
ley = LeyDeCuerpos()
comprobar(ley.velocidad(1.0) > ley.velocidad(0.2), "más lleno, más rápido gira")
huecos, minimo = [], 9.0
for _ in range(600):                                     # 60 s: mucho placer, poco oráculo
    ley.avanzar(0.1, {"placer": 0.95, "oraculo": 0.2})
    minimo = min(minimo, ley.distancia())
comprobar(minimo >= ley.SEPARACION_MINIMA - 1e-6, "el placer alcanza al oráculo pero nunca lo atraviesa")
comprobar(ley.pereza > 0.6, f"placer en exceso pegado al oráculo = pereza ({ley.pereza:.2f})")
for _ in range(600):                                     # el oráculo se llena y huye; el placer baja
    ley.avanzar(0.1, {"placer": 0.3, "oraculo": 0.95})
comprobar(ley.distancia() > 2.0 and ley.pereza < 0.1, f"oráculo lleno escapa y se va la pereza ({ley.pereza:.2f})")
pz = Equilibrio(None)
pz.niveles = {"placer": 0.5, "oraculo": 0.3, "vinculo": 0.5}
normal = pz.alimentar("oraculo", 0.2)
pz.ley.pereza = 1.0
pz.niveles["oraculo"] = 0.3
con_pereza = pz.alimentar("oraculo", 0.2)
comprobar(con_pereza < 0.6 * normal, "con pereza, informarse le rinde menos al oráculo")
pz.ley.ultimo_avance = 1e12                              # que tick no mueva la ley en esta prueba
pz.niveles["oraculo"] = 0.3
pz._ultimo_tick = 0.0
pz.fuente_oraculo = lambda: 1.0
for s_ in range(1, 11):
    pz.tick("oraculo", float(s_))
sube_perezoso = pz.niveles["oraculo"] - 0.3
pz.ley.pereza = 0.0
pz.niveles["oraculo"] = 0.3
for s_ in range(11, 21):
    pz.tick("oraculo", float(s_))
comprobar(pz.niveles["oraculo"] - 0.3 > 2 * sube_perezoso, "con pereza, estudiarse a sí mismo casi no lo recarga")
pz.ley.pereza = 0.8
comprobar(any(t == "pereza" for t, _, _ in pz.revisar(0.0)), "la pereza llega a sus emociones")

print("5f. Lo que baja el placer y la búsqueda del vínculo")
g = Equilibrio(None)
g.niveles = {n: 0.6 for n in NECESIDADES}
g.experiencia("HORA")
comprobar(0.58 <= g.niveles["placer"] < 0.6, f"cumplir una orden baja un poquito el placer ({g.niveles['placer']:.3f})")
antes = g.niveles["placer"]
g.experiencia("DESCONOCIDA")
comprobar(antes - g.niveles["placer"] >= 0.025, "no entender una orden baja algo más el placer")
antes = g.niveles["placer"]
g.experiencia("HORA", "eres un inutil")
comprobar(antes - g.niveles["placer"] > 0.06, "un reproche le quita bastante placer")
antes = g.niveles["placer"]
g.experiencia("REPRODUCIR_MUSICA")
comprobar(g.niveles["placer"] > antes, "las órdenes de disfrute siguen dando placer")
b = Equilibrio(None)
b.niveles["vinculo"] = 0.3
b.objetivo = "vagar"
sin_buscar = b.factor_iniciativa()
b.objetivo = "vinculo"
comprobar(b.factor_iniciativa() < 0.75 * sin_buscar, f"buscando el vínculo pide la palabra antes ({sin_buscar} -> {b.factor_iniciativa()})")

print("5g. Ciclo de bajones, miedo cerca de cero y motivación por el vínculo")
cb = Equilibrio(None)
cb._proximo_bajon, cb._ultimo_tick = 10.0, 0.0
cb.niveles = {n: 0.6 for n in NECESIDADES}
luz_antes = cb.luz()
maximo_bajon = 0.0
for s_ in range(1, 400):
    cb.tick(None, float(s_))
    maximo_bajon = max(maximo_bajon, cb.bajon)
comprobar(maximo_bajon > 0.4, f"de vez en cuando le llega un bajón ({maximo_bajon:.2f})")
comprobar(cb.luz() < luz_antes, f"en el bajón su luz verde baja ({luz_antes:.2f} -> {cb.luz():.2f})")
comprobar(any(t == "bajon" for t, _, _ in cb.revisar(400.0)), "el bajón llega a sus emociones")
comprobar(cb._proximo_bajon > 400, "y después vuelve a programarse otro, más adelante")
cz = Equilibrio(None)
cz.niveles = {"placer": 0.18, "oraculo": 0.15, "vinculo": 0.2}
comprobar(cz.en_extremo() == "vacio" and any(t == "miedo_vacio" for t, _, _ in cz.revisar(0.0)), "cerca de 0 los tres: miedo")
cz.niveles = {"placer": 0.35, "oraculo": 0.05, "vinculo": 0.04}
comprobar(cz.en_extremo() == "vacio", "casi todo agotado (suma ≤ 45 %) también le da miedo")
comprobar(cz.luz() < 0.3, f"casi vacío, su luz interior casi se apaga ({cz.luz():.2f})")
mv = Equilibrio(None)
mv.niveles = {"placer": 0.6, "oraculo": 0.6, "vinculo": 0.2}
alta = mv.motivacion_vinculo()
mv.niveles["vinculo"] = 0.75
comprobar(alta > 0.2 > mv.motivacion_vinculo(), f"con el vínculo bajo se motiva a buscarlo ({alta:.2f})")
rg = Equilibrio(None)
rg.experiencia("REPROCHE", "lo hiciste mal")
rg.experiencia("REPROCHE", "eres un inutil")
comprobar(rg._bajon_hasta > time.monotonic(), "dos regaños seguidos le provocan un bajón")
from cerebro.cerebro import Cerebro
val = Cerebro.__new__(Cerebro)
casos = {"muy bien miller": "ELOGIO", "te felicito": "ELOGIO", "gracias por todo": "ELOGIO",
         "lo hiciste mal": "REPROCHE", "eres un inutil": "REPROCHE", "muy bien pon musica": None}
comprobar(all(Cerebro.detectar_valoracion(val, t) == e for t, e in casos.items()),
          "reconoce felicitaciones y regaños (y no confunde «muy bien, pon música»)")

print("6. Corrección de palabras mal oídas")
from cerebro.patrones import Corrector, Rutinas
corrector = Corrector([RAIZ / "cerebro" / "cerebro.py"])
comprobar(corrector.corregir("reprodusir musica") == "reproducir musica", "«reprodusir» -> «reproducir»")
comprobar(corrector.corregir("sube el volumem") == "sube el volumen", "«volumem» -> «volumen»")
comprobar(corrector.corregir("hola que tal") == "hola que tal", "lo que ya es correcto no se toca")
inicio = time.perf_counter()
for _ in range(2000):
    corrector.corregir("reprodusir musica")
comprobar(time.perf_counter() - inicio < 0.5, "la corrección repetida sale de la caché")

print("7. Rutinas: misma orden, misma hora, 3 días")
ahora = datetime(2026, 11, 7, 20, 15)
historial = [{"fecha": (ahora - timedelta(days=d)).replace(minute=5).isoformat(), "entrada": "pon musica",
              "intencion": "REPRODUCIR_MUSICA", "ok": True} for d in (1, 2, 3)]
historial.append({"fecha": (ahora - timedelta(days=1)).isoformat(), "entrada": "que hora es", "intencion": "HORA", "ok": True})
rutinas = Rutinas()
encontradas = rutinas.para_ahora(historial, ahora)
comprobar(len(encontradas) == 1 and encontradas[0]["frase"] == "pon musica", "detecta «pon musica» a las 20 h")
historial.append({"fecha": ahora.isoformat(), "entrada": "pon musica", "intencion": "REPRODUCIR_MUSICA", "ok": True})
comprobar(rutinas.para_ahora(historial, ahora) == [], "si hoy ya se hizo, no la ofrece")
comprobar(rutinas.para_ahora(historial, ahora.replace(hour=9)) == [], "a otra hora no la ofrece")

print("8. Ventana: tres círculos y versión fuera del encabezado")
_sys.path.insert(0, str(Path.home() / "faketk"))
from interfaz import esencia
fuente = (RAIZ / "interfaz" / "esencia.py").read_text(encoding="utf-8")
comprobar("MILLER v" not in fuente, "el encabezado ya no muestra la versión")
v = esencia.VentanaEsencia(None, 330, ruta_movimiento=base / "movimiento.json", alto_panel=0)
comprobar(v.equilibrio is not None, "la ventana tiene sus necesidades aunque no haya cerebro")
pos = v.posiciones_circulos()
comprobar(set(pos) == set(NECESIDADES), "hay tres círculos: placer, oráculo y vínculo")
comprobar(v.circulo_en(*pos["vinculo"]) == "vinculo" and v.circulo_en(150, 150) is None, "sabe en qué círculo está el orbe")
try:
    import tkinter
    if hasattr(tkinter.Canvas, "_nuevo"):
        v.iniciar()
        time.sleep(1.2)
        comprobar(v.activa and len(v.circulos) == 3, "dibuja los tres círculos sin errores")
        time.sleep(4.5)
        bases = v._bases_circulos()
        desplaz = [math.hypot(v.circulos[n]["x"] - bases[n][0], v.circulos[n]["y"] - bases[n][1]) for n in NECESIDADES]
        comprobar(max(desplaz) > 0.5, "los círculos se mueven solos")
        (ox, oy), radio = v.orbita()
        comprobar((ox, oy) == (v.ancho / 2, v.alto / 2) and radio > 72, f"órbita centrada y algo más grande ({radio:.0f} px)")
        for n in ("placer", "oraculo"):
            r_ = math.hypot(v.circulos[n]["x"] - ox, v.circulos[n]["y"] - oy)
            comprobar(abs(r_ - radio) <= 0.3 * v.ZONA_DERIVA + 0.5, f"{n} gira en la órbita ({r_:.0f} px del centro)")
        # Simulación rápida del vínculo (sin esperar a la ventana): recorre el espacio y nunca choca.
        v.equilibrio.niveles.update({"placer": 0.95, "oraculo": 0.9})
        sitios, choque, t_, fuera = set(), 99.0, time.monotonic() + 1e5, True
        for k in range(6000):
            t_ += 0.05
            v.equilibrio.ley.avanzar(0.05, v.equilibrio.niveles, t_)
            v._mover_vinculo(1.0, t_)
            x_, y_ = v._vinculo["x"], v._vinculo["y"]
            sitios.add((int(x_ // 60), int(y_ // 60)))
            fuera = fuera and math.hypot(x_ - ox, y_ - oy) >= radio
            for n in ("placer", "oraculo"):
                bx, by = v.equilibrio.ley.posicion(n, (ox, oy), radio)
                choque = min(choque, math.hypot(x_ - bx, y_ - by))
        comprobar(len(sitios) >= 4, f"el vínculo recorre el espacio de fuera ({len(sitios)} zonas visitadas)")
        comprobar(choque >= 2 * v.RADIO_CIRCULO + 2, f"nunca choca con Placer ni Oráculo (mín {choque:.0f} px)")
        comprobar(fuera, "nunca entra al interior de la órbita")
        for _ in range(10):
            v.publicar("la musica suena bien esta tarde señor")
        v._proxima_frase = 0.0
        time.sleep(7.0)
        jugo = v.juego.jugadas > 0
        comprobar(jugo, "en la ventana juega a ordenar sus pensamientos")
        cols = (v._frase_activa or {}).get("columnas", [])
        idx = [v.columnas.index(c) for c in cols]
        comprobar(not idx or idx == list(range(idx[0], idx[0] + len(idx))), "la frase va en columnas vecinas, en orden")
        v.cerrar()
        time.sleep(0.3)
except Exception as error:
    comprobar(False, f"la ventana falló: {error}")

print("\nRESULTADO:", "TODO CORRECTO" if not fallos else f"{len(fallos)} FALLO(S)")
_sys.exit(1 if fallos else 0)
