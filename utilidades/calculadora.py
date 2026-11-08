"""MILLER · Calculadora por voz: suma, resta, multiplicación, división, potencias, raíces y porcentajes (sin eval)."""
import math
import re

from utilidades.numeros import palabras_a_numeros as _a_numeros, plano


def palabras_a_numeros(texto):
    return _a_numeros(re.sub(r"\bpor ?cientos?\b", "%", plano(texto)))

_OPERADORES = [
    (r"\bmultiplicad[oa] por\b", "*"), (r"\bdividid[oa] (?:entre|por|en)\b", "/"), (r"\belevado a(?: la)?\b", "^"),
    (r"\bal cuadrado\b", "^ 2"), (r"\bal cubo\b", "^ 3"), (r"\bpor ciento de\b", "% de"),
    (r"\bmas\b", "+"), (r"\bmenos\b", "-"), (r"\bpor\b", "*"), (r"\bx\b", "*"), (r"\bentre\b", "/"),
    (r"\bsobre\b", "/"), (r"[×]", "*"), (r"[÷]", "/"),
]
_RE_PEDIDO = re.compile(r"\b(cuanto es|cuanto da|calcula|calcular|suma|sumar|resta|restar|multiplica|multiplicar|"
                        r"divide|dividir|raiz|porcentaje|por ciento|elevado|al cuadrado|al cubo|resultado de|operacion)\b")
PRIORIDAD = {"+": 1, "-": 1, "*": 2, "/": 2, "^": 3}


def es_operacion(texto):
    """Hay al menos dos números (o una raíz) y una operación: así 'más volumen' no se confunde."""
    t = palabras_a_numeros(texto)
    numeros = re.findall(r"\d+(?:\.\d+)?", t)
    if re.search(r"\braiz (?:cuadrada )?de \d", t):
        return True
    if len(numeros) < 2:
        return False
    return bool(_RE_PEDIDO.search(t) or re.search(r"\d+(?:\.\d+)? (mas|menos|por|entre|x|multiplicad|dividid|elevado|sobre)\b", t))


def _expresion(texto):
    t = palabras_a_numeros(texto)
    t = re.sub(r"^(?:miller )?(?:cuanto (?:es|son|da)|calcula(?:r)?|dime|resultado de|la operacion|operacion)\s*", "", t)
    # Verbos: "suma 3 y 4", "resta 3 a 10", "multiplica 2 por 5", "divide 9 entre 3".
    m = re.match(r"^(suma|sumar|multiplica|multiplicar)\s+(.+)$", t)
    if m:
        signo = "+" if m.group(1).startswith("sum") else "*"
        t = re.sub(r"\b(y|con|mas|por|x)\b", signo, m.group(2))
    m = re.match(r"^(?:resta|restar)\s+(\S+)\s+(?:a|de)\s+(\S+)$", t)
    if m:
        t = f"{m.group(2)} - {m.group(1)}"
    else:
        t = re.sub(r"^(?:resta|restar)\s+", "", t)
    t = re.sub(r"^(?:divide|dividir)\s+(\S+)\s+(?:entre|por|en)\s+", r"\1 / ", t)
    m = re.search(r"(\d+(?:\.\d+)?) (?:%|por ciento) de (\d+(?:\.\d+)?)", t)
    if m:
        t = t.replace(m.group(0), f"( {m.group(1)} * {m.group(2)} / 100 )")
    t = re.sub(r"\braiz (?:cuadrada )?de (\d+(?:\.\d+)?)", r"R \1", t)
    for patron, op in _OPERADORES:
        t = re.sub(patron, f" {op} ", t)
    return re.findall(r"\d+(?:\.\d+)?|[-+*/^()R]", t)


def _evaluar(tokens):
    """Shunting-yard: números, + - * / ^, paréntesis y R (raíz). Nunca ejecuta código."""
    salida, pila, anterior = [], [], None
    for tk in tokens:
        if re.fullmatch(r"\d+(?:\.\d+)?", tk):
            salida.append(float(tk))
        elif tk == "R":
            pila.append(tk)
        elif tk == "(":
            pila.append(tk)
        elif tk == ")":
            while pila and pila[-1] != "(":
                salida.append(pila.pop())
            if not pila:
                raise ValueError("paréntesis")
            pila.pop()
            if pila and pila[-1] == "R":
                salida.append(pila.pop())
        else:
            if tk == "-" and (anterior is None or anterior in PRIORIDAD or anterior == "("):
                salida.append(0.0)                               # negativo: "menos 5 más 3"
            while pila and pila[-1] in PRIORIDAD and (PRIORIDAD[pila[-1]] > PRIORIDAD[tk] or
                                                     (PRIORIDAD[pila[-1]] == PRIORIDAD[tk] and tk != "^")):
                salida.append(pila.pop())
            while pila and pila[-1] == "R":
                salida.append(pila.pop())
            pila.append(tk)
        anterior = tk
    while pila:
        op = pila.pop()
        if op == "(":
            raise ValueError("paréntesis")
        salida.append(op)
    valores = []
    for tk in salida:
        if isinstance(tk, float):
            valores.append(tk)
        elif tk == "R":
            a = valores.pop()
            if a < 0:
                raise ValueError("raíz negativa")
            valores.append(math.sqrt(a))
        else:
            b, a = valores.pop(), valores.pop()
            if tk == "/" and b == 0:
                raise ZeroDivisionError
            if tk == "^" and abs(b) > 100:
                raise ValueError("exponente enorme")
            operaciones = {"+": lambda: a + b, "-": lambda: a - b, "*": lambda: a * b, "/": lambda: a / b,
                           "^": lambda: a ** b}
            valores.append(operaciones[tk]())
    if len(valores) != 1:
        raise ValueError("expresión incompleta")
    return valores[0]


def formatear(numero):
    if abs(numero - round(numero)) < 1e-9 and abs(numero) < 1e15:
        return f"{int(round(numero)):,}".replace(",", ".")
    return f"{numero:,.4f}".rstrip("0").rstrip(".").replace(",", "_").replace(".", ",").replace("_", ".")


def calcular(texto):
    """Respuesta corta: 'Resultado: 12.' / 'Negativo. División entre cero.'"""
    try:
        tokens = _expresion(texto)
        if not tokens:
            return "Indique la operación, señor."
        return f"Resultado: {formatear(_evaluar(tokens))}."
    except ZeroDivisionError:
        return "Negativo. División entre cero."
    except (ValueError, IndexError, OverflowError):
        return "Negativo. Operación no válida."
