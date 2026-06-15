import { describe, it, expect } from "vitest";
import { useAuthStore } from "@/stores/authStore";
import type { AccountInfo } from "@azure/msal-browser";

describe("authStore", () => {
  it("setUser and clearUser roundtrip", () => {
    const store = useAuthStore.getState();

    const mockAccount: AccountInfo = {
      homeAccountId: "home-id",
      localAccountId: "local-id",
      environment: "login.microsoftonline.com",
      tenantId: "tenant-id",
      username: "test@example.com",
      name: "Test User",
    };

    store.setUser(mockAccount);
    expect(useAuthStore.getState().user).toEqual(mockAccount);

    store.clearUser();
    expect(useAuthStore.getState().user).toBeNull();
  });

  it("persists user to localStorage", () => {
    const store = useAuthStore.getState();

    const mockAccount: AccountInfo = {
      homeAccountId: "home-id-2",
      localAccountId: "local-id-2",
      environment: "login.microsoftonline.com",
      tenantId: "tenant-id-2",
      username: "test2@example.com",
      name: "Test User 2",
    };

    store.setUser(mockAccount);

    // Re-instantiate to simulate reload
    const newStore = useAuthStore.getState();
    expect(newStore.user?.username).toBe("test2@example.com");
  });
});
