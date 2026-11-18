import { Navigate, Route, Routes } from "react-router-dom";
import { LabScreen } from "@/features/board/LabScreen";
import { ChatScreen } from "@/features/call/ChatScreen";
import { HomeScreen } from "@/features/call/HomeScreen";
import { ExperimentsPage } from "@/features/experiments/ExperimentsPage";
import { ResearchPage } from "@/features/research/ResearchPage";
import { AppShell } from "./AppShell";
import { useShell } from "./ShellContext";

const Home = () => <HomeScreen onMenu={useShell().openMenu} />;
const Chat = () => <ChatScreen onMenu={useShell().openMenu} />;

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Home />} />
        <Route path="chat" element={<Chat />} />
        <Route path="lab" element={<LabScreen />} />
        <Route path="experiments" element={<ExperimentsPage />} />
        <Route path="research" element={<ResearchPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
