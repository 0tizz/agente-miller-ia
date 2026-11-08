"""MILLER · test.probar_internet: PRUEBA DE CONSULTAS A INTERNET Comprueba la limpieza de preguntas, el analizador de resultados y que, sin…"""
import sys as _sys
from pathlib import Path as _Path
RAIZ = _Path(__file__).resolve().parent.parent      # carpeta raíz de MILLER
if str(RAIZ) not in _sys.path:
    _sys.path.insert(0, str(RAIZ))
import time
from utilidades.consulta_internet import ConsultorInternet, _ParserDuck
fallos = []

def comprobar(condicion, mensaje):
    print(("  OK    " if condicion else "  FALLO ") + mensaje)
    if not condicion:
        fallos.append(mensaje)
print("=" * 60)
print("PRUEBA DE CONSULTAS A INTERNET")
print("=" * 60)
c = ConsultorInternet()
comprobar(c.limpiar_pregunta("miller cuando juega nacional") == "cuando juega nacional", "limpia la palabra de activación")
comprobar(c.limpiar_pregunta("busca en internet quien es Shakira") == "quien es Shakira", "limpia 'busca en internet'")
muestra = ('<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.ejemplo.com%2Fx">Titulo</a>'
           '<a class="result__snippet" href="x">Atlético Nacional juega el sábado a las 8 p. m. contra '
           'Millonarios en el estadio Atanasio Girardot de Medellín.</a>')
p = _ParserDuck()
p.feed(muestra)
comprobar(bool(p.resultados) and "sábado" in p.resultados[0]["fragmento"], "el analizador extrae el fragmento")
comprobar(c._dominio(p.resultados[0]["url"]) == "ejemplo.com", "identifica la fuente")
comprobar(len(c._acortar("Frase uno. " * 60)) <= c.MAX_CARACTERES + 1, "acorta respuestas largas")
offline = ConsultorInternet()
offline._conexion = (time.monotonic() + 999, False)
t0 = time.monotonic()
r = offline.consultar("cuando juega nacional")
comprobar(r == {"ok": False, "motivo": "sin_conexion"} and time.monotonic() - t0 < 0.5,
          "sin conexión responde al instante")
t0 = time.monotonic()
hay = c.hay_conexion()
print(f"\nConexión a internet: {'sí' if hay else 'no'} ({time.monotonic() - t0:.1f} s)")
comprobar(time.monotonic() - t0 < 6, "comprobar la conexión nunca tarda más de unos segundos")
if hay:
    r = c.consultar("capital de Colombia")
    print("Consulta real:", r)
    comprobar(r.get("ok") or r.get("motivo") in ("sin_resultados", "error"), "la consulta real termina sin errores")
print()
print("=" * 60)
if fallos:
    print(f"PRUEBA FALLIDA: {len(fallos)} comprobaciones fallaron")
    raise SystemExit(1)
print("PRUEBA SUPERADA: las consultas a internet funcionan correctamente")
