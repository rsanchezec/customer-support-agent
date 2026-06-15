import { Routes, Route, Navigate } from "react-router-dom";
import { ProtectedRoute } from "@/auth/ProtectedRoute";
import { LoginPage } from "@/pages/LoginPage";
import { ChatPage } from "@/pages/ChatPage";
import { NotFoundPage } from "@/pages/NotFoundPage";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/chat"
        element={
          <ProtectedRoute>
            <ChatPage />
          </ProtectedRoute>
        }
      />
      <Route path="/" element={<Navigate to="/chat" replace />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
