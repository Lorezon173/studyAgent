from app.services.evidence_policy import evaluate_evidence


def test_evidence_high_confidence():
    result = evaluate_evidence([{"score": 0.91}, {"score": 0.83}], min_hits=2)
    assert result.level == "high"
    assert result.low_evidence is False


def test_evidence_low_confidence_when_insufficient_hits():
    result = evaluate_evidence([{"score": 0.42}], min_hits=2)
    assert result.level == "low"
    assert result.low_evidence is True
