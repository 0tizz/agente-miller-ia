"""MILLER · Prueba del reproductor de audio"""
import sys as _sys
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent      # carpeta raíz de MILLER
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
from pathlib import Path
import time
from audio.reproductor import Reproductor
CARPETA_AUDIOS = (RAIZ / "audios")

def linea():
    print("-" * 70)

def titulo(texto):
    print()
    print("=" * 70)
    print(f"  {texto}")
    print("=" * 70)
    print()

def pausa_consola():
    input("\nPresiona ENTER para continuar...")

def mostrar_biblioteca(reproductor):
    titulo("BIBLIOTECA")
    canciones = reproductor.obtener_canciones()
    if not canciones:
        print("No hay archivos de audio.")
        print()
        print("Coloca archivos en:")
        print(CARPETA_AUDIOS)
        return
    print(f"Total de canciones: {len(canciones)}")
    linea()
    for numero, cancion in enumerate(canciones, start=1):
        print(f"{numero:02d}. {cancion.name}")

def mostrar_estado(reproductor):
    titulo("ESTADO DEL REPRODUCTOR")
    estado = reproductor.obtener_estado()
    for clave, valor in estado.items():
        print(f"{clave:<25}: {valor}")

def probar_busqueda(reproductor):
    titulo("BUSCAR CANCIÓN")
    consulta = input("Escribe el nombre de una canción: ").strip()
    if not consulta:
        print("Consulta vacía.")
        return
    print()
    resultado = reproductor.buscar_cancion(consulta)
    print("MEJOR RESULTADO:")
    if resultado:
        print(f"✓ {resultado.name}")
    else:
        print("✗ No se encontró ninguna canción.")
    print()
    resultados = reproductor.buscar_canciones(consulta)
    print("RESULTADOS:")
    if not resultados:
        print("No hay coincidencias.")
        return
    for numero, archivo in enumerate(resultados, start=1):
        print(f"{numero}. {archivo.name}")

def probar_reproducir(reproductor):
    titulo("REPRODUCIR")
    print("Puedes escribir el nombre de una canción.")
    print("También puedes dejar vacío para selección automática.")
    nombre = input("\nCanción: ").strip()
    if nombre:
        exito = reproductor.reproducir(nombre)
    else:
        exito = reproductor.reproducir()
    if exito:
        print()
        print("✓ Reproducción iniciada.")
        print(f"🎵 Actual: " f"{reproductor.obtener_nombre_actual()}")
    else:
        print()
        print("✗ No se pudo reproducir.")

def probar_pausa(reproductor):
    titulo("PAUSAR")
    if reproductor.pausar():
        print("⏸ Música pausada correctamente.")
    else:
        print("✗ No se pudo pausar.")

def probar_continuar(reproductor):
    titulo("CONTINUAR")
    if reproductor.continuar():
        print("▶ Música continuando.")
    else:
        print("✗ No se pudo continuar.")

def probar_detener(reproductor):
    titulo("DETENER")
    if reproductor.detener():
        print("⏹ Música detenida.")
    else:
        print("✗ No se pudo detener.")

def probar_siguiente(reproductor):
    titulo("SIGUIENTE")
    actual = (reproductor .obtener_nombre_actual())
    print(f"Anterior: {actual}")
    if reproductor.siguiente():
        print(f"⏭ Siguiente: " f"{reproductor.obtener_nombre_actual()}")
    else:
        print("✗ No se pudo reproducir la siguiente.")

def probar_anterior(reproductor):
    titulo("ANTERIOR")
    actual = (reproductor .obtener_nombre_actual())
    print(f"Actual: {actual}")
    if reproductor.anterior():
        print(f"⏮ Anterior: " f"{reproductor.obtener_nombre_actual()}")
    else:
        print("✗ No hay canción anterior disponible.")

def probar_volumen(reproductor):
    titulo("CONTROL DE VOLUMEN")
    print(f"Volumen actual: " f"{reproductor.obtener_volumen()}%")
    print()
    print("1. Subir volumen")
    print("2. Bajar volumen")
    print("3. Establecer volumen")
    print("4. Consultar volumen")
    opcion = input("\nSelecciona: ").strip()
    if opcion == "1":
        if reproductor.subir_volumen():
            print(f"🔊 Volumen: " f"{reproductor.obtener_volumen()}%")
    elif opcion == "2":
        if reproductor.bajar_volumen():
            print(f"🔉 Volumen: " f"{reproductor.obtener_volumen()}%")
    elif opcion == "3":
        valor = input("Volumen (0-100): ").strip()
        try:
            porcentaje = float(valor)
            reproductor.establecer_volumen(porcentaje / 100)
            print(f"🔊 Volumen establecido en " f"{reproductor.obtener_volumen()}%")
        except ValueError:
            print("✗ Valor inválido.")
    elif opcion == "4":
        print(f"Volumen: " f"{reproductor.obtener_volumen()}%")
    else:
        print("Opción no válida.")

def mostrar_cola(reproductor):
    titulo("COLA DE REPRODUCCIÓN")
    cola = reproductor.obtener_cola()
    if not cola:
        print("La cola está vacía.")
        return
    print(f"Canciones en cola: {len(cola)}")
    linea()
    for numero, archivo in enumerate(cola, start=1):
        print(f"{numero}. {archivo.name}")

def agregar_a_cola(reproductor):
    titulo("AGREGAR A COLA")
    nombre = input("Nombre de la canción: ").strip()
    if not nombre:
        print("Nombre vacío.")
        return
    if reproductor.agregar_a_cola(nombre):
        print("✓ Canción agregada.")
    else:
        print("✗ No se pudo agregar.")

def eliminar_de_cola(reproductor):
    titulo("ELIMINAR DE COLA")
    cola = reproductor.obtener_cola()
    if not cola:
        print("La cola está vacía.")
        return
    for numero, archivo in enumerate(cola, start=1):
        print(f"{numero}. {archivo.name}")
    posicion = input("\nNúmero de canción a eliminar: ").strip()
    try:
        posicion = int(posicion)
    except ValueError:
        print("✗ Número inválido.")
        return
    if reproductor.eliminar_de_cola(posicion):
        print("✓ Canción eliminada.")
    else:
        print("✗ No se pudo eliminar.")

def limpiar_cola(reproductor):
    titulo("LIMPIAR COLA")
    cantidad = (reproductor.cantidad_en_cola())
    if cantidad == 0:
        print("La cola ya está vacía.")
        return
    confirmar = input(f"¿Eliminar {cantidad} canciones? (s/n): ").strip().lower()
    if confirmar == "s":
        reproductor.limpiar_cola()
        print("✓ Cola limpiada.")
    else:
        print("Operación cancelada.")

def probar_aleatorio(reproductor):
    titulo("REPRODUCCIÓN ALEATORIA")
    estado = (reproductor.alternar_aleatorio())
    if estado:
        print("🔀 Aleatorio ACTIVADO.")
    else:
        print("🔀 Aleatorio DESACTIVADO.")

def probar_repetir(reproductor):
    titulo("REPETICIÓN")
    estado = (reproductor.alternar_repetir())
    if estado:
        print("🔁 Repetición ACTIVADA.")
    else:
        print("🔁 Repetición DESACTIVADA.")

def mostrar_historial(reproductor):
    titulo("HISTORIAL")
    historial = (reproductor.obtener_historial())
    if not historial:
        print("El historial está vacío.")
        return
    print(f"Canciones registradas: " f"{len(historial)}")
    linea()
    for numero, archivo in enumerate(historial, start=1):
        print(f"{numero}. {archivo.name}")

def limpiar_historial(reproductor):
    titulo("LIMPIAR HISTORIAL")
    historial = (reproductor.obtener_historial())
    if not historial:
        print("El historial ya está vacío.")
        return
    confirmar = input("¿Quieres borrar el historial? (s/n): ").strip().lower()
    if confirmar == "s":
        reproductor.limpiar_historial()
        print("✓ Historial limpiado.")
    else:
        print("Operación cancelada.")

def mostrar_tiempo(reproductor):
    titulo("TIEMPO DE REPRODUCCIÓN")
    cancion = (reproductor.obtener_nombre_actual())
    tiempo = (reproductor.obtener_tiempo_reproduccion())
    if not cancion:
        print("No hay una canción seleccionada.")
        return
    minutos = tiempo // 60
    segundos = tiempo % 60
    print(f"🎵 Canción: {cancion}")
    print(f"⏱ Tiempo: " f"{minutos:02d}:{segundos:02d}")

def prueba_automatica(reproductor):
    titulo("PRUEBA AUTOMÁTICA")
    canciones = (reproductor.obtener_canciones())
    if not canciones:
        print("No hay canciones para probar.")
        return
    print("Iniciando prueba automática...")
    print()
    print("1. Reproducir")
    if reproductor.reproducir():
        print(f"✓ {reproductor.obtener_nombre_actual()}")
    else:
        print("✗ Falló reproducción.")
        return
    time.sleep(1)
    print("2. Pausar")
    if reproductor.pausar():
        print("✓ Pausado.")
    else:
        print("✗ Falló pausa.")
    time.sleep(1)
    print("3. Continuar")
    if reproductor.continuar():
        print("✓ Continuando.")
    else:
        print("✗ Falló continuar.")
    time.sleep(1)
    print("4. Volumen")
    reproductor.establecer_volumen(0.5)
    print(f"✓ Volumen: " f"{reproductor.obtener_volumen()}%")
    if len(canciones) >= 2:
        print("5. Cola")
        if reproductor.agregar_archivo_a_cola(canciones[1]):
            print(f"✓ Agregada: " f"{canciones[1].name}")
    print("6. Estado")
    estado = (reproductor.obtener_estado())
    print(f"✓ Actual: " f"{estado['cancion_actual']}")
    print(f"✓ Cola: " f"{estado['cantidad_en_cola']}")
    print(f"✓ Volumen: " f"{estado['volumen']}%")
    print()
    print("✓ PRUEBA AUTOMÁTICA FINALIZADA.")

def mostrar_menu():
    titulo("MILLER - PRUEBA DEL REPRODUCTOR")
    print("  1  → Mostrar biblioteca")
    print("  2  → Buscar canción")
    print("  3  → Reproducir")
    print("  4  → Pausar")
    print("  5  → Continuar")
    print("  6  → Detener")
    print("  7  → Siguiente")
    print("  8  → Anterior")
    print("  9  → Controlar volumen")
    print(" 10  → Mostrar cola")
    print(" 11  → Agregar a cola")
    print(" 12  → Eliminar de cola")
    print(" 13  → Limpiar cola")
    print(" 14  → Activar/desactivar aleatorio")
    print(" 15  → Activar/desactivar repetición")
    print(" 16  → Mostrar historial")
    print(" 17  → Limpiar historial")
    print(" 18  → Mostrar tiempo")
    print(" 19  → Mostrar estado completo")
    print(" 20  → Actualizar biblioteca")
    print(" 21  → PRUEBA AUTOMÁTICA")
    print("  0  → Salir")
    linea()

def main():
    print()
    print("=" * 70)
    print("       MILLER - REPRODUCTOR DE AUDIO")
    print("             PRUEBA INDEPENDIENTE")
    print("=" * 70)
    print()
    print("[ TEST ] Carpeta de audios:")
    print(f"        {CARPETA_AUDIOS}")
    print()
    try:
        # Memoria aparte: la prueba nunca toca datos/memoriamusical.json (MILLER puede estar abierto).
        prueba = RAIZ / "datos" / "pruebas" / "memoriamusical_prueba.json"
        prueba.parent.mkdir(parents=True, exist_ok=True)
        reproductor = Reproductor(CARPETA_AUDIOS, ruta_memoria=prueba)
    except Exception as error:
        print()
        print("[ ERROR ] No se pudo crear " "el reproductor.")
        print(f"[ ERROR ] {error}")
        return
    if not reproductor.inicializado:
        print()
        print("[ ERROR ] El motor de audio " "no pudo inicializarse.")
        reproductor.cerrar()
        return
    print()
    print("[ TEST ] Reproductor inicializado correctamente.")
    try:
        while True:
            mostrar_menu()
            opcion = input("MILLER TEST > ").strip()
            if opcion == "0":
                break
            elif opcion == "1":
                mostrar_biblioteca(reproductor)
            elif opcion == "2":
                probar_busqueda(reproductor)
            elif opcion == "3":
                probar_reproducir(reproductor)
            elif opcion == "4":
                probar_pausa(reproductor)
            elif opcion == "5":
                probar_continuar(reproductor)
            elif opcion == "6":
                probar_detener(reproductor)
            elif opcion == "7":
                probar_siguiente(reproductor)
            elif opcion == "8":
                probar_anterior(reproductor)
            elif opcion == "9":
                probar_volumen(reproductor)
            elif opcion == "10":
                mostrar_cola(reproductor)
            elif opcion == "11":
                agregar_a_cola(reproductor)
            elif opcion == "12":
                eliminar_de_cola(reproductor)
            elif opcion == "13":
                limpiar_cola(reproductor)
            elif opcion == "14":
                probar_aleatorio(reproductor)
            elif opcion == "15":
                probar_repetir(reproductor)
            elif opcion == "16":
                mostrar_historial(reproductor)
            elif opcion == "17":
                limpiar_historial(reproductor)
            elif opcion == "18":
                mostrar_tiempo(reproductor)
            elif opcion == "19":
                mostrar_estado(reproductor)
            elif opcion == "20":
                titulo("ACTUALIZAR BIBLIOTECA")
                canciones = (reproductor .actualizar_lista())
                print(f"✓ Biblioteca actualizada.")
                print(f"Total: {len(canciones)} canciones.")
            elif opcion == "21":
                prueba_automatica(reproductor)
            else:
                print()
                print("✗ Opción no válida.")
            pausa_consola()
    except KeyboardInterrupt:
        print()
        print()
        print("[ TEST ] Interrumpido por el usuario.")
    except Exception as error:
        print()
        print("[ TEST ] Error inesperado:")
        print(f"[ TEST ] {error}")
    finally:
        print()
        print("[ TEST ] Cerrando reproductor...")
        try:
            reproductor.cerrar()
        except Exception as error:
            print(f"[ TEST ] Error cerrando: {error}")
        print("[ TEST ] Reproductor cerrado.")
        print()
        print("=" * 70)
        print("             PRUEBA FINALIZADA")
        print("=" * 70)
        print()
if __name__ == "__main__":
    main()
