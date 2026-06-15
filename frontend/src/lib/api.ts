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
