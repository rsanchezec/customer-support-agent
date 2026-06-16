const env = {
  entraTenantId: import.meta.env.VITE_ENTRA_TENANT_ID ?? "",
  entraClientId: import.meta.env.VITE_ENTRA_CLIENT_ID ?? "",
  entraApiScope: import.meta.env.VITE_ENTRA_API_SCOPE ?? "",
  entraRedirectUri:
    import.meta.env.VITE_ENTRA_REDIRECT_URI ?? "http://localhost:5173",
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000",
} as const;

export type Env = typeof env;

export function getEnv(): Env {
  return env;
}

export function validateEnvVars(): void {
  const missing: string[] = [];
  if (!env.entraTenantId) missing.push("VITE_ENTRA_TENANT_ID");
  if (!env.entraClientId) missing.push("VITE_ENTRA_CLIENT_ID");
  if (!env.entraApiScope) missing.push("VITE_ENTRA_API_SCOPE");
  if (missing.length > 0) {
    throw new Error(
      `Missing required environment variables: ${missing.join(", ")}. ` +
        "Copy .env.example to .env.local and fill in your Entra App registration values."
    );
  }
}

export { env };
