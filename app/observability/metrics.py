from prometheus_client import Counter, Gauge, Histogram, generate_latest

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds", "HTTP request latency", ["route", "method"]
)
PREDICTION_LATENCY = Histogram("prediction_duration_seconds", "Prediction latency", ["kind"])
PROVIDER_REQUESTS = Counter(
    "provider_requests_total", "Provider requests", ["provider", "operation", "status"]
)
PREDICTION_COUNT = Counter("predictions_total", "Predictions", ["kind", "status"])
LLM_FALLBACK_COUNT = Counter(
    "llm_fallback_total", "LLM deterministic fallbacks", ["provider", "reason"]
)
SSE_CLIENTS = Gauge("sse_clients", "Connected SSE clients")
GEMINI_SLOT_HEALTH = Gauge("gemini_key_slot_health", "Gemini key slot health", ["slot"])


def render_metrics() -> bytes:
    return generate_latest()
