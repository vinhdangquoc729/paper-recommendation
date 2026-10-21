import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import { PrefsProvider } from "./prefs";
import { SessionProvider } from "./session";
import "katex/dist/katex.min.css";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <PrefsProvider>
      <SessionProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </SessionProvider>
    </PrefsProvider>
  </StrictMode>,
);
