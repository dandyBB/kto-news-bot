import asyncio
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import websockets
from aiogram import Bot

from app.config import CHANNEL_ID


WS_URL = "wss://neptun.in.ua/api/v1/stream"

# Только Киев и Киевская область
KYIV_NAMES = {
    "Київ",
    "м. Київ",
    "Київська область",
}

TYPE_NAMES = {
    "uav": "БпЛА",
    "recon": "розвідувальний БпЛА",
    "missile": "ракета",
    "ballistic": "балістична ракета",
    "kab": "КАБ",
    "mig31k": "МіГ-31К",
    "unknown": "невідома загроза",
}


# Уже активные тревоги
active_alerts = set()

# Уже отправленные угрозы
known_threats = set()


def get_time(value: str | None) -> str:
    """Преобразует ISO-время в украинское время Europe/Kyiv."""
    kyiv_tz = ZoneInfo("Europe/Kyiv")

    if not value:
        return datetime.now(kyiv_tz).strftime("%H:%M")

    try:
        value = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(value)

        # Если время пришло без timezone — считаем его UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))

        return dt.astimezone(kyiv_tz).strftime("%H:%M")

    except Exception:
        return datetime.now(kyiv_tz).strftime("%H:%M")

def is_kyiv_region(item: dict) -> bool:
    """Проверяет, относится ли объект к Киеву/Киевской области."""

    region = str(
        item.get("region")
        or item.get("oblast")
        or ""
    ).strip()

    district = str(
        item.get("district")
        or ""
    ).strip()

    locality = str(
        item.get("locality")
        or ""
    ).strip()

    if region in KYIV_NAMES:
        return True

    if locality in KYIV_NAMES:
        return True

    if "Київ" in region:
        return True

    if "Київ" in district:
        return True

    if "Київ" in locality:
        return True

    return False


def format_alert_start(alert: dict) -> str:
    """Формирует сообщение о начале тревоги."""

    time = get_time(
        alert.get("since")
        or alert.get("started_at")
    )

    name = (
        alert.get("name")
        or alert.get("oblast")
        or "Київ / Київська область"
    )

    return (
        f"🔴 <b>{time} ПОВІТРЯНА ТРИВОГА</b>\n\n"
        f"📍 {name}\n\n"
        "⚠️ Не ігноруйте сигнал повітряної тривоги."
    )


def format_alert_end(previous_alerts: list[dict]) -> str:
    """Формирует сообщение об отбое."""

    time = datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%H:%M")

    locations = []

    for alert in previous_alerts:
        name = (
            alert.get("name")
            or alert.get("oblast")
        )

        if name and name not in locations:
            locations.append(name)

    if not locations:
        locations.append("Київ / Київська область")

    location_text = "\n".join(
        f"📍 {name}"
        for name in locations
    )

    return (
        f"🟢 <b>{time} ВІДБІЙ ПОВІТРЯНОЇ ТРИВОГИ</b>\n\n"
        f"{location_text}"
    )


def format_threat(threat: dict) -> str:
    """Формирует сообщение о конкретной угрозе."""

    time = get_time(
        threat.get("updatedAt")
        or threat.get("confirmedAt")
    )

    threat_type = TYPE_NAMES.get(
        threat.get("type"),
        threat.get("title")
        or "невідома загроза",
    )

    title = threat.get("title")

    region = threat.get("region")
    district = threat.get("district")
    locality = threat.get("locality")

    confidence = threat.get("confidenceLevel")

    heading = threat.get("heading")

    explanation = threat.get(
        "explanationShort"
    )

    count = threat.get("count")

    lines = [
        f"🚨 <b>{time} ПОВІТРЯНА ЗАГРОЗА</b>",
        "",
        f"🎯 <b>Що:</b> {threat_type}",
    ]

    if title and title != threat_type:
        lines.append(
            f"📡 <b>Назва:</b> {title}"
        )

    if count and count > 1:
        lines.append(
            f"🔢 <b>Кількість:</b> {count}"
        )

    if region:
        lines.append(
            f"📍 <b>Область:</b> {region}"
        )

    if district:
        lines.append(
            f"📍 <b>Район:</b> {district}"
        )

    if locality:
        lines.append(
            f"📍 <b>Населений пункт:</b> {locality}"
        )

    if heading is not None:
        lines.append(
            f"🧭 <b>Курс:</b> {heading}°"
        )

    if confidence:
        confidence_names = {
            "low": "низька",
            "medium": "середня",
            "high": "висока",
        }

        confidence_text = confidence_names.get(
            confidence,
            confidence,
        )

        lines.append(
            f"ℹ️ <b>Достовірність:</b> "
            f"{confidence_text}"
        )

    if explanation:
        lines.append(
            f"\n📝 {explanation}"
        )

    return "\n".join(lines)


def get_alert_key(alert: dict) -> str:
    return str(
        alert.get("key")
        or alert.get("id")
        or (
            alert.get("name"),
            alert.get("oblast"),
        )
    )


async def send_alert(
    bot: Bot,
    text: str,
):
    try:
        await bot.send_message(
            chat_id=CHANNEL_ID,
            text=text,
            parse_mode="HTML",
        )

        print(
            "[ALERTS] Сообщение отправлено:"
        )
        print(text)

    except Exception as error:
        print(
            f"[ALERTS] Ошибка отправки: {error}"
        )


async def handle_alerts(
    bot: Bot,
    data: dict,
):
    """
    Обработка официальных тревог NEPTUN.
    """

    raions = data.get("raions", [])
    oblasts = data.get("oblasts", [])

    current = []

    for item in raions:
        if is_kyiv_region(item):
            current.append(item)

    for item in oblasts:
        if is_kyiv_region(item):
            current.append(item)

    current_keys = {
        get_alert_key(item)
        for item in current
    }

    # Первое подключение — просто запоминаем состояние.
    if not active_alerts:
        active_alerts.update(current_keys)

        print(
            "[ALERTS] Начальное состояние:",
            current_keys,
        )

        return

    # Новые тревоги
    new_alerts = [
        item
        for item in current
        if get_alert_key(item) not in active_alerts
    ]

    # Отправляем новые тревоги
    for alert in new_alerts:
        await send_alert(
            bot,
            format_alert_start(alert),
        )

    # Если раньше тревога была, а теперь её нет
    if active_alerts and not current_keys:
        previous = [
            {
                "name": key,
            }
            for key in active_alerts
        ]

        await send_alert(
            bot,
            format_alert_end(previous),
        )

    active_alerts.clear()
    active_alerts.update(current_keys)


async def handle_threat(
    bot: Bot,
    threat: dict,
):
    """
    Обработка новых угроз.
    """

    if not is_kyiv_region(threat):
        return

    # Наблюдения без официальной тревоги
    # не публикуем как "тревогу".
    if threat.get("advisory") is True:
        print(
            "[ALERTS] Advisory-пропуск:",
            threat.get("title"),
        )
        return

    threat_id = threat.get("id")

    if not threat_id:
        return

    # Не спамим повторными обновлениями
    if threat_id in known_threats:
        return

    known_threats.add(threat_id)

    # Ограничиваем размер памяти
    if len(known_threats) > 1000:
        known_threats.clear()
        known_threats.add(threat_id)

    await send_alert(
        bot,
        format_threat(threat),
    )


async def websocket_worker(bot: Bot):
    """
    Постоянное WebSocket-подключение к NEPTUN.
    """

    while True:
        try:
            print(
                "[ALERTS] Подключение к NEPTUN..."
            )

            async with websockets.connect(
                WS_URL,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=5,
            ) as websocket:

                print(
                    "[ALERTS] NEPTUN подключён."
                )

                async for raw_message in websocket:
                    try:
                        envelope = json.loads(
                            raw_message
                        )
                    except json.JSONDecodeError:
                        continue

                    event_type = envelope.get(
                        "type"
                    )

                    data = envelope.get(
                        "data"
                    ) or {}

                    # Полный снимок при подключении
                    if event_type == "snapshot":
                        threats = data.get(
                            "threats",
                            [],
                        )

                        for threat in threats:
                            if is_kyiv_region(
                                threat
                            ):
                                threat_id = threat.get(
                                    "id"
                                )

                                if threat_id:
                                    known_threats.add(
                                        threat_id
                                    )

                        print(
                            "[ALERTS] Snapshot получен."
                        )

                    # Новая/обновлённая угроза
                    elif event_type == "upsert":
                        if isinstance(
                            data,
                            dict,
                        ):
                            await handle_threat(
                                bot,
                                data,
                            )

                    # Угроза исчезла
                    elif event_type == "remove":
                        threat_id = data.get(
                            "id"
                        )

                        if threat_id:
                            known_threats.discard(
                                threat_id
                            )

                    # Изменение официальных тревог
                    elif event_type == "alerts":
                        if isinstance(
                            data,
                            dict,
                        ):
                            await handle_alerts(
                                bot,
                                data,
                            )

                    elif event_type == "heartbeat":
                        continue

        except asyncio.CancelledError:
            raise

        except Exception as error:
            print(
                f"[ALERTS] WebSocket ошибка: "
                f"{error}"
            )

            print(
                "[ALERTS] Повторное подключение "
                "через 5 секунд..."
            )

            await asyncio.sleep(5)


async def alerts_worker(bot: Bot):
    print(
        "[ALERTS] Монитор NEPTUN запущен."
    )

    await websocket_worker(bot)