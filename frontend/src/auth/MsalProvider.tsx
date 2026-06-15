import { useEffect, useState } from "react";
import { MsalProvider, useMsal } from "@azure/msal-react";
import { msalInstance } from "@/lib/msalConfig";

interface MsalProviderWrapperProps {
  children: React.ReactNode;
}

function MsalProviderInner({ children }: MsalProviderWrapperProps) {
  const { instance } = useMsal();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    instance
      .initialize()
      .then(() => setReady(true))
      .catch(() => setReady(false));
  }, [instance]);

  if (!ready) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return <>{children}</>;
}

export function MsalProviderInstance({ children }: MsalProviderWrapperProps) {
  return (
    <MsalProvider instance={msalInstance}>
      <MsalProviderInner>{children}</MsalProviderInner>
    </MsalProvider>
  );
}
