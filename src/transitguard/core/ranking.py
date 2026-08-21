from transitguard.core.evaluator import evaluate_route
from transitguard.core.models import RouteCandidate, RouteEvaluation, TransferStatus

_STATUS_WEIGHT = {
    TransferStatus.SAFE: 0,
    TransferStatus.TIGHT: 1,
    TransferStatus.UNKNOWN: 2,
    TransferStatus.MISSED: 3,
}
_STATUS_PENALTY = {
    TransferStatus.SAFE: 0.0,
    TransferStatus.TIGHT: 8.0,
    TransferStatus.UNKNOWN: 20.0,
    TransferStatus.MISSED: 10_000.0,
}


def rank_routes(routes: list[RouteCandidate]) -> list[RouteEvaluation]:
    evaluations = [evaluate_route(route) for route in routes]
    return sorted(
        evaluations,
        key=lambda result: (
            _ranking_score(result),
            _STATUS_WEIGHT[result.status],
            result.total_minutes,
            result.route_id,
        ),
    )


def _ranking_score(result: RouteEvaluation) -> float:
    return result.ranking_score
