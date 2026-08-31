# Crypto Monitor Dashboard V4

## Nuevo
- Supabase integrado al dashboard.
- Señales activas.
- Historial completo.
- Conteo de señales con ganancia.
- TP1, TP2 y STOP.
- Tasa de acierto de señales resueltas.
- Resultado simulado acumulado en R.
- Eventos del Signal Tracker.

## Regla de performance
- TP2 = +2.00R
- TP1 + break-even = +0.75R
- STOP = -1.00R
- EXPIRED / AMBIGUOUS no entran en win rate.

## Render
Además de las variables ya existentes, agregar al Web Service:
- SUPABASE_URL
- SUPABASE_SECRET_KEY

No poner estas claves en el repositorio.
