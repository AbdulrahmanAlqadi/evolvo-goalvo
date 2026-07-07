# Data-source assessment

| Source | Fixtures | Live events | Lineups | Injuries | Stats/xG | Cost/testing posture | Decision |
|---|---:|---:|---:|---:|---:|---|---|
| Replay fixture | Yes | Yes | Yes | Synthetic | Synthetic | Offline | Reference test path |
| API-Football | Yes | Coverage-dependent | Coverage-dependent | Coverage-dependent | Stats; xG not assumed | Credential required; quota-limited | Primary production candidate after contract testing |
| football-data.org | Yes | Limited representation | Some plans/resources | No uniform injury feed | No uniform xG | Free tier rate-limited | Fixture/score fallback |
| TheSportsDB | Yes | Not assumed | Not assumed | No | No | Public/dev key constraints | Low-detail fallback |
| StatsBomb Open Data | Selected historical competitions | Recorded events | Recorded | No universal availability | Event/xG fields where released | Open-data agreement | Training/replay research |
| OpenFootball | Historical/schedules | Not live | No | No | No | CC0; manually updated | Bootstrap only |
| Sportmonks / Sportradar / Opta | Contract-dependent | Potentially strong | Contract-dependent | Contract-dependent | Contract-dependent | Paid/licensed | Explicit extension adapters |

No adapter claims a capability that its internal flag does not expose. A fallback provider is called only for operations it supports.
