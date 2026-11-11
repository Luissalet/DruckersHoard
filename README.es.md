# Drucker's Hoard

La oficina de encargos profesionales de la familia Hoard. Guarda un expediente por encargo y ayuda con cinco tareas: cambios de alcance, propuestas, revisión de entregables y paquetes de entrega.

No es un CRM. Los contactos siguen en People, los movimientos de dinero en Ledger y los archivos en Atlas. Aquí solo se guardan referencias (`{app, id}`, una ruta o una URL), nunca copias. Un cobro sin referencia a Ledger queda marcado como `manual`.

## Arrancar

Python 3.11 o posterior.

```
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"     # Windows; en otros sistemas .venv/bin/python
python -m drucker                                    # http://127.0.0.1:5246/
python -m pytest -q
```

`--port` cambia el puerto. `DRUCKER_DATA` (o `--data-dir`) elige la carpeta de datos; por defecto `data/` del repositorio, ignorada por Git. Contiene `drucker.db` (SQLite), `mcp-token` y `packages/`.

## Qué hace

| Página | Tarea |
| --- | --- |
| Encargos | Lista y expediente por encargo. Pestañas: Alcance, Hitos, Materiales, Decisiones, Horas reales, Entregables, Cobros, Órdenes de cambio, Referencias, Historial. Cada cambio queda en el historial con el valor anterior y el nuevo. |
| Comparar alcance | Petición inicial, acuerdo y petición nueva (texto o elementos). Cada elemento sale como añadido, quitado, ambiguo, ya incluido o sin cambio. El esfuerzo es un rango de horas con su motivo; tres opciones: incluir, orden de cambio con rango, aplazar; cada opción se puede elegir y queda como decisión. Se pueden proponer bandas desde horas reales y editar sinónimos. |
| Propuesta | Borrador en Markdown, HTML o DOCX, con plantilla opcional por tipo de encargo. Cada frase lleva etiqueta: verificada (con su dato de origen), supuesto o pregunta. La exportación se rechaza si el texto contiene un nombre interno de la lista prohibida. |
| Revisión | Versiones de cada entregable (referencia de archivo y SHA-256), comentarios anclados a una versión y, si se quiere, a página, región, tramo de tiempo u objeto. Estado abierto / corregido en la versión N / no se corrige. Una sola versión marcada para entregar. El comentario sobre una versión vieja se muestra como obsoleto. |
| Paquete | Verifica el paquete de una versión (archivos existen, hashes coinciden, exportaciones abren, fuentes de datos autorizadas, instrucciones y límites presentes) y escribe `manifest.json` y `package.zip`. No queda listo si falla una comprobación. |

La interfaz está en castellano y en inglés (selector en la cabecera; se recuerda la elección).

## Horas reales, referencias vivas, decisiones

- **Bandas desde horas reales.** Cada encargo cerrado puede registrar puntos de `effort` (tipo de trabajo, medida, horas, unidades). `GET /api/bands/suggest` / `drucker_bands_suggest` los convierte en un rango propuesto por parte de banda (percentil 10 a 90 con tres o más muestras, mínimo y máximo observados con menos) e informa de media, desviación, mínimo, máximo y una palabra: `ok`, `scattered` (desviación por encima del 60 % de la media) o `insufficient`. No se aplica nada solo; «Aplicar las propuestas fiables» en Comparar alcance las guarda con `drucker_settings`.
- **Referencias vivas.** `GET /api/engagements/{id}/refs` / `drucker_refs_resolve` preguntan por el bus de la familia a People (`get_person`), Ledger (`list_entries` / `search_entries` alrededor de la fecha del cobro) y Atlas (`atlas_file_resolve`) por el nombre, importe y ruta actuales, y si siguen coincidiendo con lo guardado. Solo lectura: no se copia ni se guarda nada. Si el Hub o la otra app no están en marcha, cada referencia dice `unavailable` y queda como estaba.
- **Punteros de Atlas en paquetes.** Una exportación o un editable puede ser `atlas:<id>` (o `{atlas, path}`): el paquete pide a Atlas la ruta y el SHA-256 actuales, comprueba los bytes contra esa revisión y usa la ruta guardada solo como recurso si Atlas no responde.
- **Más formatos.** DOCX, XLSX, SVG y MP4/M4V se validan por estructura (partes y relaciones OOXML, hojas, viewBox y formas, moov / pistas / mdat). El PDF comprueba la tabla xref, el trailer, el árbol de páginas y el EOF; el GLB comprueba trozos, accesores y rangos de buffer y, si Vulcan está en marcha, añade el resultado de su validador Khronos (`gltf_validate`): los errores impiden el paquete, los avisos no.
- **Plantillas y DOCX.** Un encargo tiene tipo (`general`, `report`, `data`, `design`, `training`). La propuesta añade el método, condiciones y preguntas habituales de ese tipo, siempre como `assumption` o `question`, nunca `verified`; `general` no añade nada. `format: docx` escribe `propuesta.docx` / `proposal.docx` (bytes deterministas) en `data/proposals/<id>/`; vale el mismo rechazo por lista prohibida.
- **Sinónimos.** Grupos como `informe = reporte` se comparten (`drucker_settings` con `synonyms`) o van por encargo (`drucker_synonyms`, `PUT /api/engagements/{id}/synonyms`). Las coincidencias logradas por sinónimo llevan `via_synonyms`.
- **Decisiones y órdenes de cambio.** `drucker_scope_decide` / `POST /api/engagements/{id}/decide` anota en el cuaderno de decisiones la opción elegida para una petición (`include`, `change_order` con horas, `defer`, `specify`) con su rango de horas y dinero, y para incluir y orden de cambio añade un punto de alcance acordado marcado como cambio. `drucker_change_orders` / `GET /api/engagements/{id}/change-orders` (`.md` para Markdown) lista las órdenes de cambio vigentes con totales y presupuesto; si una petición se decidió dos veces solo cuenta la última.

## Comparación de alcance

La coincidencia es determinista: palabras sin tildes con raíz simplificada, solapamiento de Jaccard y razón de secuencia de difflib. Si la coincidencia es dudosa, el elemento es `ambiguous`; nunca se fuerza. Un número distinto («5» a «8 plantillas») o una negación invertida («con» a «sin anexos») es ambiguo a propósito.

El esfuerzo sale de bandas editables y de qué entregables e hitos toca cada elemento:

- `format`: formato de salida de entregables existentes. Solo la última etapa. Por defecto 1-4 h por entregable.
- `pipeline`: cambia cómo se produce el trabajo. Etapa anterior, así que se rehace todo lo posterior. Por defecto 16-40 h más 4-10 h por cada entregable o hito abierto adicional.
- `quantity`: más de lo mismo, por unidad extra.
- `content`: solo un solapamiento ambiguo con un punto acordado que pide más (por defecto 4-12 h, mínimo forzado a 0).
- `given`: las horas que indiques en el elemento (`{text, hours}` con un número, `[min,max]` o `{min,max}`) se usan tal cual.

El trabajo nuevo sin nada parecido en el acuerdo («una app móvil para comerciales») no recibe horas: sale como `added`, esfuerzo `unestimated` (necesita especificación), aparte y fuera de los totales, que muestran «+ N puntos sin estimar». Opciones: `specify` (especificar y estimar aparte) o `defer` (aplazar). Una banda por defecto infravaloraría un producto entero.

### Idioma

Todo texto que el servidor escribe para personas (motivos, opciones, notas, avisos de revisión, comprobaciones de paquete, líneas de historial, errores) sale en `lang` (`es` castellano, `en`). Las herramientas y la ruta de propuesta aceptan `lang`; la interfaz envía su idioma en la cabecera `X-Lang` en cada llamada. Sin ninguno, la respuesta es en inglés (las propuestas, en castellano). Los campos de máquina (`class`, `effort.kind`, códigos de opción, ids de comprobación, números) no cambian con el idioma. El historial guarda una clave de mensaje, así que las líneas antiguas se leen en cualquier idioma. No se traduce el texto que viene de los datos del usuario ni los mensajes de validación de la librería de esquemas fuera de los casos comunes.

El resultado es siempre un rango y su motivo. Solo aparece dinero si se da un rango de tarifa por hora. Las bandas son un punto de partida para calibrar, no un presupuesto.

Bandas guardadas: Comparar alcance > Bandas de esfuerzo edita cada par [mín, máx] y lo guarda para todos los encargos (`GET`/`PUT /api/settings` con `bands`, MCP `drucker_settings`). Solo se guardan las partes cambiadas; «Volver a las de por defecto» (`bands: {}`) las borra. Las `bands` de una llamada siguen mandando sobre las guardadas, parte a parte, y cada comparación devuelve las `bands` que usó.

## Superficies

- REST: `/api/...` (OpenAPI en `/docs`). Se rechazan escrituras desde otro origen.
- MCP (stdio): `python -m drucker.mcp_server`. Veinticuatro herramientas con prefijo `drucker_` (lista en README.md). Las de solo lectura declaran `readOnlyHint`; `drucker_item_delete` declara `destructiveHint`; `drucker_proposal` escribe un archivo con `docx` y no es de solo lectura. El puente lista herramientas sin la app en marcha. Las llamadas van a la app en 127.0.0.1 con el token de `data/mcp-token` (`POST /api/agent/call`, token bearer).
- Copiloto: panel y lanzador comunes de la familia, en `/api/copilot/*`. La página expone lo que hay en pantalla mediante `window.hoardCopilot`.

## Datos

Tablas SQLite: `engagements`, `items` (alcance, hito, material, decisión, cobro, supuesto, pregunta, esfuerzo), `history`, `deliverables`, `versions`, `comments`, `packages`, `settings`. Los datos de ejemplo son inventados y se marcan como tales («Cooperativa Ejemplo S. L. (ficticia)»); se cargan desde la página Encargos.

## Pruebas

`python -m pytest -q`: 137 pruebas. Cubren calibración con horas reales, referencias vivas con las otras apps sustituidas por un Hub falso, punteros de Atlas, validación de DOCX/XLSX/SVG/MP4/PDF/GLB, plantillas y DOCX, sinónimos, decisiones e informe de órdenes de cambio, y además altas y cambios con historial, clases y rangos de alcance, bandas guardadas, etiquetado de propuestas y lista prohibida, detección de comentarios obsoletos, verificación de paquetes (archivo ausente, hash distinto, PNG/PDF/GLB/STL/JSON/CSV/ZIP rotos, fuente no autorizada), zip con bytes idénticos a igual entrada, REST, la ruta de agente con token y el puente stdio contra un servidor real.

## Límites

- Las horas son rangos por reglas. No hay modelo: una redacción que las reglas no conocen sale `ambiguous` o, si nada del acuerdo se le parece, como punto sin estimar.
- Las comprobaciones de paquete prueban que un archivo abre y coincide con su hash, no que esté bien hecho. Las URL remotas no se pueden verificar; un paquete que las lista no queda listo hasta indicar una ruta local. Los punteros de Atlas se verifican solo mientras Atlas responde (si no, se usa la ruta guardada y la comprobación lo dice).
- La validación de formatos es estructural (zip, JSON, CSV, PDF, PNG, GLB, STL, DOCX, XLSX, SVG, MP4), no un analizador completo; la validación Khronos de un GLB necesita Vulcan en marcha.
- Las referencias vivas necesitan el Hub y la app propietaria en marcha; el movimiento de Ledger se busca por ventana de fechas o título porque Ledger no tiene lectura por id.
- La interfaz no tiene autenticación (app local en 127.0.0.1, como el resto de la familia).

## Skills para los agentes que se conectan

Esta app lleva procedimientos de la biblioteca de skills del espacio de trabajo de la familia para los agentes que se conectan: `engagement-proposal-and-delivery`, `writing-plans`, `pretask-interview`, `docs-release-review`. Aparecen en lo que el agente lee al conectarse, se leen con `skills_list` y `skill_read`, se buscan y asignan con `skills_library` y `skills_assign`, y se ofrecen como prompts. Se eligen en la página de skills (`/api/agent/skills/page`) o en la pestaña Skills del hub; el bloque `skills` de `faustus-plugin.json` guarda lo que la app pide por defecto.
