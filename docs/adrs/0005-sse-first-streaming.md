# ADR 0005: Server-Sent Events for probability streaming

- Status: accepted
- Alternatives: polling only; WebSockets; SSE.
- Decision: SSE is the initial one-way update transport.
- Rationale: forecasts are server-to-client events and SSE works over ordinary HTTP with simple reconnect semantics.
- Tradeoffs: no bidirectional channel and browser connection limits.
- Failure modes: proxy buffering and disconnects. Responses disable buffering and send heartbeats.
- Upgrade path: WebSockets only if interactive bidirectional use cases justify the complexity.
