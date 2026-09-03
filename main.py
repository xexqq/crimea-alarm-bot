import os
import time
import json
import urllib.request
import urllib.parse

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"


def api_call(method, params=None):
    url = API_URL + method
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=40) as response:
        return json.loads(response.read().decode("utf-8"))


def send_message(chat_id, text):
    api_call("sendMessage", {"chat_id": chat_id, "text": text})


def main():
    print("Бот запущен...")
    offset = None
    while True:
        params = {"timeout": 30}
        if offset:
            params["offset"] = offset
        try:
            result = api_call("getUpdates", params)
        except Exception as e:
            print("Ошибка запроса:", e)
            time.sleep(5)
            continue

        for update in result.get("result", []):
            offset = update["update_id"] + 1
            message = update.get("message")
            if not message:
                continue
            chat_id = message["chat"]["id"]
            text = message.get("text", "")

            if text == "/start":
                send_message(chat_id, "Привет! Бот запущен и работает. 🚀")


if __name__ == "__main__":
    main()
