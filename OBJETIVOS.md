# Próximos pasos

1. Registrar la app en el Hub (manifiesto listo) y probar un turno real del copiloto y de un modelo por MCP sobre un encargo completo. Hoy solo está probado el puente contra un servidor local.
2. Calibrar las bandas de esfuerzo con encargos reales del propietario (`bands` en `drucker_scope_compare`) y guardarlas como ajuste en vez de pasarlas en cada llamada.
3. Leer referencias vivas: resolver `{app: people}`, `{app: ledger}` y `{app: atlas}` mediante el bus de la familia para mostrar nombre, importe y presencia del archivo sin copiarlos. Hoy se guardan como punteros.
4. Verificar punteros de Atlas: pedir a Atlas la ruta y el hash actuales para que un paquete que los lista pueda quedar listo.
5. Más formatos en la verificación de exportaciones (DOCX, XLSX, SVG, MP4) y validación más profunda de PDF y GLB.
6. Plantillas de propuesta por tipo de encargo y exportación a DOCX.
7. Coincidencia de alcance con sinónimos configurables por encargo; informe de cambios aceptados como órdenes de cambio con su rango y la decisión tomada.
8. Entradas en el cuaderno de decisiones al elegir una opción comercial (incluir / orden de cambio / aplazar).
