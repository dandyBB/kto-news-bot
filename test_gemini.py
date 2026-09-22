import asyncio

from app.ai import ask_gemini


async def main():
    print("Отправляю тест в Gemini...")

    result = await ask_gemini(
        "Ответь одним словом: РАБОТАЕТ"
    )

    print("Ответ Gemini:")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())