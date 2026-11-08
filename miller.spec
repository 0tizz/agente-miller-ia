# -*- mode: python ; coding: utf-8 -*-
# MILLER · Especificación de PyInstaller (modo carpeta: dist\MILLER\MILLER.exe).
# Se compila con compilar_exe.bat. modelos\, audios\ y datos\ NO van dentro del ejecutable:
# el programa los busca en la carpeta del proyecto (ver configuracion._ruta_base).
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

RAIZ = os.path.abspath(SPECPATH)

datos, binarios, ocultos = [], [], []

# Paquetes con datos o librerías nativas que PyInstaller no detecta solo.
for paquete in ("pygame", "vosk", "yt_dlp", "pyttsx3", "piper"):
    try:
        d, b, h = collect_all(paquete)
        datos += d
        binarios += b
        ocultos += h
    except Exception:
        pass   # si un paquete no está instalado, MILLER lo informa en la pestaña INSTALACIÓN

# Módulos propios que se cargan dinámicamente (importlib, probador de test/).
for modulo in ("cerebro", "audio", "interfaz", "utilidades", "voz"):
    try:
        ocultos += collect_submodules(modulo)
    except Exception:
        pass

a = Analysis(
    [os.path.join(RAIZ, "principal.py")],
    pathex=[RAIZ],
    binaries=binarios,
    datas=datos,
    hiddenimports=sorted(set(ocultos)),
    excludes=["pytest", "unittest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MILLER",
    debug=False,
    strip=False,
    upx=False,
    icon=os.path.join(RAIZ, "miller_icono.ico"),
    console=True,        # consola visible: los mensajes [ AUDIO ], [ VOZ ]... se ven al depurar
)

coleccion = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="MILLER",
)
