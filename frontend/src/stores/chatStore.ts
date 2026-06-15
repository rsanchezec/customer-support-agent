import { create } from "zustand";
import { persist } from "zustand/middleware";

interface ChatState {
  threadId: string | null;
  setThreadId: (_id: string | null) => void;
  clearThreadId: () => void;
}

export const useChatStore = create<ChatState>()(
  persist(
    (set) => ({
      threadId: null,
      setThreadId: (newId: string | null) => set({ threadId: newId }),
      clearThreadId: () => set({ threadId: null }),
    }),
    {
      name: "chat-thread-id",
    }
  )
);
