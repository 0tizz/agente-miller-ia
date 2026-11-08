# Graph Report - Miller  (2026-11-08)

## Corpus Check
- 101 files · ~1,318,285 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 35 file(s) not represented in the graph (top: .ffpreset 5, .conf 4, .firma 3)

## Summary
- 2142 nodes · 4799 edges · 105 communities (40 shown, 65 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 191 edges (avg confidence: 0.87)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Cerebro
- Memoria
- Equilibrio
- pathlib
- Iniciativa
- seguridad.py
- alarmas.py
- RutinaMatutina
- Ecualizador
- probar_reproductor.py
- Activador
- Comandos
- os
- Hablador
- time
- Emociones
- VentanaEsencia
- supervisor_biblioteca.py
- DescargadorMusica
- Escuchador
- SupervisorBiblioteca
- .procesar
- llave_boy.py
- acceso.py
- shutil
- Reproductor
- ._ciclo_interno
- re
- ventanas.py
- cuota.py
- configuracion.py
- instalador.py
- .ejecutar
- procesar_voz
- FadeController
- principal.py
- ProbadorModulos
- probar_papelera.py
- _main
- Sistema
- probar_disco_memoria.py
- PanelInteraccion
- consulta_internet.py
- ConsultorInternet
- _Musica
- ._numero
- Percepcion
- CatalogoAplicaciones
- main
- _Musica
- .abrir_sitio_web
- escribir_json
- .guardar_memoria_musical
- ._refrescar_llaves
- .guardar_recuerdo
- clave
- panel.py
- AtenuadorVoz
- Corrector
- .registrar
- integridad_codigo
- catalogo.py
- CuerpoAprendiz
- ._dibujar
- ReproductorFalso
- _guardado
- .__init__
- .controlar_ecualizador
- probar_acceso.py
- JuegoFrases
- probar_descarga.py
- ContextoOrdenes
- Rutinas
- ._medir_tamano
- probar_catalogo.py
- anunciar_alarmas
- FadeSimulado
- sanear_texto
- describir
- esperar_nombre_en_ventana
- _registrar_error_hilo
- Reproductor
- HabladorFalso
- Ini
- CerebroFalso
- entradas

## God Nodes (most connected - your core abstractions)
1. `Comandos` - 122 edges
2. `Cerebro` - 121 edges
3. `Reproductor` - 105 edges
4. `Memoria` - 85 edges
5. `SupervisorBiblioteca` - 69 edges
6. `VentanaEsencia` - 56 edges
7. `Iniciativa` - 49 edges
8. `PanelInteraccion` - 44 edges
9. `Equilibrio` - 39 edges
10. `Ecualizador` - 36 edges

## Surprising Connections (you probably didn't know these)
- `Comandos` --uses--> `Reproductor`  [INFERRED]
  cerebro/comandos.py → audio/reproductor.py
- `subir_a()` --uses--> `Reproductor`  [INFERRED]
  test/probar_volumen.py → audio/reproductor.py
- `Comandos` --uses--> `ConfigSupervisor`  [INFERRED]
  cerebro/comandos.py → audio/supervisor_biblioteca.py
- `Comandos` --uses--> `SupervisorBiblioteca`  [INFERRED]
  cerebro/comandos.py → audio/supervisor_biblioteca.py
- `Comandos` --uses--> `GestorAlarmas`  [INFERRED]
  cerebro/comandos.py → utilidades/alarmas.py

## Import Cycles
- 2-file cycle: `utilidades/acceso.py -> utilidades/cuota.py -> utilidades/acceso.py`

## Communities (105 total, 65 thin omitted)

### Community 2 - "Equilibrio"
Cohesion: 0.05
Nodes (7): bienestar(), _cerca_de_cero(), comodidad(), Equilibrio, LeyDeCuerpos, _limitar(), _tramo()

### Community 5 - "seguridad.py"
Cohesion: 0.07
Nodes (6): Pensador, _Equilibrio, _Lienzo, _ventana(), CerebroFalso, _M

### Community 6 - "alarmas.py"
Cohesion: 0.07
Nodes (18): al_cambiar_modo(), _describir_relativo(), es_pedido(), extraer_motivo(), GestorAlarmas, interpretar_momento(), tipo_pedido(), calcular() (+10 more)

### Community 7 - "RutinaMatutina"
Cohesion: 0.07
Nodes (4): Clima, Noticias, Reloj, RutinaMatutina

### Community 8 - "Ecualizador"
Cohesion: 0.08
Nodes (6): nuevo_comandos(), _Reproductor, _bandas_validas(), Ecualizador, trabajo(), _limitar()

### Community 9 - "probar_reproductor.py"
Cohesion: 0.08
Nodes (27): arrancar_panel(), Widget, agregar_a_cola(), eliminar_de_cola(), limpiar_cola(), limpiar_historial(), linea(), main() (+19 more)

### Community 12 - "os"
Cohesion: 0.09
Nodes (8): formato_db(), nombre_perfil(), sin_tildes(), abrir(), _buscar_archivo(), mostrar_en_explorador(), raices_busqueda(), ruta_navegador()

### Community 13 - "Hablador"
Cohesion: 0.08
Nodes (4): Hablador, frecuencia_mezclador(), voces_instaladas(), VozNeural

### Community 14 - "time"
Cohesion: 0.08
Nodes (9): _M, atender(), esperar(), esperar_terminal(), procesar_cola(), textos_de_la_ventana(), retener(), _M (+1 more)

### Community 15 - "Emociones"
Cohesion: 0.10
Nodes (4): Emociones, _limitar(), CerebroFalso, CerebroFalso

### Community 17 - "supervisor_biblioteca.py"
Cohesion: 0.09
Nodes (12): _cajas_mp4(), diagnosticar_extension(), identificar_contenido(), _inicio_tras_id3(), _longitud_trama_mp3(), _pistas_matroska(), _pistas_mp4(), _tipo_real() (+4 more)

### Community 18 - "DescargadorMusica"
Cohesion: 0.10
Nodes (6): buscar_ejecutable(), comprobar_ejecutable(), DescargadorMusica, trabajo(), hook(), url_segura()

### Community 20 - "SupervisorBiblioteca"
Cohesion: 0.14
Nodes (3): _escribir_json(), _iso(), SupervisorBiblioteca

### Community 22 - "llave_boy.py"
Cohesion: 0.11
Nodes (16): _canonica_llave(), codificar(), completado(), formato(), fragmento_pendiente(), _fragmentos(), _guardar(), _huella() (+8 more)

### Community 23 - "acceso.py"
Cohesion: 0.13
Nodes (17): reiniciar_intentos(), _avisar_modo(), aviso_llave_voz(), bloquear(), canonica(), _cargar(), estado_texto(), _fijar() (+9 more)

### Community 24 - "shutil"
Cohesion: 0.09
Nodes (7): CerebroFalso, reiniciar_nombre(), borrar_guardado(), buscar_ffmpeg(), _borrar(), ejecutar_si_pedida(), purgar()

### Community 27 - "re"
Cohesion: 0.14
Nodes (7): _texto_busqueda(), _normalizar(), _normalizar(), _normalizar(), _normalizar(), _norma(), _normalizar()

### Community 28 - "ventanas.py"
Cohesion: 0.16
Nodes (15): _api(), buscar(), cerrar(), disponible(), _exe_de(), limpiar_nombre(), minimizar_activa(), minimizar_todo() (+7 more)

### Community 29 - "cuota.py"
Cohesion: 0.14
Nodes (16): trabajo(), aviso_presion(), _base(), _disco(), espacio_disco(), estado_disco(), instantanea(), _libre() (+8 more)

### Community 31 - "configuracion.py"
Cohesion: 0.09
Nodes (7): es_comando_salida(), _plano(), _rango(), _ruta_base(), validar(), hace(), recuerdo()

### Community 32 - "instalador.py"
Cohesion: 0.12
Nodes (12): calcular(), trabajo(), comprobar(), faltantes(), _dentro(), _descargar(), descargar_modelo(), estado() (+4 more)

### Community 34 - "procesar_voz"
Cohesion: 0.13
Nodes (6): espera_respuesta(), procesar_voz(), hay_evento(), quiere_hablar(), reiniciar_activador(), Conversacion

### Community 36 - "principal.py"
Cohesion: 0.16
Nodes (12): atender_permiso(), atender_terminal(), _comando_de_terminal(), decidir_permiso(), descartar_eco(), ejecutar_orden(), interfaz(), pedir_permiso_para_hablar() (+4 more)

### Community 38 - "probar_papelera.py"
Cohesion: 0.12
Nodes (5): _M, wav(), crear_wav(), _reproducir(), suavizar_wav()

### Community 39 - "_main"
Cohesion: 0.11
Nodes (4): ConfigSupervisor, _leer_json(), _main(), _pid_activo()

### Community 40 - "Sistema"
Cohesion: 0.10
Nodes (4): archivo_peligroso(), ruta_dentro(), texto_para_comando(), Sistema

### Community 41 - "probar_disco_memoria.py"
Cohesion: 0.15
Nodes (4): Conexiones, hace(), memoria_nueva(), recuerdo()

### Community 49 - "CatalogoAplicaciones"
Cohesion: 0.17
Nodes (3): CatalogoAplicaciones, agregar(), _ruta_datos()

### Community 50 - "main"
Cohesion: 0.13
Nodes (10): abrir_interfaz(), cerrar_miller(), _fundir_musica(), _identidad_barra_tareas(), iniciar_musica(), main(), vigilar_cierre(), mostrar_encabezado() (+2 more)

### Community 52 - ".abrir_sitio_web"
Cohesion: 0.19
Nodes (5): buscar_archivo(), detectar_navegador(), plano(), quitar_navegador(), url_busqueda()

### Community 53 - "escribir_json"
Cohesion: 0.21
Nodes (11): _aislar(), alerta(), _desde_respaldo(), escribir_json(), _firma_valida(), firmar(), leer_json(), _obtener_clave() (+3 more)

### Community 60 - "._refrescar_llaves"
Cohesion: 0.17
Nodes (3): trabajo(), trabajo(), activas()

### Community 62 - "clave"
Cohesion: 0.18
Nodes (8): _como_miller(), _como_miller_crudo(), _normalizar(), aplicar_nombre(), conectar_atenuador(), crear_componentes(), obtener_palabra_activacion(), clave()

### Community 63 - "panel.py"
Cohesion: 0.23
Nodes (5): _es_clave(), _guardar_historial(), _leer_historial(), _ruta_historial(), _tamano()

### Community 68 - "integridad_codigo"
Cohesion: 0.20
Nodes (6): revisar(), _huellas_codigo(), integridad_codigo(), limpiar_antiguos(), resumen(), sellar_codigo()

### Community 69 - "catalogo.py"
Cohesion: 0.22
Nodes (4): _frases(), listado(), listado_completo(), Respuesta

### Community 75 - "_guardado"
Cohesion: 0.27
Nodes (5): configurar_al_iniciar(), fijado(), fijar(), _guardado(), valido()

### Community 82 - "probar_descarga.py"
Cohesion: 0.36
Nodes (6): main(), mostrar_estado(), mostrar_historial(), probar_descarga(), progreso(), descargar_musica()

### Community 90 - "anunciar_alarmas"
Cohesion: 0.33
Nodes (4): anunciar_alarmas(), gestor_alarmas(), vigilar_alarmas(), sonar_tono()

### Community 92 - "sanear_texto"
Cohesion: 0.33
Nodes (4): nombre_seguro(), sanear_entrada(), sanear_estructura(), sanear_texto()

## Knowledge Gaps
- **65 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Cerebro` connect `Cerebro` to `Memoria`, `Equilibrio`, `pathlib`, `Iniciativa`, `seguridad.py`, `alarmas.py`, `Comandos`, `os`, `time`, `Emociones`, `.procesar`, `shutil`, `re`, `configuracion.py`, `principal.py`, `probar_papelera.py`, `probar_disco_memoria.py`, `.guardar_recuerdo`, `clave`, `Corrector`, `.__init__`, `.agregar_contexto`, `.olvidar_tema`, `ContextoOrdenes`, `probar_catalogo.py`, `.recuperar_olvidado`?**
  _High betweenness centrality (0.173) - this node is a cross-community bridge._
- **Are the 11 inferred relationships involving `Comandos` (e.g. with `Cerebro` and `Reproductor`) actually correct?**
  _`Comandos` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Should `Cerebro` be split into smaller, more focused modules?**
  _Cohesion score 0.04421052631578947 - nodes in this community are weakly interconnected._
- **Why does `Comandos` connect `Comandos` to `Cerebro`, `pathlib`, `alarmas.py`, `RutinaMatutina`, `Ecualizador`, `os`, `SupervisorBiblioteca`, `Reproductor`, `re`, `ventanas.py`, `._n`, `configuracion.py`, `.ejecutar`, `ProbadorModulos`, `probar_papelera.py`, `_main`, `Sistema`, `ConsultorInternet`, `.abrir_sitio_web`, `.borrar_cancion`, `.__init__`, `.controlar_ecualizador`, `describir`?**
  _High betweenness centrality (0.156) - this node is a cross-community bridge._
- **Are the 8 inferred relationships involving `Cerebro` (e.g. with `Comandos` and `Conexiones`) actually correct?**
  _`Cerebro` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Should `Memoria` be split into smaller, more focused modules?**
  _Cohesion score 0.06210526315789474 - nodes in this community are weakly interconnected._
- **Why does `VentanaEsencia` connect `VentanaEsencia` to `Equilibrio`, `.registrar`, `._jugar_frases`, `seguridad.py`, `CuerpoAprendiz`, `._dibujar`, `PanelInteraccion`, `Percepcion`, `.publicar`, `JuegoFrases`, `._medir_tamano`, `.posiciones_circulos`, `probar_catalogo.py`, `.limpiar_terminal`?**
  _High betweenness centrality (0.126) - this node is a cross-community bridge._