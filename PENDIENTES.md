# Decisiones del propietario

Nada bloqueante. Los valores por defecto ya están aplicados y se cambian desde la propia app:

- Nombres prohibidos en material para clientes: página Propuesta o `drucker_settings` (`denylist`).
- Bandas de esfuerzo: Comparar alcance > Bandas de esfuerzo, `PUT /api/settings {bands}` o `drucker_settings` (`bands`).
  Conviene calibrarlas con los primeros encargos reales; hasta entonces son las de partida (formato 1-4 h por entregable,
  flujo 16-40 h, cantidad 1-3 h por unidad, ampliación 4-12 h). Cuando haya encargos cerrados con horas reales,
  `drucker_bands_suggest` propone las bandas calibradas.
