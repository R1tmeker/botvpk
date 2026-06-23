import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import WebApp from "@twa-dev/sdk";

import { App } from "./screens/App";
import { applyInitialTheme } from "./theme";
import "./styles/global.scss";

WebApp.ready();
WebApp.expand();

applyInitialTheme((WebApp as { colorScheme?: string | null }).colorScheme);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnMount: "always",
      refetchOnReconnect: true,
      refetchOnWindowFocus: true,
      staleTime: 0,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App webApp={WebApp} />
    </QueryClientProvider>
  </React.StrictMode>,
);

if ("serviceWorker" in navigator && import.meta.env.PROD) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // PWA is an enhancement; the app must keep working if registration fails.
    });
  });
}
