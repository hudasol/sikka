import "@fontsource/space-grotesk/500.css";
import "@fontsource/space-grotesk/700.css";
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-sans-arabic/400.css";
import "@fontsource/ibm-plex-sans-arabic/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/600.css";
import "./styles/base.css";
import "./i18n";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { themeCss } from "./styles/tokens";

const style = document.createElement("style");
style.id = "sikka-theme";
style.textContent = themeCss();
document.head.appendChild(style);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
