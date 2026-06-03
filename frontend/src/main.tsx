import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import WebApp from "@twa-dev/sdk";

import { App } from "./screens/App";
import "./styles/global.scss";

WebApp.ready();
WebApp.expand();

// Force light theme always — remove before React renders to avoid flash
document.documentElement.removeAttribute("data-theme");
document.documentElement.setAttribute("data-theme", "light");

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
