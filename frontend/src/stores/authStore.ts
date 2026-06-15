import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { AccountInfo } from "@azure/msal-browser";

interface AuthState {
  user: AccountInfo | null;
  setUser: (_user: AccountInfo | null) => void;
  clearUser: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      setUser: (newUser: AccountInfo | null) => set({ user: newUser }),
      clearUser: () => set({ user: null }),
    }),
    {
      name: "auth-user",
    }
  )
);
