"""HTTP client for Rappi's internal API. Handles auth, rate limiting, retries."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

log = logging.getLogger(__name__)

BASE_API = "https://services.mxgrability.rappi.com"
BASE_WEB = "https://www.rappi.com.mx"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEVICE_ID = "rappi-competitive-intel-001"
DEFAULT_RATE_LIMIT_SEC = 2.0
MAX_RETRIES = 3
RETRY_BACKOFF_SEC = 5.0


class RappiClientError(Exception):
    """Raised for recoverable client failures and exhausted retries."""

    pass


class RappiClient:
    """Thin wrapper around httpx with auth, rate limiting, and retries."""

    def __init__(self, rate_limit_sec: float = DEFAULT_RATE_LIMIT_SEC) -> None:
        self.rate_limit_sec = rate_limit_sec
        self.client = httpx.Client(
            timeout=30.0,
            headers={
                "user-agent": USER_AGENT,
                "accept": "application/json",
                "accept-language": "es-MX",
            },
        )
        self.bearer_token: str | None = None
        self._last_request_time = 0.0

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_sec:
            time.sleep(self.rate_limit_sec - elapsed)
        self._last_request_time = time.time()

    def _api_headers(self) -> dict[str, str]:
        h = {
            "deviceid": DEVICE_ID,
            "app-version": "1.161.2",
            "vendor": "rappi",
            "x-application-id": "rappi-microfront-web/competitive-intel",
            "referer": f"{BASE_WEB}/",
            "content-type": "application/json",
        }
        if self.bearer_token:
            h["authorization"] = f"Bearer {self.bearer_token}"
        return h

    def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Retry on 5xx and network errors with exponential backoff."""
        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                self._rate_limit()
                response = self.client.request(method, url, **kwargs)
                if response.status_code >= 500:
                    raise RappiClientError(f"Server error {response.status_code}")
                response.raise_for_status()
                return response
            except (httpx.HTTPError, RappiClientError) as e:
                last_exc = e
                if attempt < MAX_RETRIES:
                    backoff = RETRY_BACKOFF_SEC * attempt
                    log.warning(
                        "Attempt %d/%d failed for %s: %s. Retrying in %.1fs",
                        attempt,
                        MAX_RETRIES,
                        url,
                        e,
                        backoff,
                    )
                    time.sleep(backoff)
        raise RappiClientError(f"All {MAX_RETRIES} retries failed for {url}: {last_exc}")

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def authenticate(self) -> None:
        """Two-step guest auth. Token is valid for ~7 days."""
        log.info("Authenticating as guest user...")

        r1 = self._request_with_retry(
            "GET",
            f"{BASE_API}/api/rocket/v2/guest/passport/",
            headers=self._api_headers(),
        )
        guest_key = r1.json()["token"]

        headers = self._api_headers()
        headers["x-guest-api-key"] = guest_key
        r2 = self._request_with_retry(
            "POST",
            f"{BASE_API}/api/rocket/v2/guest",
            headers=headers,
            json={},
        )
        data = r2.json()
        self.bearer_token = data["access_token"]
        log.info("Bearer token acquired (expires in %s sec)", data["expires_in"])

    # ------------------------------------------------------------------
    # Geocoding
    # ------------------------------------------------------------------

    def autocomplete_address(self, text: str, lat: float, lng: float) -> list[dict[str, Any]]:
        r = self._request_with_retry(
            "GET",
            f"{BASE_API}/api/ms/address/autocomplete",
            headers=self._api_headers(),
            params={"lat": lat, "lng": lng, "text": text, "source": "locationservices"},
        )
        return r.json()

    def place_details(self, place_id: str) -> dict[str, Any]:
        r = self._request_with_retry(
            "GET",
            f"{BASE_API}/api/ms/address/place-details",
            headers=self._api_headers(),
            params={
                "placeid": place_id,
                "source": "locationservices",
                "raw": "false",
                "strictbounds": "true",
            },
        )
        return r.json()

    def resolve_address(
        self, address: str, anchor_lat: float, anchor_lng: float
    ) -> tuple[float, float, str]:
        """High-level: address text -> (lat, lng, full_resolved_address)."""
        suggestions = self.autocomplete_address(address, anchor_lat, anchor_lng)
        if not suggestions:
            raise RappiClientError(f"No suggestions found for address: {address!r}")
        first = suggestions[0]
        details = self.place_details(first["place_id"])
        lat, lng = details["location"]
        return float(lat), float(lng), str(details.get("name", ""))

    # ------------------------------------------------------------------
    # Store info
    # ------------------------------------------------------------------

    def get_store_by_brand(self, brand_id: int, lat: float, lng: float) -> dict[str, Any]:
        r = self._request_with_retry(
            "POST",
            f"{BASE_API}/api/restaurant-bus/store/brand/id/{brand_id}",
            headers=self._api_headers(),
            json={
                "is_prime": False,
                "lat": lat,
                "lng": lng,
                "store_type": "restaurant",
                "prime_config": {"unlimited_shipping": False},
            },
        )
        return r.json()

    def get_store_html(self, store_id: int, slug: str) -> str:
        url = f"{BASE_WEB}/restaurantes/{store_id}-{slug}"
        r = self._request_with_retry(
            "GET",
            url,
            headers={
                "user-agent": USER_AGENT,
                "accept-language": "es-MX",
                "accept": "text/html,application/xhtml+xml",
            },
            follow_redirects=True,
        )
        return r.text

    def close(self) -> None:
        self.client.close()
