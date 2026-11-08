"""MILLER · Reloj del sistema."""
from datetime import datetime


def hora_12(momento=None, minutos=True):
    """Hora de 1 a 12 con a. m. / p. m.: 15:05 -> '3:05 p. m.', 00:30 -> '12:30 a. m.', 12:00 -> '12:00 p. m.'."""
    momento = momento or datetime.now()
    hora = momento.hour % 12 or 12
    sufijo = "a. m." if momento.hour < 12 else "p. m."
    return f"{hora}:{momento.minute:02d} {sufijo}" if minutos else f"{hora} {sufijo}"


def hora_12_de(hora24):
    """Solo la hora (0-23) -> '8 p. m.'."""
    hora24 = int(hora24) % 24
    return f"{hora24 % 12 or 12} {'a. m.' if hora24 < 12 else 'p. m.'}"


def frase_hora(momento=None):
    """'Son las 3:05 p. m.' / 'Es la 1:20 a. m.' (en español la una va en singular)."""
    momento = momento or datetime.now()
    return f"{'Es la' if momento.hour % 12 == 1 else 'Son las'} {hora_12(momento)}"

class Reloj:
    """Proporciona información temporal del sistema."""
    # DÍAS DE LA SEMANA
    DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo",)
    MESES = (
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    )
    def obtener_hora(self):
        """Hora actual de 1 a 12 con a. m. / p. m."""
        return hora_12()
    def obtener_fecha(self):
        """24 de agosto de 2026"""
        ahora = datetime.now()
        dia = ahora.day
        mes = self.MESES[ahora.month - 1]
        año = ahora.year
        return (f"{dia} de {mes} de {año}")
    def obtener_dia_semana(self):
        """Devuelve el día actual de la semana."""
        ahora = datetime.now()
        return self.DIAS[ahora.weekday()]
    def obtener_informacion(self):
        """Devuelve toda la información temporal en un diccionario."""
        ahora = datetime.now()
        return {
            "hora":
                hora_12(ahora),
            "hora_24":
                ahora.strftime("%H:%M"),
            "fecha":
                self.obtener_fecha(),
            "dia":
                self.obtener_dia_semana(),
            "dia_numero":
                ahora.day,
            "mes":
                ahora.month,
            "año":
                ahora.year,
        }
    def obtener_periodo(self):
        """Determina el periodo del día."""
        hora = datetime.now().hour
        if 0 <= hora < 6:
            return "madrugada"
        if 6 <= hora < 12:
            return "mañana"
        if 12 <= hora < 18:
            return "tarde"
        return "noche"
if __name__ == "__main__":
    reloj = Reloj()
    print("Hora:", reloj.obtener_hora())
    print("Fecha:", reloj.obtener_fecha())
    print("Día:", reloj.obtener_dia_semana())
    print("Periodo:", reloj.obtener_periodo())
    print()
    print("Información completa:")
    print(reloj.obtener_informacion())
