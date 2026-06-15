import { useMsal } from "@azure/msal-react";
import { useAuthStore } from "@/stores/authStore";

export function ChatPage() {
  const { instance, accounts } = useMsal();
  const clearUser = useAuthStore((s) => s.clearUser);

  const account = accounts[0];

  const handleLogout = () => {
    clearUser();
    instance.logoutRedirect().catch(() => {
      // logoutRedirect navigates away
    });
  };

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      <header className="flex items-center justify-between px-6 py-4 bg-white border-b border-gray-200">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center">
            <span className="text-white text-sm font-medium">
              {account?.name?.[0] ?? "?"}
            </span>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-900">
              {account?.name ?? "Usuario"}
            </p>
            <p className="text-xs text-gray-500">{account?.username}</p>
          </div>
        </div>
        <button
          onClick={handleLogout}
          className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
        >
          Cerrar sesión
        </button>
      </header>
      <main className="flex-1 flex items-center justify-center">
        <div className="text-center p-8">
          <div className="w-16 h-16 mx-auto mb-4 bg-blue-100 rounded-full flex items-center justify-center">
            <svg
              className="w-8 h-8 text-blue-600"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
              />
            </svg>
          </div>
          <h2 className="text-xl font-semibold text-gray-900 mb-2">
            Chat will be available in slice 10
          </h2>
          <p className="text-gray-500">
            Tu sesión está activa. El chat completo llegará en el próximo slice.
          </p>
        </div>
      </main>
    </div>
  );
}
