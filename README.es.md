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
| Encargos | Lista y expediente por encargo. Pestañas: Alcance, Hitos, Materiales, Decisiones, Entregables, Cobros, Historial. Cada cambio queda en el historial con el valor anterior y el nuevo. |
| Comparar alcance | Petición inicial, acuerdo y petición nueva (texto o elementos). Cada elemento sale como añadido, quitado, ambiguo, ya incluido o sin cambio. El esfuerzo es un rango de horas con su motivo; tres opciones: incluir, orden de cambio con rango, aplazar. |
| Propuesta | Borrador en Markdown o HTML. Cada frase lleva etiqueta: verificada (con su dato de origen), supuesto o pregunta. La exportación se rechaza si el texto contiene un nombre interno de la lista prohibida. |
| Revisión | Versiones de cada entregable (referencia de archivo y SHA-256), comentarios anclados a una versión y, si se quiere, a página, región, tramo de tiempo u objeto. Estado abierto / corregido en la versión N / no se corrige. Una sola versión marcada para entregar. El comentario sobre una versión vieja se muestra como obsoleto. |
| Paquete | Verifica el paquete de una versión (archivos existen, hashes coinciden, exportaciones abren, fuentes de datos autorizadas, instrucciones y límites presentes) y escribe `manifest.json` y `package.zip`. No queda listo si falla una comprobación. |

La interfaz está en castellano y en inglés (selector en la cabecera; se recuerda la elección).

## Comparación de alcance

La coincidencia es determinista: palabras sin tildes con raíz simplificada, solapamiento de Jaccard y razón de secuencia de difflib. Si la coincidencia es dudosa, el elemento es `ambiguous`; nunca se fuerza. Un número distinto («5» a «8 plantillas») o una negación invertida («con» a «sin anexos») es ambiguo a propósito.

El esfuerzo sale de bandas editables y de qué entregables e hitos toca cada elemento:

- `format`: formato de salida de entregables existentes. Solo la última etapa. Por defecto 1-4 h por entregable.
- `pipeline`: cambia cómo se produce el trabajo. Etapa anterior, así que se rehace todo lo posterior. Por defecto 16-40 h más 4-10 h por cada entregable o hito abierto adicional.
- `quantity`: más de lo mismo, por unidad extra.
- `content`: trabajo nuevo sin coincidencia cercana.

El resultado es siempre un rango y su motivo. Solo aparece dinero si se da un rango de tarifa por hora. Las bandas son un punto de partida para calibrar, no un presupuesto.

## Superficies

- REST: `/api/...` (OpenAPI en `/docs`). Se rechazan escrituras desde otro origen.
- MCP (stdio): `python -m drucker.mcp_server`. Dieciocho herramientas con prefijo `drucker_` (lista en README.md). Las de solo lectura declaran `readOnlyHint`; `drucker_item_delete` declara `destructiveHint`. El puente lista herramientas sin la app en marcha. Las llamadas van a la app en 127.0.0.1 con el token de `data/mcp-token` (`POST /api/agent/call`, token bearer).
- Copiloto: panel y lanzador comunes de la familia, en `/api/copilot/*`. La página expone lo que hay en pantalla mediante `window.hoardCopilot`.

## Datos

Tablas SQLite: `engagements`, `items` (alcance, hito, material, decisión, cobro, supuesto, pregunta), `history`, `deliverables`, `versions`, `comments`, `packages`, `settings`. Los datos de ejemplo son inventados y se marcan como tales («Cooperativa Ejemplo S. L. (ficticia)»); se cargan desde la página Encargos.

## Pruebas

`python -m pytest -q`: 64 pruebas. Cubren altas y cambios con historial, clases y rangos de alcance, etiquetado de propuestas y lista prohibida, detección de comentarios obsoletos, verificación de paquetes (archivo ausente, hash distinto, PNG/PDF/GLB/STL/JSON/CSV/ZIP rotos, fuente no autorizada), zip con bytes idénticos a igual entrada, REST, la ruta de agente con token y el puente stdio contra un servidor real.

## Límites

- Las horas son rangos por reglas. No hay modelo: una redacción que las reglas no conocen cae en la banda `content` por defecto o en `ambiguous`.
- Las comprobaciones de paquete prueban que un archivo abre y coincide con su hash, no que esté bien hecho. Las URL remotas y los punteros de Atlas no se pueden verificar; un paquete que los lista no queda listo hasta indicar una ruta local.
- La validación de formatos es estructural y básica (zip, JSON, CSV, PDF, PNG, GLB, STL), no un analizador completo.
- La interfaz no tiene autenticación (app local en 127.0.0.1, como el resto de la familia).
