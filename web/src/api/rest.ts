import type { ExperimentResult, ExperimentSpec, Info, RunningExperiment } from "./types";

async function json<T>(res: Response): Promise<T> {
  const body = (await res.json()) as T;
  if (!res.ok) throw new Error((body as { error?: string }).error ?? `Request failed (${res.status})`);
  return body;
}

export const fetchInfo = (): Promise<Info> => fetch("/api/info").then((r) => json<Info>(r));

export const fetchExperiments = (): Promise<{ saved: ExperimentResult[]; current: RunningExperiment | null }> =>
  fetch("/api/experiments").then((r) => json(r));

export const startExperiment = (spec: ExperimentSpec): Promise<{ ok: true; id: string }> =>
  fetch("/api/experiments", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(spec),
  }).then((r) => json(r));
