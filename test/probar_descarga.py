"""MILLER · Probador del descargador de musica."""
import sys
from pathlib import Path
RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
from utilidades import descargar_musica as modulo_descargador
# Importar explícitamente las funciones públicas del módulo.
from utilidades.descargar_musica import (descargar_musica, descargador_musica,)

def mostrar_estado():
    estado = descargador_musica.estado()
    print("\n" + "=" * 60)
    print(" MILLER | DIAGNOSTICO DE FFmpeg Y DESCARGAS")
    print("=" * 60)
    for clave, valor in estado.items():
        print(f"{clave}: {valor}")
    print("\n--- Comprobacion directa de los archivos ---")
    for nombre in ("ffmpeg.exe", "ffprobe.exe"):
        ruta = RAIZ / "modelos" / "ffmpeg-master-gpl" / "bin" / nombre
        print(f"{nombre}:")
        print(f"  Ruta esperada: {ruta}")
        print(f"  Existe: {ruta.is_file()}")
    print("=" * 60)

def mostrar_historial():
    historial = descargador_musica.obtener_historial(15)
    print("\n--- HISTORIAL ---")
    if not historial:
        print("No hay descargas registradas.")
        return
    for registro in reversed(historial):
        print(f"\nFecha: {registro.get('fecha', '')}")
        print(f"Titulo: {registro.get('titulo') or registro.get('consulta', '')}")
        print(f"Estado: {registro.get('estado', '')}")
        print(f"Archivo: {registro.get('archivo') or 'Sin archivo'}")
        print(f"Mensaje: {registro.get('mensaje', '')}")

def progreso(datos):
    print(
        f"\r[{datos.get('porcentaje', 0):5.1f}%] "
        f"{datos.get('estado', '').upper():14} "
        f"{datos.get('mensaje', '')[:65]:65}",
        end="",
        flush=True,
    )

def probar_descarga(consulta):
    print(f"\nConsulta: {consulta}")
    print("Iniciando descarga...\n")
    resultado = descargar_musica(consulta, callback_progreso=progreso,)
    print("\n\n--- RESULTADO ---")
    if resultado.get("exito"):
        print("Correcto: descarga finalizada.")
    else:
        print("Error: no se completó la descarga.")
    for clave, valor in resultado.items():
        print(f"{clave}: {valor}")

def main():
    print("\nRaiz del proyecto:", RAIZ)
    print("Archivo del probador:", Path(__file__).resolve())
    print("Modulo importado:", Path(modulo_descargador.__file__).resolve())
    mostrar_estado()
    print("\nComandos disponibles:")
    print("  estado")
    print("  historial")
    print("  descargar nombre de canción")
    print("  descargar https://URL-compatible")
    print("  salir")
    while True:
        try:
            entrada = input("\nMILLER > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nPrueba finalizada.")
            break
        if not entrada:
            continue
        if entrada.casefold() in ("salir", "exit", "quit"):
            print("Prueba finalizada.")
            break
        if entrada.casefold() == "estado":
            mostrar_estado()
            continue
        if entrada.casefold() == "historial":
            mostrar_historial()
            continue
        if entrada.casefold().startswith("descargar "):
            consulta = entrada[len("descargar "):].strip()
            if consulta:
                probar_descarga(consulta)
            else:
                print("Indica el nombre de una canción o una URL compatible.")
            continue
        print("Comando no reconocido.")
if __name__ == "__main__":
    main()
