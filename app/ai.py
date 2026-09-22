import asyncio
import time

from google import genai
from google.genai import types

from app.config import GEMINI_API_KEY


client = genai.Client(
    api_key=GEMINI_API_KEY
)

MODEL = "gemini-3.5-flash"

# Только один запрос Gemini одновременно.
GEMINI_SEMAPHORE = asyncio.Semaphore(1)

# Минимальный интервал между запросами.
MIN_REQUEST_INTERVAL = 6.0

_last_request_time = 0.0


SYSTEM_PROMPT = """
Ты профессиональный редактор украинского Telegram-канала
с новостями Киева и Киевской области.

Твоя задача — определить ценность публикации и, если она
подходит, подготовить из неё готовую украинскую новость.

ОБЩИЕ ПРАВИЛА:

- Только украинский язык.
- Не копируй исходный текст.
- Перестраивай предложения.
- Сохраняй факты.
- Не выдумывай факты.
- Не меняй даты.
- Не меняй числа.
- Не меняй названия.
- Не добавляй собственное мнение.
- Не добавляй неподтверждённые детали.
- Сохраняй слова "попередньо", "за даними", "повідомляють"
  и другие указания на неопределённость.
- Убирай рекламный мусор.
- Используй короткие абзацы.
- Не начинай словами "Ось новина".
- Не добавляй пояснений от себя.
"""


def is_bad_request(error: Exception) -> bool:
    text = str(error).upper()

    return (
        "400" in text
        or "INVALID_ARGUMENT" in text
        or "BAD REQUEST" in text
    )


def is_temporary_error(error: Exception) -> bool:
    text = str(error).upper()

    return any(
        value in text
        for value in (
            "429",
            "500",
            "502",
            "503",
            "504",
            "RESOURCE_EXHAUSTED",
            "UNAVAILABLE",
            "INTERNAL",
            "TIMEOUT",
            "DEADLINE",
            "TEMPORAR",
        )
    )


async def wait_before_request():
    global _last_request_time

    now = time.monotonic()
    elapsed = now - _last_request_time

    if elapsed < MIN_REQUEST_INTERVAL:
        delay = MIN_REQUEST_INTERVAL - elapsed

        print(
            f"[GEMINI] Пауза перед запросом: "
            f"{delay:.1f} сек."
        )

        await asyncio.sleep(delay)

    _last_request_time = time.monotonic()


async def request_model(
    prompt: str,
) -> str:

    async with GEMINI_SEMAPHORE:

        await wait_before_request()

        print(
            f"[GEMINI] Запрос к {MODEL}"
        )

        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    automatic_function_calling=(
                        types.AutomaticFunctionCallingConfig(
                            disable=True
                        )
                    )
                ),
            ),
            timeout=90,
        )

        if not response:
            raise RuntimeError(
                "Gemini не вернул ответ."
            )

        if not response.text:
            raise RuntimeError(
                "Gemini вернул пустой ответ."
            )

        result = response.text.strip()

        if not result:
            raise RuntimeError(
                "Gemini вернул пустой текст."
            )

        print("[GEMINI] Ответ получен.")

        return result


async def ask_gemini(
    prompt: str,
) -> str:

    temporary_attempt = 0

    while True:

        try:

            print(
                f"[GEMINI] Запрос "
                f"(временная попытка "
                f"{temporary_attempt + 1})"
            )

            return await request_model(
                prompt
            )

        except asyncio.TimeoutError as error:

            temporary_attempt += 1

            print(
                "[GEMINI] Timeout."
            )

            if temporary_attempt >= 3:
                raise RuntimeError(
                    "Gemini слишком долго "
                    "не отвечает."
                ) from error

            delay = 30 * temporary_attempt

            print(
                f"[GEMINI] Повтор через "
                f"{delay} сек."
            )

            await asyncio.sleep(delay)

        except Exception as error:

            print(
                f"[GEMINI] Ошибка: {error}"
            )

            # 400 не повторяем.
            if is_bad_request(error):
                raise RuntimeError(
                    f"Gemini отклонил запрос: {error}"
                ) from error

            # Временные ошибки тоже не долбим.
            # Монитор сам вернёт новость в очередь.
            if is_temporary_error(error):
                raise RuntimeError(
                    f"TEMPORARY_GEMINI_ERROR: {error}"
                ) from error

            raise


def clean_source_text(
    source_text: str,
) -> str:

    text = source_text.strip()

    if len(text) > 12000:
        text = (
            text[:12000]
            + "\n[Текст сокращён]"
        )

    return text


async def analyze_and_generate_news(
    source_text: str,
    source_name: str = "",
) -> dict:

    source_text = clean_source_text(
        source_text
    )

    if not source_name:
        source_name = "невідоме джерело"

    prompt = f"""
{SYSTEM_PROMPT}

Источник:
{source_name}

Проанализируй эту публикацию.

Твоя задача — решить, стоит ли передавать её редактору
новостного Telegram-канала Киева и Киевской области.

ВАЖНО:

Не ограничивайся только новостями, где прямо написано
"Київ".

Подходят:

1. События в Киеве.
2. События в Киевской области.
3. Воздушные тревоги в Киеве или Киевской области.
4. Ракеты, БпЛА и другие угрозы, если они связаны
   с Киевом или Киевской областью.
5. Важные общенациональные события, которые напрямую
   влияют на жителей Киева или всей Украины.
6. Решения центральной власти Украины, если они имеют
   заметное значение для жителей Киева/Украины.
7. Масштабные события в Украине, если они действительно
   важны для аудитории киевского новостного канала.
8. Общенациональные отключения, ограничения,
   транспортные или инфраструктурные события.
9. Другие актуальные события, которые разумно интересны
   аудитории Киева и Киевской области.

НЕ подходят:

- локальная новость другой области без значения
  для Киева/Украины в целом;
- реклама;
- продажа товаров;
- промокоды;
- казино;
- ставки;
- розыгрыши;
- мемы;
- поздравления;
- опросы;
- личные мнения;
- бессодержательные публикации;
- посты без конкретного события;
- очевидный спам.

ОЧЕНЬ ВАЖНО:

Если публикация короткая, но содержит потенциально важное
событие, НЕ отбрасывай её только из-за длины.

Например:

"Тривога Київ"
"У Києві вибух"
"Київ, вибухи"
"Повітряна тривога в Києві"

такие сообщения нужно анализировать.

Если информация выглядит как слух или неподтверждённое
сообщение, не превращай её в подтверждённый факт.

Если исходник говорит:
"попередньо",
"можливо",
"повідомляють",
"за словами очевидців",
"за попередніми даними"

сохрани эту неопределённость.

Ответ СТРОГО:

INTERESTING: YES
PRIORITY: HIGH
REASON: краткая причина
NEWS:
готовая новость

или:

INTERESTING: NO
PRIORITY: NORMAL
REASON: краткая причина
NEWS:

PRIORITY:

HIGH — срочное или очень важное событие.

NORMAL — обычная актуальная новость.

Не используй другие значения.

Если INTERESTING: YES:

NEWS обязательно должна быть написана
своими словами.

Не копируй исходный текст.

Не добавляй ничего после готовой новости.

ИСХОДНАЯ ПУБЛИКАЦИЯ:

{source_text}
"""

    result = await ask_gemini(
        prompt
    )

    interesting = False
    priority = "NORMAL"
    reason = ""
    news_lines = []

    reading_news = False

    for line in result.splitlines():

        stripped = line.strip()
        upper = stripped.upper()

        if upper.startswith(
            "INTERESTING:"
        ):

            value = stripped.split(
                ":",
                1
            )[1].strip().upper()

            interesting = (
                value == "YES"
            )

        elif upper.startswith(
            "PRIORITY:"
        ):

            value = stripped.split(
                ":",
                1
            )[1].strip().upper()

            if value == "HIGH":
                priority = "HIGH"
            else:
                priority = "NORMAL"

        elif upper.startswith(
            "REASON:"
        ):

            reason = stripped.split(
                ":",
                1
            )[1].strip()

        elif upper == "NEWS:":

            reading_news = True

        elif reading_news:

            news_lines.append(line)

    news = "\n".join(
        news_lines
    ).strip()

    if interesting and not news:

        raise RuntimeError(
            "Gemini определил новость как "
            "интересную, но не вернул текст."
        )

    return {
        "interesting": interesting,
        "priority": priority,
        "reason": reason,
        "news": news,
    }


async def check_news(
    source_text: str,
) -> dict:

    result = await analyze_and_generate_news(
        source_text
    )

    return {
        "interesting": result[
            "interesting"
        ],
        "reason": result[
            "reason"
        ],
        "priority": result[
            "priority"
        ],
    }


async def generate_news(
    source_text: str,
    mode: str = "normal",
    edit_request: str | None = None,
) -> str:

    mode_instruction = {
        "normal": """
Сделай полноценную новость среднего размера.
""",

        "short": """
Сделай короткую новость.
Оставь только важные факты.
""",

        "urgent": """
Сделай срочную новость.
Начни с короткого понятного заголовка.
Не добавляй драматизации.
""",

        "detailed": """
Сделай подробную новость.
Используй важные детали исходника.
""",
    }.get(
        mode,
        "",
    )

    edit_instruction = ""

    if edit_request:

        edit_instruction = f"""
Измени готовую новость согласно пожеланию:

{edit_request}

Не меняй факты.
"""

    prompt = f"""
{SYSTEM_PROMPT}

{mode_instruction}

{edit_instruction}

Исходный текст:

{clean_source_text(source_text)}

Перепиши текст.

Не копируй исходник.
Не выдумывай факты.

Верни только готовую новость.
"""

    return await ask_gemini(
        prompt
    )