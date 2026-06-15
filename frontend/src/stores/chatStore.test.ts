import { describe, it, expect, beforeEach } from "vitest";
import { useChatStore } from "@/stores/chatStore";

describe("chatStore", () => {
  beforeEach(() => {
    // Reset store state
    useChatStore.setState({
      threadId: null,
      messages: [],
      wsStatus: "idle",
      conversationId: null,
      foundryConversationId: null,
    });
  });

  describe("addOptimisticUserMessage", () => {
    it("adds a user message with status sending", () => {
      const id = useChatStore.getState().addOptimisticUserMessage("Hola");
      const msgs = useChatStore.getState().messages;
      expect(msgs).toHaveLength(1);
      expect(msgs[0].id).toBe(id);
      expect(msgs[0].role).toBe("user");
      expect(msgs[0].content).toBe("Hola");
      expect(msgs[0].status).toBe("sending");
    });

    it("returns a non-empty string id", () => {
      const id = useChatStore.getState().addOptimisticUserMessage("Test");
      expect(typeof id).toBe("string");
      expect(id.length).toBeGreaterThan(0);
    });
  });

  describe("appendDelta", () => {
    it("accumulates text on the streaming message", () => {
      const state = useChatStore.getState();
      // Simulate a streaming assistant message
      state.messages = [
        { id: "stream-1", role: "assistant", content: "Hola", status: "streaming" },
      ];

      useChatStore.getState().appendDelta("stream-1", " mundo");
      const msgs = useChatStore.getState().messages;
      expect(msgs[0].content).toBe("Hola mundo");
      expect(msgs[0].status).toBe("streaming");
    });

    it("creates a new streaming message if none exists", () => {
      const state = useChatStore.getState();
      state.messages = [];

      useChatStore.getState().appendDelta("tmp-1", "First delta");
      const msgs = useChatStore.getState().messages;
      expect(msgs).toHaveLength(1);
      expect(msgs[0].content).toBe("First delta");
      expect(msgs[0].status).toBe("streaming");
    });
  });

  describe("completeMessage", () => {
    it("marks the message as sent", () => {
      const state = useChatStore.getState();
      state.messages = [
        { id: "msg-1", role: "assistant", content: "Hello", status: "streaming" },
      ];

      useChatStore.getState().completeMessage("msg-1", "foundry-abc");
      const msgs = useChatStore.getState().messages;
      expect(msgs[0].status).toBe("sent");
    });
  });

  describe("failMessage", () => {
    it("marks the message as failed", () => {
      const state = useChatStore.getState();
      state.messages = [
        { id: "msg-1", role: "assistant", content: "Hello", status: "streaming" },
      ];

      useChatStore.getState().failMessage("msg-1");
      const msgs = useChatStore.getState().messages;
      expect(msgs[0].status).toBe("failed");
    });
  });

  describe("clearChat", () => {
    it("clears messages and conversation ids", () => {
      const state = useChatStore.getState();
      state.messages = [
        { id: "msg-1", role: "user", content: "Hi", status: "sent" },
      ];
      state.conversationId = "conv-1";
      state.foundryConversationId = "foundry-1";

      useChatStore.getState().clearChat();
      expect(useChatStore.getState().messages).toHaveLength(0);
      expect(useChatStore.getState().conversationId).toBeNull();
      expect(useChatStore.getState().foundryConversationId).toBeNull();
    });
  });

  describe("setConversationId", () => {
    it("sets both conversation and foundry ids", () => {
      useChatStore.getState().setConversationId("conv-1", "foundry-1");
      const state = useChatStore.getState();
      expect(state.conversationId).toBe("conv-1");
      expect(state.foundryConversationId).toBe("foundry-1");
    });
  });
});
