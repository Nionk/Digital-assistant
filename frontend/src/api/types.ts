/**
 * Строгие TypeScript-контракты, на 100% синхронизированные с openapi.json (Pydantic v2).
 */

export type EventFormat =
  | "roundtable"
  | "business_breakfast"
  | "forum"
  | "conference"
  | "session";

export type ParticipationRole = "delegate" | "speaker" | "sponsor";

export type SelectionStatus = "draft" | "published";

export type ClientReactionStatus = "pending" | "interested" | "rejected";

// ============================================================================
// 1. ДАШБОРД МЕНЕДЖЕРА И КАТАЛОГ МЕРОПРИЯТИЙ (/api/manager/clients, /events)
// ============================================================================

export interface BurningDeadlineOut {
  event_id: number;
  event_title: string;
  early_bird_deadline: string; // YYYY-MM-DD
  potential_savings: number;
}

export interface ClientSummaryOut {
  id: number;
  company_name: string;
  contact_person: string | null;
  raw_manager_notes: string;
  latest_selection_id: number | null;
  latest_selection_status: SelectionStatus | null;
  magic_token: string | null; // UUIDv4
}

export interface ManagerDashboardOut {
  clients: ClientSummaryOut[];
  burning_deadlines: BurningDeadlineOut[];
}

export interface TariffOptionOut {
  tariff_id: number;
  tariff_name: string;
  participation_role: ParticipationRole;
  base_price: number | null; // null = По запросу
  early_bird_price: number | null;
  early_bird_deadline: string | null; // YYYY-MM-DD
  actual_price: number | null;
  savings: number;
  included_benefits: string | null;
}

export interface CatalogEventItemOut {
  event_id: number;
  canonical_title: string;
  event_format: EventFormat;
  city: string | null;
  is_online: boolean;
  venue: string | null;
  start_date: string;
  end_date: string;
  summary: string;
  themes: string[];
  tariffs: TariffOptionOut[];
}

export interface ManagerEventsCatalogOut {
  total_count: number;
  events: CatalogEventItemOut[];
}

// ============================================================================
// 2. ИИ-ПРОФИЛИРОВАНИЕ И СБОРКА ПАКЕТОВ (POST /api/manager/clients/{id}/match)
// ============================================================================

export interface ClientQueryExtracted {
  cities: string[];
  include_online: boolean;
  date_from: string | null;
  date_to: string | null;
  total_budget_max: number;
  target_events_count: number;
  preferred_formats: EventFormat[];
  required_roles: ParticipationRole[];
  min_speaker_events: number;
  themes_keywords: string[];
  semantic_search_query: string;
}

export interface MatchRequestIn {
  raw_manager_notes: string;
  override_profile?: ClientQueryExtracted | null;
}

export interface BundleEventItemOut {
  event_id: number;
  canonical_title: string;
  event_format: EventFormat;
  city: string | null;
  is_online: boolean;
  venue: string | null;
  start_date: string;
  end_date: string;
  themes: string[];
  recommended_tariff: TariffOptionOut;
  available_tariffs: TariffOptionOut[];
  ai_rationale: string;
}

export interface BundleVariantOut {
  bundle_group: number; // 1 или 2
  bundle_title: string;
  items: BundleEventItemOut[];
  total_actual_price: number;
  total_base_price: number;
  total_savings: number;
  earliest_deadline: string | null;
  is_over_budget_tolerance: boolean;
}

export interface MatchResponseOut {
  selection_id: number;
  client_id: number;
  extracted_profile: ClientQueryExtracted;
  bundle_variants: BundleVariantOut[];
  bonus_on_request_items: BundleEventItemOut[];
  generated_pitch_text: string;
}

// ============================================================================
// 3. ПУБЛИКАЦИЯ ВИТРИНЫ (PUT /api/manager/selections/{id}/publish)
// ============================================================================

export interface SelectedEventTariffPairIn {
  event_id: number;
  tariff_id: number;
  ai_rationale?: string | null;
}

export interface PublishSelectionIn {
  selected_bundle_group: number;
  final_items: SelectedEventTariffPairIn[];
  final_pitch_text: string;
}

export interface PublishSelectionOut {
  selection_id: number;
  status: "published";
  magic_token: string;
  public_showcase_url: string;
  total_package_price: number;
  total_package_savings: number;
}

// ============================================================================
// 4. ПУБЛИЧНАЯ ВИТРИНА КЛИЕНТА И ИЗОЛИРОВАННЫЙ RAG (/api/public/s/{magic_token})
// ============================================================================

export interface ShowcaseEventItemOut {
  selection_item_id: number;
  event_id: number;
  canonical_title: string;
  event_format: string;
  city: string | null;
  is_online: boolean;
  venue: string | null;
  start_date: string;
  end_date: string;
  summary: string;
  themes: string[];
  tariff_name: string;
  participation_role: ParticipationRole;
  actual_price: number | null;
  base_price: number | null;
  early_bird_deadline: string | null;
  savings: number;
  included_benefits: string | null;
  ai_rationale: string;
  client_reaction: ClientReactionStatus;
  client_comment: string | null;
}

export interface ShowcaseViewOut {
  selection_id: number;
  company_name: string;
  manager_full_name: string;
  pitch_text: string;
  total_events_count: number;
  total_actual_price: number;
  total_savings: number;
  min_early_bird_deadline: string | null;
  items: ShowcaseEventItemOut[];
  faq_quick_chips: string[];
}

export interface ClientReactionIn {
  reaction: "interested" | "rejected";
  comment?: string | null;
}

export interface ClientReactionOut {
  selection_item_id: number;
  new_reaction: "interested" | "rejected";
  manager_notified: boolean;
}

export interface AskRegulationQuestionIn {
  question_text: string;
}

export interface AskRegulationQuestionOut {
  event_id: number;
  question_text: string;
  is_answer_found: boolean;
  answer_text: string;
  source_quote: string | null;
  from_cache: boolean;
  escalated_to_telegram: boolean;
}

