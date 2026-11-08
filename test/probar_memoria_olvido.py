"""MILLER · Prueba de memoria a corto y largo plazo y del plan de olvido (en una carpeta temporal)."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

_base = Path(tempfile.mkdtemp())
os.environ["MILLER_DIR_SEGURIDAD"] = str(_base / "seguridad")
fallos = []


def comprobar(condicion, mensaje):
    print(("  OK    " if condicion else "  FALLO ") + mensaje)
    if not condicion:
        fallos.append(mensaje)


import configuracion
from cerebro.memoria import Memoria
from cerebro.cerebro import Cerebro

ahora = datetime.now()


def hace(dias):
    return (ahora - timedelta(days=dias)).isoformat(timespec="seconds")


def recuerdo(texto, dias, importancia=1.0, frecuencia=0, categoria="general", con_fecha=True):
    r = {"id": 0, "contenido": texto, "categoria": categoria, "importancia": importancia, "frecuencia": frecuencia}
    if con_fecha:
        r["fecha"] = hace(dias)
        r["ultimo_acceso"] = hace(dias)
    return r


memoria = Memoria(_base / "memoria.json")
memoria.memoria[:] = [
    recuerdo("el gato se llama tomas", 2),                                  # reciente
    recuerdo("pedí una pizza el lunes", 200),                               # vieja y sin importancia
    recuerdo("mi color favorito es el azul", 100, importancia=2.0, frecuencia=10),   # vieja pero muy usada
    recuerdo("dato de hace 100 días", 100),                                 # vieja, poco usada
    recuerdo("recuerdo sin fecha fiable", 0, con_fecha=False),              # sin fecha: no se olvida
]

print("1. Fuerza de los recuerdos")
comprobar(memoria.fuerza_recuerdo(memoria.memoria[0]) > 0.5, "lo reciente tiene mucha fuerza")
comprobar(memoria.fuerza_recuerdo(memoria.memoria[2]) > memoria.fuerza_recuerdo(memoria.memoria[3]),
          "lo muy usado aguanta más que lo poco usado")
comprobar(memoria.fuerza_recuerdo(memoria.memoria[1]) < memoria.FUERZA_MINIMA, "lo viejo y sin uso pierde fuerza")

print("2. Plan de olvido")
resumen = memoria.plan_de_olvido()
textos = [r["contenido"] for r in memoria.memoria]
comprobar("pedí una pizza el lunes" not in textos, "archiva lo viejo y sin importancia")
comprobar("mi color favorito es el azul" in textos, "conserva lo viejo pero muy usado")
comprobar("dato de hace 100 días" not in textos, "archiva lo de 100 días poco usado")
comprobar("el gato se llama tomas" in textos, "conserva lo reciente")
comprobar("recuerdo sin fecha fiable" in textos, "conserva lo que no tiene fecha fiable")
comprobar(resumen["recuerdos"] == 2, "el resumen cuenta 2 recuerdos archivados")
comprobar(len(memoria._aprendizaje()["olvidados"]) == 2, "quedan en «olvidados», no se borran")
comprobar(memoria._aprendizaje()["ultimo_olvido"].get("fecha", "")[:10] == ahora.date().isoformat(),
          "guarda cuándo fue el último plan")

print("3. Recuperar y olvidar por tema")
comprobar(memoria.recuperar_olvidado("pizza") == 1, "recupera lo olvidado de pizza")
comprobar(any("pizza" in r["contenido"] for r in memoria.memoria), "vuelve a estar en la memoria")
recuperado = [r for r in memoria.memoria if "pizza" in r["contenido"]][0]
comprobar("olvidado" not in recuperado and memoria.fuerza_recuerdo(recuperado) > 0.5,
          "recuperado sin marca de olvido y con fuerza")
memoria.memoria.append(recuerdo("mi gato come pescado", 1, categoria="gatos"))
comprobar(memoria.olvidar_tema("gatos") == 1, "olvida todo lo de un tema (el recuerdo de gatos)")
comprobar(memoria.olvidar_tema("ab") == 0, "no olvida con temas de dos letras")

print("4. Alias y sinónimos sin uso")
viejo = hace(200)
memoria._aprendizaje()["alias"]["frase vieja"] = {"texto": "pon musica", "intencion": "X", "usos": 0, "desde": viejo}
memoria._aprendizaje()["alias"]["frase usada"] = {"texto": "pon musica", "intencion": "X", "usos": 3,
                                                  "desde": viejo, "ultimo_uso": hace(1)}
memoria.plan_de_olvido()
comprobar("frase vieja" not in memoria._aprendizaje()["alias"], "quita el alias que nadie usa")
comprobar("frase usada" in memoria._aprendizaje()["alias"], "conserva el alias usado hace poco")

print("5. Plan diario")
memoria._aprendizaje()["ultimo_olvido"] = {"fecha": ahora.isoformat(timespec="seconds")}
comprobar(memoria._plan_diario() is None, "no repite el plan el mismo día")
memoria._aprendizaje()["ultimo_olvido"] = {"fecha": hace(1)}
comprobar(memoria._plan_diario() is not None, "lo hace si el último fue otro día")

print("6. Memoria a corto plazo (la conversación)")
cer = Cerebro.__new__(Cerebro)
cer.memoria = memoria
cer.contexto = [{"rol": "usuario", "contenido": "pon musica", "momento": (ahora - timedelta(minutes=10)).isoformat()},
                {"rol": "usuario", "contenido": "vieja", "momento": (ahora - timedelta(hours=3)).isoformat()}]
cer.maximo_contexto = 20
cer.agregar_contexto("usuario", "que recuerdas de hoy")
comprobar(all(e["contenido"] != "vieja" for e in cer.contexto), "lo de hace horas sale de la memoria a corto plazo")
texto = cer.memoria_corto_plazo()
comprobar("pon musica" in texto and "que recuerdas de hoy" not in texto, "dice lo último sin repetir la pregunta: " + texto[-45:])
comprobar(f"{configuracion.MEMORIA_CORTO_MINUTOS} minutos" in texto, "menciona el tiempo de la memoria")

print("7. Memoria a largo plazo")
texto = cer.memoria_largo_plazo()
comprobar("recuerdos activos" in texto and "archivados" in texto, "resume la memoria a largo plazo")
comprobar(cer.ejecutar_plan_olvido().startswith("Afirmativo"), "el plan de olvido por voz responde")

print("8. Órdenes")
comprobar(cer.detectar_intencion("plan de olvido") == "PLAN_OLVIDO", "«plan de olvido»")
comprobar(cer.detectar_intencion("miller ejecuta el plan de olvido") == "PLAN_OLVIDO", "«ejecuta el plan de olvido»")
comprobar(cer.detectar_intencion("que he olvidado") == "OLVIDADOS", "«que he olvidado»")
comprobar(cer.detectar_intencion("que olvidaste") == "OLVIDADOS", "«que olvidaste»")
comprobar(cer.detectar_intencion("memoria a corto plazo") == "MEMORIA_CORTO", "«memoria a corto plazo»")
comprobar(cer.detectar_intencion("que recuerdas de hoy") == "MEMORIA_CORTO", "«que recuerdas de hoy»")
comprobar(cer.detectar_intencion("memoria a largo plazo") == "MEMORIA_LARGO", "«memoria a largo plazo»")
comprobar(cer.detectar_intencion("olvida lo de gatos") == "OLVIDAR_TEMA", "«olvida lo de gatos»")
comprobar(cer.detectar_intencion("recupera lo olvidado de pizza") == "RECUPERAR_OLVIDADO", "«recupera lo olvidado de pizza»")
comprobar(cer.detectar_intencion("que recuerdas de juan") != "MEMORIA_CORTO", "«que recuerdas de juan» sigue siendo búsqueda por tema")
comprobar(cer.detectar_intencion("olvida el nombre tomas") == "OLVIDAR_NOMBRE", "«olvida el nombre» sigue igual")
r = cer.recuperar_olvidado_orden("recupera lo olvidado de pizza")
comprobar(r.startswith("Afirmativo") or r.startswith("No tengo"), "recuperar por voz responde: " + r)

print()
if fallos:
    print(f"FALLOS: {len(fallos)}")
    raise SystemExit(1)
print("TODO OK")
