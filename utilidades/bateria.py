"""MILLER · Nivel de la batería del equipo (Windows: GetSystemPowerStatus; Linux: /sys). Sin librerías extra."""
import os
from pathlib import Path


def estado():
    """{'porcentaje': int|None, 'cargando': bool|None, 'enchufado': bool|None, 'minutos': int|None, 'hay_bateria': bool}"""
    if os.name == "nt":
        try:
            import ctypes

            class _Estado(ctypes.Structure):
                _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                            ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                            ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]
            e = _Estado()
            if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(e)):
                return {"hay_bateria": False}
            sin_bateria = e.BatteryFlag == 128 or e.BatteryFlag == 255 and e.BatteryLifePercent == 255
            porcentaje = None if e.BatteryLifePercent == 255 else int(e.BatteryLifePercent)
            enchufado = {0: False, 1: True}.get(e.ACLineStatus)
            minutos = None if e.BatteryLifeTime in (0xFFFFFFFF, -1) else int(e.BatteryLifeTime) // 60
            return {"hay_bateria": not sin_bateria and porcentaje is not None, "porcentaje": porcentaje,
                    "enchufado": enchufado, "cargando": bool(e.BatteryFlag & 8), "minutos": minutos}
        except Exception:
            return {"hay_bateria": False}
    base = Path("/sys/class/power_supply")
    try:
        for d in base.iterdir():
            if (d / "type").read_text().strip() == "Battery":
                porcentaje = int((d / "capacity").read_text().strip())
                st = (d / "status").read_text().strip().lower()
                return {"hay_bateria": True, "porcentaje": porcentaje, "cargando": st == "charging",
                        "enchufado": st in ("charging", "full", "not charging"), "minutos": None}
    except OSError:
        pass
    return {"hay_bateria": False}


def describir(e=None):
    e = estado() if e is None else e
    if not e.get("hay_bateria"):
        return "Este equipo no tiene batería: funciona conectado a la corriente."
    p = e.get("porcentaje")
    partes = [f"Batería al {p} %"]
    if e.get("cargando"):
        partes.append("cargando")
    elif e.get("enchufado"):
        partes.append("conectada a la corriente")
    texto = ", ".join(partes) + "."
    minutos = e.get("minutos")
    if minutos and not e.get("enchufado"):
        h, m = divmod(minutos, 60)
        texto += f" Quedan unas {h} h {m:02d} min." if h else f" Quedan unos {m} minutos."
    if p is not None and p <= 15 and not e.get("enchufado"):
        texto += " Conviene conectar el cargador, señor."
    return texto
