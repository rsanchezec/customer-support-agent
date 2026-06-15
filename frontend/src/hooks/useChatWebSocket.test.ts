import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { useChatStore } from "@/stores/chatStore";

// ---------------------------------------------------------------------------
// Mock WebSocket factory
// ---------------------------------------------------------------------------

const createMockWs = () => {
  let _readyState = 0;
  const handlers = {
    onopen: null as ((e: Event) => void) | null,
    onmessage: null as ((e: MessageEvent) => void) | null,
    onclose: null as ((e: CloseEvent) => void) | null,
  };
  return {
    get readyState() { return _readyState; },
    close: vi.fn(),
    send: vi.fn(),
    get onopen() { return handlers.onopen; },
    set onopen(v) { handlers.onopen = v; },
    get onmessage() { return handlers.onmessage; },
    set onmessage(v) { handlers.onmessage = v; },
    get onclose() { return handlers.onclose; },
    set onclose(v) { handlers.onclose = v; },
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(() => true),
    _triggerOpen() { _readyState = 1; handlers.onopen?.(new Event("open")); },
    _triggerMessage(data: string) { handlers.onmessage?.(new MessageEvent("message", { data })); },
    _triggerClose(code: number, reason?: string) { _readyState = 3; handlers.onclose?.(new CloseEvent("close", { code, reason })); },
  };
};

type MockWs = ReturnType<typeof createMockWs>;

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useChatWebSocket", () => {
  beforeEach(() => {
    useChatStore.setState({ wsStatus: "idle", messages: [], conversationId: null });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("creates WebSocket with correct URL and subprotocol", async () => {
    const mockWs = createMockWs();
    vi.stubGlobal("WebSocket", vi.fn(() => mockWs) as unknown as typeof WebSocket);

    const { useChatWebSocket } = await import("@/hooks/useChatWebSocket");
    const { result } = renderHook(() => useChatWebSocket());
    result.current.setMounted(true);
    result.current.connect("fake.token");

    expect(vi.mocked(WebSocket)).toHaveBeenCalledOnce();
    const [url, protocol] = vi.mocked(WebSocket).mock.calls[0]!;
    expect(url).toContain("/ws/chat");
    expect(protocol).toBe("bearer.jwt.fake.token");
  });

  it("sets connecting status when connect is called", async () => {
    const mockWs = createMockWs();
    vi.stubGlobal("WebSocket", vi.fn(() => mockWs) as unknown as typeof WebSocket);

    const { useChatWebSocket } = await import("@/hooks/useChatWebSocket");
    const { result } = renderHook(() => useChatWebSocket());
    result.current.setMounted(true);
    result.current.connect("fake.token");

    expect(useChatStore.getState().wsStatus).toBe("connecting");
  });

  it("sets open status when WebSocket fires open event", async () => {
    const mockWs = createMockWs();
    vi.stubGlobal("WebSocket", vi.fn(() => mockWs) as unknown as typeof WebSocket);

    const { useChatWebSocket } = await import("@/hooks/useChatWebSocket");
    const { result } = renderHook(() => useChatWebSocket());
    result.current.setMounted(true);
    result.current.connect("fake.token");
    mockWs._triggerOpen();

    expect(useChatStore.getState().wsStatus).toBe("open");
  });

  it("queues messages when WebSocket is not open", async () => {
    const mockWs = createMockWs();
    vi.stubGlobal("WebSocket", vi.fn(() => mockWs) as unknown as typeof WebSocket);

    const { useChatWebSocket } = await import("@/hooks/useChatWebSocket");
    const { result } = renderHook(() => useChatWebSocket());
    result.current.setMounted(true);
    result.current.connect("fake.token");
    result.current.send("Hello");

    expect(mockWs.send).not.toHaveBeenCalled();
  });

  it("delivers messages when WebSocket is open", async () => {
    const mockWs = createMockWs();
    vi.stubGlobal("WebSocket", vi.fn(() => mockWs) as unknown as typeof WebSocket);

    const { useChatWebSocket } = await import("@/hooks/useChatWebSocket");
    const { result } = renderHook(() => useChatWebSocket());
    result.current.setMounted(true);
    result.current.connect("fake.token");
    mockWs._triggerOpen();
    result.current.send("Hello");

    expect(mockWs.send).toHaveBeenCalledWith(
      JSON.stringify({ content: "Hello", metadata: null })
    );
  });

  it("appends delta to the last streaming assistant message", async () => {
    const mockWs = createMockWs();
    vi.stubGlobal("WebSocket", vi.fn(() => mockWs) as unknown as typeof WebSocket);

    const { useChatWebSocket } = await import("@/hooks/useChatWebSocket");
    const { result } = renderHook(() => useChatWebSocket());
    result.current.setMounted(true);
    result.current.connect("fake.token");
    mockWs._triggerOpen();

    useChatStore.setState({
      messages: [{ id: "s1", role: "assistant", content: "Hola", status: "streaming" }],
    });

    mockWs._triggerMessage(JSON.stringify({ type: "delta", text: " mundo" }));

    const msgs = useChatStore.getState().messages;
    expect(msgs[0].content).toBe("Hola mundo");
  });

  it("sets conversation id on done frame", async () => {
    const mockWs = createMockWs();
    vi.stubGlobal("WebSocket", vi.fn(() => mockWs) as unknown as typeof WebSocket);

    const { useChatWebSocket } = await import("@/hooks/useChatWebSocket");
    const { result } = renderHook(() => useChatWebSocket());
    result.current.setMounted(true);
    result.current.connect("fake.token");
    mockWs._triggerOpen();

    useChatStore.setState({
      messages: [{ id: "s1", role: "assistant", content: "Hola", status: "streaming" }],
    });

    mockWs._triggerMessage(JSON.stringify({
      type: "done",
      conversation_id: "conv-123",
      foundry_conversation_id: "foundry-456",
    }));

    expect(useChatStore.getState().conversationId).toBe("conv-123");
    expect(useChatStore.getState().foundryConversationId).toBe("foundry-456");
  });

  it("marks message as failed on error frame", async () => {
    const mockWs = createMockWs();
    vi.stubGlobal("WebSocket", vi.fn(() => mockWs) as unknown as typeof WebSocket);

    const { useChatWebSocket } = await import("@/hooks/useChatWebSocket");
    const { result } = renderHook(() => useChatWebSocket());
    result.current.setMounted(true);
    result.current.connect("fake.token");
    mockWs._triggerOpen();

    useChatStore.setState({
      messages: [{ id: "s1", role: "assistant", content: "Hola", status: "streaming" }],
    });

    mockWs._triggerMessage(JSON.stringify({ type: "error", code: "internal", message: "Oops" }));

    const msgs = useChatStore.getState().messages;
    expect(msgs.find((m) => m.status === "failed")).toBeDefined();
  });

  it("sets failed status after 1008 close (no reconnect)", async () => {
    const mockWs = createMockWs();
    vi.stubGlobal("WebSocket", vi.fn(() => mockWs) as unknown as typeof WebSocket);

    const { useChatWebSocket } = await import("@/hooks/useChatWebSocket");
    const { result } = renderHook(() => useChatWebSocket());
    result.current.setMounted(true);
    result.current.connect("fake.token");
    mockWs._triggerOpen();
    mockWs._triggerClose(1008, "auth");

    expect(useChatStore.getState().wsStatus).toBe("failed");
  });

  it("schedules reconnect after 1006 with backoff", async () => {
    vi.useFakeTimers();

    const mockWs = createMockWs();
    vi.stubGlobal("WebSocket", vi.fn(() => mockWs) as unknown as typeof WebSocket);

    const { useChatWebSocket } = await import("@/hooks/useChatWebSocket");
    const { result } = renderHook(() => useChatWebSocket());
    result.current.setMounted(true);
    result.current.connect("fake.token");
    mockWs._triggerOpen();
    mockWs._triggerClose(1006, "transient");

    expect(useChatStore.getState().wsStatus).toBe("disconnected");

    vi.advanceTimersByTime(1_000);

    expect(vi.mocked(WebSocket)).toHaveBeenCalledTimes(2);

    vi.useRealTimers();
  });
});
