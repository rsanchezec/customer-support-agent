import { create } from "zustand";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type MessageRole = "user" | "assistant";

export type MessageStatus = "sending" | "sent" | "failed" | "streaming";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  status: MessageStatus;
  onRetry?: () => void;
}

export type WsStatus =
  | "idle"
  | "connecting"
  | "open"
  | "disconnected"
  | "failed";

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

interface ChatState {
  // Persisted
  threadId: string | null;
  setThreadId: (_id: string | null) => void;
  clearThreadId: () => void;

  // Transient
  messages: ChatMessage[];
  wsStatus: WsStatus;
  conversationId: string | null;
  foundryConversationId: string | null;

  // Actions
  setWsStatus: (_status: WsStatus) => void;
  setConversationId: (_id: string | null, _foundryId?: string | null) => void;
  addOptimisticUserMessage: (_content: string) => string;
  appendDelta: (_messageId: string, _delta: string) => void;
  replaceMessageContent: (_messageId: string, _content: string) => void;
  completeMessage: (_messageId: string, _foundryId?: string) => void;
  failMessage: (_messageId: string) => void;
  sendMessage: (_content: string) => void;
  clearChat: () => void;
}

let messageCounter = 0;

export const useChatStore = create<ChatState>()(
    (set, _get) => ({
      threadId: null,
      setThreadId: (id) => set({ threadId: id }),
      clearThreadId: () => set({ threadId: null }),

      // Transient
      messages: [],
      wsStatus: "idle",
      conversationId: null,
      foundryConversationId: null,

      // Actions
      setWsStatus: (status) => set({ wsStatus: status }),

      setConversationId: (id, foundryId = null) =>
        set({ conversationId: id, foundryConversationId: foundryId }),

      addOptimisticUserMessage: (content) => {
        const id = `opt-${++messageCounter}`;
        set((s) => ({
          messages: [
            ...s.messages,
            { id, role: "user", content, status: "sending" },
          ],
        }));
        return id;
      },

      appendDelta: (messageId, delta) => {
        set((s) => {
          const msgs = [...s.messages];
          const idx = msgs.findIndex((m) => m.id === messageId);
          if (idx === -1) {
            // No optimistic message yet — create one
            msgs.push({ id: messageId, role: "assistant", content: delta, status: "streaming" });
          } else {
            msgs[idx] = {
              ...msgs[idx],
              content: msgs[idx].content + delta,
              status: "streaming",
            };
          }
          return { messages: msgs };
        });
      },

      replaceMessageContent: (messageId, content) => {
        set((s) => ({
          messages: s.messages.map((m) =>
            m.id === messageId ? { ...m, content } : m
          ),
        }));
      },

      completeMessage: (messageId, foundryId) => {
        set((s) => ({
          messages: s.messages.map((m) =>
            m.id === messageId
              ? { ...m, status: "sent" as MessageStatus }
              : m
          ),
          foundryConversationId:
            foundryId && s.foundryConversationId === null
              ? foundryId
              : s.foundryConversationId,
        }));
      },

      failMessage: (messageId) => {
        set((s) => ({
          messages: s.messages.map((m) =>
            m.id === messageId
              ? { ...m, status: "failed" as MessageStatus }
              : m
          ),
        }));
      },

      sendMessage: (_content) => {
        // Handled by the WebSocket hook — no-op here
      },

      clearChat: () =>
        set({
          messages: [],
          threadId: null,
          conversationId: null,
          foundryConversationId: null,
        }),
    })
);
