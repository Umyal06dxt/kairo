import math

from kairo.bench.domains import get_domain
from kairo.bench.run import (PROFILES, ExperimentResult, Summary, TurnRec, format_experiment,
                             run_experiment)


def rec(turn, hit, src="cache", embed=10.0, retr=0.2, llm=100.0, gold=None, doc=None, fid=None):
    return TurnRec("S", turn, "q", src, hit, embed, retr, llm, "", [], gold, doc, fid)


def test_summary_math():
    recs = [rec(1, False, "store", retr=100.0, gold=True, doc=True),
            rec(2, True, "draft", llm=0.0, gold=True, doc=True, fid=1.0),
            rec(3, True, "cache", gold=False, doc=False, fid=0.5),
            rec(4, False, "store", retr=100.0)]
    s = Summary.of(recs)
    assert s.hit_rate == 0.5 and abs(s.warm_hit_rate - 2 / 3) < 1e-9 and s.draft_rate == 0.25
    assert abs(s.accuracy - 2 / 3) < 1e-9 and abs(s.evidence - 2 / 3) < 1e-9
    assert abs(s.fidelity - 0.75) < 1e-9 and abs(s.hit_retrieval_ms - 0.2) < 1e-9
    assert recs[1].user_ms == 10.0 + 0.2 + 0.0


def test_summary_without_gold_or_hits_is_nan_not_crash():
    s = Summary.of([rec(1, False, "store")])
    assert math.isnan(s.accuracy) and math.isnan(s.fidelity) and math.isnan(s.hit_retrieval_ms)


def test_profiles_defined():
    assert set(PROFILES) == {"baseline", "reactive", "paper", "neighbors", "verified", "optimized", "fast"}
    assert not PROFILES["baseline"].cache and PROFILES["optimized"].config.speculative_answers
    assert PROFILES["optimized"].config.verify_hits and not PROFILES["fast"].config.verify_hits


async def test_offline_experiment_end_to_end_on_bank_domain():
    res = await run_experiment("bank", ["baseline", "reactive", "neighbors"], embedder="hash",
                               llm="extractive", think_s=(0.0, 0.01), store_latency_s=0.005, llm_ttft_s=0.0,
                               sweep_profile="reactive", taus=[0.4, 0.2])
    n = get_domain("bank").n_turns
    assert isinstance(res, ExperimentResult)
    for key, pr in res.results.items():
        assert pr.summary.n == n, key
        assert all(0.0 <= (r.fidelity or 0.0) <= 1.0 for r in pr.recs)
        assert any(r.doc_ok is not None for r in pr.recs)  # evidence is scored with gold docs
    base = res.results["baseline"].summary
    assert base.hit_rate == 0.0 and math.isnan(base.accuracy)  # extractive LLM: no accuracy claim
    assert res.results["neighbors"].summary.hit_rate >= res.results["reactive"].summary.hit_rate
    assert [t for t, _ in res.sweep] == [0.4, 0.2]
    assert res.sweep[1][1].hit_rate >= res.sweep[0][1].hit_rate  # lower tau never loses hits
    text = format_experiment(res)
    assert "Traditional RAG" in text and "hash embeddings" in text and "threshold sweep" in text
    js = res.to_json()
    assert js["profiles"]["baseline"]["summary"]["accuracy"] is None  # NaN -> null for JSON


async def test_transient_failures_do_not_abort_a_run():
    from kairo.bench.run import make_env, run_profile
    domain = get_domain("bank")
    env = await make_env(domain, "hash", "extractive", True, 0.0, llm_ttft_s=0.0)
    real = env.embedder.embed
    calls = {"n": 0}

    async def flaky(texts):
        calls["n"] += 1
        if calls["n"] % 7 == 0:  # every 7th embedding call fails, like a dropped connection
            raise ConnectionError("boom")
        return await real(texts)

    env.embedder.embed = flaky
    for key in ("baseline", "reactive"):
        recs = await run_profile(domain, PROFILES[key], env, (0.0, 0.01))
        s = Summary.of(recs)
        assert len(recs) == domain.n_turns  # every turn accounted for, none aborted
        assert 0 < s.errors < domain.n_turns and s.n + s.errors == domain.n_turns
        assert all(r.gold_ok is None and r.fidelity is None for r in recs if r.source == "error")


def test_parse_overrides_types_and_errors():
    import pytest
    from kairo.bench.run import parse_overrides
    o = parse_overrides("llm_context_chunks=6, answer_threshold=0.78,verify_hits=false,strategy=neighbors")
    assert o == {"llm_context_chunks": 6, "answer_threshold": 0.78, "verify_hits": False,
                 "strategy": "neighbors"}
    assert parse_overrides("") == {}
    with pytest.raises(ValueError, match="unknown config field"):
        parse_overrides("nope=1")
