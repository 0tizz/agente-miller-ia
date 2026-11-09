"""MILLER · Explorador de archivos: navegación y cambios (sin ventana).

Como el Explorador de Windows, con dos discos dentro de la carpeta de MILLER:
- MILLER: la raíz. Muestra sus dos discos.
- Disco local (C:): la carpeta de MILLER con el programa, los modelos y los datos (salvo audios).
  Para entrar y para hacer cualquier cosa hacen falta las DOS llaves: PRO y NIÑOS (boy).
- Archivos de MILLER: la carpeta audios. Se ve sin llave; modificarla necesita PRO. Su raíz se divide en
  secciones globales (Biblioteca musical, Documentos, Vídeos y Otros archivos si hay): son vistas de los
  archivos de audios, no carpetas en disco. No se renombran, no se borran y no se pega nada dentro de ellas.

Reglas:
- Nunca se sale de la carpeta de MILLER: ni con «..», ni con rutas absolutas, ni con enlaces.
- datos\\seguridad se ve (nombre y tamaño), pero no se abre ni se copia: ahí están las claves y las firmas.
- datos entero solo se mira: no se renombra, no se copia y no se borra desde aquí. La única escritura
  en datos es la papelera del propio explorador (datos\\papelera_explorador).
- Modificar (crear carpetas, copiar, cortar y pegar, renombrar, eliminar) necesita la llave PRO.
- Lo que MILLER está usando (canción sonando, cola, historial) no se mueve, renombra ni borra.
- Las raíces de los discos no se renombran ni se borran. Abrir solo con el programa predeterminado;
  nunca ejecutables ni scripts.
"""
import os
from datetime import datetime
from pathlib import Path

from utilidades import seguridad

RAIZ_MILLER = "MILLER"
DISCOS = {"programa": "Disco local (C:)", "archivos": "Archivos de MILLER"}
CARPETA_ARCHIVOS = "audios"
LLAVES_DISCO_C = frozenset({"pro", "boy"})
PROTEGIDA = ("datos", "seguridad")
PAPELERA = ("datos", "papelera_explorador")
MENSAJE_PRO = "Negativo. Modificar necesita la llave PRO: póngala en la página MILLER, señor."
MENSAJE_BLOQUEADO = "Negativo. El disco local (C:) necesita las llaves PRO y NIÑOS: póngalas en la página MILLER, señor."
_INVALIDOS = set('<>:"/\\|?*')
_RESERVADOS = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def _resuelta(ruta):
    try:
        return Path(ruta).resolve()
    except OSError:
        return None


def dentro_de(base, ruta):
    """True si «ruta» es la carpeta base o está dentro de ella (sin seguir enlaces)."""
    b, r = _resuelta(base), _resuelta(ruta)
    return b is not None and r is not None and (r == b or b in r.parents)


def _partes(base, ruta):
    b, r = _resuelta(base), _resuelta(ruta)
    if b is None or r is None:
        return None
    try:
        return r.relative_to(b).parts
    except ValueError:
        return None


def vista_de(base, ruta):
    """«archivos» dentro de audios; «programa» en el resto de MILLER; None si está fuera de MILLER."""
    partes = _partes(base, ruta)
    if partes is None:
        return None
    if partes and partes[0].lower() == CARPETA_ARCHIVOS:
        return "archivos"
    return "programa"


def raiz_de(base, vista):
    """La carpeta raíz de un disco: la de MILLER para C:, audios para Archivos de MILLER."""
    b = _resuelta(base)
    return b / CARPETA_ARCHIVOS if vista == "archivos" else b


def es_raiz_de_disco(base, ruta):
    r = _resuelta(ruta)
    return r is not None and (r == raiz_de(base, "programa") or r == raiz_de(base, "archivos"))


def puede_ver(vista, llaves):
    """Archivos de MILLER se ven siempre; Disco local (C:) solo con las dos llaves."""
    return vista != "programa" or LLAVES_DISCO_C <= set(llaves or ())


def en_datos(base, ruta):
    partes = _partes(base, ruta)
    return bool(partes) and partes[0].lower() == "datos"


def protegida(base, ruta):
    """datos\\seguridad: se ve, pero no se abre ni se copia."""
    partes = _partes(base, ruta)
    return partes is not None and tuple(p.lower() for p in partes[:2]) == PROTEGIDA


def direccion(base, ruta):
    """Lo que muestra la barra de dirección: «MILLER», «Disco local (C:)\\cerebro», «Archivos de MILLER\\rock»."""
    if ruta is None:
        return RAIZ_MILLER
    vista = vista_de(base, ruta)
    partes = _partes(base, ruta)
    if vista is None or partes is None:
        return str(ruta)
    resto = partes[1:] if vista == "archivos" else partes
    return "\\".join([DISCOS[vista], *resto])


def tamano_legible(bytes_):
    if bytes_ is None:
        return ""
    for unidad, tope in (("GB", 1024 ** 3), ("MB", 1024 ** 2), ("KB", 1024)):
        if bytes_ >= tope:
            return f"{bytes_ / tope:.1f} {unidad}".replace(".", ",")
    return f"{bytes_} B"


def tamano_exacto(bytes_):
    """Los bytes exactos, como en Propiedades: «1 234 567 bytes»."""
    if bytes_ is None:
        return ""
    return f"{bytes_:,}".replace(",", " ") + " bytes"


def fecha_legible(instante):
    """Fecha y hora con la hora en 12 h: «08/11/2026 8:40 p. m.»."""
    dt = datetime.fromtimestamp(instante)
    hora = dt.hour % 12 or 12
    sufijo = "a. m." if dt.hour < 12 else "p. m."
    return f"{dt:%d/%m/%Y} {hora}:{dt:%M} {sufijo}"


def tipo_de(ruta, es_carpeta):
    if es_carpeta:
        return "Carpeta"
    extension = Path(ruta).suffix.lower().lstrip(".")
    return f"Archivo {extension.upper()}" if extension else "Archivo"


def _entrada(ruta, es_carpeta, st, base):
    return {
        "nombre": ruta.name, "ruta": ruta, "carpeta": es_carpeta, "unidad": None,
        "tipo": tipo_de(ruta, es_carpeta),
        "tamano": None if es_carpeta else st.st_size,
        "modificado": fecha_legible(st.st_mtime), "mtime": st.st_mtime,
        "protegida": protegida(base, ruta), "solo_lectura": en_datos(base, ruta), "bloqueada": False,
    }


SECCIONES = (
    ("Biblioteca musical", frozenset({".mp3", ".wav", ".ogg", ".flac"})),
    ("Documentos", frozenset({".pdf", ".doc", ".docx", ".txt", ".md", ".rtf", ".odt", ".csv",
                              ".xls", ".xlsx", ".ppt", ".pptx"})),
    ("Vídeos", frozenset({".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".m4v", ".flv"})),
)
NOMBRE_OTROS = "Otros archivos"
NOMBRES_SECCIONES = tuple(nombre for nombre, _ in SECCIONES) + (NOMBRE_OTROS,)


def categoria_de(nombre):
    """Sección global de un archivo según su extensión; Otros archivos si no encaja en ninguna."""
    extension = Path(nombre).suffix.lower()
    for seccion, extensiones in SECCIONES:
        if extension in extensiones:
            return seccion
    return NOMBRE_OTROS


def seccion_de(base, ruta):
    """Nombre de la sección si «ruta» es una sección virtual de Archivos de MILLER; si no, None."""
    partes = _partes(base, ruta)
    if partes is None or len(partes) != 2 or partes[0].lower() != CARPETA_ARCHIVOS:
        return None
    return partes[1] if partes[1] in NOMBRES_SECCIONES else None


def navegable(base, ruta):
    """True si se puede entrar en «ruta»: una carpeta real o una sección."""
    return seccion_de(base, ruta) is not None or Path(ruta).is_dir()


def _entrada_seccion(base, nombre):
    return {
        "nombre": nombre, "ruta": raiz_de(base, "archivos") / nombre, "carpeta": True, "unidad": None,
        "tipo": "Sección de archivos", "tamano": None, "modificado": "", "mtime": 0.0,
        "protegida": False, "solo_lectura": False, "bloqueada": False,
    }


def _secciones_raiz(base):
    """Las secciones de la raíz de Archivos de MILLER. «Otros archivos» solo aparece si hay algo que no encaja."""
    hay_otros = False
    try:
        with os.scandir(raiz_de(base, "archivos")) as iterador:
            for entrada in iterador:
                try:
                    if entrada.is_symlink() or entrada.is_dir(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                if categoria_de(entrada.name) == NOMBRE_OTROS:
                    hay_otros = True
                    break
    except OSError:
        pass
    nombres = [n for n, _ in SECCIONES] + ([NOMBRE_OTROS] if hay_otros else [])
    return [_entrada_seccion(base, n) for n in nombres]


def _listar_seccion(seccion, base):
    """Los archivos de audios que caen en una sección (solo el nivel de audios; cada uno con su ruta real)."""
    salida = []
    try:
        with os.scandir(raiz_de(base, "archivos")) as iterador:
            for entrada in iterador:
                try:
                    if entrada.is_symlink() or entrada.is_dir(follow_symlinks=False):
                        continue
                    if categoria_de(entrada.name) != seccion:
                        continue
                    st = entrada.stat(follow_symlinks=False)
                except OSError:
                    continue
                salida.append(_entrada(Path(entrada.path), False, st, base))
    except OSError:
        return []
    salida.sort(key=lambda e: e["nombre"].lower())
    return salida


def listar(carpeta, base, llaves=()):
    """Entradas de una carpeta: carpetas primero, luego archivos, por nombre. Los enlaces se omiten.
    La carpeta de MILLER (disco C:) no muestra audios: eso está en Archivos de MILLER. La raíz de Archivos de
    MILLER muestra sus secciones; los archivos se ven dentro de cada una. Sin las llaves que pide el disco, sale vacía."""
    carpeta = Path(carpeta)
    vista = vista_de(base, carpeta)
    if vista is None or not puede_ver(vista, llaves):
        return []
    seccion = seccion_de(base, carpeta)
    if seccion is not None:
        return _listar_seccion(seccion, base)
    if not carpeta.is_dir():
        return []
    resuelta = _resuelta(carpeta)
    en_raiz_c = vista == "programa" and resuelta == _resuelta(base)
    en_raiz_archivos = vista == "archivos" and resuelta == _resuelta(raiz_de(base, "archivos"))
    entradas = []
    try:
        with os.scandir(carpeta) as iterador:
            for entrada in iterador:
                if en_raiz_c and entrada.name.lower() == CARPETA_ARCHIVOS:
                    continue
                try:
                    if entrada.is_symlink():
                        continue
                    es_carpeta = entrada.is_dir(follow_symlinks=False)
                    if en_raiz_archivos and (not es_carpeta or entrada.name in NOMBRES_SECCIONES):
                        continue
                    st = entrada.stat(follow_symlinks=False)
                except OSError:
                    continue
                entradas.append(_entrada(Path(entrada.path), es_carpeta, st, base))
    except OSError:
        return []
    if en_raiz_archivos:
        entradas.extend(_secciones_raiz(base))
    entradas.sort(key=lambda e: (not e["carpeta"], e["nombre"].lower()))
    return entradas


def unidades(base, llaves=()):
    """La raíz de MILLER: sus dos discos. El de C: siempre aparece; sin las dos llaves va bloqueado."""
    salida = []
    for vista in ("programa", "archivos"):
        salida.append({
            "nombre": DISCOS[vista], "ruta": raiz_de(base, vista), "carpeta": True, "unidad": vista,
            "tipo": "Disco local" if vista == "programa" else "Carpeta de archivos",
            "tamano": None, "modificado": "", "mtime": 0.0,
            "protegida": False, "solo_lectura": False, "bloqueada": not puede_ver(vista, llaves),
        })
    return salida


def subcarpetas(carpeta, base, llaves=()):
    return [e for e in listar(carpeta, base, llaves) if e["carpeta"]]


def ordenar(entradas, clave="nombre", descendente=False):
    """Como el Explorador: las carpetas siempre primero; cada grupo ordenado por la columna elegida."""
    claves = {
        "nombre": lambda e: e["nombre"].lower(),
        "tipo": lambda e: e["tipo"].lower(),
        "tamano": lambda e: e["tamano"] or 0,
        "modificado": lambda e: e["mtime"],
    }
    orden = claves.get(clave, claves["nombre"])
    carpetas = sorted((e for e in entradas if e["carpeta"]), key=orden, reverse=descendente)
    archivos = sorted((e for e in entradas if not e["carpeta"]), key=orden, reverse=descendente)
    return carpetas + archivos


def filtrar(entradas, texto):
    """Las entradas cuyo nombre contiene el texto, sin distinguir mayúsculas. Vacío = todas."""
    buscado = (texto or "").strip().lower()
    if not buscado:
        return list(entradas)
    return [e for e in entradas if buscado in e["nombre"].lower()]


def _plural(n, uno, varios):
    return f"{n} {uno if n == 1 else varios}"


def resumen(entradas):
    carpetas = sum(1 for e in entradas if e["carpeta"])
    archivos = [e for e in entradas if not e["carpeta"]]
    total = sum(e["tamano"] or 0 for e in archivos)
    return (f"{_plural(carpetas, 'carpeta', 'carpetas')} · {_plural(len(archivos), 'archivo', 'archivos')} · "
            f"{tamano_legible(total)}")


def medir_carpeta(ruta, base=None):
    """Cuenta lo que hay dentro: archivos, carpetas y bytes exactos. Los enlaces no se siguen."""
    seccion = seccion_de(base, ruta) if base is not None else None
    if seccion is not None:
        archivos = _listar_seccion(seccion, base)
        return {"archivos": len(archivos), "carpetas": 0, "bytes": sum(a["tamano"] or 0 for a in archivos), "errores": 0}
    archivos = carpetas = bytes_ = errores = 0
    pendientes = [Path(ruta)]
    while pendientes:
        actual = pendientes.pop()
        try:
            with os.scandir(actual) as iterador:
                for entrada in iterador:
                    try:
                        if entrada.is_symlink():
                            continue
                        if entrada.is_dir(follow_symlinks=False):
                            carpetas += 1
                            pendientes.append(Path(entrada.path))
                        else:
                            archivos += 1
                            bytes_ += entrada.stat(follow_symlinks=False).st_size
                    except OSError:
                        errores += 1
        except OSError:
            errores += 1
    return {"archivos": archivos, "carpetas": carpetas, "bytes": bytes_, "errores": errores}


def abrir_permitido(base, ruta, llaves=()):
    """(ok, motivo). Solo archivos normales dentro de MILLER, no en datos\\seguridad y no ejecutables."""
    ruta = Path(ruta)
    if not dentro_de(base, ruta):
        return False, "Negativo. Eso está fuera de MILLER, señor."
    if not puede_ver(vista_de(base, ruta), llaves):
        return False, MENSAJE_BLOQUEADO
    if ruta.is_symlink():
        return False, "Negativo. Los enlaces no se abren desde aquí, señor."
    if ruta.is_dir():
        return False, "Negativo. Es una carpeta: entre en ella, señor."
    if protegida(base, ruta):
        return False, "Negativo. Esa carpeta guarda claves y firmas: se puede ver, pero no abrir, señor."
    if seguridad.archivo_peligroso(ruta):
        return False, f"Negativo. Por seguridad no abro {ruta.name}: es un programa o un script, señor."
    if not ruta.is_file():
        return False, "Negativo. No existe, señor."
    return True, ""


def subir(base, ruta):
    """Ruta de la carpeta de encima. None = la raíz de MILLER (desde la raíz de un disco se vuelve a ella)."""
    if ruta is None or es_raiz_de_disco(base, ruta):
        return None
    padre = _resuelta(ruta).parent
    return padre if dentro_de(base, padre) else None


def ruta_desde_texto(base, texto):
    """(True, ruta) o (False, motivo). La ruta None es la raíz de MILLER. Acepta «MILLER», «Disco local (C:)\\…»,
    «Archivos de MILLER\\…» o «MILLER\\…». Cualquier ruta que salga de MILLER se rechaza."""
    t = (texto or "").strip().replace("/", "\\").rstrip("\\")
    if not t:
        return False, "Negativo. Escriba una ruta, señor."
    if t.lower() == RAIZ_MILLER.lower():
        return True, None
    for vista, etiqueta in DISCOS.items():
        if t.lower() == etiqueta.lower() or t.lower().startswith(etiqueta.lower() + "\\"):
            raiz = raiz_de(base, vista)
            resto = [p for p in t[len(etiqueta):].split("\\") if p]
            destino = raiz.joinpath(*resto).resolve()
            if not dentro_de(raiz, destino):
                return False, "Negativo. Esa ruta sale de su disco, señor."
            return True, destino
    partes = [p for p in t.split("\\") if p]
    if partes and partes[0].lower() == RAIZ_MILLER.lower():
        destino = _resuelta(base).joinpath(*partes[1:]).resolve()
        if not dentro_de(base, destino):
            return False, "Negativo. Esa ruta sale de MILLER, señor."
        return True, destino
    return False, "Negativo. No entiendo esa ruta, señor."


def nombre_valido(nombre):
    """(True, nombre limpio) o (False, motivo). Mismas reglas de seguridad de MILLER, con un mensaje claro."""
    limpio = (nombre or "").strip()
    if not limpio:
        return False, "Negativo. El nombre está vacío, señor."
    if len(limpio) > 120:
        return False, "Negativo. El nombre es demasiado largo, señor."
    if limpio in (".", "..") or any(c in _INVALIDOS or ord(c) < 32 for c in limpio):
        return False, "El nombre tiene caracteres que Windows no admite (\\ / : * ? \" < > |)."
    if limpio.endswith("."):
        return False, "Negativo. El nombre no puede acabar en punto, señor."
    if limpio.split(".")[0].upper() in _RESERVADOS:
        return False, "Negativo. Ese nombre está reservado por Windows, señor."
    if seguridad.nombre_seguro(limpio) != limpio:
        return False, "Negativo. Ese nombre no es seguro para MILLER, señor."
    return True, limpio


def nombre_nueva_carpeta(carpeta):
    """«Nueva carpeta», o «Nueva carpeta (2)»… si ya existe."""
    candidato, n = "Nueva carpeta", 2
    while (Path(carpeta) / candidato).exists():
        candidato, n = f"Nueva carpeta ({n})", n + 1
    return candidato


def nombre_copia(carpeta, nombre):
    """«tema.mp3» → «tema - copia.mp3»; si ya existe, «tema - copia (2).mp3»…"""
    ruta = Path(nombre)
    raiz_nombre, sufijo = ruta.stem, ruta.suffix
    candidato, n = f"{raiz_nombre} - copia{sufijo}", 2
    while (Path(carpeta) / candidato).exists():
        candidato, n = f"{raiz_nombre} - copia ({n}){sufijo}", n + 1
    return candidato


def puede_crear_en(base, carpeta, llaves):
    """(ok, motivo) para crear, copiar o pegar dentro de una carpeta de MILLER."""
    c = Path(carpeta)
    if seccion_de(base, c) is not None:
        return False, "Negativo. Las secciones son vistas: para crear o pegar, entre en una carpeta de archivos, señor."
    if not dentro_de(base, c) or not c.is_dir() or c.is_symlink():
        return False, "Negativo. Esa carpeta no está en MILLER, señor."
    if not puede_ver(vista_de(base, c), llaves):
        return False, MENSAJE_BLOQUEADO
    if en_datos(base, c):
        return False, "Negativo. datos solo se puede mirar: aquí no se crea ni se pega nada, señor."
    if "pro" not in set(llaves or ()):
        return False, MENSAJE_PRO
    return True, ""


def modificable(base, ruta, llaves):
    """(ok, motivo) para renombrar, eliminar o mover algo. Las raíces de los discos y datos no se tocan."""
    r = Path(ruta)
    if r.is_symlink():
        return False, "Negativo. Los enlaces no se modifican, señor."
    if not dentro_de(base, r):
        return False, "Negativo. Eso está fuera de MILLER, señor."
    if seccion_de(base, r) is not None:
        return False, "Negativo. Una sección no se renombra ni se borra: es una vista de sus archivos, señor."
    if es_raiz_de_disco(base, r):
        return False, "Negativo. La raíz de un disco no se renombra ni se borra, señor."
    if not puede_ver(vista_de(base, r), llaves):
        return False, MENSAJE_BLOQUEADO
    if en_datos(base, r):
        return False, "Negativo. datos guarda la memoria y las claves de MILLER: solo se puede mirar, señor."
    if "pro" not in set(llaves or ()):
        return False, MENSAJE_PRO
    return True, ""


def copiable(base, ruta, llaves):
    """(ok, motivo) para copiar o cortar: hay que poder verlo, y no puede ser un disco ni estar en datos."""
    r = Path(ruta)
    if r.is_symlink():
        return False, "Negativo. Los enlaces no se copian, señor."
    if not dentro_de(base, r):
        return False, "Negativo. Eso está fuera de MILLER, señor."
    if es_raiz_de_disco(base, r):
        return False, "Negativo. Un disco entero no se copia desde aquí, señor."
    if seccion_de(base, r) is not None:
        return False, "Negativo. Una sección no se copia: copie los archivos que hay dentro, señor."
    if not puede_ver(vista_de(base, r), llaves):
        return False, MENSAJE_BLOQUEADO
    if protegida(base, r):
        return False, "datos\\seguridad guarda las claves: no se copia."
    if en_datos(base, r):
        return False, "datos solo se mira: no se copia desde aquí."
    return True, ""


def en_uso_bajo(ruta, en_uso):
    """True si la ruta es, o contiene, algo que MILLER está usando (canción sonando, cola o historial)."""
    r = str(Path(ruta).resolve()).casefold()
    prefijo = r + os.sep
    return any(u.casefold() == r or u.casefold().startswith(prefijo) for u in en_uso)


def destino_papelera(base, ruta, ahora):
    """Dónde se guarda lo eliminado: datos\\papelera_explorador\\AAAAMMDD-HHMMSS_nombre."""
    carpeta = Path(base).resolve().joinpath(*PAPELERA)
    nombre = Path(ruta).name
    marca = f"{ahora:%Y%m%d-%H%M%S}"
    destino = carpeta / f"{marca}_{nombre}"
    n = 2
    while destino.exists():
        destino = carpeta / f"{marca}_{n}_{nombre}"
        n += 1
    return destino
