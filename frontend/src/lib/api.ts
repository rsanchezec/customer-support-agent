// ---------------------------------------------------------------------------
// Core fetch helper
// ---------------------------------------------------------------------------

interface ApiFetchOptions extends RequestInit {
  accessToken?: string;
}

export class ApiError extends Error {
  public readonly code: string;
  public readonly status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

export async function apiFetch<T = unknown>(
  path: string,
  options: ApiFetchOptions = {}
): Promise<T> {
  const { accessToken, headers, ...rest } = options;

  const fullUrl = path.startsWith("http")
    ? path
    : `${import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"}${path}`;

  const requestHeaders: Record<string, string> = {
    ...(headers as Record<string, string>),
  };

  if (accessToken) {
    requestHeaders["Authorization"] = `Bearer ${accessToken}`;
  }

  if (
    accessToken &&
    !Object.keys(requestHeaders).find(
      (k) => k.toLowerCase() === "content-type"
    )
  ) {
    requestHeaders["Content-Type"] = "application/json";
  }

  const response = await fetch(fullUrl, {
    ...rest,
    headers: requestHeaders,
  });

  if (!response.ok) {
    let message = response.statusText;
    let code = "unknown_error";
    try {
      const body = await response.json();
      message = body.message ?? message;
      code = body.code ?? code;
    } catch {
      // ignore parse errors
    }
    throw new ApiError(code, message, response.status);
  }

  return response.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Conversation API helpers
// ---------------------------------------------------------------------------

export interface ConversationOut {
  id: string;
  title: string | null;
  created_at: string;
}

export interface MessageOut {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface ConversationDetailOut {
  id: string;
  title: string | null;
  foundry_conversation_id: string | null;
  messages: MessageOut[];
  created_at: string;
}

export async function listConversations(
  accessToken: string
): Promise<ConversationOut[]> {
  return apiFetch<ConversationOut[]>("/conversations", { accessToken });
}

export async function getConversation(
  id: string,
  accessToken: string
): Promise<ConversationDetailOut> {
  return apiFetch<ConversationDetailOut>(`/conversations/${id}`, {
    accessToken,
  });
}

export async function createConversation(
  accessToken: string,
  title?: string
): Promise<{ id: string }> {
  return apiFetch<{ id: string }>("/conversations", {
    accessToken,
    method: "POST",
    body: title ? JSON.stringify({ title }) : JSON.stringify({}),
  });
}
