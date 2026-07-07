from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Any

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from app.core.timezones import resolve_timezone
from app.domain.enums import MatchStatus
from app.providers.football.base import FootballProviderError
from app.services.arabic import telegram_prediction_details_text, telegram_prediction_text
from app.telegram.formatting import split_message
from app.telegram.keyboards import main_menu, match_actions, matches_page

_LIVE_STATUSES = {
    MatchStatus.LIVE,
    MatchStatus.HALF_TIME,
    MatchStatus.EXTRA_TIME,
    MatchStatus.PENALTIES,
}
_PREMATCH_STATUSES = {MatchStatus.SCHEDULED, MatchStatus.PRE_MATCH}
_HIDDEN_LIST_STATUSES = {MatchStatus.FINISHED, MatchStatus.POSTPONED, MatchStatus.CANCELLED}
_LIVE_SOON_WINDOW = timedelta(minutes=20)
_MATCH_SCOPE_PROMPTS = {
    "prematch": "اختر مباراة قادمة للحصول على التوقع:",
    "live_forecast": "اختر مباراة مباشرة أو تبدأ الآن للحصول على التوقع:",
}
_MATCH_SCOPE_EMPTY = {
    "prematch": "لا توجد مباريات كأس عالم قادمة متاحة للتوقع الآن.",
    "live_forecast": "لا توجد مباريات كأس عالم مباشرة أو قريبة من البداية الآن.",
}
_MATCH_SCOPE_ACTIONS = {
    "prematch": "predict",
    "live_forecast": "live",
}
_EVENT_TYPE_AR = {
    "GOAL": "هدف",
    "GOAL_CANCELLED": "إلغاء هدف",
    "OWN_GOAL": "هدف عكسي",
    "PENALTY_SCORED": "ركلة جزاء مسجلة",
    "PENALTY_MISSED": "ركلة جزاء ضائعة",
    "RED_CARD": "بطاقة حمراء",
    "YELLOW_RED": "بطاقة صفراء ثانية",
    "SUBSTITUTION": "تبديل",
    "PERIOD_START": "بداية فترة",
    "PERIOD_END": "نهاية فترة",
    "SHOOTOUT_KICK": "ركلة ترجيح",
    "OTHER": "حدث",
}


async def _safe_edit(query: Any, text: str, *, reply_markup=None) -> None:
    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
    except TelegramError:
        if query.message:
            await query.message.reply_text(text, reply_markup=reply_markup)


def _allowed(update: Update, settings) -> bool:
    allowed = settings.telegram_allowed_user_id_set
    user = update.effective_user
    return not allowed or (user is not None and user.id in allowed)


def _duplicate(update: Update, bot_data: dict) -> bool:
    update_id = update.update_id
    if update_id is None:
        return False
    seen: set[int] = bot_data.setdefault("seen_update_ids", set())
    order: deque[int] = bot_data.setdefault("seen_update_order", deque())
    if update_id in seen:
        return True
    seen.add(update_id)
    order.append(update_id)
    while len(order) > 1000:
        seen.discard(order.popleft())
    return False


def _rate_limited(user_id: int, bot_data: dict, *, limit: int) -> bool:
    now = time.monotonic()
    windows: dict[int, deque[float]] = bot_data.setdefault(
        "telegram_rate_windows", defaultdict(deque)
    )
    entries = windows[user_id]
    while entries and entries[0] <= now - 60:
        entries.popleft()
    if len(entries) >= limit:
        return True
    entries.append(now)
    return False


def _local_today(timezone_name: str):
    zone = resolve_timezone(timezone_name)
    return datetime.now(zone).date()


async def _main_menu_text(service) -> str:
    try:
        user_count = await service.telegram_user_count()
    except Exception:
        user_count = 0
    return "\n".join(
        [
            "اختر الخدمة المطلوبة:",
            f"عدد المستخدمين: {user_count}",
        ]
    )


async def _record_user(service, user) -> None:
    if user is None:
        return
    try:
        await service.record_telegram_user(user.id)
    except Exception:
        return


def _archive_text(items: list[dict[str, object]], *, arabic_digits: bool = False) -> str:
    if not items:
        return "لا توجد توقعات منتهية محفوظة حتى الآن."
    lines = ["توقعاتنا لحد اللحظة", ""]
    correct = sum(1 for item in items if item.get("correct") is True)
    lines.append(f"الدقة على العينة المعروضة: {correct}/{len(items)}")
    lines.append("")
    for item in items:
        prediction = item["prediction"]
        home = prediction.home_team.name_ar or prediction.home_team.name
        away = prediction.away_team.name_ar or prediction.away_team.name
        predicted_key = str(item["predicted_key"])
        actual_key = str(item["actual_key"])
        country_labels = {"home": home, "away": away, "draw": "تعادل"}
        mark = "صح" if item.get("correct") else "خطأ"
        lines.extend(
            [
                f"• {home} vs {away}",
                f"  التوقع: {country_labels[predicted_key]} - {mark}",
                (
                    f"  النتيجة: {item['home_score']}-{item['away_score']} "
                    f"({country_labels[actual_key]})"
                ),
            ]
        )
    return "\n".join(lines)


async def _list_matches(provider, scope: str, settings):
    today = _local_today(settings.app_timezone)
    zone = resolve_timezone(settings.app_timezone)
    now = datetime.now(zone)
    if scope in {"live", "live_forecast"}:
        live_matches = await provider.get_live_matches()
        today_matches = await provider.list_matches(date_from=today, date_to=today)
        live_ids = {match.id for match in live_matches}
        starting_soon = [
            match
            for match in today_matches
            if match.id not in live_ids
            and match.status in _PREMATCH_STATUSES
            and now <= match.kickoff.astimezone(zone) <= now + _LIVE_SOON_WINDOW
        ]
        return sorted(
            [*live_matches, *starting_soon],
            key=lambda match: (match.kickoff, match.id),
        )
    if scope == "today":
        matches = await provider.list_matches(date_from=today, date_to=today)
        return [match for match in matches if match.status not in _HIDDEN_LIST_STATUSES]
    if scope == "upcoming":
        matches = await provider.list_matches(date_from=today, date_to=today + timedelta(days=30))
        return [
            match
            for match in matches
            if match.status in _PREMATCH_STATUSES and match.kickoff.astimezone(zone) >= now
        ]
    matches = await provider.list_matches()
    if scope == "prematch":
        return [
            match
            for match in matches
            if match.status in _PREMATCH_STATUSES and match.kickoff.astimezone(zone) >= now
        ]
    return matches


async def _prediction_for_match(service, provider, match_id: str, *, force_live: bool = False):
    match = await provider.get_match(match_id)
    if match.status in _LIVE_STATUSES:
        return await service.live(match_id)
    if force_live and match.kickoff <= datetime.now(match.kickoff.tzinfo):
        return await service.live(match_id)
    return await service.pre_match(match_id)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    service = context.application.bot_data["prediction_service"]
    if not _allowed(update, settings):
        if update.effective_message:
            await update.effective_message.reply_text("هذا المستخدم غير مصرح له باستخدام البوت.")
        return
    await _record_user(service, update.effective_user)
    if update.effective_message:
        await update.effective_message.reply_text(
            await _main_menu_text(service), reply_markup=main_menu()
        )


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    bot_data = context.application.bot_data
    settings = bot_data["settings"]
    await query.answer()
    if not _allowed(update, settings):
        await _safe_edit(query, "هذا المستخدم غير مصرح له باستخدام البوت.")
        return
    if _duplicate(update, bot_data):
        return
    user = update.effective_user
    if user and _rate_limited(user.id, bot_data, limit=settings.telegram_rate_limit_per_minute):
        await _safe_edit(query, "تم تجاوز حد الطلبات المؤقت. أعد المحاولة بعد دقيقة.")
        return

    provider = bot_data["provider"]
    service = bot_data["prediction_service"]
    await _record_user(service, user)
    data = query.data or ""

    try:
        if data == "menu":
            await _safe_edit(query, await _main_menu_text(service), reply_markup=main_menu())
            return

        if data.startswith("predictions:archive"):
            archive = await service.prediction_archive(limit=7)
            await _safe_edit(
                query,
                _archive_text(archive, arabic_digits=settings.arabic_digits_enabled),
                reply_markup=main_menu(),
            )
            return

        if data.startswith("matches:"):
            _, scope, page_text = (data.split(":", 2) + ["0", "0"])[0:3]
            page = max(0, int(page_text))
            matches = await _list_matches(provider, scope, settings)
            if not matches:
                await _safe_edit(
                    query,
                    _MATCH_SCOPE_EMPTY.get(
                        scope, "لا توجد مباريات كأس عالم متاحة وفق مصدر البيانات الحالي."
                    ),
                    reply_markup=main_menu(),
                )
                return
            await _safe_edit(
                query,
                _MATCH_SCOPE_PROMPTS.get(scope, "اختر المباراة:"),
                reply_markup=matches_page(
                    matches,
                    scope=scope,
                    page=page,
                    action=_MATCH_SCOPE_ACTIONS.get(scope, "match"),
                ),
            )
            return

        if data.startswith("match:"):
            match_id = data.split(":", 1)[1]
            match = await provider.get_match(match_id)
            home = match.home_team.name_ar or match.home_team.name
            away = match.away_team.name_ar or match.away_team.name
            await _safe_edit(query, f"{home} vs {away}", reply_markup=match_actions(match.id))
            return

        if data.startswith(("predict:", "refresh:", "live:")):
            action, match_id = data.split(":", 1)
            if match_id == "last":
                match_id = bot_data.get("last_match_by_user", {}).get(user.id if user else 0)
                if not match_id:
                    await _safe_edit(query, "اختر مباراة أولاً.", reply_markup=main_menu())
                    return
            prediction = await _prediction_for_match(
                service, provider, match_id, force_live=action == "live"
            )
            text = telegram_prediction_text(
                prediction, arabic_digits=settings.arabic_digits_enabled
            )
            if action == "refresh":
                text = "تم تحديث الاحتمالات من مصدر البيانات الحالي.\n\n" + text
            elif action == "live":
                text = "تحديث الاحتمالات المباشرة الآن:\n\n" + text
            chunks = split_message(text)
            await _safe_edit(query, chunks[0], reply_markup=match_actions(match_id))
            for chunk in chunks[1:]:
                if query.message:
                    await query.message.reply_text(chunk)
            bot_data["last_match_by_user"] = {
                **bot_data.get("last_match_by_user", {}),
                user.id if user else 0: match_id,
            }
            return

        if data.startswith(("details:", "explain:")):
            action, match_id = data.split(":", 1)
            prediction = await service.latest(match_id)
            if prediction is None:
                prediction = await _prediction_for_match(service, provider, match_id)
            if action == "details":
                text = telegram_prediction_details_text(
                    prediction, arabic_digits=settings.arabic_digits_enabled
                )
            else:
                factors = "\n".join(f"• {item}" for item in prediction.explanation.key_factors_ar)
                text = "\n".join(
                    filter(
                        None,
                        [
                            "شرح التوقع",
                            f"{prediction.home_team.name_ar or prediction.home_team.name} vs "
                            f"{prediction.away_team.name_ar or prediction.away_team.name}",
                            "",
                            prediction.explanation.summary_ar,
                            "",
                            factors,
                            "",
                            prediction.explanation.uncertainty_ar,
                            prediction.explanation.data_warning_ar,
                        ],
                    )
                )
            await _safe_edit(query, text, reply_markup=match_actions(match_id))
            return

        if data.startswith("lineup:"):
            match_id = data.split(":", 1)[1]
            match = await provider.get_match(match_id)
            team_names = {
                match.home_team.id: match.home_team.name_ar or match.home_team.name,
                match.away_team.id: match.away_team.name_ar or match.away_team.name,
            }
            try:
                lineups = await provider.get_lineups(match_id)
            except FootballProviderError:
                lineups = []
            if not lineups:
                text = "لا توجد تشكيلة مؤكدة لدى مصدر البيانات الحالي."
            else:
                lines = ["التشكيلات المتاحة:"]
                for lineup in lineups:
                    team_id = lineup.get("team_id", "-")
                    team_name = team_names.get(team_id, team_id)
                    formation = lineup.get("formation") or "غير معروفة"
                    confirmed = "مؤكدة" if lineup.get("confirmed") else "غير مؤكدة"
                    lines.append(f"• {team_name}: {formation} - {confirmed}")
                text = "\n".join(lines)
            await _safe_edit(query, text, reply_markup=match_actions(match_id))
            return

        if data.startswith("events:"):
            match_id = data.split(":", 1)[1]
            match = await provider.get_match(match_id)
            side_names = {
                "HOME": match.home_team.name_ar or match.home_team.name,
                "AWAY": match.away_team.name_ar or match.away_team.name,
                "NEUTRAL": "محايد",
            }
            events = await provider.get_match_events(match_id)
            if not events:
                text = "لا توجد أحداث مسجلة للمباراة حتى الآن."
            else:
                lines = ["أحدث أحداث المباراة:"]
                for event in events[-12:]:
                    event_name = _EVENT_TYPE_AR.get(event.type.value, event.type.value)
                    side_name = side_names.get(event.side.value, event.side.value)
                    lines.append(
                        f"• الدقيقة {event.minute}: {event_name} - {side_name}"
                    )
                text = "\n".join(lines)
            await _safe_edit(query, text, reply_markup=match_actions(match_id))
            return

        if data.startswith(("subscribe_start:", "subscribe_delta:")):
            action, match_id = data.split(":", 1)
            if user is None:
                await _safe_edit(query, "تعذر تحديد المستخدم لهذا الاشتراك.")
                return
            kind = "start" if action == "subscribe_start" else "probability_delta"
            await service.subscribe(telegram_user_id=user.id, match_id=match_id, kind=kind)
            delivery = bot_data.setdefault("delivery_subscriptions", set())
            delivery.add((user.id, match_id, kind))
            text = (
                "تم حفظ تنبيه بدء المباراة."
                if kind == "start"
                else "تم حفظ تنبيه تغير الاحتمال وفق الحد والفاصل الزمني المضبوطين."
            )
            await _safe_edit(query, text, reply_markup=match_actions(match_id))
            return

        if data == "methodology":
            await _safe_edit(
                query,
                (
                    "نرسل إشارات المباراة المنظمة إلى نموذج اللغة ليصيغ توقعا واضحا للمستخدم. "
                    "السجل الداخلي يبقى مبنيا على نموذج قابل لإعادة التشغيل حتى لا نخترع بيانات."
                ),
                reply_markup=main_menu(),
            )
            return
        if data == "settings":
            provider_items = getattr(provider, "providers", [provider])
            provider_names = ", ".join(
                getattr(item, "name", "unknown") for item in provider_items
            )
            scope_text = "كأس العالم فقط" if settings.world_cup_only else "كل المسابقات"
            live_text = "مفعّل" if settings.live_polling_enabled else "غير مفعّل"
            llm_text = "مفعّل لصياغة التوقع" if settings.llm_enabled else "غير مفعّل"
            await _safe_edit(
                query,
                "\n".join(
                    [
                        "الإعدادات الحالية:",
                        f"• النطاق: {scope_text}",
                        f"• مصادر البيانات: {provider_names}",
                        f"• التحديث المباشر: {live_text}",
                        f"• نموذج اللغة: {llm_text}",
                        "• واجهة البوت تعرض توقعا مختصرا بلا معادلات أو نسب مزدحمة.",
                    ]
                ),
                reply_markup=main_menu(),
            )
            return
        await _safe_edit(query, "هذا الخيار غير متاح.", reply_markup=main_menu())
    except Exception:
        await _safe_edit(
            query,
            "تعذر تنفيذ الطلب حالياً بسبب مصدر البيانات أو خدمة داخلية. لم تُنشأ أي معلومات بديلة.",
            reply_markup=main_menu(),
        )
