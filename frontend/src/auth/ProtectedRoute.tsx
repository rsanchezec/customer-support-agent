import { useIsAuthenticated, useMsal } from "@azure/msal-react";
import { Outlet } from "react-router-dom";
import { loginRequest } from "@/lib/msalConfig";

interface ProtectedRouteProps {
  children?: React.ReactNode;
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const isAuthenticated = useIsAuthenticated();
  const { instance } = useMsal();

  if (!isAuthenticated) {
    instance.loginRedirect(loginRequest).catch(() => {
      // loginRedirect will navigate away; ignore errors
    });
    return null;
  }

  return children ? <>{children}</> : <Outlet />;
}
