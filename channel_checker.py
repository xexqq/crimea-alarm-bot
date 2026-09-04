import urllib.request
import re
import html
import json
import sqlite3
import datetime

from locations_data import LOCATIONS, SORTED_KEYS
from threats_data import THREATS, THREAT_KEYS_SORTED

DB_PATH = "bot.db"
CHANNEL_URL = "https://t.me/s/lpr1_Crimea_Alarm"


def get_db():
    return sqlite3.connect(DB_PATH)


def get_state(key, default=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM state WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else default


def set_state(key, value):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO state (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )
    conn.commit()
    conn.close()


def fetch_posts():
    req = urllib.request.Request(CHANNEL_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as response:
        page = response.read().decode("utf-8")

    raw_posts = re.findall(
        r'data-post="lpr1_Crimea_Alarm/(\d+)".*?class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
        page,
        re.DOTALL
    )

    posts = []
    for post_id, raw_text in raw_posts:
        text = re.sub(r"<br\s*/?>", "\n", raw_text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        text = re.sub(r"[ \t]+", " ", text)
        text = text.strip()
        posts.append((int(post_id), text))

    return posts


def find_locations(text):
    text_lower = text.lower()
    found_places = []
    found_cities = set()
    for key in SORTED_KEYS:
        pattern = r'(?<![а-яё])' + re.escape(key) + r'[а-яё]{0,3}(?![а-яё])'
        if re.search(pattern, text_lower):
            found_places.append(key.capitalize())
            found_cities.add(LOCATIONS[key])
    return found_places, found_cities


def find_threats(text):
    text_lower = text.lower()
    found = []
    for key in THREAT_KEYS_SORTED:
        pattern = r'(?<![а-яё])' + re.escape(key) + r'(?![а-яё])'
        if re.search(pattern, text_lower):
            found.append(key)
    return found


def detect_level(text):
    text_lower = text.lower()
    if "отбой" in text_lower:
        return "отбой"
    if "возможн" in text_lower:
        return "возможная"
    return "угроза"

def get_new_posts():
    last_id = get_state("last_post_id")

    posts = fetch_posts()

    if last_id is None:
        # Первый запуск - просто запоминаем текущий последний пост, ничего не рассылаем
        if posts:
            max_id = max(pid for pid, _ in posts)
            set_state("last_post_id", max_id)
        return []

    last_id = int(last_id)
    new_posts = [(pid, text) for pid, text in posts if pid > last_id]

    if posts:
        max_id = max(pid for pid, _ in posts)
        set_state("last_post_id", max_id)

    return new_posts


def format_alert(level, cities, places, threat_keys):
    threat_names = [THREATS[k]["name"] for k in threat_keys]
    threat_text = ", ".join(threat_names) if threat_names else "неизвестная угроза"
    instructions = list(dict.fromkeys(THREATS[k]["instruction"] for k in threat_keys))
    instruction_text = "\n".join("❗ " + i for i in instructions)

    if cities:
        city_part = ", ".join(cities)
        if places:
            city_part += " (" + ", ".join(places) + ")"
    else:
        city_part = "Весь Крым"

    if level == "возможная":
        return (
            f"⚠️ ВОЗМОЖНАЯ АТАКА\n\n"
            f"Возможная атака на {city_part}: {threat_text}\n\n"
            f"Будьте начеку."
        )
    elif level == "отбой":
        return f"✅ ОТБОЙ ОПАСНОСТИ — {city_part}"
    else:
        return (
            f"🚨 ОПАСНОСТЬ — {city_part}\n\n"
            f"{threat_text}\n\n"
            f"{instruction_text}"
        )


def get_subscribers_for_cities(cities):
    """Возвращает список chat_id, которым нужно отправить алерт по данным городам"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id, cities FROM subscribers")
    rows = cursor.fetchall()
    conn.close()

    result = []
    for chat_id, cities_str in rows:
        user_cities = set(cities_str.split(","))
        if "Весь Крым" in user_cities:
            if not cities:
                result.append(chat_id)
            else:
                result.append(chat_id)
        elif cities and (cities & user_cities):
            result.append(chat_id)

    return result


def update_cooldown(cities):
    now = datetime.datetime.utcnow().isoformat()
    conn = get_db()
    cursor = conn.cursor()
    for city in cities:
        cursor.execute(
            "INSERT INTO active_threats (city, last_threat_time) VALUES (?, ?) "
            "ON CONFLICT(city) DO UPDATE SET last_threat_time = excluded.last_threat_time",
            (city, now),
        )
    conn.commit()
    conn.close()


def clear_cooldown(cities):
    conn = get_db()
    cursor = conn.cursor()
    if cities:
        for city in cities:
            cursor.execute("DELETE FROM active_threats WHERE city = ?", (city,))
    else:
        cursor.execute("DELETE FROM active_threats")
    conn.commit()
    conn.close()


def process_new_posts(send_message_func):
    new_posts = get_new_posts()

    for post_id, text in new_posts:
        places, cities = find_locations(text)
        threat_keys = find_threats(text)
        level = detect_level(text)

        if not threat_keys:
            continue  # не про угрозу - пропускаем

        alert_text = format_alert(level, cities, places, threat_keys)

        if level == "отбой":
            recipients = get_subscribers_for_cities(cities) if cities else get_subscribers_for_cities(set())
            clear_cooldown(cities)
        else:
            recipients = get_subscribers_for_cities(cities)
            update_cooldown(cities)

        for chat_id in recipients:
            silent = (level != "угроза" and level != "возможная")
            send_message_func(chat_id, alert_text, silent=silent)

COOLDOWN_HOURS = 2.5  # среднее между 2 и 3 часами


def check_timeout_recoveries(send_message_func):
    """Проверяет города с истёкшим кулдауном и шлёт отбой по времени"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT city, last_threat_time FROM active_threats")
    rows = cursor.fetchall()
    conn.close()

    now = datetime.datetime.now(datetime.UTC)
    expired_cities = []

    for city, last_time_str in rows:
        last_time = datetime.datetime.fromisoformat(last_time_str)
        if last_time.tzinfo is None:
            last_time = last_time.replace(tzinfo=datetime.UTC)
        hours_passed = (now - last_time).total_seconds() / 3600
        if hours_passed >= COOLDOWN_HOURS:
            expired_cities.append(city)

    for city in expired_cities:
        alert_text = (
            f"⏱ ОТБОЙ ОПАСНОСТИ ПО ВРЕМЕНИ — {city}\n\n"
            f"Повторных угроз не наблюдалось в течение 2-3 часов."
        )
        recipients = get_subscribers_for_cities({city})
        for chat_id in recipients:
            send_message_func(chat_id, alert_text, silent=True)

    if expired_cities:
        clear_cooldown(expired_cities)
