import math

from kairo.bench.kb import NOVACRM_DOCS
from kairo.bench.run import Report, TurnRec, format_report, run_benchmark
from kairo.bench.scenarios import SCENARIOS
from kairo.config import Config
from kairo.ingest import chunk_documents


def test_kb_and_scenarios_shape():
    assert len(NOVACRM_DOCS) == 12
    assert len(SCENARIOS) == 10 and sum(len(v) for v in SCENARIOS.values()) == 200
    assert len(chunk_documents(list(NOVACRM_DOCS.items()))) >= 24


def test_report_math():
    recs = [TurnRec("S1 New customer overview", 1, False, 100.0),
            TurnRec("S1 New customer overview", 2, True, 0.5),
            TurnRec("S1 New customer overview", 3, True, 0.3),
            TurnRec("S1 New customer overview", 4, False, 100.0)]
    r = Report("offline", 0.4, 100.0, recs)
    assert r.hit_rate == 0.5 and abs(r.warm_hit_rate - 2 / 3) < 1e-9
    assert abs(r.hit_ms - 0.4) < 1e-9 and abs(r.speedup - 250) < 1e-6
    assert abs(r.saved_ms - (99.5 + 99.7)) < 1e-9
    assert not math.isnan(r.by_depth()[0][1])


def test_report_with_no_hits_does_not_crash():
    r = Report("offline", 0.4, 100.0, [TurnRec("S1 New customer overview", 1, False, 100.0)])
    assert math.isnan(r.speedup)
    assert "Kairo benchmark" in format_report([r])


async def test_offline_benchmark_runs_end_to_end():
    reports = await run_benchmark("offline", Config(), taus=[0.4, 0.3],
                                  think_s=(0.0, 0.01), store_latency_s=0.005)
    assert [r.tau for r in reports] == [0.4, 0.3]
    for r in reports:
        assert len(r.turns) == 200 and 0.0 <= r.hit_rate <= 1.0
        assert all(not t.hit for t in r.turns if t.turn == 1)  # cold start always misses
    main = reports[0]
    assert main.hit_rate > 0 and main.hit_ms < main.baseline_ms
    assert reports[1].hit_rate >= reports[0].hit_rate  # lower tau never reduces hits
    text = format_report(reports)
    assert "OFFLINE" in text and "Threshold sweep" in text
