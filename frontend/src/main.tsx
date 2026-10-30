import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { Toaster } from "sonner";
import App from "./App";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
        <Toaster
          position="bottom-left"
          theme="dark"
          toastOptions={{
            style: {
              background: "#161B22",
              color: "#F4EFE6",
              border: "1px solid rgba(197, 160, 89, 0.45)",
              borderRadius: "8px",
              fontSize: "12px",
              fontFamily: '"Inter", -apple-system, BlinkMacSystemFont, sans-serif',
              boxShadow: "0 12px 32px rgba(0, 0, 0, 0.75)",
            },
            classNames: {
              toast: "select-none",
            },
          }}
        />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);

