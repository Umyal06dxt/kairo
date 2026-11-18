from kairo.bench.domains import get_domain, score_answer
from kairo.ingest import chunk_documents


def test_score_answer_whole_token_matching():
    assert score_answer("The fee is $30 per item.", ("30",)) is True
    assert score_answer("Up to 300 dollars", ("30",)) is False          # not a substring match
    assert score_answer("Limit is 5,000 dollars", ("5",)) is False      # "5" is not "5,000"
    assert score_answer("Limit is 5,000 dollars", ("5,000",)) is True
    assert score_answer("a 25 dollar deposit", ("5",)) is False
    assert score_answer("Provide your documents", ("id",)) is False
    assert score_answer("Bring a photo ID.", ("id",)) is True
    assert score_answer("rate is 4.10 percent", ("4.10|4.1",)) is True
    assert score_answer("rate is 14.10 percent", ("4.10",)) is False
    assert score_answer("anything", None) is None and score_answer("x", ()) is None
    assert score_answer("7 to 10 business days", ("7|seven", "10")) is True
    assert score_answer("seven days", ("7|seven", "10")) is False


def test_bank_domain_gold_is_consistent_with_its_documents():
    d = get_domain("bank")
    assert len(d.docs) == 12 and len(d.scenarios) == 10 and d.n_turns == 100
    assert len(chunk_documents(list(d.docs.items()))) >= 20
    for name, turns in d.scenarios.items():
        for t in turns:
            assert t.doc in d.docs and t.expect, (name, t.q)
            # every gold fact must be findable in the document it is attributed to
            assert score_answer(d.docs[t.doc], t.expect), (name, t.q, t.expect)


def test_novacrm_domain_has_no_gold_and_unknown_domain_errors():
    d = get_domain("novacrm")
    assert d.n_turns == 200 and all(t.expect is None for v in d.scenarios.values() for t in v)
    import pytest
    with pytest.raises(KeyError):
        get_domain("nope")
