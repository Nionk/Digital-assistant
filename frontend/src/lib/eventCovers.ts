/**
 * Курированная коллекция архитектурно-деловых обложек для карточек витрины клиента (в стиле Фото 8).
 * Каждая обложка имеет резервный глубокий архитектурный градиент на случай работы без внешнего интернета.
 */

export interface EventCoverVisual {
  imageUrl: string;
  fallbackGradient: string;
  categoryCaption: string;
}

const ARCHITECTURAL_COVERS: EventCoverVisual[] = [
  {
    // Современные небоскребы делового центра (аналог левой карточки с Фото 8 «Форум по девелопменту»)
    imageUrl:
      "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=900&q=80",
    fallbackGradient: "linear-gradient(135deg, #16382C 0%, #0F291F 55%, #1E3A5F 100%)",
    categoryCaption: "Девелопмент и градостроительство",
  },
  {
    // Переговорный круглый стол руководителей (аналог правой карточки с Фото 8 «Круглый стол»)
    imageUrl:
      "https://images.unsplash.com/photo-1542744173-8e7e53415bb0?auto=format&fit=crop&w=900&q=80",
    fallbackGradient: "linear-gradient(135deg, #1C2826 0%, #2D4A43 55%, #16382C 100%)",
    categoryCaption: "Закрытая встреча руководителей",
  },
  {
    // Архитектурный атриум и современная урбанистика
    imageUrl:
      "https://images.unsplash.com/photo-1513694203232-719a280e022f?auto=format&fit=crop&w=900&q=80",
    fallbackGradient: "linear-gradient(135deg, #233329 0%, #16382C 60%, #3D5A45 100%)",
    categoryCaption: "Архитектура и проектирование",
  },
  {
    // Пленарный зал отраслевого форума
    imageUrl:
      "https://images.unsplash.com/photo-1511578314322-379afb476865?auto=format&fit=crop&w=900&q=80",
    fallbackGradient: "linear-gradient(135deg, #18181B 0%, #16382C 65%, #2D6A4F 100%)",
    categoryCaption: "Пленарная программа и экспозиция",
  },
  {
    // Камерный деловой завтрак и панорамный зал
    imageUrl:
      "https://images.unsplash.com/photo-1497366216548-37526070297c?auto=format&fit=crop&w=900&q=80",
    fallbackGradient: "linear-gradient(135deg, #27272A 0%, #1E3F32 60%, #16382C 100%)",
    categoryCaption: "Деловые знакомства и партнёрства",
  },
  {
    // Индустриальная и строительная архитектура
    imageUrl:
      "https://images.unsplash.com/photo-1503387762-592deb58ef4e?auto=format&fit=crop&w=900&q=80",
    fallbackGradient: "linear-gradient(135deg, #1E293B 0%, #16382C 70%, #0F291F 100%)",
    categoryCaption: "Строительная индустрия и ИЖС",
  },
];

export function getEventCoverVisual(
  eventId: number,
  eventFormat: string
): EventCoverVisual {
  if (eventFormat === "roundtable" || eventFormat === "business_breakfast") {
    return eventId % 2 === 0 ? ARCHITECTURAL_COVERS[1] : ARCHITECTURAL_COVERS[4];
  }
  if (eventFormat === "forum") {
    return eventId % 2 === 0 ? ARCHITECTURAL_COVERS[0] : ARCHITECTURAL_COVERS[3];
  }
  const index = Math.abs(eventId) % ARCHITECTURAL_COVERS.length;
  return ARCHITECTURAL_COVERS[index];
}

