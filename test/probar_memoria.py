"""MILLER · test.probar_memoria: PRUEBA DE LA MEMORIA Y EL APRENDIZAJE Usa un archivo temporal (no toca datos/memoria.json)."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent      # carpeta raíz de MILLER
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
import json
import shutil
import tempfile
from pathlib import Path
from cerebro.memoria import Memoria
fallos = []

def comprobar(condicion, mensaje):
    print(("  OK    " if condicion else "  FALLO ") + mensaje)
    if not condicion:
        fallos.append(mensaje)
print("=" * 60)
print("PRUEBA DE LA MEMORIA Y EL APRENDIZAJE")
print("=" * 60)
base = Path(tempfile.mkdtemp(prefix="miller_test_memoria_"))
try:
    ruta = base / "memoria.json"
    ruta.write_text(json.dumps([{"id": 1, "contenido": "que el mar es azul", "categoria": "general",
                                 "fecha": "2026-10-23T22:17:49"}]), encoding="utf-8")
    m = Memoria(ruta)
    comprobar(m.cantidad_recuerdos() == 1, "migra los recuerdos del formato antiguo")
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    comprobar(datos.get("version") == 2 and "aprendizaje" in datos, "el archivo pasa al formato nuevo")
    m.iniciar_sesion()
    ctx = {"cancion_actual": "Bob Marley - Jammin.mp3", "volumen": 60}
    for _ in range(3):
        m.aprender("reproduce jammin", "REPRODUCIR_CANCION", "Reproduciendo Bob Marley - Jammin.", "jammin", ctx)
    m.aprender("sube el volumen", "SUBIR_VOLUMEN", "Volumen al 70 %.", None, {"volumen": 70})
    m.aprender("abre spotify", "ABRIR_APLICACION", "Afirmativo. Abriendo Spotify.")
    m.aprender("cuando juega nacional", "PREGUNTA_INTERNET",
               "Nacional juega el sábado a las 8 p. m. Fuente: ejemplo.com.", None, {"fuente_internet": True})
    m.aprender("xyzzy frase rara", "DESCONOCIDA", "Orden no comprendida.")
    m.aprender("cierra word", "CERRAR_APLICACION", "Word no está abierto.")
    m.finalizar_sesion()
    a = Memoria(ruta).aprendizaje                      # recargar desde disco: lo aprendido persiste
    comprobar(a["comandos"]["REPRODUCIR_CANCION"]["usos"] == 3, "cuenta las órdenes usadas")
    comprobar(a["musica"]["pedidas"].get("jammin") == 3, "aprende las canciones pedidas")
    comprobar(a["musica"]["artistas"].get("Bob Marley") == 3, "aprende los artistas escuchados")
    comprobar(a["musica"]["volumen"]["promedio"] == 70, "aprende el volumen preferido")
    comprobar(a["aplicaciones"].get("spotify") == 1, "aprende los programas que abre")
    comprobar("xyzzy frase rara" in a["no_entendidas"], "registra lo que no entendió")
    comprobar(a["sesiones"]["total"] == 1 and a["sesiones"]["ultima_fin"], "registra las sesiones")
    m2 = Memoria(ruta)
    dato = m2.respuesta_aprendida("cuando juega el nacional")
    comprobar(dato is not None and "sábado" in dato["respuesta"], "recuerda respuestas de internet para usarlas sin conexión")
    resumen = m2.resumen_aprendizaje()
    print("   Resumen:", resumen)
    comprobar("Sesiones: 1" in resumen and "jammin" in resumen, "genera el resumen de lo aprendido")
    comprobar(m2.cancion_favorita()[0] == "jammin", "identifica la canción favorita")
    from utilidades import seguridad
    seguridad.DIR_SEGURIDAD = base / "seguridad"
    ruta.write_text("{ esto no es json", encoding="utf-8")
    m3 = Memoria(ruta)
    comprobar(any((base / "seguridad" / "sospechosos").iterdir()), "un archivo dañado se aísla en seguridad/sospechosos")
    comprobar(m3.cantidad_recuerdos() >= 1, "y se recupera el último respaldo válido")
finally:
    shutil.rmtree(base, ignore_errors=True)
print()
print("=" * 60)
if fallos:
    print(f"PRUEBA FALLIDA: {len(fallos)} comprobaciones fallaron")
    raise SystemExit(1)
print("PRUEBA SUPERADA: la memoria aprende correctamente")
