"""MILLER · test.probar_atenuador: PRUEBA DEL ATENUADOR DE VOZ Con un reproductor simulado comprueba que la música baja mientras MILLER habla,…"""
import sys as _sys
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent      # carpeta raíz de MILLER
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
from audio.atenuador import AtenuadorVoz

class FadeSimulado:
    def __init__(self, rep):
        self.rep, self.historial = rep, []
    def transicionar(self, objetivo, duracion=None):
        self.rep.nivel_mezclador = objetivo
        self.historial.append(round(objetivo, 3))
        return True

class ReproductorSimulado:
    def __init__(self, volumen, sonando=True):
        self.volumen, self.reproduciendo, self.pausado, self.cerrado = volumen, sonando, False, False
        self.inicializado, self.nivel_mezclador = True, volumen
        self.fade_controller = FadeSimulado(self)
        self.nivel = 0.15
    def nivel_cancion_actual(self):
        return self.nivel
fallos = []

def comprobar(condicion, mensaje):
    print(("  OK    " if condicion else "  FALLO ") + mensaje)
    if not condicion:
        fallos.append(mensaje)
print("=" * 60)
print("PRUEBA DEL ATENUADOR DE VOZ")
print("=" * 60)
import math
rep = ReproductorSimulado(0.8)
at = AtenuadorVoz(rep, factor=0.40, factor_voz=1.2, minimo_voz=0.06, maximo_voz=1.0, db_sobre_musica=1.0, nivel_voz=0.21)
with at:
    comprobar(abs(rep.nivel_mezclador - 0.32) < 0.01, f"mientras habla la música baja al 40 % ({rep.nivel_mezclador:.2f})")
    comprobar(rep.volumen == 0.8, "el volumen guardado del reproductor no cambia")
comprobar(abs(rep.nivel_mezclador - 0.8) < 0.01, "la música vuelve a su volumen al terminar")
for nivel in (0.10, 0.15, 0.23):                       # canciones suaves, normales y muy masterizadas
    for v in (0.1, 0.3):
        rep.volumen, rep.nivel = v, nivel
        voz = at.volumen_voz()
        db = 20 * math.log10((voz * 0.21) / (v * 0.40 * nivel))
        comprobar(8.0 < db < 11.5, f"canción RMS {nivel}, volumen {v:.0%}: voz {voz:.1%} = {db:+.1f} dB sobre la música atenuada")
rep_quieto = ReproductorSimulado(0.10, sonando=False)
at_q = AtenuadorVoz(rep_quieto, factor_voz=1.2)
comprobar(abs(at_q.volumen_voz() - 0.12) < 0.001, f"sin música: volumen 10 % -> voz {at_q.volumen_voz():.0%} (20 % más)")
rep2 = ReproductorSimulado(0.6, sonando=False)
at2 = AtenuadorVoz(rep2)
with at2:
    pass
comprobar(rep2.fade_controller.historial == [], "sin música sonando no toca el volumen")
rep3 = ReproductorSimulado(0.6)
at3 = AtenuadorVoz(rep3)
at3.atenuar(); rep3.volumen = 0.9; at3.restaurar()
comprobar(abs(rep3.nivel_mezclador - 0.9) < 0.01, "si el volumen cambia mientras habla, vuelve al volumen nuevo")
print()
print("=" * 60)
if fallos:
    print(f"PRUEBA FALLIDA: {len(fallos)} comprobaciones fallaron")
    raise SystemExit(1)
print("PRUEBA SUPERADA: la atenuación funciona correctamente")
