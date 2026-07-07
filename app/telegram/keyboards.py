from __future__ import annotations

from collections.abc import Sequence

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.domain.entities import Match

_MATCH_ACTION_PREFIX = {
    "match": "match",
    "predict": "predict",
    "explain": "explain",
    "live": "live",
}


def main_menu() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("🔮 توقعات المباريات القادمة", callback_data="matches:prematch:0")],
        [InlineKeyboardButton("🔴 توقع مباشر", callback_data="matches:live_forecast:0")],
        [InlineKeyboardButton("📊 توقعاتنا لحد اللحظة", callback_data="predictions:archive:0")],
    ]
    return InlineKeyboardMarkup(rows)


def matches_page(
    matches: Sequence[Match],
    *,
    scope: str,
    page: int,
    page_size: int = 6,
    action: str = "match",
) -> InlineKeyboardMarkup:
    page = max(0, page)
    start = page * page_size
    visible = matches[start : start + page_size]
    rows = []
    callback_prefix = _MATCH_ACTION_PREFIX.get(action, "match")
    for match in visible:
        home = match.home_team.name_ar or match.home_team.name
        away = match.away_team.name_ar or match.away_team.name
        rows.append(
            [
                InlineKeyboardButton(
                    f"{home} vs {away}", callback_data=f"{callback_prefix}:{match.id}"
                )
            ]
        )
    navigation = []
    if page > 0:
        navigation.append(
            InlineKeyboardButton("السابق", callback_data=f"matches:{scope}:{page - 1}")
        )
    if start + page_size < len(matches):
        navigation.append(
            InlineKeyboardButton("التالي", callback_data=f"matches:{scope}:{page + 1}")
        )
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton("القائمة الرئيسية", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


def match_actions(_match_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("القائمة الرئيسية", callback_data="menu")],
        ]
    )
