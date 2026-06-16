import type { MessageStatus } from "@/stores/chatStore";

const FILE_CITATION_RE =
  /[\u25a0\u25aa\u25fc\u25fe\u2606\u2605\u21a9\u21b5\u3010\u3011[\]()]*?(?:filcite|filecite)\S*/gi;
const CITATION_GLYPHS_RE = /[\u25a0\u25aa\u25fc\u25fe\u2606\u2605\u21a9\u21b5]/g;

function cleanContent(value: string): string {
  return value
    .replace(FILE_CITATION_RE, "")
    .replace(CITATION_GLYPHS_RE, "")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}

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
  const visibleContent = role === "assistant" ? cleanContent(content) : content;

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
        {visibleContent}
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
