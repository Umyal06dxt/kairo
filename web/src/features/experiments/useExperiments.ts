import { useCallback, useEffect, useState } from "react";
import { fetchExperiments, startExperiment } from "@/api/rest";
import type { ExperimentResult, ExperimentSpec, RunningExperiment } from "@/api/types";

const POLL_MS = 1200;

export interface ExperimentsApi {
  saved: ExperimentResult[];
  running: RunningExperiment | null;
  message: string;
  busy: boolean;
  run: (spec: ExperimentSpec) => Promise<void>;
}

/** Saved runs plus the single in-flight run, polled until it finishes. */
export function useExperiments(): ExperimentsApi {
  const [saved, setSaved] = useState<ExperimentResult[]>([]);
  const [running, setRunning] = useState<RunningExperiment | null>(null);
  const [message, setMessage] = useState("");
  // Bumped to force a fetch (on mount, after starting a run, and while a run is in flight).
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetchExperiments()
      .then((d) => {
        if (cancelled) return;
        setSaved(d.saved);
        setRunning(d.current);
        if (d.current?.state === "error") setMessage(`The run failed: ${d.current.error ?? "unknown error"}`);
        else if (d.current?.state === "done") setMessage("Done.");
      })
      .catch(() => { if (!cancelled) setMessage("Couldn't reach the server."); });
    return () => { cancelled = true; };
  }, [tick]);

  // While a run is in flight, poll; stops by itself when the state leaves "running".
  const isRunning = running?.state === "running";
  useEffect(() => {
    if (!isRunning) return;
    const id = setTimeout(() => setTick((t) => t + 1), POLL_MS);
    return () => clearTimeout(id);
  }, [isRunning, tick]);

  const run = useCallback(async (spec: ExperimentSpec) => {
    setMessage("Starting…");
    try {
      await startExperiment(spec);
      setMessage("Running…");
      setTick((t) => t + 1);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Couldn't start the run.");
    }
  }, []);

  return { saved, running, message, busy: isRunning, run };
}
