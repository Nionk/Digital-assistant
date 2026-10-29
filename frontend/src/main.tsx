import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { Toaster } from "sonner";
import { X } from "lucide-react";
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
          position="bottom-right"
          theme="dark"
          closeButton
          icons={{
            close: <X className="h-3.5 w-3.5" strokeWidth={2} />,
          }}
          toastOptions={{
            style: {
              background: "#161B22",
              color: "#E5C378",
              border: "1px solid #7C5A20",
              borderRadius: "8px",
              fontSize: "13px",
              fontFamily: 'Lora, Georgia, Cambria, "Times New Roman", serif',
              fontStyle: "italic",
              boxShadow: "0 12px 32px rgba(0, 0, 0, 0.75)",
              paddingRight: "44px",
            },
            classNames: {
              toast: "pr-11 select-none",
              closeButton:
                "!absolute !top-2.5 !right-2.5 !left-auto !transform-none !opacity-100 !flex !items-center !justify-center !h-6 !w-6 !rounded-[4px] !bg-[#1E252E] !border !border-[#7C5A20] !text-[#E5C378] hover:!border-[#E5C378] hover:!bg-[#2A1F10] hover:!text-white hover:!shadow-[0_0_8px_rgba(229,195,120,0.3)] transition-all",
            },
          }}
        />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);

