import type { components } from "./schema";

type Schema<K extends keyof components["schemas"]> = components["schemas"][K];

/**
 * Доменные TypeScript-контракты поверх автосгенерированной OpenAPI-схемы (src/api/schema.d.ts).
 * Источник правды: backend/openapi.json -> npm run gen:api.
 *
 * Примечание: FastAPI/Pydantic v2 при сериализации ответов всегда включает все поля
 * (включая значения `null` и пустые списки), поэтому для *Out-схем используется Required<...>,
 * тогда как *In-схемы сохраняют точные необязательные поля из OpenAPI.
 */

export type EventFormat = Schema<"CatalogEventItemOut">["event_format"];

export type ParticipationRole = Schema<"TariffOptionOut">["participation_role"];

export type EventDataStatus = Schema<"CatalogEventItemOut">["data_status"];

export type SelectionStatus = NonNullable<
  Schema<"ClientSummaryOut">["latest_selection_status"]
>;

export type ClientReactionStatus =
  Schema<"ShowcaseEventItemOut">["client_reaction"];

export type ProfileSource = Schema<"ClientQueryExtracted">["profile_source"];

export type ScraperSourceKey = Schema<"ScraperRunIn">["source_key"];

export type ScraperRunStatus = Schema<"ScraperRunOut">["status"];

export type ChatSenderRole = Schema<"ShowcaseChatMessageOut">["sender_role"];

// ---- Авторизация (/api/auth/*) ----
export type LoginRequestIn = Schema<"LoginRequestIn">;
export type ManagerUser = Required<Schema<"ManagerUser">>;
export type TokenOut = Omit<Required<Schema<"TokenOut">>, "user"> & {
  user: ManagerUser;
};

// ---- Кабинет менеджера (/api/manager/*) ----
export type BurningDeadlineOut = Required<Schema<"BurningDeadlineOut">>;
export type ClientSummaryOut = Required<Schema<"ClientSummaryOut">>;
export type ManagerDashboardOut = {
  clients: ClientSummaryOut[];
  burning_deadlines: BurningDeadlineOut[];
};

export type TariffOptionOut = Required<Schema<"TariffOptionOut">>;

export type CatalogEventItemOut = Omit<
  Required<Schema<"CatalogEventItemOut">>,
  "tariffs"
> & {
  tariffs: TariffOptionOut[];
};

export type ManagerEventsCatalogOut = {
  total_count: number;
  events: CatalogEventItemOut[];
};

export interface CatalogEventsFilterParams {
  city?: string | null;
  event_format?: EventFormat | null;
  data_status?: EventDataStatus | null;
  date_from?: string | null;
  date_to?: string | null;
}

export interface EventUploadIn {
  file?: File | null;
  raw_text?: string | null;
  source_url?: string | null;
}

export type EventUploadOut = Required<Schema<"EventUploadOut">>;

export type ScraperRunIn = Schema<"ScraperRunIn">;
export type ScraperRunOut = Required<Schema<"ScraperRunOut">>;

export type ClientQueryExtracted = Required<Schema<"ClientQueryExtracted">>;

export type MatchRequestIn = {
  raw_manager_notes: string;
  override_profile?: ClientQueryExtracted | null;
};

export type BundleEventItemOut = Omit<
  Required<Schema<"BundleEventItemOut">>,
  "recommended_tariff" | "available_tariffs"
> & {
  recommended_tariff: TariffOptionOut;
  available_tariffs: TariffOptionOut[];
};

export type BundleVariantOut = Omit<
  Required<Schema<"BundleVariantOut">>,
  "items"
> & {
  items: BundleEventItemOut[];
};

export type MatchResponseOut = Omit<
  Required<Schema<"MatchResponseOut">>,
  "extracted_profile" | "bundle_variants" | "bonus_on_request_items"
> & {
  extracted_profile: ClientQueryExtracted;
  bundle_variants: BundleVariantOut[];
  bonus_on_request_items: BundleEventItemOut[];
};

export type SelectedEventTariffPairIn = Schema<"SelectedEventTariffPairIn">;
export type PublishSelectionIn = Schema<"PublishSelectionIn">;
export type PublishSelectionOut = Required<Schema<"PublishSelectionOut">>;

export type SelectionItemReactionActivity = Required<
  Schema<"SelectionItemReactionActivity">
>;
export type SelectionQuestionActivity = Required<
  Schema<"SelectionQuestionActivity">
>;
export type SelectionActivityOut = {
  selection_id: number;
  reactions: SelectionItemReactionActivity[];
  pending_questions: SelectionQuestionActivity[];
};

export type ManagerReplyIn = Schema<"ManagerReplyIn">;
export type ManagerReplyOut = Required<Schema<"ManagerReplyOut">>;

// ---- Публичная витрина клиента (/api/public/s/{magic_token}/*) ----
export type ShowcaseChatMessageOut = Required<Schema<"ShowcaseChatMessageOut">>;

export type ShowcaseEventItemOut = Omit<
  Required<Schema<"ShowcaseEventItemOut">>,
  "chat_messages"
> & {
  chat_messages: ShowcaseChatMessageOut[];
};

export type ShowcaseViewOut = Omit<
  Required<Schema<"ShowcaseViewOut">>,
  "items"
> & {
  items: ShowcaseEventItemOut[];
};

export type ClientReactionIn = Schema<"ClientReactionIn">;
export type ClientReactionOut = Required<Schema<"ClientReactionOut">>;

export type AskRegulationQuestionIn = Schema<"AskRegulationQuestionIn">;
export type AskRegulationQuestionOut = Required<
  Schema<"AskRegulationQuestionOut">
>;

export type EscalateQuestionIn = Schema<"EscalateQuestionIn">;
export type EscalateQuestionOut = Required<Schema<"EscalateQuestionOut">>;
