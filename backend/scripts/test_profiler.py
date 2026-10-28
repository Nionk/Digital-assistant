import asyncio
import sys
from pathlib import Path
from pprint import pprint

# Настройка путей для прямого запуска
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.profiler import extract_client_profile

async def main():
    print("=== Тест D-06: Профилировщик заметок менеджера (5 сценариев) ===\n")

    test_notes = [
        # 1. Базовый сценарий (ГК Пионер: по умолчанию include_online=True)
        "Созвонились с ГК Пионер. Ищут на ноябрь-декабрь в Москве или СПб 3 небольших мероприятия (круглые столы или закрытые завтраки) по теме КРТ, урбанистики и жилой застройки. Хоят выступить спикером хотя бы на одном, на остальных просто делегатами. Общий бюджет на всё — потолок 400 тыс. руб.",
        
        # 2. Нечеткие даты и один город
        "Нужны 2 региональные сессии по ИЖС и мастер-планированию на конец осени. Только делегатами, бюджет до 150 000 руб. Город — Екатеринбург.",
        
        # 3. Онлайн-формат и разговорная сумма
        "Интересует онлайн-конференция по BIM и цифровизации стройки, бюджет до полтора миллиона. Хотим быть спонсорами сессии.",
        
        # 4. Сленг, опечатки и несколько форматов
        "Нада 3-4 тусы в мск и питере на след месяц по девелопменту. Бюджет 350к. Ищем форматы форумов или конференций. Роли - делегаты и спикеры.",
        
        # 5. Смена решения в ходе разговора
        "Сначала думали про Сочи, но решили только в Казани. Нужен 1 круглый стол по урбанистике в начале декабря. Бюджет 120000 рублей. Спикером не хотим, только послушать.",

        # 6. Строго оффлайн (проверка include_online = False)
        "Нужен строго очный строительный форум в Москве, только офлайн, без вебинаров и трансляций. Бюджет 200 000 руб.",

        # 7. Слово 'онлайн' в качестве локации (проверка отсечения 'Онлайн' из списка cities)
        "Ищем мероприятия на ноябрь: онлайн или в Москве. Бюджет 100 тыс руб."
    ]

    failed_tests = 0

    for i, notes in enumerate(test_notes, 1):
        print(f"--- Тестовая заметка №{i} ---")
        print(f"Текст: {notes}\n")
        
        try:
            profile = await extract_client_profile(notes)
            pprint(profile.model_dump())
            
            # Проверки (DoD)
            assert profile.total_budget_max > 0, "Бюджет должен быть числом > 0"
            
            if i == 1:
                assert "Москва" in profile.cities and "Санкт-Петербург" in profile.cities
                assert profile.min_speaker_events == 1
                assert profile.include_online == True, "По умолчанию include_online должен быть True"
            elif i == 2:
                assert "Екатеринбург" in profile.cities
                assert profile.min_speaker_events == 0
            elif i == 3:
                assert profile.include_online == True
                assert profile.total_budget_max == 1500000.0
            elif i == 4:
                assert "Москва" in profile.cities and "Санкт-Петербург" in profile.cities
                assert profile.total_budget_max == 350000.0
                assert profile.target_events_count in (3, 4)
            elif i == 5:
                assert "Казань" in profile.cities
                assert "Сочи" not in profile.cities
            elif i == 6:
                assert profile.include_online == False, "При явном указании 'строго офлайн' include_online должен быть False"
                assert "Москва" in profile.cities
            elif i == 7:
                assert "Онлайн" not in profile.cities, "'Онлайн' не должен попадать в список городов"
                assert profile.include_online == True, "При упоминании онлайн include_online должен быть True"
            
            print("\n[OK] Проверки пройдены успешно!\n")
            
        except Exception as e:
            failed_tests += 1
            print(f"\n[FAIL] Ошибка: {e}\n")

    if failed_tests > 0:
        print(f"Итог: {failed_tests} тестов провалено!")
        sys.exit(1)
    else:
        print("Итог: Все 7 тестов успешно пройдены!")

if __name__ == "__main__":
    asyncio.run(main())