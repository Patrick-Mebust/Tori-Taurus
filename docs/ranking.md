# Tori evidence ranking v1

The top-three panel ranks eligible **inspected** stocks from the current scan, not the entire market. It may show fewer than three. Each card explains its evidence, score components, conditional levels and limitations. This deterministic research score is not a probability of winning, a forecast, or account risk approval.

| Component | Maximum | Rule |
| --- | ---: | --- |
| Setup | 25 | Selected confirmed setup 25; watch 15; fresh premarket conditional range 12. |
| Liquidity | 15 | Quoted spread <=0.3%: 15; <=0.75%: 11; <=1.25%: 6; otherwise 0. No depth or fill claim. |
| Volume participation | 15 | Matched-time relative volume times 5, capped at 15; otherwise acceleration times 4 capped at 10; otherwise completed-day relative volume times 3 capped at 6. |
| Trend / extension | 15 | Observed close 0–3% above VWAP: 10; >3–5%: 5. Completed daily close >= EMA9 and EMA5 >= EMA9 >= EMA20: another 5. |
| Invalidation distance | 15 | Entry-to-invalidation percentage <=3: 15; <=5: 10; <=8: 5; otherwise 0. A tight level does not establish stop reliability. |
| Snapshot momentum | 10 | Positive snapshot percentage change, capped at 10. |
| Public social sample | 5 | Fresh manual sample: positive tone with at least three posts and three authors earns author count / 2, capped at 5; mixed earns 1; otherwise 0. |

Points round to the nearest integer per component. Missing evidence earns zero and is never redistributed. Evidence coverage separately reports available model weight (historical volume counts for only 6/15, acceleration for 10/15, and trend coverage reflects which of VWAP/daily structure is present); this is not a confidence probability. Ordering uses score, then available evidence, then ticker name. Quote eligibility expires in the browser after 60 seconds and top picks update without a new provider request. Premarket quote and observation timestamps must both remain current. Stale, future-dated, unsupported-session, missing-level, invalidated-setup, incomplete-intraday and >2%-spread candidates cannot enter the top-three panel.

Social requires a successfully validated manual report from this running browser tab, containing the ticker and a sampled source. Reports expire for ranking after one hour; the actual fetched discussion window remains 24 hours. Saved imports do not influence ranking. Demo ranking never uses real social evidence. No paid request or background social poll is triggered by ranking. Keyword sentiment, author counts and cashtags do not establish authentic interest or verified news.

News catalysts, float, dilution, halts, order-book depth and broker stops are currently unverified and explicitly listed as blind spots. Account values determine sizing separately; risk blockers remain visible even when a research candidate ranks highly. Illustrative 2R targets are not used to reward scores because they are arithmetic constructions.

Run ranking regressions with `node --test tests/test_ranking.mjs`.
