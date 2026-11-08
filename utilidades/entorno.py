"""MILLER · Comprobación del entorno: versión de Python y librerías necesarias."""
import importlib.util
import sys

# módulo importable: (paquete pip, para qué sirve, imprescindible)
LIBRERIAS = {
    "pygame": ("pygame>=2.6.1", "reproductor de música", True),
    "pyttsx3": ("pyttsx3>=2.98", "voz de MILLER", False),
    "vosk": ("vosk>=0.3.45", "reconocimiento de voz local", False),
    "pyaudio": ("PyAudio>=0.2.14", "micrófono", False),
    "yt_dlp": ("yt-dlp>=2025.1.1", "descarga de música", False),
    "piper": ("piper-tts==1.3.0", "voces neurales masculinas", False),
}


def faltantes():
    return {m: datos for m, datos in LIBRERIAS.items() if importlib.util.find_spec(m) is None}


def comprobar(imprimir=True):
    """Devuelve True si MILLER puede arrancar. Muestra qué falta y cómo instalarlo."""
    import configuracion
    avisos = list(getattr(configuracion, "AVISOS_CONFIGURACION", []))
    falta = faltantes()
    if imprimir:
        print(f"[ENTORNO] Python {sys.version.split()[0]}")
        for aviso in avisos:
            print(f"[ENTORNO] ⚠ {aviso}")
        for modulo, (paquete, uso, _) in falta.items():
            print(f"[ENTORNO] Falta {modulo} ({uso}).")
        if falta:
            paquetes = " ".join(f'"{p}"' for p, _, _ in falta.values())
            print(f"[ENTORNO] Instale con:  {sys.executable} -m pip install {paquetes}")
            print("[ENTORNO] O todo de una vez:  python -m pip install -r requirements.txt")
    return not any(imprescindible for _, _, imprescindible in falta.values()) and sys.version_info >= (3, 10)


if __name__ == "__main__":
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    print("Entorno correcto." if comprobar() else "Faltan componentes imprescindibles.")
