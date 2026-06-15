import type { AccountInfo } from "@azure/msal-browser";
import { useMsal } from "@azure/msal-react";
import {
  InteractionRequiredAuthError,
} from "@azure/msal-browser";
import { loginRequest } from "@/lib/msalConfig";

export async function acquireAccessToken(
  instance: ReturnType<typeof useMsal>["instance"],
  accounts: AccountInfo[]
): Promise<string> {
  if (accounts.length === 0) {
    throw new Error("No authenticated account found.");
  }

  const account = accounts[0];

  try {
    const response = await instance.acquireTokenSilent({
      scopes: loginRequest.scopes,
      account,
    });
    return response.accessToken;
  } catch (error) {
    if (error instanceof InteractionRequiredAuthError) {
      await instance.acquireTokenRedirect({
        scopes: loginRequest.scopes,
        account,
      });
      throw new Error("Token interaction required. Redirecting...");
    }
    throw error;
  }
}

export function useAccessToken(): () => Promise<string> {
  const { instance, accounts } = useMsal();

  return () => acquireAccessToken(instance, accounts);
}
