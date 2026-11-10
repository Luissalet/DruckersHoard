# Próximos pasos

1. Verificar en vivo los punteros de Atlas (`atlas:<id>` en un paquete) cuando Atlas arranque: hoy se probaron solo con un Atlas simulado en las pruebas, porque Atlas no arrancó en la última comprobación por un BOM en su archivo de configuración.
2. Calibrar las bandas con encargos reales: registrar puntos de `effort` en los encargos que se cierren y aplicar `drucker_bands_suggest` cuando haya tres o más muestras por parte.
3. Orden de cambio con importe: hoy el dinero de la decisión sale de la tarifa por hora de la comparación; pasar la tarifa en `drucker_scope_decide` cuando se quiera el total en euros.
