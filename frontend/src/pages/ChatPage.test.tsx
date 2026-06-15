import { describe, it, expect, vi, beforeEach } from "vitest";
import { useChatStore } from "@/stores/chatStore";
import { useAuthStore } from "@/stores/authStore";
import * as useAccessTokenModule from "@/auth/useAccessToken";
import type { AccountInfo } from "@azure/msal-browser";

const mockAccount: AccountInfo = {
  homeAccountId: "home-id",
  localAccountId: "local-id",
  environment: "login.microsoftonline.com",
  tenantId: "tenant-id",
  username: "test@example.com",
  name: "Test User",
};

describe("ChatPage (unit via store)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({ user: mockAccount });
    useChatStore.setState({
      threadId: null,
      messages: [],
      wsStatus: "idle",
      conversationId: null,
    });
    vi.spyOn(useAccessTokenModule, "acquireAccessToken").mockResolvedValue(
      "fake.access.token"
    );
  });

  it("initial store state has no messages", () => {
    expect(useChatStore.getState().messages).toHaveLength(0);
  });

  it("clearChat resets messages and conversation ids", () => {
    useChatStore.setState({
      messages: [{ id: "1", role: "user", content: "Hi", status: "sent" }],
      conversationId: "conv-1",
      foundryConversationId: "f1",
    });

    useChatStore.getState().clearChat();

    expect(useChatStore.getState().messages).toHaveLength(0);
    expect(useChatStore.getState().conversationId).toBeNull();
    expect(useChatStore.getState().foundryConversationId).toBeNull();
  });

  it("user account is set in auth store", () => {
    expect(useAuthStore.getState().user?.username).toBe("test@example.com");
  });

  it("wsStatus starts as idle", () => {
    expect(useChatStore.getState().wsStatus).toBe("idle");
  });
});
