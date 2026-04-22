# Ethics and Legality

This project is designed for competitive research and technical evaluation.
It follows constraints that reduce platform impact and legal risk.

## robots.txt Respect

Before scraping a domain, validate robots policies and disallow rules:

```python
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser


def is_allowed(url: str, user_agent: str) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.read()
    return parser.can_fetch(user_agent, url)
```

If a critical target path is disallowed, the scraper should skip it and log
the decision.

## Rate Limiting

Use strict domain-level pacing to avoid abusive traffic:

- Recommended baseline: **max 20 requests/minute per domain**.
- Add jittered delays and retries with backoff.
- Pause runs if anti-bot signals increase.

## Transparent User-Agent

Use an identifiable automation user agent where possible. Do not intentionally
misrepresent the client as a real human user for deceptive purposes.

## Authentication and Account Usage

- Do not log in with real customer accounts.
- Restrict collection to publicly visible data flows.
- Avoid any action that simulates purchases or enters checkout with real identities.

## Privacy and PII

Do not collect or store personally identifiable information:

- No customer names, addresses, phone numbers, or order history.
- No courier personal data.
- Keep data model focused on pricing, fees, and availability metadata only.

## Legal Disclaimer

This implementation is for research and competitive analysis in a technical-case context.
Any production deployment should undergo legal review, terms-of-service analysis,
and formal approval before data collection starts.

