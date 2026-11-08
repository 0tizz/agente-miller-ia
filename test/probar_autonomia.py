"""MILLER · Prueba del aprendizaje autónomo: órdenes nuevas, tono congruente y movimiento que aprende."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
import tempfile
from pathlib import Path
from utilidades import seguridad
from cerebro.memoria import Memoria
from cerebro.emociones import Emociones
from cerebro.iniciativa import Iniciativa
from interfaz.esencia import CuerpoAprendiz
fallos = []


def comprobar(condicion, mensaje):
    print(("  OK    " if condicion else "  FALLO ") + mensaje)
    if not condicion:
        fallos.append(mensaje)


base = Path(tempfile.mkdtemp())
seguridad.DIR_SEGURIDAD = base / "seguridad"
seguridad._clave = None
print("1. Aprende órdenes solo")
m = Memoria(base / "memoria.json")
alias = m.proponer_alias("ponme algo de flaca", "pon flaca", "REPRODUCIR_CANCION")
comprobar(alias and alias["texto"] == "pon flaca", "reformulación con palabras en común: aprendida al instante")
comprobar(m.alias_para("ponme algo de flaca")["intencion"] == "REPRODUCIR_CANCION", "la frase nueva ya se entiende")
comprobar(m.proponer_alias("dale caña", "sube el volumen", "SUBIR_VOLUMEN") is None, "sin palabras en común: espera otra vez")
comprobar(m.proponer_alias("dale caña", "sube el volumen", "SUBIR_VOLUMEN") is not None, "la segunda vez la aprende")
for _ in range(3):
    m.aprender("baja el volumen", "BAJAR_VOLUMEN", "Volumen al 40 %.")
parecida = m.similar_conocida("baja el volumn")
comprobar(parecida == ("baja el volumen", "BAJAR_VOLUMEN"), f"reconoce una variante de una orden conocida: {parecida}")
comprobar(m.aprender_alias("abre powershell", "pon musica", "REPRODUCIR_MUSICA", "x") is None, "no aprende órdenes peligrosas")
m2 = Memoria(base / "memoria.json")
comprobar(m2.alias_para("dale caña") is not None, "lo aprendido se recuerda al reiniciar")
print("2. Tono congruente con la noticia")


class CerebroFalso:
    comandos = memoria = None
    emociones = Emociones()


c = CerebroFalso()
c.emociones.registrar_evento("descarga_ok")                 # MILLER está contento...
c.emociones.registrar_evento("descarga_ok")
ini = Iniciativa(c, silencio_previo=0, intervalo_minimo=0)
ini.agregar("p1", "falló la prueba: voz.", 3)
texto = ini.entregar()
comprobar("buenas noticias" not in texto.lower() and texto.startswith(("Atención", "Señor, debo")),
          f"mala noticia con tono de alerta aunque esté contento: {texto}")
ini.agregar("p2", "descarga lista: Flaca.", 3)
texto = ini.entregar()
comprobar(texto.startswith(("Buenas noticias", "Señor", "Reporte en verde", "Misión cumplida")), f"buena noticia: {texto}")
for t, esperado in (("3 archivos dañados a cuarentena", "malo"), ("aprendí a reconocer «mi lee»", "bueno"),
                    ("su volumen preferido: 40 %.", "neutro")):
    comprobar(Iniciativa.clasificar_tono(t) == esperado, f"«{t}» -> {esperado}")
print("3. El núcleo de la ventana aprende a moverse")
import random
random.seed(3)                                    # aprendizaje con azar: semilla fija, resultado repetible
cuerpo = CuerpoAprendiz(base / "movimiento.json")
for _ in range(1000):
    cuerpo.decidir("positivo")
antes = cuerpo.choques
for _ in range(3000):
    cuerpo.decidir("positivo")
tasa_inicial, tasa_final = antes / 1000, (cuerpo.choques - antes) / 3000
comprobar(tasa_final < tasa_inicial, f"choca menos con los bordes ({tasa_inicial:.0%} -> {tasa_final:.0%})")
arriba = sum(1 for _ in range(300) if cuerpo.decidir("positivo")[1] == 0)
comprobar(arriba > 150, f"feliz, prefiere la parte alta ({arriba}/300)")
cuerpo.guardar()
comprobar(CuerpoAprendiz(base / "movimiento.json").pasos == cuerpo.pasos, "lo aprendido se guarda")
print()
print("RESULTADO:", "OK" if not fallos else f"FALLO ({len(fallos)})")
if fallos:
    raise SystemExit(1)
