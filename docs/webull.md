# Webull local connection

Install `pip install -e ".[calendar,webull]"`, then run `tori-beta`.
The Webull SDK extra is pinned to the version used for integration testing.

## Connect

1. Activate Webull OpenAPI and register your application in Webull's API management page.
2. Leave two-factor verification enabled. Tori exposes no order-placement endpoints.
3. In the local dashboard, enter the App Key and App Secret under Connect my Webull account.
4. Approve verification in Webull if requested, then refresh the account.
5. Select the account using its type and masked number, and click Use this account.
6. Choose Webull mode and click Scan for stocks.

Keys submitted through the dashboard stay in the server process environment and clear on restart.
They are never returned by the server. The official SDK stores its verification token under
`%LOCALAPPDATA%/ToriTaurus/webull-auth` on Windows (under the home directory on other systems).
No credentials or account responses belong in Git, screenshots for publication, or support logs.
The service binds to loopback only, checks Host and Origin, disables request logging and sends
no-store responses. This is a private local app, not a shared or hosted deployment.

Environment configuration is also supported: WEBULL_APP_KEY, WEBULL_APP_SECRET and optional
WEBULL_ACCOUNT_ID. The app does not automatically load a .env file.

## Market-data access

Broker account access and market-data access are separate. A successful account refresh does
not verify scanner access. Webull may offer Nasdaq Basic - Non Display for free in its OpenAPI
Advanced Quotes center. Review the current account-specific offering and agreements there;
terminal/mobile quote subscriptions do not automatically provide OpenAPI entitlement.

A 403 on most-active discovery stops the scan and reports the access problem. It does not mean
that there are no qualifying stocks. Authentication, rate-limit and request errors are reported
without exposing provider response bodies or secrets.

## Account and research boundaries

Webull mode overrides manual equity, buying power and holdings with broker-reported values.
The buying-power cap uses the smaller of day and overnight buying power. Average cost remains
the broker-reported cost basis. Fractional, short or unsupported holdings and open margin calls
disable sizing. Realized losses must be confirmed separately; account day P/L is not used as
realized losses. Stops and pending orders remain unverified.

The scanner inspects at most 20 matches from the top active/gainer lists. It is not a full-market
scan. Quote freshness and regular-session requirements still apply. Delayed bars are rejected;
missing data does not produce invented prices. Each candidate is a separate allocation scenario.
Optional refresh starts 60 seconds after the previous scan finishes; it is polling, not streaming.
