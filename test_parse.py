import urllib.request
import re
import html
import json

with open("locations.json", "r", encoding="utf-8") as f:
    LOCATIONS = json.load(f)

SORTED_KEYS = sorted(LOCATIONS.keys(), key=len, reverse=True)

def detect_level(text):
    text_lower = text.lower()

    # Сначала проверяем отбой - это приоритетнее всего
    if "отбой" in text_lower:
        return "отбой"

    # Потом "возможная" атака
    if "возможн" in text_lower:
        return "возможная"

    # Иначе считаем подтверждённой угрозой
    return "угроза"

THREATS = {
    "мрш": {"name": "МРШ (малоразмерный шар/аэростат)", "instruction": "Возможен удар с воздуха — в укрытие, отойдите от окон"},
    "бпла": {"name": "БПЛА (беспилотник)", "instruction": "Срочно отойдите от окон, не находитесь на улице"},
    "бэк": {"name": "БЭК (безэкипажный катер)", "instruction": "Срочно отойдите от берега"},
    "кр": {"name": "КР (крылатая ракета)", "instruction": "Срочно в ближайшее укрытие"},
    "пкр": {"name": "ПКР (противокорабельная ракета)", "instruction": "Срочно в ближайшее укрытие"},
    "крвб": {"name": "КРВБ (крылатая ракета авиабазирования)", "instruction": "Срочно в ближайшее укрытие"},
    "прр": {"name": "ПРР (противорадиолокационная ракета)", "instruction": "Срочно в ближайшее укрытие"},
    "уаб": {"name": "УАБ (управляемая авиабомба)", "instruction": "Срочно в ближайшее укрытие"},
    "рсзо": {"name": "РСЗО (реактивная система залпового огня)", "instruction": "Срочно в ближайшее укрытие"},
    "отрк": {"name": "ОТРК (оперативно-тактический ракетный комплекс)", "instruction": "Срочно в ближайшее укрытие"},
    "та": {"name": "ТА (тактическая авиация)", "instruction": "Возможен удар с воздуха — в укрытие, отойдите от окон"},
    "аа": {"name": "АА (армейская авиация)", "instruction": "Возможен удар с воздуха — в укрытие, отойдите от окон"},
}

THREAT_KEYS_SORTED = sorted(THREATS.keys(), key=len, reverse=True)


def find_locations(text):
    text_lower = text.lower()
    found_places = []
    found_cities = set()
    for key in SORTED_KEYS:
        pattern = r'(?<![а-яё])' + re.escape(key) + r'[а-яё]{0,3}(?![а-яё])'
        if re.search(pattern, text_lower):
            found_places.append(key)
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


url = "https://t.me/s/lpr1_Crimea_Alarm"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

with urllib.request.urlopen(req, timeout=20) as response:
    page = response.read().decode("utf-8")

posts = re.findall(
    r'data-post="lpr1_Crimea_Alarm/(\d+)".*?class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
    page,
    re.DOTALL
)

print("Найдено постов:", len(posts))

for post_id, raw_text in posts:
    text = re.sub(r"<br\s*/?>", "\n", raw_text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = text.strip()

    places, cities = find_locations(text)
    threats = find_threats(text)

    print("---")
    print("ID:", post_id)
    print("Текст:", text.replace("\n", " | "))
    print("Найденные места:", places)
    print("Города:", cities)
    print("Угрозы:", threats)
    level = detect_level(text)
    print("Уровень:", level)
