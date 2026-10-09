# Public social buzz: first integration

The scanner can open a saved `tori.social.v1` JSON report in its Public social
buzz panel. Loading a report is local to the browser; it does not send the file
to the broker or execute orders. Refresh the scanner page to see the new panel.

The read-only social CLI collects a bounded sample: up to 100 latest posts each
from r/pennystocks and r/stocks, and optionally one X recent-search request with
up to 100 posts. Only posts published within the preceding 24 hours are counted.
No pagination, automatic polling or retries are performed. Missing access is
reported separately from successful samples with no matching cashtags.

From the repository, with approved credentials set in the process environment:

```powershell
.venv/Scripts/python.exe -m tori_taurus.social --symbols ABC,XYZ --output exports/social-report.json
```

Replace ABC/XYZ with the real tickers to check. Create `exports` locally first.
It is ignored by Git. Open the resulting report using the scanner's file picker.
Without credentials the report contains access statuses, not invented social data.
Do not commit reports or put credentials into command history or this chat.
The program does not read `.env` automatically.

Reddit requires approved Data API access and `TORI_REDDIT_ACCESS_TOKEN` (an
unexpired OAuth access token). X requires `TORI_X_BEARER_TOKEN` and the explicit
`--allow-paid-x` flag. Configure an X billing-cycle spending limit before using
that flag. The CLI does not purchase credits or change spending limits. A query
over 512 characters is skipped rather than silently checking fewer tickers.
All requests have a 10-second timeout and a 2 MB response limit.

The ranking is **among supplied tickers and fetched posts**, not the most talked
about stocks across the entire internet. Only explicit cashtags (`$XYZ`) count.
Each post counts once per ticker, duplicate platform/post IDs count once, and
unique authors are counted separately. Author IDs and post text are not written
to the report. Evidence contains at most five links per ticker. The collector
currently excludes comments, video/audio, reshares and independent discovery of
tickers outside the supplied list. Price under $5 must be checked by the market
scanner; social posts cannot establish current price.

Sentiment uses a small, conservative keyword heuristic. Multi-ticker sentences
and explicit negation are unclear. Contradictory opinions are mixed. A directional
aggregate needs at least three directional posts and 60% directional coverage.
Confidence remains low; neither spam nor sarcasm is reliably detected. Mention
counts are not unique-person counts, verified catalysts, or entry instructions.
The imported sample shows collection time and never refreshes automatically.

Discord, Kick and TikTok are explicitly not connected. No private communities
are accessed. The report viewer does not alter setup, entry, stop or sizing logic.

Official access references:
- [Reddit Data API](https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki)
- [X search](https://docs.x.com/x-api/posts/search/introduction)
- [X pricing and spending limits](https://docs.x.com/x-api/getting-started/pricing)
- [TikTok eligibility](https://developers.tiktok.com/docs/en/research-api-faq)

## Private local X connection

The Public social buzz panel now accepts an X bearer token in a password field.
Click **Use token for this session**; the field clears and the server stores it
only in process memory. No verification or billing occurs at connection time.
**Disconnect X** removes the process token. A server restart clears tokens entered
through the form, including existing Webull session credentials.

Enter real tickers or use tickers from the latest live market scan. Demo symbols
are not transferred to a paid search. Check the per-scan cost acknowledgment and
click **Scan public X posts**. The acknowledgment resets after every request;
there is no automatic social polling. Only one social scan can run at a time.
The estimated maximum is $0.50 for 100 post reads at $0.005 per post; prices may
change, so verify X pricing and configure a billing-cycle spending limit.

Imported files remain supported. All reports are timestamped snapshots; an X
access failure is coverage unavailable, never a successful zero-mention result.
