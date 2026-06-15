import { useCallback, useRef } from "react";
import { useChatStore } from "@/stores/chatStore";

// ---------------------------------------------------------------------------
// WebSocket factory type (injectable for testing)
// ---------------------------------------------------------------------------

export type WebSocketFactory = (
  _url: string,
  _protocol?: string | string[]
) => WebSocket;

// ---------------------------------------------------------------------------
// Backoff constants
// ---------------------------------------------------------------------------

const INITIAL_BACKOFF_MS = 1_000;
const MAX_BACKOFF_MS = 30_000;
const MAX_RETRIES = 5;

function getBackoffMs(attempt: number): number {
  return Math.min(INITIAL_BACKOFF_MS * 2 ** attempt, MAX_BACKOFF_MS);
}

// ---------------------------------------------------------------------------
// WS URL builder
// ---------------------------------------------------------------------------

function buildWsUrl(apiBase: string): string {
  // Convert http(s):// to ws(s)://
  const base = apiBase.replace(/^http/, "ws");
  return `${base}/ws/chat`;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useChatWebSocket(
  wsFactory: WebSocketFactory = (
    _url: string,
    _protocol?: string | string[]
  ) => new WebSocket(_url, _protocol)
) {
  const wsRef = useRef<WebSocket | null>(null);
  const retryCountRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const messageQueueRef = useRef<string[]>([]);
  const isMountedRef = useRef(false);
  // Store factory in a ref so async callbacks don't need it in deps
  const wsFactoryRef = useRef(wsFactory);
  wsFactoryRef.current = wsFactory;

  const clearRetry = useCallback(() => {
    if (retryTimerRef.current !== null) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
  }, []);

  const updateStore = useCallback(
    (patch: Partial<ReturnType<typeof useChatStore.getState>>) => {
      useChatStore.setState(patch);
    },
    []
  );

  const connect = useCallback(
    async (accessToken: string) => {
      if (!isMountedRef.current) return;

      const apiBase =
        import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
      const url = buildWsUrl(apiBase);

      updateStore({ wsStatus: "connecting" });

      const subprotocol = `bearer.jwt.${accessToken}`;
      const ws = wsFactoryRef.current(url, subprotocol);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!isMountedRef.current) return;
        retryCountRef.current = 0;
        updateStore({ wsStatus: "open" });

        // Flush queued messages
        while (messageQueueRef.current.length > 0) {
          const msg = messageQueueRef.current.shift();
          if (msg && ws.readyState === WebSocket.OPEN) {
            ws.send(msg);
          }
        }
      };

      ws.onmessage = (event) => {
        if (!isMountedRef.current) return;
        try {
          const frame = JSON.parse(event.data as string) as {
            type: string;
            text?: string;
            conversation_id?: string;
            foundry_conversation_id?: string;
            code?: string;
            message?: string;
          };

          switch (frame.type) {
            case "delta": {
              // Find the last streaming/optimistic assistant message
              const state = useChatStore.getState();
              const msgs = state.messages;
              const lastAsst = [...msgs].reverse().find(
                (m) => m.role === "assistant" && m.status === "streaming"
              );
              if (lastAsst) {
                useChatStore.getState().appendDelta(lastAsst.id, frame.text ?? "");
              } else {
                // First delta with no optimistic message — create one
                const tmpId = `stream-${Date.now()}`;
                useChatStore.getState().appendDelta(tmpId, frame.text ?? "");
              }
              break;
            }
            case "done": {
              const state = useChatStore.getState();
              const msgs = state.messages;
              const lastAsst = [...msgs].reverse().find(
                (m) => m.role === "assistant" && m.status === "streaming"
              );
              if (lastAsst) {
                useChatStore.getState().completeMessage(
                  lastAsst.id,
                  frame.foundry_conversation_id
                );
              }
              if (frame.conversation_id) {
                useChatStore.getState().setConversationId(
                  frame.conversation_id,
                  frame.foundry_conversation_id
                );
                useChatStore.getState().setThreadId(frame.conversation_id);
              }
              break;
            }
            case "error": {
              const state = useChatStore.getState();
              const msgs = state.messages;
              const lastAsst = [...msgs].reverse().find(
                (m) => m.role === "assistant" && m.status === "streaming"
              );
              if (lastAsst) {
                useChatStore.getState().failMessage(lastAsst.id);
              }
              break;
            }
          }
        } catch {
          // Ignore parse errors
        }
      };

      ws.onclose = (event) => {
        if (!isMountedRef.current) return;
        wsRef.current = null;

        if (event.code === 1008) {
          // Auth error — do not reconnect
          updateStore({ wsStatus: "failed" });
          return;
        }

        if (event.code === 1011) {
          // Server error — do not reconnect
          updateStore({ wsStatus: "failed" });
          return;
        }

        // Transient close (1006 or abnormal) — reconnect with backoff
        if (retryCountRef.current < MAX_RETRIES) {
          const backoff = getBackoffMs(retryCountRef.current);
          retryCountRef.current += 1;
          updateStore({ wsStatus: "disconnected" });
          retryTimerRef.current = setTimeout(() => {
            if (isMountedRef.current) {
              connect(accessToken).catch(() => {
                // connect handles its own state
              });
            }
          }, backoff);
        } else {
          updateStore({ wsStatus: "failed" });
        }
      };

      ws.onerror = () => {
        // onclose will fire after onerror — let onclose handle reconnect logic
      };
    },
    [updateStore]
  );

  const send = useCallback((content: string) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      // Queue the message
      messageQueueRef.current.push(
        JSON.stringify({ content, metadata: null })
      );
      return;
    }
    ws.send(JSON.stringify({ content, metadata: null }));
  }, []);

  const close = useCallback(() => {
    isMountedRef.current = false;
    clearRetry();
    if (wsRef.current) {
      wsRef.current.close(1000, "client disconnect");
      wsRef.current = null;
    }
    updateStore({ wsStatus: "idle" });
  }, [clearRetry, updateStore]);

  // Track mount/unmount
  const setMounted = useCallback((v: boolean) => {
    isMountedRef.current = v;
    if (!v) {
      clearRetry();
    }
  }, [clearRetry]);

  return { connect, send, close, setMounted };
}
