from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core.config import Settings
from app.core.security import hash_identifier
from app.domain.entities import Match, MatchStatistics
from app.domain.enums import EventType
from app.domain.events import CanonicalMatchState
from app.features.data_quality_features import build_data_quality_features
from app.features.pre_match_features import build_pre_match_features
from app.features.team_strength import TeamStrengthProfile, build_team_strength_profiles
from app.forecasting.calibration import TemperatureCalibrator
from app.forecasting.classifiers import TransparentMultinomialClassifier
from app.forecasting.dixon_coles import apply_dixon_coles
from app.forecasting.elo import EloModel, EloRating
from app.forecasting.ensemble import ModelComponent, combine_components
from app.forecasting.knockout import advancement_from_90_minutes, advancement_from_extra_time
from app.forecasting.live_simulation import (
    LiveSimulationInput,
    simulate_live,
    simulate_penalty_shootout,
)
from app.forecasting.poisson import forecast_poisson, probabilities_from_matrix
from app.observability.metrics import PREDICTION_COUNT, PREDICTION_LATENCY
from app.providers.football.base import ProviderUnavailable
from app.providers.football.composite import CompositeFootballProvider
from app.repositories.catalog import CatalogRepository
from app.repositories.database import Database
from app.repositories.models import PredictionRow
from app.repositories.predictions import PredictionRepository
from app.repositories.subscriptions import TelegramSubscriptionRepository
from app.repositories.telegram_users import TelegramUserRepository
from app.schemas.predictions import (
    CompetitionRef,
    DataQuality,
    EvidenceItem,
    ExpectedGoals,
    ModelMetadata,
    Outcome90,
    PredictionResponse,
    Qualification,
    Scoreline,
    TeamRef,
    Uncertainty,
)
from app.services.events import PredictionEventBroker
from app.services.explanations import ExplanationService

logger = logging.getLogger(__name__)


class PredictionService:
    def __init__(
        self,
        *,
        settings: Settings,
        provider: CompositeFootballProvider,
        database: Database,
        explanations: ExplanationService,
        broker: PredictionEventBroker,
        profile_path: Path = Path("configs/team_profiles.json"),
    ) -> None:
        self.settings = settings
        self.provider = provider
        self.database = database
        self.explanations = explanations
        self.broker = broker
        self.repository = PredictionRepository()
        self.catalog_repository = CatalogRepository()
        self.subscription_repository = TelegramSubscriptionRepository()
        self.telegram_user_repository = TelegramUserRepository()
        self.profiles = (
            json.loads(profile_path.read_text(encoding="utf-8")) if profile_path.exists() else {}
        )
        self.classifier = TransparentMultinomialClassifier()
        self.calibrator = TemperatureCalibrator(
            temperature=1.0, version=settings.calibration_version
        )

    async def _historical_matches(self, match: Match, generated_at: datetime) -> list[Match]:
        try:
            return await self.provider.list_matches(date_to=match.kickoff.date())
        except Exception:
            logger.warning("historical match lookup failed", exc_info=True)
            return []

    async def _model_inputs(self, match: Match, generated_at: datetime):
        history = await self._historical_matches(match, generated_at)
        home, away, eligible_history = build_team_strength_profiles(
            match,
            historical_matches=history,
            prediction_time=generated_at,
            configured_profiles=self.profiles,
        )
        elo = EloModel()
        elo.ratings[match.home_team.id] = EloRating(home.elo, generated_at)
        elo.ratings[match.away_team.id] = EloRating(away.elo, generated_at)
        elo_probability = elo.probabilities(
            match.home_team.id, match.away_team.id, generated_at, match.neutral_venue
        )

        neutral_factor = 1.0 if match.neutral_venue else 1.08
        home_xg = max(0.15, 1.30 * home.attack * away.defence * neutral_factor)
        away_xg = max(0.15, 1.22 * away.attack * home.defence)
        poisson = forecast_poisson(home_xg, away_xg, self.settings.max_score_goals)
        corrected_matrix = apply_dixon_coles(
            poisson.matrix, home_xg, away_xg, self.settings.dixon_coles_rho
        )
        dc_probability = probabilities_from_matrix(corrected_matrix)

        features = build_pre_match_features(
            match,
            prediction_time=generated_at,
            home_elo=home.elo,
            away_elo=away.elo,
            home_attack=home.attack,
            away_attack=away.attack,
            home_defence=home.defence,
            away_defence=away.defence,
            rest_days_home=home.rest_days,
            rest_days_away=away.rest_days,
        )
        available_groups = {"fixture", "ratings", "results"}
        if eligible_history:
            available_groups.update({"tournament_results", "team_strength"})
        if "default_prior" not in {home.source, away.source}:
            available_groups.add("team_profiles")
        quality = build_data_quality_features(
            prediction_time=generated_at,
            available_groups=available_groups,
            expected_groups={
                "fixture",
                "ratings",
                "results",
                "tournament_results",
                "team_strength",
                "team_profiles",
                "lineups",
                "availability",
                "xg",
            },
        )[0].value
        classifier_probability = self.classifier.predict(
            {
                "elo_diff_scaled": (home.elo - away.elo) / 400.0,
                "xg_diff": home_xg - away_xg,
                "neutral_venue": float(match.neutral_venue),
                "data_completeness": float(quality),
            }
        )
        components = [
            ModelComponent("elo", elo_probability, self.settings.ensemble_elo_weight, "elo-v1"),
            ModelComponent(
                "dixon_coles",
                dc_probability,
                self.settings.ensemble_poisson_weight,
                "dixon-coles-v1",
            ),
            ModelComponent(
                "classifier",
                classifier_probability,
                self.settings.ensemble_classifier_weight,
                "transparent-softmax-demo-v1",
            ),
        ]
        combined = combine_components(components)
        calibrated = self.calibrator.apply(combined)
        return (
            home_xg,
            away_xg,
            poisson,
            calibrated,
            components,
            float(quality),
            features,
            home,
            away,
            eligible_history,
        )

    async def _persist(self, prediction: PredictionResponse, match: Match) -> None:
        row = PredictionRow(
            id=prediction.prediction_id,
            match_id=prediction.match_id,
            kind="live"
            if prediction.status in {"LIVE", "EXTRA_TIME", "PENALTIES"}
            else "pre_match",
            generated_at=prediction.generated_at,
            data_as_of=prediction.data_as_of,
            payload_json=prediction.model_dump(mode="json"),
            model_version=prediction.model.ensemble_version,
            calibration_version=prediction.model.calibration_version,
            stale=prediction.data_quality.stale,
        )
        async for session in self.database.session():
            await self.catalog_repository.upsert_match_graph(session, match)
            await session.flush()
            await self.repository.save(session, row)

    async def _previous(self, match_id: str) -> PredictionResponse | None:
        async for session in self.database.session():
            row = await self.repository.latest(session, match_id)
            return PredictionResponse.model_validate(row.payload_json) if row else None
        return None

    async def pre_match(
        self, match_id: str, generated_at: datetime | None = None
    ) -> PredictionResponse:
        generated_at = (generated_at or datetime.now(UTC)).astimezone(UTC)
        with PREDICTION_LATENCY.labels("pre_match").time():
            match = await self.provider.get_match(match_id)
            (
                home_xg,
                away_xg,
                poisson,
                probability,
                components,
                completeness,
                _features,
                home_profile,
                away_profile,
                eligible_history,
            ) = await self._model_inputs(match, generated_at)
            data_as_of = min(match.updated_at, generated_at)
            age = max(0, int((generated_at - data_as_of).total_seconds()))
            stale = age > self.settings.live_data_stale_after_seconds and match.status.value in {
                "LIVE",
                "EXTRA_TIME",
                "PENALTIES",
            }
            warnings = ["LINEUPS_NOT_CONFIRMED", "PLAYER_AVAILABILITY_LIMITED"]
            if stale:
                warnings.append("LIVE_DATA_STALE")
            if not eligible_history:
                warnings.append("TEAM_STRENGTH_HISTORY_LIMITED")
            if "default_prior" in {home_profile.source, away_profile.source}:
                warnings.append("TEAM_STRENGTH_PRIOR_LIMITED")
            uncertainty_level = (
                "high" if completeness < 0.6 else "medium" if completeness < 0.85 else "low"
            )
            evidence = self._evidence(match, home_xg, away_xg, home_profile, away_profile)
            explanation = await self.explanations.build(
                home_name=match.home_team.name_ar or match.home_team.name,
                away_name=match.away_team.name_ar or match.away_team.name,
                home_probability=probability.home_win,
                draw_probability=probability.draw,
                away_probability=probability.away_win,
                evidence=evidence,
                uncertainty=uncertainty_level,
                warning="بيانات التشكيلة أو الغيابات غير مكتملة." if warnings else None,
            )
            knockout = advancement_from_90_minutes(probability) if match.is_knockout else None
            response = PredictionResponse(
                prediction_id=str(uuid.uuid4()),
                match_id=match.id,
                competition=CompetitionRef(
                    id=match.competition.id,
                    name=match.competition.name,
                    name_ar=match.competition.name_ar,
                    season=match.competition.season,
                ),
                home_team=TeamRef(
                    id=match.home_team.id,
                    name=match.home_team.name,
                    name_ar=match.home_team.name_ar,
                ),
                away_team=TeamRef(
                    id=match.away_team.id,
                    name=match.away_team.name,
                    name_ar=match.away_team.name_ar,
                ),
                status="PRE_MATCH",
                generated_at=generated_at,
                data_as_of=data_as_of,
                data_freshness_seconds=age,
                outcomes_90_minutes=Outcome90(
                    home_win=probability.home_win,
                    draw=probability.draw,
                    away_win=probability.away_win,
                ),
                qualification=Qualification(**asdict(knockout)) if knockout else None,
                expected_goals=ExpectedGoals(home=home_xg, away=away_xg),
                likely_scorelines=[
                    Scoreline(
                        home_goals=item.home_goals,
                        away_goals=item.away_goals,
                        probability=item.probability,
                    )
                    for item in poisson.scorelines
                ],
                uncertainty=Uncertainty(level=uncertainty_level, reason_codes=warnings),
                evidence=evidence,
                data_quality=DataQuality(
                    completeness=completeness, freshness_seconds=age, stale=stale, warnings=warnings
                ),
                model=ModelMetadata(
                    ensemble_version=self.settings.prematch_model_version,
                    calibration_version=self.settings.calibration_version,
                    component_versions={item.name: item.version for item in components},
                ),
                provenance=[
                    {
                        "provider": self.provider.name,
                        "stage": match.stage.value,
                        "historical_matches_used": len(eligible_history),
                        "team_strength": {
                            "home_source": home_profile.source,
                            "away_source": away_profile.source,
                            "home_prior_source": home_profile.prior_source,
                            "away_prior_source": away_profile.prior_source,
                            "home_matches_played": home_profile.matches_played,
                            "away_matches_played": away_profile.matches_played,
                            "home_goal_difference": home_profile.goal_difference,
                            "away_goal_difference": away_profile.goal_difference,
                            "home_opponent_average_elo": home_profile.opponent_average_elo,
                            "away_opponent_average_elo": away_profile.opponent_average_elo,
                            "home_opponent_adjusted_form": home_profile.opponent_adjusted_form,
                            "away_opponent_adjusted_form": away_profile.opponent_adjusted_form,
                            "home_rest_days": home_profile.rest_days,
                            "away_rest_days": away_profile.rest_days,
                            "home_fatigue_penalty": home_profile.fatigue_penalty,
                            "away_fatigue_penalty": away_profile.fatigue_penalty,
                            "free_signals_used": self._free_signals_used(
                                home_profile, away_profile
                            ),
                            "free_signals_unavailable": [
                                "confirmed_lineups",
                                "injuries",
                                "market_odds",
                                "xg",
                                "weather",
                                "tactical_event_data",
                            ],
                        },
                        "data_timestamp": data_as_of.isoformat(),
                    }
                ],
                explanation=explanation,
                disclaimer_ar="هذه احتمالات تقديرية وليست ضماناً لنتيجة المباراة أو نصيحة للمراهنة.",
            )
            await self._persist(response, match)
            await self.broker.publish(response)
            PREDICTION_COUNT.labels("pre_match", "ok").inc()
            return response

    async def live(
        self, match_id: str, generated_at: datetime | None = None, event_limit: int | None = None
    ) -> PredictionResponse:
        generated_at = (generated_at or datetime.now(UTC)).astimezone(UTC)
        with PREDICTION_LATENCY.labels("live").time():
            match = await self.provider.get_match(match_id)
            events = [
                event
                for event in await self.provider.get_match_events(match_id)
                if event.received_at <= generated_at
            ]
            if event_limit is not None:
                events = events[:event_limit]
            events.sort(key=lambda event: (event.received_at, event.minute, event.second, event.id))
            state = CanonicalMatchState()
            for event in events:
                state.apply(event)
            try:
                statistics = await self.provider.get_match_statistics(match_id)
            except ProviderUnavailable:
                statistics = None
            if statistics and statistics.captured_at > generated_at + timedelta(seconds=5):
                statistics = None
            (
                home_xg,
                away_xg,
                _poisson,
                _pre_probability,
                components,
                completeness,
                _features,
                home_profile,
                away_profile,
                eligible_history,
            ) = await self._model_inputs(match, generated_at)
            minute = max((event.minute for event in events), default=match.minute or 0)
            has_shootout = any(event.type == EventType.SHOOTOUT_KICK for event in events)
            is_extra_time = minute > 90 and not has_shootout
            status = "PENALTIES" if has_shootout else "EXTRA_TIME" if is_extra_time else "LIVE"

            simulation = None
            shootout = None
            if has_shootout:
                shootout = simulate_penalty_shootout(
                    home_scored=state.shootout_home_scored,
                    away_scored=state.shootout_away_scored,
                    home_taken=state.shootout_home_taken,
                    away_taken=state.shootout_away_taken,
                    simulation_count=self.settings.simulation_count,
                    seed=self.settings.simulation_seed + len(events),
                )
                regulation_probability = Outcome90(home_win=0.0, draw=1.0, away_win=0.0)
                knockout = Qualification(
                    home_advance=shootout.home_advance,
                    away_advance=shootout.away_advance,
                    extra_time=1.0,
                    penalties=1.0,
                )
                explanation_probability = (
                    shootout.home_advance,
                    0.0,
                    shootout.away_advance,
                )
                remaining_home = 0.0
                remaining_away = 0.0
                likely_scorelines = [
                    Scoreline(
                        home_goals=state.score.home,
                        away_goals=state.score.away,
                        probability=1.0,
                    )
                ]
                explanation_scope = "في ركلات الترجيح"
            else:
                regulation = 120 if is_extra_time else 90
                simulation = simulate_live(
                    LiveSimulationInput(
                        minute=minute,
                        home_score=state.score.home,
                        away_score=state.score.away,
                        prematch_home_xg=home_xg,
                        prematch_away_xg=away_xg,
                        red_cards_home=state.red_cards_home,
                        red_cards_away=state.red_cards_away,
                        observed_xg_home=statistics.xg_home if statistics else None,
                        observed_xg_away=statistics.xg_away if statistics else None,
                        regulation_minutes=regulation,
                    ),
                    simulation_count=self.settings.simulation_count,
                    seed=self.settings.simulation_seed + len(events),
                )
                probability = self.calibrator.apply(simulation.probabilities)
                remaining_home = simulation.expected_remaining_home_goals
                remaining_away = simulation.expected_remaining_away_goals
                remaining_poisson = forecast_poisson(
                    remaining_home,
                    remaining_away,
                    self.settings.max_score_goals,
                )
                likely_scorelines = [
                    Scoreline(
                        home_goals=item.home_goals + state.score.home,
                        away_goals=item.away_goals + state.score.away,
                        probability=item.probability,
                    )
                    for item in remaining_poisson.scorelines
                ]
                if is_extra_time:
                    regulation_probability = Outcome90(home_win=0.0, draw=1.0, away_win=0.0)
                    extra_time_knockout = advancement_from_extra_time(probability)
                    knockout = Qualification(**asdict(extra_time_knockout))
                    explanation_probability = (
                        knockout.home_advance,
                        0.0,
                        knockout.away_advance,
                    )
                    explanation_scope = "للتأهل بعد الوقت الإضافي"
                else:
                    regulation_probability = Outcome90(
                        home_win=probability.home_win,
                        draw=probability.draw,
                        away_win=probability.away_win,
                    )
                    regulation_knockout = (
                        advancement_from_90_minutes(probability) if match.is_knockout else None
                    )
                    knockout = (
                        Qualification(**asdict(regulation_knockout))
                        if regulation_knockout
                        else None
                    )
                    explanation_probability = probability.as_tuple()
                    explanation_scope = "بعد 90 دقيقة"
            data_candidates = [match.updated_at, *(event.received_at for event in events)]
            if statistics:
                data_candidates.append(statistics.captured_at)
            data_as_of = min(generated_at, max(data_candidates))
            age = max(0, int((generated_at - data_as_of).total_seconds()))
            stale = age > self.settings.live_data_stale_after_seconds
            warnings = ["LIVE_DATA_STALE"] if stale else []
            if statistics is None:
                warnings.append("LIVE_STATISTICS_UNAVAILABLE")
            if any(event.type.value == "GOAL_CANCELLED" for event in events):
                warnings.append("PROVIDER_CORRECTION_APPLIED")
            if has_shootout and (state.shootout_home_taken == 0 or state.shootout_away_taken == 0):
                warnings.append("SHOOTOUT_STATE_PARTIAL")
            evidence = self._live_evidence(match, state, statistics, minute)
            uncertainty_level = "high" if stale or statistics is None else "medium"
            explanation = await self.explanations.build(
                home_name=match.home_team.name_ar or match.home_team.name,
                away_name=match.away_team.name_ar or match.away_team.name,
                home_probability=explanation_probability[0],
                draw_probability=explanation_probability[1],
                away_probability=explanation_probability[2],
                evidence=evidence,
                uncertainty=uncertainty_level,
                warning="البيانات المباشرة قديمة؛ لا ينبغي اعتبار الاحتمال مباشراً."
                if stale
                else None,
                scope_ar=explanation_scope,
            )
            previous = await self._previous(match_id)
            movement = None
            if previous:
                movement = {
                    "home_win": (
                        regulation_probability.home_win - previous.outcomes_90_minutes.home_win
                    ),
                    "draw": regulation_probability.draw - previous.outcomes_90_minutes.draw,
                    "away_win": (
                        regulation_probability.away_win - previous.outcomes_90_minutes.away_win
                    ),
                }
            response = PredictionResponse(
                prediction_id=str(uuid.uuid4()),
                match_id=match.id,
                competition=CompetitionRef(
                    id=match.competition.id,
                    name=match.competition.name,
                    name_ar=match.competition.name_ar,
                    season=match.competition.season,
                ),
                home_team=TeamRef(
                    id=match.home_team.id,
                    name=match.home_team.name,
                    name_ar=match.home_team.name_ar,
                ),
                away_team=TeamRef(
                    id=match.away_team.id,
                    name=match.away_team.name,
                    name_ar=match.away_team.name_ar,
                ),
                status=status,
                generated_at=generated_at,
                data_as_of=data_as_of,
                data_freshness_seconds=age,
                outcomes_90_minutes=regulation_probability,
                qualification=knockout,
                expected_goals=ExpectedGoals(
                    home=home_xg,
                    away=away_xg,
                    remaining_home=remaining_home,
                    remaining_away=remaining_away,
                ),
                likely_scorelines=likely_scorelines,
                uncertainty=Uncertainty(level=uncertainty_level, reason_codes=warnings),
                evidence=evidence,
                data_quality=DataQuality(
                    completeness=completeness
                    if statistics is None
                    else min(1.0, completeness + 0.15),
                    freshness_seconds=age,
                    stale=stale,
                    warnings=warnings,
                ),
                model=ModelMetadata(
                    ensemble_version=self.settings.live_model_version,
                    calibration_version=self.settings.calibration_version,
                    component_versions={item.name: item.version for item in components},
                    simulation_count=(
                        simulation.simulations if simulation else shootout.simulations
                    ),
                    simulation_seed=(simulation.seed if simulation else shootout.seed),
                ),
                provenance=[
                    {
                        "provider": self.provider.name,
                        "stage": match.stage.value,
                        "event_count": len(events),
                        "score": state.score.model_dump(),
                        "shootout": {
                            "home_scored": state.shootout_home_scored,
                            "away_scored": state.shootout_away_scored,
                            "home_taken": state.shootout_home_taken,
                            "away_taken": state.shootout_away_taken,
                        },
                        "historical_matches_used": len(eligible_history),
                        "team_strength": {
                            "home_source": home_profile.source,
                            "away_source": away_profile.source,
                            "home_prior_source": home_profile.prior_source,
                            "away_prior_source": away_profile.prior_source,
                            "home_matches_played": home_profile.matches_played,
                            "away_matches_played": away_profile.matches_played,
                            "home_goal_difference": home_profile.goal_difference,
                            "away_goal_difference": away_profile.goal_difference,
                            "home_opponent_average_elo": home_profile.opponent_average_elo,
                            "away_opponent_average_elo": away_profile.opponent_average_elo,
                            "home_opponent_adjusted_form": home_profile.opponent_adjusted_form,
                            "away_opponent_adjusted_form": away_profile.opponent_adjusted_form,
                            "home_rest_days": home_profile.rest_days,
                            "away_rest_days": away_profile.rest_days,
                            "home_fatigue_penalty": home_profile.fatigue_penalty,
                            "away_fatigue_penalty": away_profile.fatigue_penalty,
                            "free_signals_used": self._free_signals_used(
                                home_profile, away_profile
                            ),
                            "free_signals_unavailable": [
                                "confirmed_lineups",
                                "injuries",
                                "market_odds",
                                "xg",
                                "weather",
                                "tactical_event_data",
                            ],
                        },
                        "data_timestamp": data_as_of.isoformat(),
                    }
                ],
                explanation=explanation,
                movement_since_previous=movement,
                disclaimer_ar="هذه احتمالات تقديرية وليست ضماناً لنتيجة المباراة أو نصيحة للمراهنة.",
            )
            await self._persist(response, match)
            await self.broker.publish(response)
            PREDICTION_COUNT.labels("live", "ok").inc()
            return response

    def _evidence(
        self,
        match,
        home_xg: float,
        away_xg: float,
        home_profile: TeamStrengthProfile,
        away_profile: TeamStrengthProfile,
    ) -> list[EvidenceItem]:
        home_name = match.home_team.name_ar or match.home_team.name
        away_name = match.away_team.name_ar or match.away_team.name
        elo_diff = home_profile.elo - away_profile.elo
        direction = (
            "HOME"
            if elo_diff > 15
            else "AWAY"
            if elo_diff < -15
            else "NEUTRAL"
        )
        evidence = [
            EvidenceItem(
                code="TEAM_STRENGTH",
                direction=direction,
                importance=0.35,
                description_ar=(
                    "تقييم القوة يستخدم النتائج المكتملة المتاحة قبل المباراة، مع تحديث تصنيف "
                    "إيلو والهجوم والدفاع بشكل حتمي من مصدر البيانات."
                ),
            )
        ]
        if home_profile.matches_played or away_profile.matches_played:
            form_direction = (
                "HOME"
                if home_profile.goal_difference > away_profile.goal_difference
                else "AWAY"
                if away_profile.goal_difference > home_profile.goal_difference
                else "NEUTRAL"
            )
            evidence.append(
                EvidenceItem(
                    code="TOURNAMENT_FORM",
                    direction=form_direction,
                    importance=0.30,
                    description_ar=(
                        f"الشكل الحالي المعدل بقوة الخصوم: {home_name} لعب "
                        f"{home_profile.matches_played} مباريات بفارق أهداف "
                        f"{home_profile.goal_difference}، و{away_name} لعب "
                        f"{away_profile.matches_played} مباريات بفارق أهداف "
                        f"{away_profile.goal_difference}."
                    ),
                )
            )
        else:
            evidence.append(
                EvidenceItem(
                    code="TOURNAMENT_FORM_LIMITED",
                    direction="NEUTRAL",
                    importance=0.20,
                    description_ar=(
                        "لا توجد نتائج كأس عالم مكتملة كافية قبل هذه المباراة للمنتخبين، "
                        "لذلك يبقى التقييم محافظا."
                    ),
                )
            )
        if home_profile.rest_days is not None and away_profile.rest_days is not None:
            rest_diff = home_profile.rest_days - away_profile.rest_days
            rest_direction = (
                "HOME" if rest_diff > 0.5 else "AWAY" if rest_diff < -0.5 else "NEUTRAL"
            )
            evidence.append(
                EvidenceItem(
                    code="REST_FATIGUE",
                    direction=rest_direction,
                    importance=0.12,
                    description_ar=(
                        f"عامل الراحة: {home_name} لديه {home_profile.rest_days:.1f} يوم راحة، "
                        f"و{away_name} لديه {away_profile.rest_days:.1f} يوم."
                    ),
                )
            )
        evidence.extend(
            [
                EvidenceItem(
                    code="EXPECTED_GOALS",
                    direction="HOME" if home_xg > away_xg else "AWAY",
                    importance=0.30,
                    description_ar=(
                        "تقدير الأهداف المتوقعة قبل المباراة يميل بشكل طفيف إلى أحد الطرفين."
                    ),
                ),
                EvidenceItem(
                    code="NEUTRAL_VENUE",
                    direction="NEUTRAL",
                    importance=0.10,
                    description_ar="المباراة على ملعب محايد، لذلك لم تُضف أفضلية أرض اعتيادية.",
                ),
            ]
        )
        return evidence

    @staticmethod
    def _free_signals_used(
        home_profile: TeamStrengthProfile, away_profile: TeamStrengthProfile
    ) -> list[str]:
        signals = [
            "worldcup26_fixtures_scores",
            "opponent_adjusted_history",
            "tournament_form",
            "rest_days",
        ]
        prior_sources = {home_profile.prior_source, away_profile.prior_source}
        if "world_football_elo" in prior_sources:
            signals.append("world_football_elo_prior")
        elif any(
            "configured_prior" in source
            for source in (home_profile.source, away_profile.source)
        ):
            signals.append("configured_global_prior")
        return signals

    def _live_evidence(
        self, match, state: CanonicalMatchState, statistics: MatchStatistics | None, minute: int
    ) -> list[EvidenceItem]:
        home = match.home_team.name_ar or match.home_team.name
        away = match.away_team.name_ar or match.away_team.name
        evidence = [
            EvidenceItem(
                code="CURRENT_SCORE",
                direction="HOME"
                if state.score.home > state.score.away
                else "AWAY"
                if state.score.away > state.score.home
                else "DRAW",
                importance=0.55,
                description_ar=(
                    "النتيجة الحالية والوقت المتبقي هما العاملان الأقوى في التحديث المباشر."
                ),
            )
        ]
        if statistics:
            stat_parts = []
            if statistics.possession_home is not None and statistics.possession_away is not None:
                stat_parts.append(
                    f"الاستحواذ {home} {statistics.possession_home:.1f}% "
                    f"و{away} {statistics.possession_away:.1f}%"
                )
            if statistics.shots_home is not None and statistics.shots_away is not None:
                stat_parts.append(
                    f"التسديدات {home} {statistics.shots_home} و{away} {statistics.shots_away}"
                )
            if (
                statistics.shots_on_target_home is not None
                and statistics.shots_on_target_away is not None
            ):
                stat_parts.append(
                    f"على المرمى {home} {statistics.shots_on_target_home} "
                    f"و{away} {statistics.shots_on_target_away}"
                )
            if statistics.passes_home is not None and statistics.passes_away is not None:
                stat_parts.append(
                    f"التمريرات {home} {statistics.passes_home} و{away} {statistics.passes_away}"
                )
            if (
                statistics.pass_accuracy_home is not None
                and statistics.pass_accuracy_away is not None
            ):
                stat_parts.append(
                    f"دقة التمرير {home} {statistics.pass_accuracy_home:.1f}% "
                    f"و{away} {statistics.pass_accuracy_away:.1f}%"
                )
            if statistics.corners_home is not None and statistics.corners_away is not None:
                stat_parts.append(
                    f"الركنيات {home} {statistics.corners_home} و{away} {statistics.corners_away}"
                )
            if statistics.fouls_home is not None and statistics.fouls_away is not None:
                stat_parts.append(
                    f"الأخطاء {home} {statistics.fouls_home} و{away} {statistics.fouls_away}"
                )
            if (
                statistics.yellow_cards_home is not None
                and statistics.yellow_cards_away is not None
            ):
                stat_parts.append(
                    f"البطاقات الصفراء {home} {statistics.yellow_cards_home} "
                    f"و{away} {statistics.yellow_cards_away}"
                )
            if statistics.red_cards_home or statistics.red_cards_away:
                stat_parts.append(
                    f"البطاقات الحمراء {home} {statistics.red_cards_home} "
                    f"و{away} {statistics.red_cards_away}"
                )
            if statistics.offsides_home is not None and statistics.offsides_away is not None:
                stat_parts.append(
                    f"التسلل {home} {statistics.offsides_home} و{away} {statistics.offsides_away}"
                )
            if statistics.saves_home is not None and statistics.saves_away is not None:
                stat_parts.append(
                    f"تصديات الحارس {home} {statistics.saves_home} "
                    f"و{away} {statistics.saves_away}"
                )
            if stat_parts:
                shot_direction = (
                    "HOME"
                    if (statistics.shots_on_target_home or 0)
                    > (statistics.shots_on_target_away or 0)
                    else "AWAY"
                    if (statistics.shots_on_target_away or 0)
                    > (statistics.shots_on_target_home or 0)
                    else "NEUTRAL"
                )
                evidence.append(
                    EvidenceItem(
                        code="LIVE_TEAM_STATS",
                        direction=shot_direction,
                        importance=0.30,
                        description_ar="الإحصائيات المباشرة: " + "؛ ".join(stat_parts) + ".",
                    )
                )
        if state.red_cards_home != state.red_cards_away:
            evidence.append(
                EvidenceItem(
                    code="RED_CARD_STATE",
                    direction="AWAY" if state.red_cards_home > state.red_cards_away else "HOME",
                    importance=0.25,
                    description_ar="حالة الطرد غيّرت شدة التسجيل المتوقعة ضمن حدود مضبوطة.",
                )
            )
        if statistics and statistics.xg_home is not None and statistics.xg_away is not None:
            evidence.append(
                EvidenceItem(
                    code="LIVE_XG",
                    direction="HOME" if statistics.xg_home > statistics.xg_away else "AWAY",
                    importance=0.20,
                    description_ar="بيانات الفرص المتوقعة المتاحة دعمت تحديث شدة التسجيل المتبقية.",
                )
            )
        return evidence

    async def latest(self, match_id: str) -> PredictionResponse | None:
        return await self._previous(match_id)

    async def history(self, match_id: str, limit: int = 50) -> list[PredictionResponse]:
        async for session in self.database.session():
            rows = await self.repository.history(session, match_id, limit)
            return [PredictionResponse.model_validate(row.payload_json) for row in rows]
        return []

    async def record_telegram_user(self, telegram_user_id: int) -> None:
        user_hash = hash_identifier(str(telegram_user_id), pepper=self.settings.api_key)
        async for session in self.database.session():
            await self.telegram_user_repository.touch(session, user_hash=user_hash)
            await session.commit()

    async def telegram_user_count(self) -> int:
        async for session in self.database.session():
            return await self.telegram_user_repository.active_count(session)
        return 0

    async def prediction_archive(self, limit: int = 20) -> list[dict[str, object]]:
        async for session in self.database.session():
            rows = await self.repository.finished_archive(session, limit)
            archive = []
            seen_matches = set()
            for prediction_row, match_row in rows:
                if match_row.id in seen_matches:
                    continue
                seen_matches.add(match_row.id)
                prediction = PredictionResponse.model_validate(prediction_row.payload_json)
                p90 = prediction.outcomes_90_minutes
                predicted_key = max(
                    {
                        "home": p90.home_win,
                        "draw": p90.draw,
                        "away": p90.away_win,
                    }.items(),
                    key=lambda item: item[1],
                )[0]
                if match_row.score_home > match_row.score_away:
                    actual_key = "home"
                elif match_row.score_away > match_row.score_home:
                    actual_key = "away"
                else:
                    actual_key = "draw"
                archive.append(
                    {
                        "prediction": prediction,
                        "home_score": match_row.score_home,
                        "away_score": match_row.score_away,
                        "predicted_key": predicted_key,
                        "actual_key": actual_key,
                        "correct": predicted_key == actual_key,
                        "kickoff": match_row.kickoff,
                    }
                )
                if len(archive) >= limit:
                    break
            return archive
        return []

    async def subscribe(self, *, telegram_user_id: int, match_id: str, kind: str) -> None:
        if kind not in {"start", "probability_delta"}:
            raise ValueError("unsupported subscription kind")
        match = await self.provider.get_match(match_id)
        user_hash = hash_identifier(str(telegram_user_id), pepper=self.settings.api_key)
        async for session in self.database.session():
            await self.catalog_repository.upsert_match_graph(session, match)
            await session.flush()
            await self.subscription_repository.upsert(
                session,
                user_hash=user_hash,
                match_id=match_id,
                kind=kind,
                threshold=self.settings.telegram_notification_min_delta,
            )
