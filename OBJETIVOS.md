# Próximos pasos

1. Probar un turno real del copiloto y de un modelo por MCP sobre un encargo completo. La app ya está en el Hub (puerto 5246) y Faustus tiene su conector; falta ese turno de extremo a extremo.
2. Bandas de esfuerzo: ya se guardan como ajuste (Comparar alcance > Bandas de esfuerzo, `drucker_settings`). Siguiente paso: proponer bandas a partir de las horas reales registradas en encargos cerrados.
3. Leer referencias vivas: resolver `{app: people}`, `{app: ledger}` y `{app: atlas}` mediante el bus de la familia para mostrar nombre, importe y presencia del archivo sin copiarlos. Hoy se guardan como punteros.
4. Verificar punteros de Atlas: pedir a Atlas la ruta y el hash actuales para que un paquete que los lista pueda quedar listo.
5. Más formatos en la verificación de exportaciones (DOCX, XLSX, SVG, MP4) y validación más profunda de PDF y GLB.
6. Plantillas de propuesta por tipo de encargo y exportación a DOCX.
7. Coincidencia de alcance con sinónimos configurables por encargo; informe de cambios aceptados como órdenes de cambio con su rango y la decisión tomada.
8. Entradas en el cuaderno de decisiones al elegir una opción comercial (incluir / orden de cambio / aplazar).
