# Drucker · capacidades actuales

Oficina de encargos: expediente por encargo, comparador de alcance, preparador de propuestas, mesa de revisión de entregables y paquete de entrega reproducible. Puerto 5246. Los contactos son de People, el dinero de Ledger y los archivos de Atlas; aquí solo hay referencias. No es un CRM.

MCP (puente stdio hacia la app, token en `data/mcp-token`): 18 herramientas `drucker_*`.
- Lectura: drucker_engagements, drucker_engagement_get, drucker_history, drucker_scope_compare, drucker_proposal, drucker_review, drucker_package_verify, drucker_example. Declaran `readOnlyHint`.
- Escritura: drucker_engagement_save, drucker_item_save, drucker_deliverable_save, drucker_version_add, drucker_comment_add, drucker_comment_status, drucker_deliver_select, drucker_package, drucker_settings.
- Destructiva: drucker_item_delete.
Listar herramientas no necesita la app. Llamar a una herramienta sí: arrancar `python -m drucker` antes.

Cómo se usa en un encargo:
1. `drucker_engagement_save` con cliente, origen, presupuesto (rango) y `items` iniciales; `drucker_item_save` para alcance, hitos, materiales, decisiones, cobros, supuestos y preguntas.
2. Cuando llega una petición nueva: `drucker_scope_compare` con `engagement_id` y `request`. Clasifica cada elemento (added, removed, ambiguous, already_included, unchanged), da horas como rango con motivo (formato frente a rehacer el flujo) y tres opciones: incluir, orden de cambio con rango, aplazar. Lo dudoso queda `ambiguous`; no se inventan precios. Un punto nuevo sin nada parecido en el acuerdo sale `added` con esfuerzo `unestimated`: sin horas, fuera de los totales (`totals.unestimated_items`), opciones `specify` y `defer`; solo se le dan horas si se pasan en el elemento (`hours`). Todas las herramientas aceptan `lang` (`es` o `en`) y devuelven los textos en ese idioma; los códigos no cambian. Dinero solo con `hourly_rate {min,max}`.
3. `drucker_proposal` con `format` md o html: cada frase es verified (con fuente), assumption o question. Se rechaza si aparece un nombre de la lista prohibida (Faustus, Hoard, nombres de herramientas internas; configurable con `drucker_settings`). El JSON devuelve siempre las infracciones.
4. `drucker_deliverable_save`, `drucker_version_add` (calcula SHA-256 si el archivo es local), `drucker_comment_add` con ancla {page|region|time|object}, `drucker_comment_status` (corregido necesita una versión posterior), `drucker_deliver_select`. `drucker_review` muestra qué comentarios son obsoletos (existe una versión posterior distinta) y qué versión se entrega.
5. `drucker_package_verify` y `drucker_package`: comprueba archivos, hashes, que las exportaciones abren (zip, JSON, CSV, PDF, PNG, GLB, STL), fuentes autorizadas, instrucciones y límites. Si algo falla, no está listo y no se escribe zip. Si todo pasa, escribe manifest.json y package.zip con bytes reproducibles.

Reglas para el agente: no copiar datos de otras apps, solo su referencia. Un cobro sin referencia a Ledger es `manual`. No presentar un rango de horas como presupuesto. No exportar una propuesta con nombres internos. Los datos de ejemplo (`drucker_example`) son inventados.

Interfaz: Encargos (pestañas Alcance, Hitos, Materiales, Decisiones, Entregables, Cobros, Historial), Comparar alcance, Propuesta, Revisión, Paquete. Castellano e inglés. Tema oscuro común con acento azul pizarra. Copiloto común en `/api/copilot/*`; `window.hoardCopilot.context` devuelve página, pestaña, encargo y entregable activos.

Verificación: 64 pruebas pytest (`python -m pytest -q`), incluido el puente stdio contra un servidor real con token. Capturas con navegador real en 1200 px y 390 px sin errores de consola ni desbordamiento horizontal. Sin probar: conexión real al Hub, turno real del copiloto con Faustus, descarga del zip desde el navegador en disco.

Límites: horas por reglas, no por modelo; verificación de formatos estructural y básica; URL remotas y punteros de Atlas no verificables; sin autenticación en la UI. Ver README.es.md.
