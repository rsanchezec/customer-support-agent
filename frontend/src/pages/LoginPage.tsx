import { useMsal } from "@azure/msal-react";
import { useEffect, useState } from "react";
import { loginRequest } from "@/lib/msalConfig";
import { validateEnvVars } from "@/lib/env";

export function LoginPage() {
  const { instance, accounts } = useMsal();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (accounts.length > 0) {
      // Already logged in, redirect
      window.location.href = "/chat";
    }
  }, [accounts]);

  const handleLogin = () => {
    try {
      validateEnvVars();
      instance.loginRedirect(loginRequest);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "No pudimos iniciar sesión. Probá de nuevo."
      );
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-50">
      <div className="w-full max-w-md p-8 bg-white rounded-xl shadow-md">
        <h1 className="text-2xl font-semibold text-center text-gray-900 mb-2">
          Chat de soporte
        </h1>
        <p className="text-center text-gray-500 mb-8">
          Iniciá sesión para comenzar a chatear con el agente de soporte.
        </p>
        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            {error}
          </div>
        )}
        <button
          onClick={handleLogin}
          className="w-full flex items-center justify-center gap-3 px-4 py-3 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors"
        >
          <svg
            className="w-5 h-5"
            viewBox="0 0 21 21"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              d="M10.5 2C5.25 2 1 6.25 1 11.5c0 4.1 2.6 7.6 6.2 9.1-.1-.8-.1-2.1.1-3 .2-.8 1.1-5.3 1.1-5.3s-.3-.6-.3-1.4c0-1.3.8-2.3 1.8-2.3.8 0 1.2.6 1.2 1.4 0 .8-.5 2.1-.8 3.3-.2.9.5 1.7 1.4 1.7 1.7 0 2.8-2.2 2.8-4.8 0-2-1.6-3.5-4.4-3.5-3.2 0-5.2 2.4-5.2 5.1 0 .9.3 1.9.7 2.5.1.1.1.2.1.3-.1.3-.2.9-.2 1.1-.1.3-.3.4-.6.3-1.5-.6-2.2-2.3-2.2-4.1 0-3.1 2.6-6.7 7.7-6.7 4.1 0 6.8 3 6.8 6.2 0 4.2-2.3 7.4-5.8 7.4-1.2 0-2.2-.6-2.6-1.4l-.7 2.8c-.2.9-.9 2-1.3 2.7.9.3 2 .5 3 .5 5.25 0 9.5-4.25 9.5-9.5S15.75 2 10.5 2z"
              fill="currentColor"
            />
          </svg>
          Iniciar sesión con Microsoft
        </button>
      </div>
    </div>
  );
}
