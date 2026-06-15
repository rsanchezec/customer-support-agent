import { useRef, useState, type FormEvent } from "react";
import { useChatStore } from "@/stores/chatStore";

export function Composer() {
  const [value, setValue] = useState("");
  const wsStatus = useChatStore((s) => s.wsStatus);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const canSend =
    wsStatus === "open" && value.trim().length > 0;

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!canSend) return;
    sendMessage(value.trim());
    setValue("");
    // Reset height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value);
    // Auto-resize up to ~4 lines
    const ta = e.target;
    ta.style.height = "auto";
    const lineHeight = 24;
    const maxHeight = lineHeight * 4;
    ta.style.height = `${Math.min(ta.scrollHeight, maxHeight)}px`;
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="border-t border-gray-200 bg-white px-4 py-3"
    >
      <div className="flex items-end gap-3">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder="Escribe tu mensaje…"
          rows={1}
          maxLength={4000}
          disabled={wsStatus !== "open"}
          className="flex-1 resize-none rounded-xl border border-gray-300 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
          style={{ minHeight: "48px", maxHeight: "96px" }}
        />
        <button
          type="submit"
          disabled={!canSend}
          className="shrink-0 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          Enviar
        </button>
      </div>
    </form>
  );
}
