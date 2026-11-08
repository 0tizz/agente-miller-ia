"""MILLER · Prueba de las voces neurales masculinas de modelos/voces (no reproduce sonido)."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
import io
import json
import time
import wave
import configuracion
from voz import voz_neural
fallos = []


def comprobar(condicion, mensaje):
    print(("  OK    " if condicion else "  FALLO ") + mensaje)
    if not condicion:
        fallos.append(mensaje)


carpeta = configuracion.RUTA_VOCES
print("1. Modelos instalados en", carpeta)
instaladas = voz_neural.voces_instaladas(carpeta)
for nombre, descripcion in voz_neural.VOCES.items():
    if nombre not in instaladas:                       # las demás voces son opcionales
        print(f"  AVISO {nombre} ({descripcion}) no descargada (opcional)")
        continue
    comprobar(True, f"{nombre} ({descripcion})")
    if True:
        datos = json.loads((carpeta / nombre / f"{nombre}.onnx.json").read_text(encoding="utf-8"))
        comprobar(datos.get("language", {}).get("family") == "es", f"   español, {datos.get('audio', {}).get('sample_rate')} Hz")
comprobar(configuracion.VOZ_NEURAL in instaladas, f"la voz configurada ({configuracion.VOZ_NEURAL}) está instalada")
print("2. Síntesis")
if voz_neural.PiperVoice is None:
    print(f"  AVISO piper-tts no instalado ({voz_neural.ERROR_PIPER}). Instale: python -m pip install piper-tts==1.3.0")
else:
    for nombre in instaladas:
        voz = voz_neural.VozNeural(carpeta, nombre)
        inicio = time.monotonic()
        audio = voz.sintetizar("Permiso para hablar, señor.")
        tiempo = time.monotonic() - inicio
        with wave.open(io.BytesIO(audio)) as w:
            segundos = w.getnframes() / w.getframerate()
        comprobar(segundos > 0.5, f"{nombre}: {segundos:.1f} s de audio en {tiempo:.2f} s")
        inicio = time.monotonic()
        voz.sintetizar("Permiso para hablar, señor.")
        comprobar(time.monotonic() - inicio < 0.01, "   la frase repetida sale de la caché")
print()
print("RESULTADO:", "OK" if not fallos else f"FALLO ({len(fallos)})")
if fallos:
    raise SystemExit(1)
