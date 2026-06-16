import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { useChatStore } from "@/stores/chatStore";

// ---------------------------------------------------------------------------
// Shared mock WebSocket — created via vi.hoisted BEFORE the module loads.
// vi.stubGlobal runs BEFORE the import, so the module-level default
// wsFactory captures the stubbed WebSocket. All tests share the same mock.
// ---------------------------------------------------------------------------

const mockWs = vi.hoisted(() => {
  let _readyState = 0;
  const handlers = {
    onopen: null as ((_e: Event) => void) | null,
    onmessage: null as ((_e: MessageEvent) => void) | null,
    onclose: null as ((_e: CloseEvent) => void) | null,
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
    _reset() { _readyState = 0; },
  };
});

// Constructor function that returns mockWs when called with `new`.
// vi.fn() wraps it as a spy so WebSocket calls are tracked.
// Must include .OPEN = 1 since the hook checks ws.readyState !== WebSocket.OPEN.
const MockWebSocketConstructor = vi.fn((..._args: ConstructorParameters<typeof WebSocket>) => {
  // Capture URL for potential inspection; return the shared mock instance
  return mockWs;
});
(MockWebSocketConstructor as any).OPEN = 1;

vi.stubGlobal("WebSocket", MockWebSocketConstructor as unknown as typeof WebSocket);

import { useChatWebSocket } from "@/hooks/useChatWebSocket";

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useChatWebSocket", () => {
  beforeEach(() => {
    useChatStore.setState({ wsStatus: "idle", messages: [], conversationId: null });
    // Reset shared mock state between tests to prevent leakage.
    mockWs.send.mockClear();
    mockWs.close.mockClear();
    mockWs._reset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("creates WebSocket with correct URL and subprotocol", () => {
    const { result } = renderHook(() => useChatWebSocket());
    result.current.setMounted(true);
    result.current.connect("fake.token", "conv-123");

    expect(vi.mocked(WebSocket)).toHaveBeenCalledOnce();
    const [url, protocol] = vi.mocked(WebSocket).mock.calls[0]!;
    expect(url).toContain("/ws/chat/conv-123");
    expect(protocol).toEqual(["bearer.jwt", "jwt.fake.token"]);
  });

  it("sets connecting status when connect is called", () => {
    const { result } = renderHook(() => useChatWebSocket());
    result.current.setMounted(true);
    result.current.connect("fake.token", "conv-123");

    expect(useChatStore.getState().wsStatus).toBe("connecting");
  });

  it("sets open status when WebSocket fires open event", () => {
    const { result } = renderHook(() => useChatWebSocket());
    result.current.setMounted(true);
    result.current.connect("fake.token", "conv-123");
    mockWs._triggerOpen();

    expect(useChatStore.getState().wsStatus).toBe("open");
  });

  it("queues messages when WebSocket is not open", () => {
    const { result } = renderHook(() => useChatWebSocket());
    result.current.setMounted(true);
    result.current.connect("fake.token", "conv-123");
    result.current.send("Hello");

    expect(mockWs.send).not.toHaveBeenCalled();
  });

  it("delivers messages when WebSocket is open", () => {
    const { result } = renderHook(() => useChatWebSocket());
    result.current.setMounted(true);
    result.current.connect("fake.token", "conv-123");
    mockWs._triggerOpen();

    result.current.send("Hello");

    expect(mockWs.send).toHaveBeenCalledWith(
      JSON.stringify({ content: "Hello", metadata: null })
    );
  });

  it("appends delta to the last streaming assistant message", () => {
    const { result } = renderHook(() => useChatWebSocket());
    result.current.setMounted(true);
    result.current.connect("fake.token", "conv-123");
    mockWs._triggerOpen();

    useChatStore.setState({
      messages: [{ id: "s1", role: "assistant", content: "Hola", status: "streaming" }],
    });

    mockWs._triggerMessage(JSON.stringify({ type: "delta", text: " mundo" }));

    const msgs = useChatStore.getState().messages;
    expect(msgs[0].content).toBe("Hola mundo");
  });

  it("sets conversation id on done frame", () => {
    const { result } = renderHook(() => useChatWebSocket());
    result.current.setMounted(true);
    result.current.connect("fake.token", "conv-123");
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

  it("marks message as failed on error frame", () => {
    const { result } = renderHook(() => useChatWebSocket());
    result.current.setMounted(true);
    result.current.connect("fake.token", "conv-123");
    mockWs._triggerOpen();

    useChatStore.setState({
      messages: [{ id: "s1", role: "assistant", content: "Hola", status: "streaming" }],
    });

    mockWs._triggerMessage(JSON.stringify({ type: "error", code: "internal", message: "Oops" }));

    const msgs = useChatStore.getState().messages;
    expect(msgs.find((m) => m.status === "failed")).toBeDefined();
  });

  it("sets failed status after 1008 close (no reconnect)", () => {
    const { result } = renderHook(() => useChatWebSocket());
    result.current.setMounted(true);
    result.current.connect("fake.token", "conv-123");
    mockWs._triggerOpen();
    mockWs._triggerClose(1008, "auth");

    expect(useChatStore.getState().wsStatus).toBe("failed");
  });

  it("schedules reconnect after 1006 with backoff", () => {
    vi.useFakeTimers();

    const { result } = renderHook(() => useChatWebSocket());
    result.current.setMounted(true);
    result.current.connect("fake.token", "conv-123");
    mockWs._triggerOpen();
    mockWs._triggerClose(1006, "transient");

    expect(useChatStore.getState().wsStatus).toBe("disconnected");

    vi.advanceTimersByTime(1_000);

    // WebSocket constructor is called twice: initial + reconnect.
    expect(vi.mocked(WebSocket)).toHaveBeenCalledTimes(2);

    vi.useRealTimers();
  });
});
