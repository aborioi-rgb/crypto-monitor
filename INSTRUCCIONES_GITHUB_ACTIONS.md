# GitHub Actions - Crypto Monitor

Subir al repositorio:

1. La carpeta `.github/workflows/crypto-alerts.yml`
2. `alert_worker.py`
3. `test_telegram.py`

Verificar además que `requirements.txt` incluya:

requests>=2.31

## Secrets en GitHub

Repositorio -> Settings -> Secrets and variables -> Actions -> New repository secret

Crear:
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID

## Probar manualmente

Repositorio -> Actions -> Crypto Monitor Alerts -> Run workflow

## Programación

El workflow está programado cada 10 minutos:

*/10 * * * *

Para una primera validación es suficiente y reduce carga.
