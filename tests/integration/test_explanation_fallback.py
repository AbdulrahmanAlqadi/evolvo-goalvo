import pytest

from app.schemas.predictions import EvidenceItem, Explanation
from app.services.explanations import ExplanationService


class FailingRouter:
    async def generate_structured(self, prompt, schema):
        raise RuntimeError("offline")


class CapturingRouter:
    def __init__(self):
        self.prompt = ""

    async def generate_structured(self, prompt, schema):
        self.prompt = prompt
        return (
            Explanation(
                headline_ar="التوقع الأقرب: الأرجنتين",
                summary_ar="الأرجنتين تبدو أقرب بسبب توازن المؤشرات العامة حول المباراة.",
                key_factors_ar=[
                    "الأرجنتين تبدو أكثر جاهزية في لحظات الحسم.",
                    "مسار النتائج الأخيرة يعطيها أفضلية بسيطة أمام فرنسا.",
                    "إيقاع المباراة المتوقع يناسب أسلوب الأرجنتين أكثر.",
                ],
                uncertainty_ar="",
            ),
            "fake",
        )


@pytest.mark.asyncio
async def test_llm_outage_uses_deterministic_fallback():
    service = ExplanationService(FailingRouter())
    result = await service.build(
        home_name="الأرجنتين",
        away_name="فرنسا",
        home_probability=0.45,
        draw_probability=0.30,
        away_probability=0.25,
        evidence=[
            EvidenceItem(
                code="TEAM_STRENGTH",
                direction="HOME",
                importance=0.5,
                description_ar="تفوق نسبي في القوة التاريخية.",
            )
        ],
        uncertainty="medium",
        warning=None,
    )
    assert result.generated_by == "deterministic"
    assert "45" not in result.summary_ar
    assert result.headline_ar.startswith("التوقع الأقرب:")


@pytest.mark.asyncio
async def test_llm_path_writes_user_facing_reasons_from_structured_evidence():
    router = CapturingRouter()
    service = ExplanationService(router)
    result = await service.build(
        home_name="الأرجنتين",
        away_name="فرنسا",
        home_probability=0.45,
        draw_probability=0.30,
        away_probability=0.25,
        evidence=[
            EvidenceItem(
                code="TEAM_STRENGTH",
                direction="HOME",
                importance=0.35,
                description_ar="تقييم القوة يميل إلى الأرجنتين.",
            ),
            EvidenceItem(
                code="REST_FATIGUE",
                direction="NEUTRAL",
                importance=0.12,
                description_ar="عامل الراحة متقارب بين المنتخبين.",
            ),
        ],
        uncertainty="medium",
        warning=None,
    )

    assert result.generated_by == "llm"
    assert "structured_evidence" in router.prompt
    assert "لا تنسخ allowed_factors_ar حرفياً" in router.prompt
    assert "الأرجنتين تبدو أكثر جاهزية" in result.key_factors_ar[0]
