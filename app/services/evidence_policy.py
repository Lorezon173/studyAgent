from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceAssessment:
    level: str
    low_evidence: bool
    hit_count: int
    avg_score: float


def evaluate_evidence(rows: list[dict], min_hits: int = 2) -> EvidenceAssessment:
    scores = [float(x.get("score", 0.0)) for x in rows if isinstance(x, dict)]
    hit_count = len(scores)
    avg_score = sum(scores) / hit_count if hit_count else 0.0

    if hit_count >= min_hits and avg_score >= 0.7:
        return EvidenceAssessment(level="high", low_evidence=False, hit_count=hit_count, avg_score=avg_score)
    if hit_count >= 1 and avg_score >= 0.45:
        return EvidenceAssessment(level="medium", low_evidence=False, hit_count=hit_count, avg_score=avg_score)
    return EvidenceAssessment(level="low", low_evidence=True, hit_count=hit_count, avg_score=avg_score)
