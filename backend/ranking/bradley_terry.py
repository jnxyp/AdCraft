from __future__ import annotations

import json
from pathlib import Path
from typing import NotRequired, TypedDict

from core.database import connect

MIN_COMPARISONS = 10
MAX_ITERATIONS = 1000
CONVERGENCE_TOLERANCE = 1e-6
ZERO_WIN_FLOOR = 1e-12


class Comparison(TypedDict):
    winner_template_id: str
    loser_template_id: str
    weight: float


class Candidate(TypedDict):
    id: NotRequired[str]
    template_id: NotRequired[str]
    freq_score: float


class EvalTaskAd(TypedDict):
    slot: str
    ad_id: str
    body: str
    template_id: str
    sequence: list[str]


def fit(comparisons: list[tuple[str, str, float]]) -> dict[str, float]:
    if len(comparisons) < MIN_COMPARISONS:
        return {}

    template_ids = sorted({winner for winner, _, _ in comparisons} | {loser for _, loser, _ in comparisons})
    wins: dict[str, float] = {template_id: 0.0 for template_id in template_ids}
    pair_counts: dict[str, dict[str, float]] = {template_id: {} for template_id in template_ids}

    for winner, loser, weight in comparisons:
        if weight <= 0.0:
            continue
        wins[winner] += weight
        pair_counts[winner][loser] = pair_counts[winner].get(loser, 0.0) + weight
        pair_counts[loser][winner] = pair_counts[loser].get(winner, 0.0) + weight

    betas: dict[str, float] = {template_id: 1.0 for template_id in template_ids}
    for _ in range(MAX_ITERATIONS):
        next_betas: dict[str, float] = {}
        for template_id in template_ids:
            denom = sum(
                count / (betas[template_id] + betas[opponent_id])
                for opponent_id, count in pair_counts[template_id].items()
            )
            if wins[template_id] <= 0.0 or denom <= 0.0:
                next_betas[template_id] = ZERO_WIN_FLOOR
            else:
                next_betas[template_id] = wins[template_id] / denom

        mean_beta = sum(next_betas.values()) / len(next_betas)
        if mean_beta > 0.0:
            next_betas = {template_id: beta / mean_beta for template_id, beta in next_betas.items()}

        max_delta = max(abs(next_betas[template_id] - betas[template_id]) for template_id in template_ids)
        betas = next_betas
        if max_delta < CONVERGENCE_TOLERANCE:
            break

    return betas


async def build_comparisons_from_resolved_tasks(db_path: Path) -> list[tuple[str, str, float]]:
    async with connect(db_path) as conn:
        rows = await (
            await conn.execute(
                """
                SELECT r.resolved_winner_slot, e.ads
                FROM resolved_eval_tasks r
                JOIN eval_tasks e ON e.id = r.task_id
                ORDER BY r.task_id
                """
            )
        ).fetchall()

    comparisons: list[tuple[str, str, float]] = []
    for row in rows:
        winner_slot = str(row["resolved_winner_slot"])
        ads = _parse_ads(str(row["ads"]))
        templates_by_slot = {ad["slot"]: ad["template_id"] for ad in ads}
        template_a = templates_by_slot["a"]
        template_b = templates_by_slot["b"]

        if winner_slot == "a":
            comparisons.append((template_a, template_b, 1.0))
        elif winner_slot == "b":
            comparisons.append((template_b, template_a, 1.0))
        elif winner_slot == "tie":
            comparisons.append((template_a, template_b, 0.5))
            comparisons.append((template_b, template_a, 0.5))
        else:
            raise ValueError(f"unsupported resolved winner slot: {winner_slot}")

    return comparisons


def rank_candidates(
    candidates: list[dict[str, object]],
    bt_scores: dict[str, float],
) -> list[dict[str, object]]:
    if not bt_scores:
        return sorted(candidates, key=_freq_score, reverse=True)[:3]

    known: list[dict[str, object]] = []
    unknown: list[dict[str, object]] = []
    for candidate in candidates:
        if _candidate_id(candidate) in bt_scores:
            known.append(candidate)
        else:
            unknown.append(candidate)

    ranked_known = sorted(
        known,
        key=lambda candidate: (bt_scores[_candidate_id(candidate)], _freq_score(candidate)),
        reverse=True,
    )
    ranked_unknown = sorted(unknown, key=_freq_score, reverse=True)
    return (ranked_known + ranked_unknown)[:3]


def _parse_ads(raw_ads: str) -> list[EvalTaskAd]:
    data = json.loads(raw_ads)
    if not isinstance(data, list):
        raise ValueError("eval task ads must be a JSON array")

    ads: list[EvalTaskAd] = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("eval task ad must be a JSON object")
        raw_sequence = item.get("sequence")
        if not isinstance(raw_sequence, list):
            raise ValueError("eval task ad sequence must be a JSON array")
        ads.append(
            EvalTaskAd(
                slot=str(item["slot"]),
                ad_id=str(item["ad_id"]),
                body=str(item["body"]),
                template_id=str(item["template_id"]),
                sequence=[str(part) for part in raw_sequence],
            )
        )
    return ads


def _candidate_id(candidate: dict[str, object]) -> str:
    template_id = candidate.get("template_id", candidate.get("id"))
    if not isinstance(template_id, str):
        raise ValueError(f"candidate missing string id: {candidate!r}")
    return template_id


def _freq_score(candidate: dict[str, object]) -> float:
    freq_score = candidate.get("freq_score", 0.0)
    if isinstance(freq_score, int | float):
        return float(freq_score)
    raise ValueError(f"candidate freq_score must be numeric: {candidate!r}")
