"""Prueba no interactiva: la lógica del explorador de MILLER (sin ventana).
Trabaja en una carpeta temporal; nunca lee ni cambia la carpeta real de MILLER."""
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
TEMPORAL = Path(tempfile.mkdtemp(prefix="miller_explorador_"))
os.environ["MILLER_DIR_SEGURIDAD"] = str(TEMPORAL / "seguridad")
from utilidades import explorador_archivos as ex  # noqa: E402

fallos = 0
PRO, NINOS = {"pro"}, {"boy"}
AMBAS = {"pro", "boy"}


def comprobar(nombre, condicion, detalle=""):
    global fallos
    if condicion:
        print(f"  OK    {nombre}")
    else:
        fallos += 1
        print(f"  FALLO {nombre} {detalle}")


base = TEMPORAL / "miller"
(base / "audios" / "rock").mkdir(parents=True)
(base / "datos" / "seguridad").mkdir(parents=True)
(base / "modelos" / "vosk").mkdir(parents=True)
(base / "cerebro").mkdir()
(base / "audios" / "tema.mp3").write_bytes(b"x" * 2048)
(base / "audios" / "rock" / "otra.mp3").write_bytes(b"y" * 10)
(base / "datos" / "seguridad" / "acceso.json").write_text("{}")
(base / "datos" / "memoria.json").write_text("[1]")
(base / "modelos" / "vosk" / "x.bin").write_bytes(b"z" * 1000)
(base / "modelos" / "y.bin").write_bytes(b"w" * 300)
(base / "descarga.exe").write_bytes(b"MZ")
(base / "LEEME.txt").write_text("hola")
(base / "cerebro" / "cerebro.py").write_text("x = 1")
fuera = TEMPORAL / "fuera.txt"
fuera.write_text("no es de MILLER")
ahora = datetime(2026, 11, 8, 20, 40, 5)
os.utime(base / "LEEME.txt", (ahora.timestamp(), ahora.timestamp()))

print("1. Raíz de MILLER: dos discos, C: bloqueado sin las dos llaves")
discos = ex.unidades(base, set())
comprobar("hay exactamente dos discos", [d["nombre"] for d in discos] == ["Disco local (C:)", "Archivos de MILLER"])
comprobar("sin llaves, C: aparece bloqueado", discos[0]["bloqueada"] is True)
comprobar("Archivos de MILLER nunca va bloqueado", discos[1]["bloqueada"] is False)
comprobar("con PRO sola, C: sigue bloqueado", ex.unidades(base, PRO)[0]["bloqueada"] is True)
comprobar("con NIÑOS sola, C: sigue bloqueado", ex.unidades(base, NINOS)[0]["bloqueada"] is True)
comprobar("con PRO y NIÑOS, C: se abre", ex.unidades(base, AMBAS)[0]["bloqueada"] is False)
comprobar("la raíz de C: es la carpeta de MILLER", discos[0]["ruta"] == base.resolve())
comprobar("la raíz de Archivos de MILLER es audios", discos[1]["ruta"] == (base / "audios").resolve())

print("2. Contenido de C: (solo con las dos llaves)")
c_sin = [e["nombre"] for e in ex.listar(base, base, set())]
comprobar("sin llaves, C: no lista nada", c_sin == [], str(c_sin))
c = [e["nombre"] for e in ex.listar(base, base, AMBAS)]
comprobar("C: trae programa, modelos y datos", {"cerebro", "datos", "modelos", "descarga.exe", "LEEME.txt"} <= set(c), str(c))
comprobar("C: no trae audios (van en Archivos de MILLER)", "audios" not in c, str(c))
comprobar("carpetas primero", c.index("cerebro") < c.index("LEEME.txt"), str(c))
arch = [e["nombre"] for e in ex.listar(base / "audios", base, set())]
comprobar("Archivos de MILLER se ve sin llaves y muestra sus secciones", {"rock", "Biblioteca musical", "Documentos", "Vídeos"} == set(arch), str(arch))

print("3. Datos y seguridad")
comprobar("datos\\seguridad está protegida", ex.protegida(base, base / "datos" / "seguridad"))
comprobar("sus archivos también", ex.protegida(base, base / "datos" / "seguridad" / "acceso.json"))
comprobar("datos entero no está protegido (sólo solo lectura)", not ex.protegida(base, base / "datos"))
mem = next(e for e in ex.listar(base / "datos", base, AMBAS) if e["nombre"] == "memoria.json")
comprobar("memoria.json sale como solo lectura", mem["solo_lectura"] is True)
seg = next(e for e in ex.listar(base / "datos", base, AMBAS) if e["nombre"] == "seguridad")
comprobar("seguridad sale como protegida", seg["protegida"] is True)

print("4. Precisión: tamaños, fechas y tipos")
mp3 = next(e for e in ex.listar(base / "audios" / "Biblioteca musical", base, set()) if e["nombre"] == "tema.mp3")
comprobar("tamaño exacto en bytes", mp3["tamano"] == 2048, str(mp3["tamano"]))
comprobar("tipo del archivo", mp3["tipo"] == "Archivo MP3", mp3["tipo"])
comprobar("las carpetas no tienen tamaño", next(e for e in ex.listar(base / "audios", base, set())
                                               if e["nombre"] == "rock")["tamano"] is None)
comprobar("tamaño exacto con separadores", ex.tamano_exacto(1234567) == "1 234 567 bytes", ex.tamano_exacto(1234567))
comprobar("tamaño legible", ex.tamano_legible(2048) == "2,0 KB" and ex.tamano_legible(5 * 1024 ** 2) == "5,0 MB")
comprobar("fecha de la tarde con a. m./p. m.", ex.fecha_legible(datetime(2026, 11, 8, 20, 40).timestamp())
          == "08/11/2026 8:40 p. m.", ex.fecha_legible(datetime(2026, 11, 8, 20, 40).timestamp()))
comprobar("medianoche es 12 a. m.", ex.fecha_legible(datetime(2026, 11, 8, 0, 5).timestamp())
          == "08/11/2026 12:05 a. m.")
comprobar("mediodía es 12 p. m.", ex.fecha_legible(datetime(2026, 11, 8, 12, 0).timestamp())
          == "08/11/2026 12:00 p. m.")
comprobar("resumen con singular y plural",
          "1 archivo · 2,0 KB" in ex.resumen(ex.listar(base / "audios" / "Biblioteca musical", base, set())),
          ex.resumen(ex.listar(base / "audios" / "Biblioteca musical", base, set())))
medida = ex.medir_carpeta(base / "modelos")
comprobar("medir carpeta: archivos y carpetas exactos", medida["archivos"] == 2 and medida["carpetas"] == 1,
          str(medida))
comprobar("medir carpeta: bytes exactos", medida["bytes"] == 1300, str(medida))
total_real = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(base) for f in fs)
comprobar("medir MILLER = suma real de todos los archivos", ex.medir_carpeta(base)["bytes"] == total_real,
          f"{ex.medir_carpeta(base)['bytes']} != {total_real}")

print("5. Dirección y navegación")
comprobar("la raíz se llama MILLER", ex.direccion(base, None) == "MILLER")
comprobar("C: se llama Disco local (C:)", ex.direccion(base, base) == "Disco local (C:)")
comprobar("dentro de C:", ex.direccion(base, base / "cerebro") == "Disco local (C:)\\cerebro")
comprobar("Archivos de MILLER", ex.direccion(base, base / "audios") == "Archivos de MILLER")
comprobar("dentro de Archivos", ex.direccion(base, base / "audios" / "rock") == "Archivos de MILLER\\rock")
comprobar("vista de C:", ex.vista_de(base, base / "cerebro") == "programa")
comprobar("vista de audios", ex.vista_de(base, base / "audios" / "rock") == "archivos")
comprobar("subir desde un disco vuelve a MILLER", ex.subir(base, base / "cerebro") == base.resolve())
comprobar("subir desde la raíz de C: va a MILLER", ex.subir(base, base) is None)
comprobar("subir desde la raíz de Archivos va a MILLER", ex.subir(base, base / "audios") is None)
comprobar("subir desde audios/rock vuelve a audios", ex.subir(base, base / "audios" / "rock")
          == (base / "audios").resolve())
comprobar("ruta escrita: MILLER", ex.ruta_desde_texto(base, "MILLER") == (True, None))
comprobar("ruta escrita: Archivos de MILLER\\rock",
          ex.ruta_desde_texto(base, "Archivos de MILLER\\rock") == (True, (base / "audios" / "rock").resolve()))
comprobar("ruta escrita: Disco local (C:)\\cerebro",
          ex.ruta_desde_texto(base, "Disco local (C:)\\cerebro") == (True, (base / "cerebro").resolve()))
ok, motivo = ex.ruta_desde_texto(base, "Disco local (C:)\\..\\..\\fuera")
comprobar("con .. no se sale de MILLER", not ok, motivo)
ok, motivo = ex.ruta_desde_texto(base, "C:\\Windows")
comprobar("una ruta absoluta de Windows se rechaza", not ok, motivo)
ok, _ = ex.ruta_desde_texto(base, "zz")
comprobar("algo que no es una ruta se rechaza", not ok)

print("6. Abrir")
ok, motivo = ex.abrir_permitido(base, base / "audios" / "tema.mp3", set())
comprobar("una canción sin llaves sí se abre", ok, motivo)
ok, motivo = ex.abrir_permitido(base, base / "cerebro" / "cerebro.py", set())
comprobar("un archivo de C: sin llaves no se abre", not ok, motivo)
ok, motivo = ex.abrir_permitido(base, base / "cerebro" / "cerebro.py", AMBAS)
comprobar("un archivo de C: con las dos llaves sí se abre", ok, motivo)
ok, motivo = ex.abrir_permitido(base, base / "descarga.exe", AMBAS)
comprobar("un programa no se abre", not ok, motivo)
ok, motivo = ex.abrir_permitido(base, base / "datos" / "seguridad" / "acceso.json", AMBAS)
comprobar("datos\\seguridad no se abre", not ok, motivo)
ok, motivo = ex.abrir_permitido(base, fuera, AMBAS)
comprobar("nada fuera de MILLER se abre", not ok, motivo)

print("7. Qué se puede modificar (solo con PRO)")
comprobar("sin PRO no se modifica una canción", not ex.modificable(base, base / "audios" / "tema.mp3", NINOS)[0])
comprobar("con PRO sí se modifica una canción", ex.modificable(base, base / "audios" / "tema.mp3", PRO)[0])
comprobar("C: sin las dos llaves no se modifica", not ex.modificable(base, base / "cerebro", PRO)[0])
comprobar("C: con las dos llaves y PRO sí se modifica", ex.modificable(base, base / "cerebro" / "cerebro.py", AMBAS)[0])
comprobar("la raíz de C: no se renombra ni borra", not ex.modificable(base, base, AMBAS)[0])
comprobar("la raíz de Archivos no se renombra ni borra", not ex.modificable(base, base / "audios", PRO)[0])
comprobar("datos no se toca ni con las llaves", not ex.modificable(base, base / "datos", AMBAS)[0])
comprobar("datos\\memoria.json no se toca", not ex.modificable(base, base / "datos" / "memoria.json", AMBAS)[0])
comprobar("nada fuera de MILLER se toca", not ex.modificable(base, fuera, AMBAS)[0])
comprobar("crear en Archivos con PRO", ex.puede_crear_en(base, base / "audios", PRO)[0])
comprobar("crear en Archivos sin PRO no", not ex.puede_crear_en(base, base / "audios", NINOS)[0])
comprobar("crear en datos no", not ex.puede_crear_en(base, base / "datos", AMBAS)[0])
comprobar("crear dentro de un archivo no", not ex.puede_crear_en(base, base / "LEEME.txt", AMBAS)[0])
comprobar("se puede crear en la raíz de C: con las dos llaves y PRO", ex.puede_crear_en(base, base, AMBAS)[0])
comprobar("nombre de nueva carpeta libre", ex.nombre_nueva_carpeta(base / "audios") == "Nueva carpeta")
(base / "audios" / "Nueva carpeta").mkdir()
comprobar("nombre de nueva carpeta con número si ya existe",
          ex.nombre_nueva_carpeta(base / "audios") == "Nueva carpeta (2)")

print("8. Copiar y cortar")
comprobar("se puede copiar una canción sin llave", ex.copiable(base, base / "audios" / "tema.mp3", set())[0])
comprobar("no se copia la raíz de un disco", not ex.copiable(base, base / "audios", AMBAS)[0])
comprobar("no se copia datos", not ex.copiable(base, base / "datos" / "memoria.json", AMBAS)[0])
comprobar("no se copia datos\\seguridad", not ex.copiable(base, base / "datos" / "seguridad", AMBAS)[0])
comprobar("de C: sin llaves no se copia", not ex.copiable(base, base / "cerebro", set())[0])
comprobar("nombre de copia", ex.nombre_copia(base / "audios", "tema.mp3") == "tema - copia.mp3")
(base / "audios" / "tema - copia.mp3").write_bytes(b"")
comprobar("nombre de copia con número si ya existe",
          ex.nombre_copia(base / "audios", "tema.mp3") == "tema - copia (2).mp3")

print("9. Nombres nuevos")
comprobar("un nombre normal vale", ex.nombre_valido("Nueva carpeta") == (True, "Nueva carpeta"))
comprobar("un nombre vacío no vale", not ex.nombre_valido("  ")[0])
comprobar("una barra no vale", not ex.nombre_valido("a/b")[0])
comprobar("un nombre reservado de Windows no vale", not ex.nombre_valido("CON")[0])
comprobar("«..» no vale", not ex.nombre_valido("..")[0])

print("10. Lo que MILLER usa no se toca")
tema = str((base / "audios" / "tema.mp3").resolve())
comprobar("la canción sonando bloquea", ex.en_uso_bajo(base / "audios" / "tema.mp3", {tema}))
comprobar("una carpeta que contiene algo en uso queda bloqueada", ex.en_uso_bajo(base / "audios", {tema}))
comprobar("otra carpeta no queda bloqueada", not ex.en_uso_bajo(base / "cerebro", {tema}))

print("11. Papelera del explorador")
destino = ex.destino_papelera(base, base / "LEEME.txt", ahora)
comprobar("lo eliminado va a datos\\papelera_explorador",
          destino.parent == (base / "datos" / "papelera_explorador").resolve(), str(destino))
comprobar("el nombre lleva la fecha y la hora", destino.name == "20261108-204005_LEEME.txt", destino.name)
comprobar("la papelera queda dentro de MILLER", ex.dentro_de(base, destino))

print("12. Ordenar y buscar")
entradas = ex.listar(base, base, AMBAS)
asc = [e["nombre"] for e in ex.ordenar(entradas, "nombre", False)]
comprobar("las carpetas van primero al ordenar por nombre", asc[:3] == ["cerebro", "datos", "modelos"], str(asc))
por_tipo = [e["tipo"] for e in ex.ordenar(entradas, "tipo", False) if not e["carpeta"]]
comprobar("ordenar por tipo agrupa los archivos", por_tipo == sorted(por_tipo), str(por_tipo))
comprobar("buscar no distingue mayúsculas", [e["nombre"] for e in ex.filtrar(entradas, "leeme")] == ["LEEME.txt"])
comprobar("buscar algo que no existe no muestra nada", ex.filtrar(entradas, "zzz-no-existe") == [])

print("13. Enlaces simbólicos: se omiten")
try:
    (base / "enlace").symlink_to(fuera)
    comprobar("un enlace a fuera no aparece", "enlace" not in [e["nombre"] for e in ex.listar(base, base, AMBAS)])
    comprobar("un enlace no se copia", not ex.copiable(base, base / "enlace", AMBAS)[0])
except (OSError, NotImplementedError):
    print("  (omitido: este sistema no permite crear enlaces)")

print("14. Secciones globales de Archivos de MILLER")
seccion = base / "audios" / "Biblioteca musical"
comprobar("una sección se reconoce", ex.seccion_de(base, seccion) == "Biblioteca musical")
comprobar("una carpeta real no es sección", ex.seccion_de(base, base / "audios" / "rock") is None)
comprobar("una sección se puede abrir aunque no exista en disco", ex.navegable(base, seccion))
comprobar("un nombre que no es sección no se abre", not ex.navegable(base, base / "audios" / "No existe"))
(base / "audios" / "peli.mp4").write_bytes(b"v" * 500)
(base / "audios" / "guia.pdf").write_bytes(b"p" * 400)
(base / "audios" / "dibujo.jpg").write_bytes(b"j" * 300)
raiz_nombres = [e["nombre"] for e in ex.listar(base / "audios", base, set())]
comprobar("la raíz muestra las tres secciones", {"Biblioteca musical", "Documentos", "Vídeos"} <= set(raiz_nombres), str(raiz_nombres))
comprobar("la raíz no muestra archivos sueltos", "tema.mp3" not in raiz_nombres, str(raiz_nombres))
comprobar("Otros archivos aparece si hay algo que no encaja", "Otros archivos" in raiz_nombres)
musica = [e["nombre"] for e in ex.listar(seccion, base, set())]
comprobar("Biblioteca musical solo tiene audio", musica == ["tema - copia.mp3", "tema.mp3"], str(musica))
docs = [e["nombre"] for e in ex.listar(base / "audios" / "Documentos", base, set())]
comprobar("Documentos solo tiene documentos", docs == ["guia.pdf"], str(docs))
videos = [e["nombre"] for e in ex.listar(base / "audios" / "Vídeos", base, set())]
comprobar("Vídeos solo tiene vídeos", videos == ["peli.mp4"], str(videos))
otros = [e["nombre"] for e in ex.listar(base / "audios" / "Otros archivos", base, set())]
comprobar("Otros archivos tiene lo que no encaja", otros == ["dibujo.jpg"], str(otros))
ruta_real = next(e["ruta"] for e in ex.listar(seccion, base, set()) if e["nombre"] == "tema.mp3")
comprobar("un archivo de una sección conserva su ruta real", Path(ruta_real).resolve() == (base / "audios" / "tema.mp3").resolve(), str(ruta_real))
comprobar("la sección no se renombra ni se borra", not ex.modificable(base, seccion, PRO)[0])
comprobar("la sección no se copia", not ex.copiable(base, seccion, AMBAS)[0])
comprobar("no se crea ni se pega dentro de una sección", not ex.puede_crear_en(base, seccion, PRO)[0])
comprobar("el archivo de dentro sí se renombra con PRO", ex.modificable(base, ruta_real, PRO)[0])
comprobar("la dirección de una sección", ex.direccion(base, seccion) == "Archivos de MILLER\\Biblioteca musical", ex.direccion(base, seccion))
comprobar("subir desde una sección vuelve a Archivos de MILLER", ex.subir(base, seccion) == (base / "audios").resolve())
medida_seccion = ex.medir_carpeta(seccion, base)
comprobar("medir una sección suma sus archivos", medida_seccion["bytes"] == 2048 and medida_seccion["archivos"] == 2, str(medida_seccion))

print()
print("Todas las comprobaciones del explorador pasaron." if not fallos else f"{fallos} comprobación(es) fallaron.")
raise SystemExit(1 if fallos else 0)
