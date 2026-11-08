"""MILLER · test.probar_cerebro: PRUEBA DE INTENCIONES DEL CEREBRO Comprueba que las frases se traducen a la intención correcta."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent      # carpeta raíz de MILLER
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
from cerebro.cerebro import Cerebro
CASOS = {
    # música (no debe cambiar)
    "pon musica": "REPRODUCIR_MUSICA", "pausa": "PAUSAR_MUSICA", "siguiente cancion": "SIGUIENTE_CANCION",
    "limpia la cola": "LIMPIAR_COLA_AUDIO", "lista las canciones": "LISTAR_AUDIOS",
    "sube el volumen": "SUBIR_VOLUMEN", "que hora es": "HORA",
    "estado de la biblioteca": "ESTADO_BIBLIOTECA", "cuales canciones estan danadas": "LISTAR_DANADOS_BIBLIOTECA",
    "hay canciones duplicadas": "LISTAR_DUPLICADOS_BIBLIOTECA", "que archivos no son compatibles": "LISTAR_NO_COMPATIBLES_BIBLIOTECA",
    "que archivos estan adulterados": "LISTAR_ADULTERADOS", "repara la biblioteca": "REPARAR_BIBLIOTECA",
    "limpia la biblioteca": "LIMPIAR_BIBLIOTECA", "vacia la cuarentena": "VACIAR_CUARENTENA",
    "elimina los archivos defectuosos": "VACIAR_CUARENTENA", "cual es el plan de eliminacion": "PLAN_ELIMINACION",
    "que hay en cuarentena": "LISTAR_CUARENTENA", "restaura todo": "RESTAURAR_CUARENTENA",
    "estado del supervisor": "ESTADO_SUPERVISOR", "resultado de la limpieza": "RESULTADO_LIMPIEZA",
    "probar voz": "PROBAR_MODULO", "prueba el reproductor": "PROBAR_MODULO",
    "probar todos los modulos": "PROBAR_TODOS_MODULOS", "resultado de las pruebas": "RESULTADO_PRUEBAS",
    "que pruebas hay": "LISTAR_PRUEBAS", "probar el supervisor": "PROBAR_MODULO",
    "miller cuando juega nacional": "PREGUNTA_INTERNET", "quien es gabriel garcia marquez": "PREGUNTA_INTERNET",
    "busca en internet el clima de bogota": "PREGUNTA_INTERNET", "averigua el precio del dolar": "PREGUNTA_INTERNET",
    # programas, descargas y aprendizaje
    "miller": "SALUDO", "oye miller": "SALUDO",
    "abre steam": "ABRIR_APLICACION", "miller ejecuta el programa de recortes": "ABRIR_APLICACION",
    "cierra word": "CERRAR_APLICACION", "abre youtube": "ABRIR_SITIO_WEB", "abre la carpeta documentos": "ABRIR_CARPETA",
    "descarga la cancion amorfoda": "DESCARGAR_MUSICA", "bajame el tema de bob marley": "DESCARGAR_MUSICA",
    "baja el volumen": "BAJAR_VOLUMEN", "como va la descarga": "ESTADO_DESCARGA", "cancela la descarga": "CANCELAR_DESCARGA",
    "que has aprendido": "RESUMEN_APRENDIZAJE", "cual es mi cancion favorita": "CANCION_FAVORITA",
    "como estas": "ESTADO", "que puedes hacer": "AYUDA", "que canciones tengo": "LISTAR_AUDIOS",
}
print("=" * 60)
print("PRUEBA DE INTENCIONES DEL CEREBRO")
print("=" * 60)
cerebro = Cerebro.__new__(Cerebro)           # sin __init__: no arranca módulos
fallos = 0
for frase, esperada in CASOS.items():
    obtenida = cerebro.detectar_intencion(frase)
    ok = obtenida == esperada
    fallos += not ok
    print(f"  {'OK   ' if ok else 'FALLO'} {frase!r:40} -> {obtenida}" + ("" if ok else f" (esperaba {esperada})"))
print()
print("=" * 60)
if fallos:
    print(f"PRUEBA FALLIDA: {fallos} de {len(CASOS)} frases mal interpretadas")
    raise SystemExit(1)
print(f"PRUEBA SUPERADA: {len(CASOS)} frases correctas")
