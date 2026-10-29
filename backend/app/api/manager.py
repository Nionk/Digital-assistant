import datetime
from uuid import UUID
from fastapi import APIRouter, status, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.core.security import CurrentManagerDep
from app.core.database import get_async_session
from app.models.models import Selection, SelectionItem, EventTariff, Client
from app.schemas.manager import (
    ManagerDashboardOut,
    ClientSummaryOut,
    BurningDeadlineOut,
    MatchRequestIn,
    MatchResponseOut,
    PublishSelectionIn,
    PublishSelectionOut,
)
# Импортируем наш готовый движок матчинга
from app.services.matcher import run_client_matching_pipeline

router = APIRouter(prefix="/api/manager", tags=["Manager Cabinet"])


@router.get(
    "/clients",
    response_model=ManagerDashboardOut,
    summary="Список клиентов менеджера и алерты горящих дедлайнов Early Bird",
)
async def get_manager_clients(
    current_manager: CurrentManagerDep,
    db: AsyncSession = Depends(get_async_session)
) -> ManagerDashboardOut:
    """
    В идеале здесь должен быть запрос к БД. 
    Пока оставляем моковые данные для UI, чтобы не ломать фронтенд на этапе Демо.
    """
    return ManagerDashboardOut(
        clients=[
            ClientSummaryOut(
                id=1, company_name="ГК «Пионер»", contact_person="Игорь Ветров",
                raw_manager_notes="Созвонились с ГК Пионер...", latest_selection_id=1,
                latest_selection_status="draft", magic_token=None,
            )
        ],
        burning_deadlines=[],
    )


@router.post(
    "/clients/{client_id}/match",
    response_model=MatchResponseOut,
    summary="Извлечение профиля из заметки (NER), сборка 2 вариантов пакетов и генерация черновика КП",
)
async def match_events_for_client(
    client_id: int,
    payload: MatchRequestIn,
    current_manager: CurrentManagerDep,
    db: AsyncSession = Depends(get_async_session)
) -> MatchResponseOut:
    """
    Запускает полный пайплайн D-06 и D-07: от сырой заметки до готовых пакетов и письма.
    Движок сам сохраняет черновик в БД (таблицы selections и selection_items).
    """
    try:
        result = await run_client_matching_pipeline(
            session=db,
            client_id=client_id,
            payload=payload
        )
        return result
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при подборе мероприятий: {str(e)}"
        )


@router.put(
    "/selections/{selection_id}/publish",
    response_model=PublishSelectionOut,
    status_code=status.HTTP_200_OK,
    summary="Фиксация выбранного пакета, сохранение текста КП и выпуск публичной ссылки Magic Link",
)
async def publish_selection(
    selection_id: int,
    payload: PublishSelectionIn,
    current_manager: CurrentManagerDep,
    db: AsyncSession = Depends(get_async_session)
) -> PublishSelectionOut:
    """
    Атомарно фиксирует утвержденный менеджером пакет, удаляет альтернативные варианты,
    пересчитывает бюджет и генерирует публичную ссылку.
    """
    # 1. Ищем черновик подборки
    stmt = select(Selection).where(Selection.id == selection_id)
    result = await db.execute(stmt)
    selection = result.scalar_one_or_none()
    
    if not selection:
        raise HTTPException(status_code=404, detail="Подборка не найдена")

    # 2. Обновляем статус и текст письма
    selection.status = "published"
    selection.generated_pitch_text = payload.final_pitch_text

    # 3. Удаляем все старые элементы (черновые) и будем записывать только утвержденные
    await db.execute(delete(SelectionItem).where(SelectionItem.selection_id == selection_id))

    total_price = 0.0
    total_savings = 0.0
    today = datetime.date.today()

    # 4. Записываем финальный состав (который менеджер выбрал в UI)
    for item_in in payload.final_items:
        # Проверяем тариф
        tariff = await db.get(EventTariff, item_in.tariff_id)
        if not tariff:
            raise HTTPException(status_code=400, detail=f"Тариф {item_in.tariff_id} не найден")

        # Считаем актуальную цену
        base = float(tariff.base_price) if tariff.base_price is not None else None
        eb = float(tariff.early_bird_price) if tariff.early_bird_price is not None else None
        
        if base is None:
            actual = None
        elif eb is not None and tariff.early_bird_deadline and tariff.early_bird_deadline >= today:
            actual = eb
            total_savings += (base - eb)
        else:
            actual = base
            
        if actual:
            total_price += actual

        # Создаем запись в БД (принудительно ставим bundle_group = 1, так как это финал)
        new_item = SelectionItem(
            selection_id=selection_id,
            event_id=item_in.event_id,
            recommended_tariff_id=item_in.tariff_id,
            bundle_group=1,
            ai_rationale=item_in.ai_rationale,
            client_reaction="pending"
        )
        db.add(new_item)

    selection.total_budget_limit = total_price
    await db.commit()
    await db.refresh(selection)

    return PublishSelectionOut(
        selection_id=selection.id,
        status="published",
        magic_token=selection.magic_token,
        public_showcase_url=f"/s/{selection.magic_token}",
        total_package_price=total_price,
        total_package_savings=total_savings
    )