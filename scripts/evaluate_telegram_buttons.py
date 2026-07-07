from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app.core.config import Settings
from app.providers.football.factory import build_football_provider
from app.repositories.database import Database
from app.services.events import PredictionEventBroker
from app.services.explanations import ExplanationService
from app.services.predictions import PredictionService
from app.telegram.handlers import callback
from app.telegram.keyboards import main_menu, match_actions, matches_page

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


class CapturedQuery:
    def __init__(self, data: str) -> None:
        self.data = data
        self.text: str | None = None
        self.reply_markup: Any = None
        self.replies: list[str] = []
        self.answer_count = 0
        self.message = self

    async def answer(self) -> None:
        self.answer_count += 1

    async def edit_message_text(self, text: str, *, reply_markup=None) -> None:
        self.text = text
        self.reply_markup = reply_markup

    async def reply_text(self, text: str, *, reply_markup=None) -> None:
        self.replies.append(text)
        self.reply_markup = reply_markup


def _buttons(markup) -> list[dict[str, str]]:
    return [
        {"label": button.text, "callback_data": button.callback_data or ""}
        for row in markup.inline_keyboard
        for button in row
    ]


async def _press(data: str, context, update_id: int) -> CapturedQuery:
    query = CapturedQuery(data)
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123),
        update_id=update_id,
    )
    await callback(update, context)
    return query


async def _build_context(tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'telegram-buttons.db'}",
        football_provider="worldcup26",
        football_provider_fallbacks="thesportsdb",
        world_cup_only=True,
        cache_static_ttl_seconds=0,
        cache_fixtures_ttl_seconds=0,
        llm_enabled=False,
        telegram_rate_limit_per_minute=1000,
        arabic_digits_enabled=False,
        live_polling_enabled=False,
    )
    database = Database(settings)
    await database.create_all()
    provider = build_football_provider(settings)
    service = PredictionService(
        settings=settings,
        provider=provider,
        database=database,
        explanations=ExplanationService(None),
        broker=PredictionEventBroker(),
    )
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "settings": settings,
                "provider": provider,
                "prediction_service": service,
            }
        )
    )
    return context, database


def _eval_date():
    value = os.environ.get("WORLD_CUP_EVAL_DATE")
    if value:
        return datetime.strptime(value, "%Y-%m-%d").date()
    return datetime.now(UTC).date()


async def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        context, database = await _build_context(Path(directory))
        try:
            provider = context.application.bot_data["provider"]
            provider_items = getattr(provider, "providers", [provider])
            provider_names = [
                getattr(item, "name", "unknown") for item in provider_items
            ]
            eval_date = _eval_date()
            today_matches = await provider.list_matches(date_from=eval_date, date_to=eval_date)
            if not today_matches:
                raise AssertionError(f"no World Cup matches returned for {eval_date.isoformat()}")
            first_match_id = today_matches[0].id
            list_markup = matches_page(today_matches, scope="today", page=0)
            list_button = _buttons(list_markup)[0]
            prediction_markup = matches_page(
                today_matches, scope="prematch", page=0, action="predict"
            )
            prediction_button = _buttons(prediction_markup)[0]
            menu_buttons = _buttons(main_menu())
            action_buttons = _buttons(match_actions(first_match_id))
            all_buttons = [
                *({"surface": "main_menu", **button} for button in menu_buttons),
                *({"surface": "match_actions", **button} for button in action_buttons),
                {"surface": "match_list", **list_button},
                {"surface": "prediction_list", **prediction_button},
            ]

            callback_counts = Counter(button["callback_data"] for button in menu_buttons)
            duplicate_top_level_callbacks = sorted(
                callback_data for callback_data, count in callback_counts.items() if count > 1
            )

            results = []
            predict_text = ""
            archive_text = ""
            for index, button in enumerate(all_buttons, start=1):
                query = await _press(button["callback_data"], context, index)
                text = query.text or ""
                if button["callback_data"] == f"predict:{first_match_id}":
                    predict_text = text
                if button["callback_data"] == "predictions:archive:0":
                    archive_text = text
                first_line = text.splitlines()[0] if text else ""
                unhandled = "هذا الخيار غير متاح" in text or "تعذر تنفيذ الطلب" in text
                results.append(
                    {
                        "surface": button["surface"],
                        "label": button["label"],
                        "callback_data": button["callback_data"],
                        "first_line": first_line,
                        "handled": bool(text) and not unhandled,
                    }
                )

            text_groups: dict[str, list[str]] = defaultdict(list)
            for result in results:
                text_groups[result["first_line"]].append(result["callback_data"])
            duplicate_first_lines = {
                first_line: callbacks
                for first_line, callbacks in text_groups.items()
                if first_line and len(callbacks) > 1
            }

            today_labels = [
                f"{match.home_team.name_ar or match.home_team.name} vs "
                f"{match.away_team.name_ar or match.away_team.name}"
                for match in today_matches
            ]
            uncertainty_label = (
                "\u062f\u0631\u062c\u0629 \u0639\u062f\u0645 "
                "\u0627\u0644\u064a\u0642\u064a\u0646"
            )
            qualification_label = (
                "\u0627\u062d\u062a\u0645\u0627\u0644 "
                "\u0627\u0644\u062a\u0623\u0647\u0644"
            )
            reasons_label = (
                "\u0644\u0645\u0627\u0630\u0627 \u0647\u0630\u0627 "
                "\u0627\u0644\u062a\u0648\u0642\u0639"
            )
            goals_label = (
                "\u062a\u0648\u0642\u0639 "
                "\u0627\u0644\u0623\u0647\u062f\u0627\u0641"
            )
            exact_scores_label = (
                "\u0623\u0642\u0631\u0628 "
                "\u0627\u0644\u0646\u062a\u0627\u0626\u062c"
            )
            player_names_label = (
                "\u0623\u0633\u0645\u0627\u0621 "
                "\u0628\u0627\u0631\u0632\u0629"
            )
            home_label = (
                "\u0641\u0648\u0632 \u0635\u0627\u062d\u0628 "
                "\u0627\u0644\u0623\u0631\u0636"
            )
            away_label = "\u0641\u0648\u0632 \u0627\u0644\u0636\u064a\u0641"
            likely_result_label = (
                "\u0627\u0644\u0646\u062a\u064a\u062c\u0629 "
                "\u0627\u0644\u0645\u062d\u062a\u0645\u0644\u0629"
            )
            win_probabilities_label = (
                "\u0627\u062d\u062a\u0645\u0627\u0644\u0627\u062a "
                "\u0627\u0644\u0641\u0648\u0632"
            )
            goal_probabilities_label = (
                "\u0627\u062d\u062a\u0645\u0627\u0644\u0627\u062a "
                "\u0627\u0644\u0623\u0647\u062f\u0627\u0641"
            )
            removed_callbacks = {
                "matches:today:0",
                "matches:upcoming:0",
                "matches:live:0",
                "matches:explain:0",
                "matches:subscribe:0",
                "refresh:last",
                "methodology",
                "settings",
            }
            expected_main_callbacks = [
                "matches:prematch:0",
                "matches:live_forecast:0",
                "predictions:archive:0",
            ]
            predict_contract_ok = (
                reasons_label in predict_text
                and likely_result_label in predict_text
                and win_probabilities_label in predict_text
                and goal_probabilities_label in predict_text
                and goals_label not in predict_text
                and exact_scores_label not in predict_text
                and player_names_label not in predict_text
                and uncertainty_label not in predict_text
                and qualification_label not in predict_text
            )
            arabic_digit_chars = set("٠١٢٣٤٥٦٧٨٩")
            predict_uses_english_digits = not any(
                char in arabic_digit_chars for char in predict_text
            )
            report = {
                "passed": (
                    provider_names[0] == "worldcup26"
                    and [button["callback_data"] for button in menu_buttons]
                    == expected_main_callbacks
                    and not any(
                        button["callback_data"] in removed_callbacks
                        for button in menu_buttons + action_buttons
                    )
                    and not duplicate_top_level_callbacks
                    and all(result["handled"] for result in results)
                    and "المغرب vs الأرجنتين" not in today_labels
                ),
                "providers": provider_names,
                "eval_date": eval_date.isoformat(),
                "buttons_checked": len(results),
                "today_labels": today_labels,
                "main_menu_callbacks": [button["callback_data"] for button in menu_buttons],
                "removed_buttons_absent": not any(
                    button["callback_data"] in removed_callbacks
                    for button in menu_buttons + action_buttons
                ),
                "predict_is_clean_narrative": predict_contract_ok,
                "predict_has_likely_result": likely_result_label in predict_text,
                "predict_has_win_probabilities": win_probabilities_label in predict_text,
                "predict_has_goal_probabilities": goal_probabilities_label in predict_text,
                "predict_removed_uncertainty": uncertainty_label not in predict_text,
                "predict_removed_qualification": qualification_label not in predict_text,
                "predict_uses_english_digits": predict_uses_english_digits,
                "archive_uses_country_names": home_label not in archive_text
                and away_label not in archive_text,
                "duplicate_top_level_callbacks": duplicate_top_level_callbacks,
                "duplicate_first_lines": duplicate_first_lines,
                "results": results,
            }
            report["passed"] = (
                report["passed"]
                and predict_contract_ok
                and predict_uses_english_digits
                and report["archive_uses_country_names"]
            )
            print(json.dumps(report, ensure_ascii=False, indent=2))
            if not report["passed"]:
                raise SystemExit(1)
        finally:
            provider = context.application.bot_data["provider"]
            for item in getattr(provider, "providers", [provider]):
                close = getattr(item, "close", None)
                if close:
                    await close()
            await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
