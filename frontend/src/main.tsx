import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import WebApp from "@twa-dev/sdk";

import { App } from "./screens/App";
import "./styles/global.scss";

WebApp.ready();
WebApp.expand();

const queryClient = new QueryClient();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App webApp={WebApp} />
    </QueryClientProvider>
  </React.StrictMode>,
);
