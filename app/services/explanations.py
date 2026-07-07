from __future__ import annotations

import json
import re

from app.observability.metrics import LLM_FALLBACK_COUNT
from app.providers.llm.router import LLMRouter
from app.schemas.predictions import EvidenceItem, Explanation
from app.services.arabic import deterministic_explanation

_DIGIT_PATTERN = re.compile(r"[0-9٠-٩]")


class ExplanationService:
    def __init__(self, router: LLMRouter | None) -> None:
        self.router = router

    async def build(
        self,
        *,
        home_name: str,
        away_name: str,
        home_probability: float,
        draw_probability: float,
        away_probability: float,
        evidence: list[EvidenceItem],
        uncertainty: str,
        warning: str | None,
        scope_ar: str = "بعد 90 دقيقة",
    ) -> Explanation:
        factors = [
            _DIGIT_PATTERN.sub("", item.description_ar).replace("  ", " ").strip()
            for item in evidence
        ]
        evidence_for_llm = [
            {
                "code": item.code,
                "direction": item.direction,
                "importance": (
                    "high"
                    if item.importance >= 0.30
                    else "medium"
                    if item.importance >= 0.15
                    else "supporting"
                ),
                "description_ar": _DIGIT_PATTERN.sub("", item.description_ar)
                .replace("  ", " ")
                .strip(),
            }
            for item in evidence
        ]
        values = [
            (home_name, home_probability),
            ("تعادل", draw_probability),
            (away_name, away_probability),
        ]
        leader, leader_probability = max(values, key=lambda item: item[1])
        runner_up = sorted(values, key=lambda item: item[1], reverse=True)[1][1]
        edge = leader_probability - runner_up
        edge_label = "واضح" if edge >= 0.15 else "خفيف" if edge >= 0.06 else "متقارب"
        fallback = deterministic_explanation(
            home_name=home_name,
            away_name=away_name,
            home_probability=home_probability,
            draw_probability=draw_probability,
            away_probability=away_probability,
            factors=factors,
            uncertainty=uncertainty,
            warning=warning,
            scope_ar=scope_ar,
        )
        if self.router is None:
            return fallback

        evidence_package = {
            "home_team": home_name,
            "away_team": away_name,
            "model_pick": leader,
            "model_edge": edge_label,
            "locked_win_probabilities_percent": {
                home_name: round(home_probability * 100),
                "تعادل": round(draw_probability * 100),
                away_name: round(away_probability * 100),
            },
            "allowed_factors_ar": factors,
            "structured_evidence": evidence_for_llm,
            "uncertainty_level": uncertainty,
            "data_warning_ar": warning,
            "forecast_scope_ar": "نهاية المباراة",
        }
        prompt = (
            "أنت محلل توقعات كأس العالم في بوت عربي. اكتب توقعاً إعلانياً نظيفاً ومباشراً "
            "بالعربية. استخدم model_pick كاختيارك الأقرب ولا تغيّره. استخدم "
            "locked_win_probabilities_percent لفهم قوة التوقع فقط لأن واجهة البوت ستعرض "
            "الأرقام المقفلة بشكل منفصل. لا تضف أرقاماً أو نسباً من عندك داخل الشرح "
            "ولا تذكر معادلات أو أسماء لاعبين. لا تستخدم كلمات صاحب الأرض أو الضيف. اذكر أسماء "
            "المنتخبات فقط. اشرح أفضلية خفيفة أو واضحة حسب model_edge وبناء على "
            "structured_evidence وallowed_factors_ar فقط. أعد JSON مطابقاً للمخطط. "
            "اجعل headline_ar مثل "
            "'التوقع الأقرب: اسم المنتخب' أو 'التوقع الأقرب: تعادل'. اجعل key_factors_ar "
            "ثلاث نقاط قصيرة فقط بصياغة تحليلية منك، لا تنسخ allowed_factors_ar حرفياً، "
            "ولا تبدأ النقاط بكلمات تقنية مثل تقييم القوة أو الشكل الحالي أو تقدير الأهداف. "
            "اكتبها كأسباب مفهومة للمستخدم عن لماذا يميل التوقع لهذا المنتخب.\n"
            + json.dumps(evidence_package, ensure_ascii=False)
        )
        try:
            result, _provider = await self.router.generate_structured(prompt, Explanation)
            serialized = " ".join(
                [
                    result.headline_ar,
                    result.summary_ar,
                    *result.key_factors_ar,
                    result.uncertainty_ar,
                    result.data_warning_ar or "",
                ]
            )
            if _DIGIT_PATTERN.search(serialized):
                raise ValueError("LLM explanation attempted to introduce numeric content")
            return result.model_copy(update={"generated_by": "llm"})
        except Exception as exc:
            LLM_FALLBACK_COUNT.labels("router", type(exc).__name__).inc()
            return fallback
