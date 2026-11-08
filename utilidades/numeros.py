"""MILLER · Números dichos en palabras ("treinta y dos", "mil doscientos") convertidos a cifras."""
import re
import unicodedata

UNIDADES = {"cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
            "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14,
            "quince": 15, "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20,
            "veintiun": 21, "veintiuno": 21, "veintiuna": 21, "veintidos": 22, "veintitres": 23, "veinticuatro": 24,
            "veinticinco": 25, "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29}
DECENAS = {"treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90}
CENTENAS = {"cien": 100, "ciento": 100, "doscientos": 200, "doscientas": 200, "trescientos": 300, "trescientas": 300,
            "cuatrocientos": 400, "cuatrocientas": 400, "quinientos": 500, "quinientas": 500, "seiscientos": 600,
            "seiscientas": 600, "setecientos": 700, "setecientas": 700, "ochocientos": 800, "ochocientas": 800,
            "novecientos": 900, "novecientas": 900}
MULTIPLOS = {"mil": 1000, "millon": 1_000_000, "millones": 1_000_000}
NUMERICAS = set(UNIDADES) | set(DECENAS) | set(CENTENAS) | set(MULTIPLOS)


def plano(texto):
    texto = unicodedata.normalize("NFD", str(texto or "").lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", texto).strip()


def _valor(palabras):
    """Valor de una secuencia de palabras numéricas ya validada."""
    total, grupo = 0, 0
    for p in palabras:
        if p in UNIDADES:
            grupo += UNIDADES[p]
        elif p in DECENAS:
            grupo += DECENAS[p]
        elif p in CENTENAS:
            grupo += CENTENAS[p]
        elif p == "mil":
            total += (grupo or 1) * 1000
            grupo = 0
        elif p in ("millon", "millones"):
            total = (total + (grupo or 1)) * 1_000_000
            grupo = 0
    return total + grupo


def palabras_a_numeros(texto, unir_y=True):
    """'treinta y dos más cuatro' -> '32 más 4'. Con unir_y=False, 'nueve y veinte' queda '9 y 20'."""
    tokens = plano(texto).split()
    salida, i = [], 0
    while i < len(tokens):
        if tokens[i] not in NUMERICAS or (tokens[i] in ("un", "una") and
                                          (i + 1 >= len(tokens) or tokens[i + 1] not in NUMERICAS | {"hora", "minuto", "cuarto"})):
            if tokens[i] in ("un", "una") and i + 1 < len(tokens) and tokens[i + 1] in ("hora", "minuto", "minutos", "cuarto"):
                salida.append("1")
            else:
                salida.append(tokens[i])
            i += 1
            continue
        grupo, j = [tokens[i]], i + 1
        while j < len(tokens):
            if tokens[j] in NUMERICAS and tokens[j] not in ("un", "una"):
                grupo.append(tokens[j])
                j += 1
            elif (unir_y and tokens[j] == "y" and j + 1 < len(tokens) and grupo[-1] in DECENAS
                  and tokens[j + 1] in UNIDADES and UNIDADES[tokens[j + 1]] < 10):
                grupo.append(tokens[j + 1])                  # "treinta y dos"
                j += 2
            else:
                break
        salida.append(str(_valor(grupo)))
        i = j
    texto = " ".join(salida)
    return re.sub(r"(\d) (?:coma|punto) (\d+)", r"\1.\2", texto)     # "2 coma 5" -> "2.5"
