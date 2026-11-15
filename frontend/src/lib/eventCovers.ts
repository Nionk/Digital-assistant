/**
 * Локальная коллекция архитектурно-деловых SVG-обложек для карточек витрины клиента.
 * Полностью автономна (без внешних HTTP-запросов) и сохраняет единую обсидианово-золотую эстетику.
 */

export interface EventCoverVisual {
  imageUrl: string;
  fallbackGradient: string;
  categoryCaption: string;
}

function encodeSvgDataUri(svgContent: string): string {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svgContent)}`;
}

const SKYLINE_COVER_SVG = encodeSvgDataUri(
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 420" preserveAspectRatio="xMidYMid slice">
    <defs>
      <linearGradient id="bg1" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#0F2620"/>
        <stop offset="55%" stop-color="#121A22"/>
        <stop offset="100%" stop-color="#1A2B3D"/>
      </linearGradient>
      <linearGradient id="gold1" x1="0%" y1="0%" x2="0%" y2="100%">
        <stop offset="0%" stop-color="#E5C378" stop-opacity="0.45"/>
        <stop offset="100%" stop-color="#7C5A20" stop-opacity="0.06"/>
      </linearGradient>
    </defs>
    <rect width="900" height="420" fill="url(#bg1)"/>
    <g stroke="#E5C378" stroke-opacity="0.10" stroke-width="1">
      <line x1="0" y1="84" x2="900" y2="84"/>
      <line x1="0" y1="168" x2="900" y2="168"/>
      <line x1="0" y1="252" x2="900" y2="252"/>
      <line x1="0" y1="336" x2="900" y2="336"/>
      <line x1="180" y1="0" x2="180" y2="420"/>
      <line x1="360" y1="0" x2="360" y2="420"/>
      <line x1="540" y1="0" x2="540" y2="420"/>
      <line x1="720" y1="0" x2="720" y2="420"/>
    </g>
    <g fill="#0E141B" fill-opacity="0.72" stroke="#E5C378" stroke-opacity="0.28" stroke-width="1.2">
      <rect x="90" y="160" width="95" height="260" rx="2"/>
      <rect x="205" y="95" width="120" height="325" rx="2"/>
      <polygon points="355,60 475,90 475,420 355,420"/>
      <rect x="505" y="130" width="110" height="290" rx="2"/>
      <polygon points="645,110 755,75 755,420 645,420"/>
    </g>
    <g stroke="url(#gold1)" stroke-width="1.5">
      <line x1="230" y1="125" x2="230" y2="390"/>
      <line x1="265" y1="125" x2="265" y2="390"/>
      <line x1="300" y1="125" x2="300" y2="390"/>
      <line x1="390" y1="100" x2="390" y2="390"/>
      <line x1="435" y1="110" x2="435" y2="390"/>
      <line x1="695" y1="115" x2="695" y2="390"/>
    </g>
    <circle cx="715" cy="90" r="95" fill="#E5C378" fill-opacity="0.06"/>
  </svg>`
);

const EXECUTIVE_TABLE_COVER_SVG = encodeSvgDataUri(
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 420" preserveAspectRatio="xMidYMid slice">
    <defs>
      <radialGradient id="rg2" cx="50%" cy="46%" r="58%">
        <stop offset="0%" stop-color="#25423B"/>
        <stop offset="65%" stop-color="#14201E"/>
        <stop offset="100%" stop-color="#0D1216"/>
      </radialGradient>
    </defs>
    <rect width="900" height="420" fill="url(#rg2)"/>
    <g fill="none" stroke="#E5C378">
      <ellipse cx="450" cy="210" rx="340" ry="145" stroke-opacity="0.14" stroke-width="1"/>
      <ellipse cx="450" cy="210" rx="265" ry="108" stroke-opacity="0.28" stroke-width="1.4"/>
      <ellipse cx="450" cy="210" rx="185" ry="72" stroke-opacity="0.42" stroke-width="1.5"/>
      <ellipse cx="450" cy="210" rx="95" ry="36" stroke-opacity="0.22" stroke-width="1"/>
    </g>
    <g fill="#E5C378" fill-opacity="0.55">
      <circle cx="185" cy="210" r="4"/>
      <circle cx="715" cy="210" r="4"/>
      <circle cx="450" cy="102" r="4"/>
      <circle cx="450" cy="318" r="4"/>
      <circle cx="268" cy="134" r="3.5"/>
      <circle cx="632" cy="134" r="3.5"/>
      <circle cx="268" cy="286" r="3.5"/>
      <circle cx="632" cy="286" r="3.5"/>
    </g>
    <line x1="60" y1="210" x2="840" y2="210" stroke="#34D399" stroke-opacity="0.14" stroke-dasharray="4 6"/>
  </svg>`
);

const ATRIUM_ARCH_COVER_SVG = encodeSvgDataUri(
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 420" preserveAspectRatio="xMidYMid slice">
    <defs>
      <linearGradient id="bg3" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#192820"/>
        <stop offset="55%" stop-color="#121E19"/>
        <stop offset="100%" stop-color="#22382B"/>
      </linearGradient>
    </defs>
    <rect width="900" height="420" fill="url(#bg3)"/>
    <g fill="none" stroke="#E5C378">
      <path d="M 140 420 L 140 190 A 310 210 0 0 1 760 190 L 760 420" stroke-opacity="0.22" stroke-width="1.5"/>
      <path d="M 220 420 L 220 205 A 230 160 0 0 1 680 205 L 680 420" stroke-opacity="0.32" stroke-width="1.4"/>
      <path d="M 300 420 L 300 220 A 150 110 0 0 1 600 220 L 600 420" stroke-opacity="0.42" stroke-width="1.2"/>
      <path d="M 380 420 L 380 245 A 70 55 0 0 1 520 245 L 520 420" stroke-opacity="0.25" stroke-width="1"/>
    </g>
    <g stroke="#34D399" stroke-opacity="0.14" stroke-width="1">
      <line x1="450" y1="20" x2="90" y2="420"/>
      <line x1="450" y1="20" x2="810" y2="420"/>
      <line x1="450" y1="20" x2="270" y2="420"/>
      <line x1="450" y1="20" x2="630" y2="420"/>
    </g>
  </svg>`
);

const PLENARY_HALL_COVER_SVG = encodeSvgDataUri(
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 420" preserveAspectRatio="xMidYMid slice">
    <defs>
      <linearGradient id="bg4" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#14171D"/>
        <stop offset="60%" stop-color="#132920"/>
        <stop offset="100%" stop-color="#1F4A38"/>
      </linearGradient>
      <linearGradient id="beam" x1="50%" y1="0%" x2="50%" y2="100%">
        <stop offset="0%" stop-color="#E5C378" stop-opacity="0.24"/>
        <stop offset="100%" stop-color="#E5C378" stop-opacity="0"/>
      </linearGradient>
    </defs>
    <rect width="900" height="420" fill="url(#bg4)"/>
    <polygon points="360,0 540,0 690,420 210,420" fill="url(#beam)"/>
    <g fill="none" stroke="#E5C378">
      <path d="M 80 350 Q 450 250 820 350" stroke-opacity="0.38" stroke-width="1.5"/>
      <path d="M 130 300 Q 450 215 770 300" stroke-opacity="0.28" stroke-width="1.3"/>
      <path d="M 185 250 Q 450 180 715 250" stroke-opacity="0.20" stroke-width="1.1"/>
      <path d="M 245 205 Q 450 148 655 205" stroke-opacity="0.14" stroke-width="1"/>
    </g>
    <rect x="370" y="96" width="160" height="6" rx="3" fill="#E5C378" fill-opacity="0.5"/>
  </svg>`
);

const NETWORK_LOUNGE_COVER_SVG = encodeSvgDataUri(
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 420" preserveAspectRatio="xMidYMid slice">
    <defs>
      <linearGradient id="bg5" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#191B20"/>
        <stop offset="55%" stop-color="#162A24"/>
        <stop offset="100%" stop-color="#0E1A16"/>
      </linearGradient>
    </defs>
    <rect width="900" height="420" fill="url(#bg5)"/>
    <g stroke="#E5C378" stroke-opacity="0.26" stroke-width="1.2">
      <line x1="170" y1="270" x2="320" y2="155"/>
      <line x1="320" y1="155" x2="495" y2="215"/>
      <line x1="495" y1="215" x2="650" y2="120"/>
      <line x1="650" y1="120" x2="760" y2="245"/>
      <line x1="320" y1="155" x2="420" y2="310"/>
      <line x1="495" y1="215" x2="610" y2="305"/>
      <line x1="170" y1="270" x2="420" y2="310"/>
      <line x1="420" y1="310" x2="610" y2="305"/>
    </g>
    <g fill="#12161A" stroke="#E5C378" stroke-width="1.8">
      <circle cx="170" cy="270" r="10"/>
      <circle cx="320" cy="155" r="14"/>
      <circle cx="495" cy="215" r="16"/>
      <circle cx="650" cy="120" r="12"/>
      <circle cx="760" cy="245" r="9"/>
      <circle cx="420" cy="310" r="11"/>
      <circle cx="610" cy="305" r="10"/>
    </g>
    <circle cx="495" cy="215" r="4.5" fill="#34D399"/>
    <circle cx="320" cy="155" r="4" fill="#E5C378"/>
    <circle cx="650" cy="120" r="4" fill="#E5C378"/>
  </svg>`
);

const INDUSTRIAL_GRID_COVER_SVG = encodeSvgDataUri(
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 420" preserveAspectRatio="xMidYMid slice">
    <defs>
      <linearGradient id="bg6" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#141C28"/>
        <stop offset="65%" stop-color="#132922"/>
        <stop offset="100%" stop-color="#0D1E18"/>
      </linearGradient>
    </defs>
    <rect width="900" height="420" fill="url(#bg6)"/>
    <g fill="none" stroke="#E5C378" stroke-opacity="0.22" stroke-width="1.2">
      <polygon points="150,310 310,165 470,310 310,360"/>
      <polygon points="360,260 540,105 720,260 540,320"/>
      <line x1="310" y1="165" x2="310" y2="360"/>
      <line x1="540" y1="105" x2="540" y2="320"/>
      <rect x="190" y="90" width="520" height="240" stroke-opacity="0.10" stroke-dasharray="6 6"/>
    </g>
    <g stroke="#34D399" stroke-opacity="0.24" stroke-width="1.4">
      <line x1="120" y1="360" x2="780" y2="360"/>
      <line x1="160" y1="360" x2="160" y2="348"/>
      <line x1="340" y1="360" x2="340" y2="348"/>
      <line x1="520" y1="360" x2="520" y2="348"/>
      <line x1="700" y1="360" x2="700" y2="348"/>
    </g>
  </svg>`
);

const ARCHITECTURAL_COVERS: EventCoverVisual[] = [
  {
    imageUrl: SKYLINE_COVER_SVG,
    fallbackGradient: "linear-gradient(135deg, #16382C 0%, #0F291F 55%, #1E3A5F 100%)",
    categoryCaption: "Девелопмент и градостроительство",
  },
  {
    imageUrl: EXECUTIVE_TABLE_COVER_SVG,
    fallbackGradient: "linear-gradient(135deg, #1C2826 0%, #2D4A43 55%, #16382C 100%)",
    categoryCaption: "Закрытая встреча руководителей",
  },
  {
    imageUrl: ATRIUM_ARCH_COVER_SVG,
    fallbackGradient: "linear-gradient(135deg, #233329 0%, #16382C 60%, #3D5A45 100%)",
    categoryCaption: "Архитектура и проектирование",
  },
  {
    imageUrl: PLENARY_HALL_COVER_SVG,
    fallbackGradient: "linear-gradient(135deg, #18181B 0%, #16382C 65%, #2D6A4F 100%)",
    categoryCaption: "Пленарная программа и экспозиция",
  },
  {
    imageUrl: NETWORK_LOUNGE_COVER_SVG,
    fallbackGradient: "linear-gradient(135deg, #27272A 0%, #1E3F32 60%, #16382C 100%)",
    categoryCaption: "Деловые знакомства и партнёрства",
  },
  {
    imageUrl: INDUSTRIAL_GRID_COVER_SVG,
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

