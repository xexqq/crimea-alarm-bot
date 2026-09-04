import os
import json
import sqlite3
import urllib.request
import urllib.parse
import time
import datetime
from channel_checker import process_new_posts, check_timeout_recoveries

from cities import CITIES
ABBREVIATIONS_TEXT = """📖 Список аббревиатур:

МРШ — малоразмерный шар, аэростат
БПЛА — беспилотный летательный аппарат
БЭК — безэкипажный катер
КР — крылатая ракета
ПКР — противокорабельная ракета
КРВБ — крылатая ракета воздушного базирования
ПРР — противорадиолокационная ракета
УАБ — управляемая авиационная бомба
РСЗО — реактивная система залпового огня
ОТРК — оперативно-тактический ракетный комплекс
ТА — тактическая авиация
АА — армейская авиация"""

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"

DB_PATH = "bot.db"

# Временное хранилище выбора городов "в процессе" (пока не нажали Готово)
user_selection = {}


def api_call(method, params=None):
    url = API_URL + method
    data = json.dumps(params or {}).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=40) as response:
        return json.loads(response.read().decode("utf-8"))


def send_message(chat_id, text, reply_markup=None, silent=False):
    params = {"chat_id": chat_id, "text": text}
    if reply_markup:
        params["reply_markup"] = reply_markup
    if silent:
        params["disable_notification"] = True
    return api_call("sendMessage", params)


def send_alert(chat_id, text, silent=False):
    try:
        result = send_message(chat_id, text, silent=silent)
        message_id = result["result"]["message_id"]
        now = datetime.datetime.now(datetime.UTC).isoformat()
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO sent_alerts (chat_id, message_id, sent_time) VALUES (?, ?, ?)",
            (chat_id, message_id, now),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print("Ошибка отправки алерта:", e)


def edit_message_markup(chat_id, message_id, reply_markup):
    params = {
        "chat_id": chat_id,
        "message_id": message_id,
        "reply_markup": reply_markup,
    }
    try:
        api_call("editMessageReplyMarkup", params)
    except Exception as e:
        print("Ошибка редактирования кнопок:", e)

def delete_message(chat_id, message_id):
    params = {"chat_id": chat_id, "message_id": message_id}
    try:
        api_call("deleteMessage", params)
    except Exception as e:
        print("Ошибка удаления сообщения (не критично):", e)

def answer_callback(callback_query_id, text=None):
    params = {"callback_query_id": callback_query_id}
    if text:
        params["text"] = text
    try:
        api_call("answerCallbackQuery", params)
    except Exception as e:
        print("Ошибка ответа на callback (не критично):", e)


def get_db():
    return sqlite3.connect(DB_PATH)


def save_subscription(chat_id, cities_list):
    conn = get_db()
    cursor = conn.cursor()
    cities_str = ",".join(cities_list)
    cursor.execute(
        "INSERT INTO subscribers (chat_id, cities) VALUES (?, ?) "
        "ON CONFLICT(chat_id) DO UPDATE SET cities = excluded.cities",
        (chat_id, cities_str),
    )
    conn.commit()
    conn.close()

def load_user_cities(chat_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT cities FROM subscribers WHERE chat_id = ?", (chat_id,))
    row = cursor.fetchone()
    conn.close()
    if row and row[0]:
        return set(row[0].split(","))
    return set()

def build_city_keyboard(chat_id):
    selected = user_selection.get(chat_id, set())
    buttons = []
    for city in CITIES:
        mark = "✅ " if city in selected else "☐ "
        buttons.append([{"text": mark + city, "callback_data": "city:" + city}])
    buttons.append([{"text": "✅ Готово", "callback_data": "done"}])
    return {"inline_keyboard": buttons}


def main_menu_keyboard():
    return {
        "keyboard": [
            [{"text": "⚙️ Настройки"}, {"text": "📖 Аббревиатуры"}]
        ],
        "resize_keyboard": True
    }


def handle_start(chat_id):
    send_message(chat_id, "Привет! Я слежу за опасностями в Крыму (БПЛА, ракеты и др.) и присылаю уведомления по выбранным городам.\n\nНажми ⚙️ Настройки, чтобы выбрать города для отслеживания.", main_menu_keyboard())


def handle_settings(chat_id):
    user_selection[chat_id] = load_user_cities(chat_id)
    keyboard = build_city_keyboard(chat_id)
    send_message(chat_id, "Выбери города/районы для отслеживания (можно несколько):", keyboard)


def handle_callback(callback_query):
    chat_id = callback_query["message"]["chat"]["id"]
    message_id = callback_query["message"]["message_id"]
    data = callback_query["data"]
    callback_id = callback_query["id"]

    if chat_id not in user_selection:
        user_selection[chat_id] = set()

    if data == "done":
        selected = user_selection.get(chat_id, set())
        if not selected:
            answer_callback(callback_id, "Выбери хотя бы один город!")
            return
        save_subscription(chat_id, list(selected))
        answer_callback(callback_id, "Сохранено!")
        delete_message(chat_id, message_id)
        send_message(chat_id, "Настройки сохранены ✅\nТы будешь получать уведомления по: " + ", ".join(selected))
        return

    if data.startswith("city:"):
        city = data[len("city:"):]
        selected = user_selection.setdefault(chat_id, set())
        if city in selected:
            selected.remove(city)
        else:
            selected.add(city)
        keyboard = build_city_keyboard(chat_id)
        edit_message_markup(chat_id, message_id, keyboard)
        answer_callback(callback_id)


def cleanup_old_alerts():
    """Удаляет алерты старше 24 часов"""
    cutoff = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=24)).isoformat()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, chat_id, message_id FROM sent_alerts WHERE sent_time < ?", (cutoff,))
    old_alerts = cursor.fetchall()

    for row_id, chat_id, message_id in old_alerts:
        delete_message(chat_id, message_id)
        cursor.execute("DELETE FROM sent_alerts WHERE id = ?", (row_id,))

    conn.commit()
    conn.close()
    if old_alerts:
        print(f"Удалено старых алертов: {len(old_alerts)}")


def main():
    print("Бот запущен...")
    offset = None
    last_channel_check = 0
    last_cleanup = 0
    CHANNEL_CHECK_INTERVAL = 90       # проверять канал раз в 90 секунд
    CLEANUP_INTERVAL = 3600           # чистить старые алерты раз в час

    while True:
        now = time.time()

        if now - last_channel_check > CHANNEL_CHECK_INTERVAL:  # 8 пробелов
            try:
                process_new_posts(send_alert)
                check_timeout_recoveries(send_alert)
            except Exception as e:
                print("Ошибка проверки канала:", e)
            last_channel_check = now

        if now - last_cleanup > CLEANUP_INTERVAL:  # 8 пробелов
            try:
                cleanup_old_alerts()
            except Exception as e:
                print("Ошибка очистки алертов:", e)
            last_cleanup = now

        params = {"timeout": 10}
        if offset:
            params["offset"] = offset
        try:
            result = api_call("getUpdates", params)
        except Exception as e:
            print("Ошибка запроса:", e)
            continue

        for update in result.get("result", []):
            offset = update["update_id"] + 1

            try:
                if "message" in update:
                    message = update["message"]
                    chat_id = message["chat"]["id"]
                    text = message.get("text", "")
                    if text == "/start":
                        handle_start(chat_id)
                    elif text == "⚙️ Настройки" or text == "/settings":
                        handle_settings(chat_id)
                    elif text == "📖 Аббревиатуры":
                        send_message(chat_id, ABBREVIATIONS_TEXT)

                elif "callback_query" in update:
                    handle_callback(update["callback_query"])
            except Exception as e:
                print("Ошибка обработки апдейта:", e)
                
if __name__ == "__main__":
    main()
