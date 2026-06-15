import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gray-50">
      <h1 className="text-6xl font-bold text-gray-300 mb-4">404</h1>
      <p className="text-xl text-gray-600 mb-8">Página no encontrada</p>
      <Link
        to="/chat"
        className="px-4 py-2 text-blue-600 hover:text-blue-700 font-medium"
      >
        Ir al chat
      </Link>
    </div>
  );
}
