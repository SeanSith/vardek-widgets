# Status Board Widget
At‑a‑glance up/down for the services you depend on, with a color dot and status text; the header flags the worst current state. Self‑contained (broad `https://` proxy, no key).

Works with any service on **Atlassian Statuspage** (fetches `/<host>/api/v2/status.json`). Defaults: OpenAI, GitHub, Vercel, Cloudflare, npm, Discord. Settings: **services** = `Name|status-host, …`. Note: Anthropic and Stripe don't expose the statuspage v2 API (Anthropic 301‑redirects, Stripe uses a custom page), so they can't be shown here.
