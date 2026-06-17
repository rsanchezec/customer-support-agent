import { type Configuration, PublicClientApplication } from "@azure/msal-browser";
import { env } from "./env";

const msalConfig: Configuration = {
  auth: {
    clientId: env.entraClientId,
    authority: env.entraAuthority,
    redirectUri: env.entraRedirectUri,
  },
  cache: {
    cacheLocation: "localStorage",
    storeAuthStateInCookie: false,
  },
};

export const msalInstance = new PublicClientApplication(msalConfig);

export const loginRequest = {
  scopes: [env.entraApiScope],
};
