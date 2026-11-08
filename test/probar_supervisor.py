"""MILLER · test.probar_supervisor: PRUEBA DEL SUPERVISOR DE BIBLIOTECA Crea una biblioteca TEMPORAL (no toca audios/) con un WAV sano, una copia…"""
import sys as _sys
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent      # carpeta raíz de MILLER
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
import math
import os
import shutil
import struct
import subprocess
import tempfile
import wave
from pathlib import Path
from audio.supervisor_biblioteca import ConfigSupervisor, SupervisorBiblioteca
fallos = []

def comprobar(condicion, mensaje):
    print(("  OK    " if condicion else "  FALLO ") + mensaje)
    if not condicion:
        fallos.append(mensaje)

def crear_wav(ruta, segundos=2, frecuencia=440):
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * frecuencia * i / 22050)))
                               for i in range(22050 * segundos)))

def buscar_ffmpeg():
    nombre = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    ruta = RAIZ / "modelos" / "ffmpeg-master-gpl" / "bin" / nombre
    return str(ruta) if ruta.is_file() else shutil.which("ffmpeg")
print("=" * 60)
print("PRUEBA DEL SUPERVISOR DE BIBLIOTECA")
print("=" * 60)
base = Path(tempfile.mkdtemp(prefix="miller_test_supervisor_"))
audios = base / "audios"
audios.mkdir()
try:
    crear_wav(audios / "Sana.wav")
    shutil.copy2(audios / "Sana.wav", audios / "Sana copia.wav")
    (audios / "Rota.mp3").write_bytes(os.urandom(4000))
    crear_wav(audios / "Disfrazada.mp3", frecuencia=660)
    ffmpeg = buscar_ffmpeg()
    if ffmpeg:
        crear_wav(base / "fuente.wav", frecuencia=550)
        subprocess.run([ffmpeg, "-loglevel", "error", "-y", "-i", str(base / "fuente.wav"), "-c:a", "aac",
                        "-f", "mp4", str(audios / "Mp4 disfrazado.mp3")], check=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    print("FFmpeg:", ffmpeg or "no disponible (se omite la prueba de conversión)")
    antiguo = os.path.getmtime(audios / "Sana.wav") - 600
    for p in audios.iterdir():
        os.utime(p, (antiguo, antiguo))
    cfg = ConfigSupervisor(modo="cuarentena", verificacion_profunda=False, estabilidad_segundos=1,
                           carpeta_datos=base / "datos", ruta_ffmpeg=ffmpeg,
                           eliminacion_automatica=True,
                           plan_eliminacion={"danados": 0, "duplicados": None,
                                             "adulterados_reparados": None, "adulterados": None})
    supervisor = SupervisorBiblioteca(carpeta=audios, config=cfg)
    informe = supervisor.escanear_una_vez()
    comprobar(informe is not None, "el supervisor completa un ciclo")
    informe = informe or {}
    acciones = {(a["accion"], a["archivo"]) for a in informe.get("acciones", [])}
    print()
    comprobar(("extension_corregida", "Disfrazada.mp3") in acciones and (audios / "Disfrazada.wav").is_file(),
              "un WAV llamado .mp3 se repara corrigiendo la extensión")
    comprobar(("cuarentena", "Sana copia.wav") in acciones or ("cuarentena", "Sana.wav") in acciones,
              "el duplicado exacto se aparta en cuarentena")
    comprobar(("cuarentena", "Rota.mp3") in acciones, "el archivo dañado se aparta en cuarentena")
    comprobar(("eliminado", "Rota.mp3") in acciones, "el plan de eliminación borra el dañado (0 días)")
    comprobar((audios / "cuarentena" / "manifiesto.json").is_file(), "la cuarentena está en audios/cuarentena")
    if ffmpeg:
        comprobar(("convertido", "Mp4 disfrazado.mp3") in acciones, "un MP4 llamado .mp3 se convierte a MP3")
        nuevo = audios / "Mp4 disfrazado.mp3"
        cabecera = nuevo.read_bytes()[:3] if nuevo.is_file() else b""
        comprobar(cabecera == b"ID3" or cabecera[:1] == b"\xff", "el archivo convertido es un MP3 real")
        comprobar(any(p.suffix == ".m4a" for p in (audios / "cuarentena" / "adulterados").glob("*")),
                  "el original se guarda en cuarentena/adulterados con su extensión real (.m4a)")
    plan = supervisor.plan_eliminacion()
    comprobar(isinstance(plan, list), "el plan de eliminación se puede consultar")
    restaurables = [e for e in supervisor.listar_cuarentena() if e["categoria"] == "duplicados"]
    if restaurables:
        comprobar(supervisor.restaurar_de_cuarentena(restaurables[0]["id"]), "un archivo se puede restaurar")
    print()
    huerfano = audios / "cuarentena" / "_temporal" / "huerfano.mp3"
    huerfano.parent.mkdir(parents=True, exist_ok=True)
    huerfano.write_bytes(b"x" * 100)
    vigentes = supervisor.listar_cuarentena()
    if vigentes:
        perdido = audios / "cuarentena" / vigentes[0]["ruta_cuarentena"]
        perdido.rename(base / "fuera.bin")
    if ffmpeg:
        for i in range(4):
            crear_wav(base / f"f{i}.wav", segundos=1, frecuencia=300 + 50 * i)
            subprocess.run([ffmpeg, "-loglevel", "error", "-y", "-i", str(base / f"f{i}.wav"), "-c:a", "aac",
                            "-f", "mp4", str(audios / f"Lote {i}.mp3")], check=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            os.utime(audios / f"Lote {i}.mp3", (antiguo, antiguo))
    cfg2 = ConfigSupervisor(modo="cuarentena", verificacion_profunda=False, estabilidad_segundos=1,
                            carpeta_datos=base / "datos", ruta_ffmpeg=ffmpeg, max_conversiones_por_ciclo=2)
    supervisor2 = SupervisorBiblioteca(carpeta=audios, config=cfg2)
    informe2 = supervisor2.escanear_una_vez() or {}
    comprobar(not huerfano.exists(), "los temporales huérfanos se eliminan al arrancar")
    if vigentes:
        comprobar(all(e["id"] != vigentes[0]["id"] for e in supervisor2.listar_cuarentena()),
                  "una entrada cuyo archivo desapareció se marca como perdida")
    if ffmpeg:
        convertidos = [a for a in informe2.get("acciones", []) if a["accion"] == "convertido"]
        comprobar(len(convertidos) == 2, f"respeta el límite de 2 conversiones por ciclo ({len(convertidos)})")
        comprobar(len(informe2.get("adulterados", [])) == 2, "los adulterados restantes quedan para el siguiente ciclo")
finally:
    shutil.rmtree(base, ignore_errors=True)
print()
print("=" * 60)
if fallos:
    print(f"PRUEBA FALLIDA: {len(fallos)} comprobaciones fallaron")
    raise SystemExit(1)
print("PRUEBA SUPERADA: el supervisor funciona correctamente")
