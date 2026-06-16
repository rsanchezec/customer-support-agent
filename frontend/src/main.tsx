import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { MsalProviderInstance } from "./auth/MsalProvider";
import { App } from "./App";
import "./index.css";

const root = document.getElementById("root");
if (!root) throw new Error("No #root element found");

createRoot(root).render(
  <MsalProviderInstance>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </MsalProviderInstance>
);
