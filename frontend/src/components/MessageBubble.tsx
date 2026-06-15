import type { MessageStatus } from "@/stores/chatStore";

interface MessageBubbleProps {
  role: "user" | "assistant";
  content: string;
  status: MessageStatus;
  onRetry?: () => void;
}

export function MessageBubble({
  role,
  content,
  status,
  onRetry,
}: MessageBubbleProps) {
  const isUser = role === "user";

  return (
    <div
      className={`flex ${isUser ? "justify-end" : "justify-start"}`}
    >
      <div
        className={`max-w-[75%] px-4 py-3 rounded-2xl text-sm leading-relaxed ${
          isUser
            ? "bg-blue-600 text-white rounded-br-md"
            : "bg-white border border-gray-200 text-gray-800 rounded-bl-md"
        }`}
      >
        {content}
        {status === "streaming" && (
          <span className="inline-block w-2 h-2 bg-gray-400 rounded-full ml-2 animate-pulse" />
        )}
        {status === "failed" && onRetry && (
          <button
            onClick={onRetry}
            className="ml-3 text-xs underline hover:no-underline"
          >
            Reintentar
          </button>
        )}
        {status === "sending" && (
          <span className="inline-block ml-2 text-xs opacity-70">Enviando…</span>
        )}
      </div>
    </div>
  );
}
