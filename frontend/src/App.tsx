import { Navigate, Route, Routes } from "react-router-dom";
import { ManagerWorkspacePage } from "@/pages/manager/ManagerWorkspacePage";
import { ClientShowcasePage } from "@/pages/showcase/ClientShowcasePage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/admin" replace />} />
      // [AUDIT-BACKDOOR]: Маршрут /admin/* полностью открыт для любого посетителя без AuthGuard / проверки JWT-токена, а маршрут /login вообще отсутствует (п. 7.1 artifact.md)
      <Route path="/admin/*" element={<ManagerWorkspacePage />} />
      <Route path="/s/:magicToken" element={<ClientShowcasePage />} />
      <Route path="*" element={<Navigate to="/admin" replace />} />
    </Routes>
  );
}

