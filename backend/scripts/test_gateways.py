import os
import asyncio
from openai import AsyncOpenAI

def load_env_simple(filepath=".env"):
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()

load_env_simple()

async def test_embedding():
    api_key = os.getenv("EMBEDDING_API_KEY")
    base_url = os.getenv("EMBEDDING_BASE_URL", "https://api.jina.ai/v1")
    model = os.getenv("EMBEDDING_MODEL", "jina-embeddings-v5-omni-small")
    dim = int(os.getenv("EMBEDDING_DIM", 1024))
    
    print("\n--- 1. Тестирование Embedding Gateway (Jina AI) ---")
    if not api_key:
        print("[FAIL] EMBEDDING_API_KEY не задан в .env!")
        return False
        
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    try:
        resp = await client.embeddings.create(
            model=model,
            input=["Тест"],
            dimensions=dim
        )
        vec = resp.data[0].embedding
        print(f"[OK] Эмбеддинг получен успешно!")
        print(f"Размерность: {len(vec)} (ожидалось {dim})")
        print(f"Использовано токенов: {resp.usage.total_tokens}")
        return len(vec) == dim
    except Exception as e:
        print(f"[FAIL] Ошибка при запросе эмбеддинга: {e}")
        return False

async def test_llm():
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL", "https://api.ru-openrouter.ru/v1")
    model = os.getenv("LLM_MODEL", "deepseek/deepseek-v4.1-flash")
    
    print("\n--- 2. Тестирование LLM Gateway (Ru-OpenRouter) ---")
    if not api_key:
        print("[FAIL] LLM_API_KEY не задан в .env (пустая строка).")
        print("-> Вставьте ваш API-ключ от Ru-OpenRouter в файл .env в строку LLM_API_KEY=...")
        return False
        
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Скажи одно слово: ОК"}],
            max_tokens=150
        )
        msg = resp.choices[0].message
        ans = msg.content if msg.content else "(reasoning only)"
        print(f"[OK] LLM ответила успешно: {ans.strip()}")
        print(f"Использовано токенов: {resp.usage.total_tokens}")
        return True
    except Exception as e:
        print(f"[FAIL] Ошибка при запросе LLM: {e}")
        return False

async def main():
    print("=== Валидация API-шлюзов (D-01) ===")
    emb_ok = await test_embedding()
    llm_ok = await test_llm()
    print("\n===============================")
    print(f"Эмбеддинги (Jina AI): {'PASSED' if emb_ok else 'FAILED'}")
    print(f"LLM генерация:        {'PASSED' if llm_ok else 'FAILED'}")

if __name__ == "__main__":
    asyncio.run(main())
