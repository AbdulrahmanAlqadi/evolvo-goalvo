from __future__ import annotations

from app.forecasting.poisson import forecast_poisson
from app.schemas.predictions import Explanation, PredictionResponse

_ARABIC_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def format_number(value: int | float, *, arabic_digits: bool = False) -> str:
    text = str(value)
    return text.translate(_ARABIC_DIGITS) if arabic_digits else text


def percent(value: float, *, arabic_digits: bool = False) -> str:
    return format_number(round(value * 100), arabic_digits=arabic_digits) + "%"


def decimal(value: float, *, places: int = 2, arabic_digits: bool = False) -> str:
    text = f"{value:.{places}f}"
    return text.translate(_ARABIC_DIGITS) if arabic_digits else text


def _scoreline_probability(prediction: PredictionResponse, predicate) -> float:
    return sum(
        scoreline.probability
        for scoreline in prediction.likely_scorelines
        if predicate(scoreline.home_goals, scoreline.away_goals)
    )


def _matrix_probability(matrix: list[list[float]], predicate) -> float:
    return sum(
        probability
        for home_goals, row in enumerate(matrix)
        for away_goals, probability in enumerate(row)
        if predicate(home_goals, away_goals)
    )


def _win_probability_lines(
    prediction: PredictionResponse, *, arabic_digits: bool = False
) -> list[str]:
    home = prediction.home_team.name_ar or prediction.home_team.name
    away = prediction.away_team.name_ar or prediction.away_team.name
    return [
        "احتمالات الفوز:",
        (
            f"• {home}: "
            f"{percent(prediction.outcomes_90_minutes.home_win, arabic_digits=arabic_digits)}"
        ),
        f"• التعادل: {percent(prediction.outcomes_90_minutes.draw, arabic_digits=arabic_digits)}",
        (
            f"• {away}: "
            f"{percent(prediction.outcomes_90_minutes.away_win, arabic_digits=arabic_digits)}"
        ),
    ]


def _goal_probability_lines(
    prediction: PredictionResponse, *, arabic_digits: bool = False
) -> list[str]:
    goal_forecast = forecast_poisson(
        prediction.expected_goals.home,
        prediction.expected_goals.away,
    )
    over_25 = _matrix_probability(
        goal_forecast.matrix, lambda home_goals, away_goals: home_goals + away_goals >= 3
    )
    both_score = _matrix_probability(
        goal_forecast.matrix, lambda home_goals, away_goals: home_goals > 0 and away_goals > 0
    )
    return [
        "احتمالات الأهداف:",
        f"• أكثر من 2.5 هدف: {percent(over_25, arabic_digits=arabic_digits)}",
        f"• تسجيل المنتخبين: {percent(both_score, arabic_digits=arabic_digits)}",
    ]


def _likely_result_phrase(
    prediction: PredictionResponse, *, arabic_digits: bool = False
) -> str | None:
    if not prediction.likely_scorelines:
        return None

    home = prediction.home_team.name_ar or prediction.home_team.name
    away = prediction.away_team.name_ar or prediction.away_team.name
    outcomes = {
        "home": prediction.outcomes_90_minutes.home_win,
        "draw": prediction.outcomes_90_minutes.draw,
        "away": prediction.outcomes_90_minutes.away_win,
    }
    leader = max(outcomes, key=outcomes.get)
    target_total = round(prediction.expected_goals.home + prediction.expected_goals.away)
    target_total = max(0, min(6, target_total))
    both_score_preferred = (
        prediction.expected_goals.home >= 0.75
        and prediction.expected_goals.away >= 0.75
        and target_total >= 2
    )

    def matches_leader(home_goals: int, away_goals: int) -> bool:
        if leader == "home":
            return home_goals > away_goals
        if leader == "away":
            return away_goals > home_goals
        return home_goals == away_goals

    candidates = [
        (index, scoreline)
        for index, scoreline in enumerate(prediction.likely_scorelines[:10])
        if matches_leader(scoreline.home_goals, scoreline.away_goals)
    ]
    if not candidates:
        candidates = list(enumerate(prediction.likely_scorelines[:10]))

    def display_key(item) -> tuple[int, int, int]:
        index, scoreline = item
        total = scoreline.home_goals + scoreline.away_goals
        both_score_penalty = (
            0
            if not both_score_preferred
            or (scoreline.home_goals > 0 and scoreline.away_goals > 0)
            else 1
        )
        nil_nil_penalty = 1 if leader == "draw" and total == 0 and target_total >= 1 else 0
        return (both_score_penalty + nil_nil_penalty, abs(total - target_total), index)

    _, selected = min(candidates, key=display_key)
    home_goals = format_number(selected.home_goals, arabic_digits=arabic_digits)
    away_goals = format_number(selected.away_goals, arabic_digits=arabic_digits)
    score = f"{home_goals}-{away_goals}"
    if selected.home_goals > selected.away_goals:
        return f"النتيجة المحتملة: {score} لصالح {home}"
    if selected.away_goals > selected.home_goals:
        return f"النتيجة المحتملة: {score} لصالح {away}"
    return f"النتيجة المحتملة: {score}"


def _goal_market_lines(prediction: PredictionResponse, *, arabic_digits: bool) -> list[str]:
    home = prediction.home_team.name_ar or prediction.home_team.name
    away = prediction.away_team.name_ar or prediction.away_team.name
    total_xg = prediction.expected_goals.home + prediction.expected_goals.away
    over_25 = _scoreline_probability(
        prediction, lambda home_goals, away_goals: home_goals + away_goals >= 3
    )
    both_score = _scoreline_probability(
        prediction, lambda home_goals, away_goals: home_goals > 0 and away_goals > 0
    )
    clean_sheet_home = _scoreline_probability(
        prediction, lambda _home_goals, away_goals: away_goals == 0
    )
    clean_sheet_away = _scoreline_probability(
        prediction, lambda home_goals, _away_goals: home_goals == 0
    )
    home_xg = decimal(prediction.expected_goals.home, arabic_digits=arabic_digits)
    away_xg = decimal(prediction.expected_goals.away, arabic_digits=arabic_digits)
    return [
        f"• أهداف متوقعة: {home} {home_xg} - {away} {away_xg}",
        f"• مجموع الأهداف المتوقع: {decimal(total_xg, arabic_digits=arabic_digits)}",
        f"• أكثر من 2.5 هدف: {percent(over_25, arabic_digits=arabic_digits)}",
        f"• كلا الفريقين يسجل: {percent(both_score, arabic_digits=arabic_digits)}",
        (
            f"• شباك نظيفة محتملة: {home} "
            f"{percent(clean_sheet_home, arabic_digits=arabic_digits)}، "
            f"{away} {percent(clean_sheet_away, arabic_digits=arabic_digits)}"
        ),
    ]


def deterministic_explanation(
    *,
    home_name: str,
    away_name: str,
    home_probability: float,
    draw_probability: float,
    away_probability: float,
    factors: list[str],
    uncertainty: str,
    warning: str | None,
    scope_ar: str = "بعد 90 دقيقة",
) -> Explanation:
    values = [
        (home_name, home_probability),
        ("تعادل", draw_probability),
        (away_name, away_probability),
    ]
    leader, probability = max(values, key=lambda item: item[1])
    scope_text = f" {scope_ar}" if "90" not in scope_ar else ""
    headline = f"التوقع الأقرب{scope_text}: {leader}"
    summary = (
        f"نميل إلى {leader} بناء على قوة المنتخب والنتائج المتاحة وسياق المباراة."
    )
    return Explanation(
        headline_ar=headline,
        summary_ar=summary,
        key_factors_ar=factors[:3],
        uncertainty_ar="التوقع قابل للخطأ لأن كرة القدم تتغير بتفاصيل صغيرة.",
        data_warning_ar=warning,
        generated_by="deterministic",
    )


def telegram_prediction_text(prediction: PredictionResponse, *, arabic_digits: bool = False) -> str:
    lines = [
        prediction.explanation.headline_ar,
        "",
        prediction.explanation.summary_ar,
    ]
    likely_result = _likely_result_phrase(prediction, arabic_digits=arabic_digits)
    if likely_result:
        lines.extend(["", likely_result])
    lines.extend(["", *_win_probability_lines(prediction, arabic_digits=arabic_digits)])
    lines.extend(["", *_goal_probability_lines(prediction, arabic_digits=arabic_digits)])
    reasons_heading = (
        "لماذا هذا التوقع (تحليل الذكاء الاصطناعي):"
        if prediction.explanation.generated_by == "llm"
        else "لماذا هذا التوقع:"
    )
    lines.extend(["", reasons_heading])
    lines.extend(f"• {factor}" for factor in prediction.explanation.key_factors_ar)
    if prediction.explanation.data_warning_ar:
        lines.extend(["", f"تنبيه: {prediction.explanation.data_warning_ar}"])
    lines.extend(["", "هذا توقع تحليلي وقد يصيب أو يخطئ."])
    return "\n".join(lines)


def telegram_prediction_details_text(
    prediction: PredictionResponse, *, arabic_digits: bool = False
) -> str:
    home = prediction.home_team.name_ar or prediction.home_team.name
    away = prediction.away_team.name_ar or prediction.away_team.name
    lines = [
        "تفاصيل التوقع",
        f"{home} vs {away}",
        "",
        prediction.explanation.summary_ar,
    ]
    if prediction.evidence:
        lines.extend(["", "العوامل التي اعتمد عليها التحليل:"])
        lines.extend(f"• {item.description_ar}" for item in prediction.evidence[:5])
    if prediction.movement_since_previous:
        lines.extend(["", "تغير التوقع منذ آخر تحديث لكنه ما زال تقديرا قابلا للخطأ."])
    warnings = prediction.data_quality.warnings
    if warnings:
        lines.extend(["", "تنبيهات البيانات:"])
        lines.extend(f"• {warning}" for warning in warnings)
    lines.extend(["", "هذا توقع تحليلي وليس ضمانا للنتيجة."])
    return "\n".join(lines)
