import type { ShowcaseChatMessageOut } from "@/api/types";
import type { RegulationChatExchange } from "@/store/useShowcaseStore";

export interface ManagerReplyEntry {
  id: number;
  text: string;
  createdAtLabel: string;
}

export interface MergedConversationItem {
  key: string;
  exchangeId: string;
  questionText: string;
  createdAtLabel: string;
  answerText: string | null;
  sourceQuote: string | null;
  isAnswerFound: boolean;
  needsManagerAttention: boolean;
  managerReplies: ManagerReplyEntry[];
  isLoading: boolean;
  error: string | null;
  isEscalating: boolean;
  isEscalated: boolean;
}

export interface MergedConversationResult {
  items: MergedConversationItem[];
  orphanManagerReplies: ManagerReplyEntry[];
}

interface ServerTurn {
  clientMsgId: number;
  questionText: string;
  createdAtLabel: string;
  needsManagerAttention: boolean;
  aiAnswerText: string | null;
  managerReplies: ManagerReplyEntry[];
}

/** Форматирует время сообщения чата в локальный формат HH:MM. */
export function formatChatTime(raw: string | null | undefined): string {
  if (!raw) return "";
  if (/^\d{2}:\d{2}$/.test(raw.trim())) return raw.trim();
  const normalized =
    raw.includes(" ") && !raw.includes("T") ? raw.replace(" ", "T") : raw;
  const parsed = new Date(normalized);
  if (Number.isNaN(parsed.getTime())) return raw;
  return parsed.toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function findTargetTurnIndexForManagerReply(serverTurns: ServerTurn[]): number {
  for (let i = serverTurns.length - 1; i >= 0; i--) {
    if (
      serverTurns[i].managerReplies.length === 0 &&
      (serverTurns[i].aiAnswerText === null ||
        serverTurns[i].needsManagerAttention)
    ) {
      return i;
    }
  }
  for (let i = serverTurns.length - 1; i >= 0; i--) {
    if (serverTurns[i].managerReplies.length === 0) {
      return i;
    }
  }
  return serverTurns.length - 1;
}

/**
 * Склеивает серверную историю сообщений (`chat_messages`) с локальными обменами
 * (`RegulationChatExchange`), вычисляя статусы ответа и эскалации куратору.
 */
export function buildMergedConversation(
  serverMessages: ShowcaseChatMessageOut[],
  localExchanges: RegulationChatExchange[],
  escalatingExchangeId: string | null,
  escalatedServerIds: Record<string, boolean>
): MergedConversationResult {
  const serverTurns: ServerTurn[] = [];
  const orphanManagerReplies: ManagerReplyEntry[] = [];

  for (const msg of serverMessages) {
    if (msg.sender_role === "client") {
      serverTurns.push({
        clientMsgId: msg.id,
        questionText: msg.message_text,
        createdAtLabel: formatChatTime(msg.created_at),
        needsManagerAttention: Boolean(msg.needs_manager_attention),
        aiAnswerText: null,
        managerReplies: [],
      });
    } else if (msg.sender_role === "ai_assistant") {
      for (let i = serverTurns.length - 1; i >= 0; i--) {
        if (serverTurns[i].aiAnswerText === null) {
          serverTurns[i].aiAnswerText = msg.message_text;
          break;
        }
      }
    } else if (msg.sender_role === "manager") {
      const replyEntry: ManagerReplyEntry = {
        id: msg.id,
        text: msg.message_text,
        createdAtLabel: formatChatTime(msg.created_at),
      };
      if (
        msg.reply_to_message_id !== null &&
        msg.reply_to_message_id !== undefined
      ) {
        const exactIdx = serverTurns.findIndex(
          (turn) => turn.clientMsgId === msg.reply_to_message_id
        );
        if (exactIdx !== -1) {
          serverTurns[exactIdx].managerReplies.push(replyEntry);
        } else {
          orphanManagerReplies.push(replyEntry);
        }
      } else if (serverTurns.length === 0) {
        orphanManagerReplies.push(replyEntry);
      } else {
        // Fallback исключительно для исторических записей до миграции (reply_to_message_id == null)
        const targetIdx = findTargetTurnIndexForManagerReply(serverTurns);
        serverTurns[targetIdx].managerReplies.push(replyEntry);
      }
    }
  }

  const usedLocalIndices = new Set<number>();
  const items: MergedConversationItem[] = [];

  for (const turn of serverTurns) {
    const normServerQ = turn.questionText.trim().toLowerCase();
    let matchedLocal: RegulationChatExchange | undefined;
    for (let i = 0; i < localExchanges.length; i++) {
      if (usedLocalIndices.has(i)) continue;
      const cand = localExchanges[i];
      if (!cand.error && cand.questionText.trim().toLowerCase() === normServerQ) {
        usedLocalIndices.add(i);
        matchedLocal = cand;
        break;
      }
    }

    const hasManagerReply = turn.managerReplies.length > 0;
    const exchangeId = matchedLocal?.id ?? `server-${turn.clientMsgId}`;
    const answerText = matchedLocal?.response?.answer_text ?? turn.aiAnswerText;
    const sourceQuote = matchedLocal?.response?.source_quote ?? null;
    const isAnswerFound = hasManagerReply
      ? true
      : matchedLocal?.response
        ? matchedLocal.response.is_answer_found
        : !turn.needsManagerAttention && Boolean(turn.aiAnswerText);

    const isEscalated = hasManagerReply
      ? false
      : Boolean(
          matchedLocal?.isEscalated ||
            matchedLocal?.response?.escalated_to_telegram ||
            escalatedServerIds[exchangeId] ||
            (turn.needsManagerAttention && turn.aiAnswerText === null)
        );

    items.push({
      key: `srv-${turn.clientMsgId}`,
      exchangeId,
      questionText: turn.questionText,
      createdAtLabel: matchedLocal?.createdAt || turn.createdAtLabel,
      answerText,
      sourceQuote,
      isAnswerFound,
      needsManagerAttention: !hasManagerReply && turn.needsManagerAttention,
      managerReplies: turn.managerReplies,
      isLoading: Boolean(matchedLocal?.isLoading),
      error: matchedLocal?.error ?? null,
      isEscalating:
        Boolean(matchedLocal?.isEscalating) ||
        escalatingExchangeId === exchangeId,
      isEscalated,
    });
  }

  for (let i = 0; i < localExchanges.length; i++) {
    if (usedLocalIndices.has(i)) continue;
    const ex = localExchanges[i];
    items.push({
      key: `loc-${ex.id}`,
      exchangeId: ex.id,
      questionText: ex.questionText,
      createdAtLabel: ex.createdAt,
      answerText: ex.response?.answer_text ?? null,
      sourceQuote: ex.response?.source_quote ?? null,
      isAnswerFound: ex.response ? ex.response.is_answer_found : false,
      needsManagerAttention: false,
      managerReplies: [],
      isLoading: ex.isLoading,
      error: ex.error,
      isEscalating: ex.isEscalating || escalatingExchangeId === ex.id,
      isEscalated: Boolean(ex.isEscalated),
    });
  }

  return { items, orphanManagerReplies };
}
