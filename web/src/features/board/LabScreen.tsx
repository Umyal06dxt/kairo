import { useNavigate } from "react-router-dom";
import { ScreenHeader } from "@/components/ScreenHeader";
import { LedgerPanel } from "./LedgerPanel";
import { MemoryBoard } from "./MemoryBoard";
import styles from "./LabScreen.module.css";

/** Mobile view of the board and ledger (on wide screens they sit beside the conversation). */
export function LabScreen() {
  const navigate = useNavigate();
  return (
    <>
      <ScreenHeader title="Memory board" subtitle="What is ready before you ask" onBack={() => navigate("/")} />
      <div className={styles.body}>
        <MemoryBoard />
        <LedgerPanel />
      </div>
    </>
  );
}
