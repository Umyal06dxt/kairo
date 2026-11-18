import { useEffect, type ReactNode } from "react";
import { fetchExperiments } from "@/api/rest";
import type { ExperimentResult } from "@/api/types";
import { fmtMs, fmtPct } from "@/lib/format";
import { useState } from "react";
import { selectRuns, summaryOf } from "./selectRuns";
import styles from "./ResearchPage.module.css";

const Num = ({ children }: { children: ReactNode }) => <span className={styles.num}>{children}</span>;
const Need = ({ what }: { what: string }) => (
  <p className={styles.empty}>Run {what} on the Experiments tab to fill in the measured numbers here.</p>
);
function Finding({ title, status, tone, children }: { title: string; status: string; tone: "yes" | "part" | "open"; children: ReactNode }) {
  return (
    <section>
      <h2>{title}<span className={`${styles.status} ${styles[tone]}`}>{status}</span></h2>
      {children}
    </section>
  );
}

const WORK: [string, string, string][] = [
  ["VoiceAgentRAG (Qiu et al., 2026)", "Background agent prefetches into a semantic cache", "The base system, reproduced"],
  ["Speculative RAG (Wang et al., 2024)", "Small drafts from document subsets, verified once", "Pre-drafted answers; smaller context per answer"],
  ["Stream RAG (Arora et al., 2025)", "Retrieve while the user is still speaking", "Partial-transcript lookups"],
  ["RaLMSpec (Zhang et al., 2024)", "Speculative retrieval with batched verification", "Verify hits against the database in parallel"],
];
const OPEN: string[] = [
  "Real calls. The scripted calls are predictable by construction. The first thing to learn is how predictable real callers are, from transcripts of a support line.",
  "A learned predictor. Replace GPT with a small model over topic transitions learned from call logs, so prediction costs nothing and gets better with use.",
  "When is a draft safe to speak? Rates and fees change. Drafts need provenance, expiry tied to knowledge-base edits, and a policy for answers that must never be stale.",
  "Barge-in. People interrupt. Interrupting should cancel the answer in progress and re-aim the background agent at the new question.",
  "Cost. Speculation spends model calls on questions never asked. A cost per saved millisecond, by strategy, would tell an operator what to turn on.",
  "Bigger knowledge bases. With thousands of pages, hit rates fall and prediction matters more. The experiments here use 157.",
];

export function ResearchPage() {
  const [saved, setSaved] = useState<ExperimentResult[]>([]);
  useEffect(() => { fetchExperiments().then((d) => setSaved(d.saved)).catch(() => {}); }, []);

  const { liveBase, liveOpt, off } = selectRuns(saved);
  const base = summaryOf(liveBase, "baseline"), opt = summaryOf(liveOpt, "optimized");
  const paper = summaryOf(liveBase, "paper"), fast = summaryOf(liveBase, "fast");
  const rea = summaryOf(off, "reactive"), nei = summaryOf(off, "neighbors"), obase = summaryOf(off, "baseline");

  return (
    <article className={styles.prose}>
      <h1>Where this could go</h1>
      <p className={styles.lede}>A voice agent can hide the vector-database wait by predicting the next question. That works, but the headline number hides things worth testing. Each is a research question.</p>

      <Finding title="1. The wait that matters is not the database" status="measured" tone="yes">
        <p>The paper reports a 316x faster lookup on a cache hit, from 110 ms to 0.35 ms. That is real, but a caller waits for three things: understanding the question, finding pages, and the model's first word. Measured here, embedding the question through an API took <Num>about 680 ms</Num> and GPT-4o-mini's first token <Num>about 1.2 s</Num>. The database trip the cache removes is a small slice of that. Embedding on the device (<Num>5 ms</Num>) and not waiting for the model at all are bigger levers.</p>
      </Finding>

      <Finding title="2. Answer before being asked" status="built, measured" tone="part">
        <p>While the caller listens, the background agent can write the answer to the question it expects. If the caller then asks something close enough, and the pages behind the draft are in memory and confirmed by the database, Kairo speaks the draft with no model wait. This borrows the draft-then-verify structure of Speculative RAG (Wang et al., Google).</p>
        {base && opt ? (
          <p>On 100 scripted calls with GPT answers, the tuned strategy's median wait was <Num>{fmtMs(opt.user_p50)}</Num> against <Num>{fmtMs(base.user_p50)}</Num> for traditional RAG, with answers correct <Num>{fmtPct(opt.accuracy)}</Num> vs <Num>{fmtPct(base.accuracy)}</Num>. Pre-drafted answers served <Num>{fmtPct(opt.draft_rate)}</Num> of turns. The slowest 10% got worse, <Num>{fmtMs(opt.user_p90)}</Num> vs <Num>{fmtMs(base.user_p90)}</Num>, because background speculation shares the API with the live answer and corrections cost a second pass.</p>
        ) : <Need what="a live comparison (GPT answers, baseline and optimized)" />}
        <p>So the median gain is modest when the model's first token takes about a second, and drafts are the only lever that removes it. Raising the share of turns they cover, without serving a wrong draft, is the open question.</p>
      </Finding>

      <Finding title="3. Is a hit a good hit?" status="measured" tone="yes">
        <p>A hit rate counts every time memory held something above the similarity threshold. It does not check that those pages are the ones the database would have returned.</p>
        {rea && obase ? (
          <p>With a 157-page knowledge base and on-device embeddings, a memory-only cache hit <Num>{fmtPct(rea.hit_rate)}</Num> of the time, but the pages it served matched the database's top three only <Num>{fmtPct(rea.fidelity)}</Num> of the time, and the right source page was used <Num>{fmtPct(rea.evidence)}</Num> of the time against <Num>{fmtPct(obase.evidence)}</Num> for a plain lookup.</p>
        ) : <Need what="an offline comparison" />}
        {paper && fast && base && (
          <p>The same gap shows up in answers. With GPT, the paper's design answered <Num>{fmtPct(paper.accuracy)}</Num> correctly and an unverified, faster variant <Num>{fmtPct(fast.accuracy)}</Num>, against <Num>{fmtPct(base.accuracy)}</Num> for plain RAG.</p>
        )}
        <p>The fix borrows from RaLMSpec: speculate, then verify. On a hit, start the model with remembered pages and check the database in parallel. The check takes about 110 ms and the first token about a second, so it finishes before anything is spoken. If the top database page is missing, cancel and answer again. Hit rate drops because wrong hits become corrections, and accuracy returns to plain-RAG level.</p>
        {off && (
          <div className={styles.tbl}>
            <table>
              <thead><tr><th>Offline run</th><th>Hit rate</th><th>Right page</th><th>Fidelity</th><th>Wait p50</th></tr></thead>
              <tbody>
                {Object.entries(off.profiles).map(([k, p]) => (
                  <tr key={k}><td>{p.label}</td><td>{fmtPct(p.summary.hit_rate)}</td><td>{fmtPct(p.summary.evidence)}</td><td>{fmtPct(p.summary.fidelity)}</td><td>{fmtMs(p.summary.user_p50)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Finding>

      <Finding title="4. Predict without a language model" status="measured" tone="part">
        <p>Asking GPT for follow-ups costs a call per turn. A cheaper guess: after finding the pages for this question, load the pages nearest to them. No model, no embedding call.</p>
        {rea && nei ? (
          <p>On the offline runs it matched memory-only hit rates (<Num>{fmtPct(nei.hit_rate)}</Num> vs <Num>{fmtPct(rea.hit_rate)}</Num>) and served better-matching pages (fidelity <Num>{fmtPct(nei.fidelity)}</Num> vs <Num>{fmtPct(rea.fidelity)}</Num>). Whether it competes with GPT prediction on conversations that jump topics needs the live comparison.</p>
        ) : <Need what="an offline comparison" />}
      </Finding>

      <Finding title="5. Start before the caller finishes" status="built, not yet measured" tone="open">
        <p>Stream RAG (Arora et al.) predicts tool calls while the user is still speaking. Kairo does the retrieval half: partial text, typed or from the browser's speech recognition, triggers a lookup that fills memory before the final transcript arrives. Violet lamps on the board show it. We have not measured how much it helps; the experiment is to replay calls word by word and compare time-to-first-word.</p>
      </Finding>

      <h2>What this builds on</h2>
      <div className={styles.tbl}>
        <table>
          <thead><tr><th>Work</th><th>Idea</th><th>Used here as</th></tr></thead>
          <tbody>{WORK.map((r) => <tr key={r[0]}>{r.map((c) => <td key={c}>{c}</td>)}</tr>)}</tbody>
        </table>
      </div>

      <h2>Open problems</h2>
      <ul>{OPEN.map((t) => <li key={t}>{t}</li>)}</ul>

      <h2>Reproduce it</h2>
      <code className={styles.code}>kairo bench --domain bank --distractors 64 --profiles baseline,paper,optimized --embedder local --llm openai --json data/experiments/run.json</code>
      <p>Everything on the Experiments tab can be run from the command line, and the same scripted calls drive the Call tab.</p>
    </article>
  );
}
