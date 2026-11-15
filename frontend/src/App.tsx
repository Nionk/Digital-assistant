import { Navigate, Route, Routes } from "react-router-dom";
import { AuthGuard } from "@/components/auth/AuthGuard";
import { LoginPage } from "@/pages/auth/LoginPage";
import { ManagerWorkspacePage } from "@/pages/manager/ManagerWorkspacePage";
import { ClientShowcasePage } from "@/pages/showcase/ClientShowcasePage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/admin" replace />} />
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/admin/*"
        element={
          <AuthGuard>
            <ManagerWorkspacePage />
          </AuthGuard>
        }
      />
      <Route path="/s/:magicToken" element={<ClientShowcasePage />} />
      <Route path="*" element={<Navigate to="/admin" replace />} />
    </Routes>
  );
}

