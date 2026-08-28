
import os
import requests

token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

if not token or not chat_id:
    raise RuntimeError("Faltan TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID")

url = f"https://api.telegram.org/bot{token}/sendMessage"
r = requests.post(url, data={
    "chat_id": chat_id,
    "text": "✅ Crypto Monitor: Telegram conectado correctamente.",
}, timeout=20)
r.raise_for_status()
print("Mensaje enviado correctamente.")
