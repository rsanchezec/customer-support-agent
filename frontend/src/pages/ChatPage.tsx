import { useEffect, useState } from "react";
import { useMsal } from "@azure/msal-react";
import { useChatStore } from "@/stores/chatStore";
import { useAuthStore } from "@/stores/authStore";
import { MessageList } from "@/components/MessageList";
import { Composer } from "@/components/Composer";
import { useChatWebSocket } from "@/hooks/useChatWebSocket";
import {
  createConversation,
  getConversation,
  type MessageOut,
} from "@/lib/api";
import { acquireAccessToken } from "@/auth/useAccessToken";

export function ChatPage() {
  const { instance, accounts } = useMsal();
  const clearUser = useAuthStore((s) => s.clearUser);
  const account = accounts[0];

  const [isLoading, setIsLoading] = useState(false);
  const [hydrationError, setHydrationError] = useState(false);

  const threadId = useChatStore((s) => s.threadId);
  const setThreadId = useChatStore((s) => s.setThreadId);
  const clearChat = useChatStore((s) => s.clearChat);
  const addOptimisticUserMessage = useChatStore(
    (s) => s.addOptimisticUserMessage
  );
  const setConversationId = useChatStore((s) => s.setConversationId);

  const { connect, send, close, setMounted } = useChatWebSocket();

  const handleLogout = () => {
    close();
    clearUser();
    instance.logoutRedirect().catch(() => {
      // logoutRedirect navigates away
    });
  };

  const handleNewConversation = async () => {
    try {
      const token = await acquireAccessToken(instance, accounts);
      const result = await createConversation(token);
      clearChat();
      setThreadId(result.id);
      setConversationId(result.id);
      setHydrationError(false);
      close();
      setMounted(true);
      connect(token, result.id);
    } catch {
      // Stay on empty state
    }
  };

  // Patch sendMessage into the store so Composer can call it
  useEffect(() => {
    useChatStore.setState({
      sendMessage: (content: string) => {
        const userMessageId = addOptimisticUserMessage(content);
        useChatStore.getState().completeMessage(userMessageId);
        useChatStore.getState().appendDelta(`stream-${Date.now()}`, "");
        send(content);
      },
    });
  }, [addOptimisticUserMessage, send]);

  // Mount: hydrate or create conversation
  useEffect(() => {
    localStorage.removeItem("chat-thread-id");
    localStorage.removeItem("chat-thread-id-v2");

    setMounted(true);
    let cancelled = false;

    async function init() {
      setIsLoading(true);
      try {
        const token = await acquireAccessToken(instance, accounts);
        let activeConversationId: string | null = threadId;

        if (threadId) {
          // Try to resume
          try {
            const conv = await getConversation(threadId, token);
            activeConversationId = conv.id;
            if (!cancelled) {
              // Load messages from server
              const hydrated = conv.messages.map((m: MessageOut) => ({
                id: m.id,
                role: m.role as "user" | "assistant",
                content: m.content,
                status: "sent" as const,
              }));
              useChatStore.setState({
                messages: hydrated,
                conversationId: conv.id,
                foundryConversationId: conv.foundry_conversation_id ?? null,
              });
              setConversationId(conv.id, conv.foundry_conversation_id ?? null);
              setHydrationError(false);
            }
          } catch {
            if (!cancelled) {
              // 404 — clear and create new
              clearChat();
              setThreadId(null);
              const result = await createConversation(token);
              activeConversationId = result.id;
              setThreadId(result.id);
              setConversationId(result.id);
              setHydrationError(false);
            }
          }
        } else {
          // No thread — create one
          const result = await createConversation(token);
          activeConversationId = result.id;
          if (!cancelled) {
            setThreadId(result.id);
            setConversationId(result.id);
          }
        }

        // Connect WebSocket
        const token2 = await acquireAccessToken(instance, accounts);
        if (!cancelled && activeConversationId) {
          connect(token2, activeConversationId);
        }
      } catch {
        if (!cancelled) {
          setHydrationError(true);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    init();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-4 bg-white border-b border-gray-200 shrink-0">
        <div className="flex items-center gap-3 flex-1">
          <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center">
            <span className="text-white text-sm font-medium">
              {account?.name?.[0] ?? "?"}
            </span>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-900">
              {account?.name ?? "Usuario"}
            </p>
            <p className="text-xs text-gray-500">{account?.username}</p>
          </div>
        </div>
        <div className="flex items-center gap-3 flex-1 justify-center">
          <div
            className="flex items-center gap-2 px-3 py-1.5 bg-emerald-50 border border-emerald-200 rounded-full"
            title="Agente Foundry: customer-support-agent (gpt-4.1-nano)"
          >
            <div className="w-7 h-7 bg-emerald-600 rounded-full flex items-center justify-center">
              <span className="text-white text-base" aria-label="bot">
                🤖
              </span>
            </div>
            <div>
              <p className="text-sm font-medium text-emerald-900">
                Atención al cliente
              </p>
              <p className="text-[10px] text-emerald-700 leading-none">
                Asistente virtual · gpt-4.1-nano
              </p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3 flex-1 justify-end">
          <button
            onClick={handleNewConversation}
            className="px-3 py-1.5 text-sm text-blue-600 border border-blue-600 rounded-lg hover:bg-blue-50 transition-colors"
          >
            Nueva conversación
          </button>
          <button
            onClick={handleLogout}
            className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
          >
            Cerrar sesión
          </button>
        </div>
      </header>

      {/* Loading state */}
      {isLoading && (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-gray-500 text-sm">Conectando…</p>
        </div>
      )}

      {/* Error state */}
      {!isLoading && hydrationError && (
        <div className="flex-1 flex flex-col items-center justify-center gap-4 p-8">
          <p className="text-gray-500 text-sm">
            No se pudo cargar la conversación.
          </p>
          <button
            onClick={handleNewConversation}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 transition-colors"
          >
            Nueva conversación
          </button>
        </div>
      )}

      {/* Chat area */}
      {!isLoading && !hydrationError && (
        <>
          <MessageList />
          <Composer />
        </>
      )}
    </div>
  );
}
