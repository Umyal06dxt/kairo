import { useEffect } from "react";
import { HashRouter } from "react-router-dom";
import { getSession } from "@/api/session";
import { AppRoutes } from "./routes";

/** Hash routing: the Python server serves one index.html and needs no per-route handling. */
export function App() {
  useEffect(() => {
    const session = getSession();
    session.start();
    return () => session.stop();
  }, []);
  return (
    <HashRouter>
      <AppRoutes />
    </HashRouter>
  );
}
