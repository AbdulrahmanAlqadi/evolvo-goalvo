# Research notes (verified 2026-07-06)

## Provider and platform findings

- API-Football documents fixtures, events, lineups, statistics, injuries, standings and odds, but coverage is competition/season-specific. Its 2026 World Cup guide identifies league `1`, season `2026`, and 104 fixtures. Sources: https://www.api-football.com/documentation-v3 and https://www.api-football.com/news/post/fifa-world-cup-2026-guide-to-using-data-with-api-sports
- football-data.org v4 exposes competition and match resources. Its published policy states 10 requests/minute on the free registered plan; therefore the adapter is not advertised as high-frequency real-time coverage. Sources: https://docs.football-data.org/general/v4/index.html and https://docs.football-data.org/general/v4/policies.html
- StatsBomb Open Data contains competitions, matches, lineups and event files for selected competitions under its data agreement. It is appropriate for replay/research where covered, not a universal live World Cup feed. Source: https://github.com/statsbomb/open-data
- OpenFootball provides CC0 World Cup fixtures/results, but its repository explicitly says updates are not live or automated. It is useful for open historical/schedule bootstrap, not live production state. Source: https://github.com/openfootball/worldcup.json
- The Google Gemini documentation recommends the official Google GenAI SDK. API keys remain the simplest server authentication path; production keys require correct restrictions and must not be logged. Sources: https://ai.google.dev/gemini-api/docs/libraries and https://ai.google.dev/gemini-api/docs/api-key
- Telegram Bot API callback queries require acknowledgement, inline keyboards carry callback data, and webhook delivery supports a secret token header. Source: https://core.telegram.org/bots/api

## Modelling findings

- Independent Poisson score models are transparent baselines for score matrices and 1X2 probabilities.
- Dixon–Coles modifies the low-score cells of a double-Poisson model and should be validated rather than assumed superior. Original paper: Dixon & Coles (1997), https://doi.org/10.1111/1467-9876.00065
- Elo-style ratings are useful time-aware strength summaries; football adaptations commonly include match importance, home advantage and goal-difference adjustments. The implementation keeps these configurable and prevents future results from entering historical ratings.
- Robberechts, Van Haaren and Davis model in-game soccer win probability as a temporal stochastic process and emphasize late-game calibration challenges. Source: https://arxiv.org/abs/1906.05029
- Proper evaluation requires temporal/rolling splits, log loss and Brier/calibration metrics. Accuracy alone hides probability quality.

## Selected MVP posture

The runnable baseline uses Elo, Poisson, Dixon–Coles and a transparent softmax ensemble before a separate calibration stage. Live updates use a seeded remaining-goals simulation. A Bayesian event-hazard model is an extension because the repository does not ship enough licensed event-level training data to justify one.
