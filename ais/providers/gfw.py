"""Global Fishing Watch (GFW) AIS Vessel Presence Data Provider.

Implements the AISProvider contract for the official Global Fishing Watch 4Wings API v3,
retrieving historical AIS Vessel Presence data (dataset `public-global-presence:latest`)
for spatio-temporal oil-spill candidate vessel attribution.

IMPORTANT DATASET & GEOMETRIC CHARACTERISTICS:
- Dataset: `public-global-presence:latest`
- Nature of data: AIS-derived vessel-presence dataset (~1 position per hour per vessel).
- Coordinate representation: Grid-cell center coordinates rather than point-by-point
  raw AIS sensor trajectories.
- Trajectory limitation: Downstream attribution engine must treat this as vessel presence
  evidence across grid cells; raw high-frequency kinematic pings (continuous SOG/COG/Heading)
  are not provided by this product and are explicitly flagged as a data limitation.
"""

from __future__ import annotations

import logging
import os
import random
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import numpy as np
import pandas as pd
import requests

from ais.data_loader.schema import (
    LAT_MAX,
    LAT_MIN,
    LATITUDE_SENTINEL,
    LON_MAX,
    LON_MIN,
    LONGITUDE_SENTINEL,
    REQUIRED_COLUMNS,
)
from ais.filtering.spatial import filter_by_radius
from ais.integration.search_request import AISSearchRequest
from ais.providers.base import (
    AISProvider,
    AISProviderConfigError,
    AISProviderConnectionError,
    AISProviderError,
    AISProviderNotFoundError,
)

logger = logging.getLogger(__name__)

DEFAULT_GFW_BASE_URL: str = "https://gateway.api.globalfishingwatch.org/v3/4wings"
DEFAULT_GFW_DATASET: str = "public-global-presence:latest"

# Default bounded HTTP timeouts: (connect_timeout_seconds, read_timeout_seconds)
DEFAULT_CONNECT_TIMEOUT: float = 10.0
DEFAULT_READ_TIMEOUT: float = 105.0

# Default bounded recovery timeout for HTTP 524 /last-report polling
DEFAULT_MAX_RECOVERY_TIMEOUT: float = 60.0

# Official GFW 4Wings uppercase enum options for group-by
VALID_GROUP_BY_ENUMS: Set[str] = {
    "VESSEL_ID",
    "MMSI",
    "FLAG",
    "GEARTYPE",
    "FLAGANDGEARTYPE",
}

# Process-level concurrency guard to prevent concurrent report submissions per user token
_GFW_CONCURRENCY_LOCK = threading.Lock()

# Authoritative benchmark: 2019-10-14 Red Sea incident parameters
RED_SEA_BENCHMARK = {
    "description": "2019-10-14 Red Sea event",
    "start_time": "2019-10-11T00:00:00Z",
    "end_time": "2019-10-17T23:59:59Z",
    "min_latitude": 17.5,
    "max_latitude": 20.0,
    "min_longitude": 38.6,
    "max_longitude": 40.4,
}


class GlobalFishingWatchAISProvider(AISProvider):
    """AIS data provider querying the Global Fishing Watch (GFW) 4Wings API v3.

    Retrieves historical AIS Vessel Presence (`public-global-presence:latest`) using
    the official GFW 4Wings report endpoint. The resulting records represent
    vessel presence observations aggregated onto spatial grid cells.

    Attributes:
        dataset: GFW dataset identifier ('public-global-presence:latest').
        base_url: Gateway API base URL.
        spatial_resolution: Spatial grid resolution ('LOW' or 'HIGH').
        temporal_resolution: Time aggregation resolution ('HOURLY', 'DAILY', etc.).
        group_by: Uppercase grouping enum (e.g. 'VESSEL_ID', 'MMSI').
        timeout: Bounded (connect_timeout, read_timeout) tuple in seconds.
        max_recovery_timeout: Maximum seconds to poll /last-report on HTTP 524.
    """

    def __init__(
        self,
        api_token: Optional[str] = None,
        dataset: str = DEFAULT_GFW_DATASET,
        base_url: str = DEFAULT_GFW_BASE_URL,
        spatial_resolution: str = "LOW",
        temporal_resolution: str = "HOURLY",
        group_by: str = "VESSEL_ID",
        timeout: Union[float, Tuple[float, float]] = (DEFAULT_CONNECT_TIMEOUT, DEFAULT_READ_TIMEOUT),
        max_retries: int = 3,
        backoff_factor: float = 2.0,
        max_recovery_timeout: float = DEFAULT_MAX_RECOVERY_TIMEOUT,
        session: Optional[requests.Session] = None,
    ) -> None:
        """Initialize the Global Fishing Watch AIS provider.

        Args:
            api_token: GFW Bearer API token. If omitted, loaded from `GFW_API_TOKEN`
                environment variable. Never hard-coded.
            dataset: 4Wings dataset identifier. Defaults to 'public-global-presence:latest'.
            base_url: Base URL for 4Wings API endpoints.
            spatial_resolution: Spatial resolution ('LOW' or 'HIGH').
            temporal_resolution: Temporal aggregation ('HOURLY', 'DAILY', etc.).
            group_by: Uppercase aggregation enum ('VESSEL_ID', 'MMSI', 'FLAG', etc.).
            timeout: Bounded HTTP timeout as a single float or (connect, read) tuple in seconds.
            max_retries: Maximum retry attempts for transient network or 429 errors.
            backoff_factor: Multiplier for exponential backoff delays.
            max_recovery_timeout: Maximum total seconds to poll /last-report after HTTP 524.
            session: Optional custom requests.Session (for connection pooling / mocking).

        Raises:
            AISProviderConfigError: If configuration parameters or group_by enums are invalid.
        """
        # Resolve token securely from argument or environment (never logged or printed)
        resolved_token = api_token or os.getenv("GFW_API_TOKEN")
        if resolved_token is not None:
            resolved_token = resolved_token.strip()
            if not resolved_token:
                resolved_token = None
        self._api_token: Optional[str] = resolved_token

        if not dataset or not isinstance(dataset, str):
            raise AISProviderConfigError("dataset must be a non-empty string.")
        self.dataset: str = dataset.strip()

        if not base_url or not isinstance(base_url, str):
            raise AISProviderConfigError("base_url must be a non-empty string.")
        self.base_url: str = base_url.strip().rstrip("/")

        self.spatial_resolution: str = spatial_resolution.strip().upper()
        self.temporal_resolution: str = temporal_resolution.strip().upper()

        # Enforce uppercase group-by enum per official GFW v3 API specs
        group_by_norm = group_by.strip().upper()
        if group_by_norm not in VALID_GROUP_BY_ENUMS:
            raise AISProviderConfigError(
                f"Invalid group_by '{group_by}'. GFW API v3 requires uppercase enum: "
                f"{sorted(list(VALID_GROUP_BY_ENUMS))}"
            )
        self.group_by: str = group_by_norm

        # Enforce bounded connect and read timeouts (Requirement 2)
        if isinstance(timeout, (int, float)):
            if timeout <= 0 or not np.isfinite(timeout):
                raise AISProviderConfigError("timeout must be a finite positive number.")
            self.timeout: Tuple[float, float] = (
                min(DEFAULT_CONNECT_TIMEOUT, float(timeout)),
                float(timeout),
            )
        elif isinstance(timeout, (tuple, list)) and len(timeout) == 2:
            c_to, r_to = timeout
            if (
                not isinstance(c_to, (int, float))
                or not isinstance(r_to, (int, float))
                or c_to <= 0
                or r_to <= 0
                or not np.isfinite(c_to)
                or not np.isfinite(r_to)
            ):
                raise AISProviderConfigError(
                    "timeout tuple must contain two finite positive numbers (connect, read)."
                )
            self.timeout = (float(c_to), float(r_to))
        else:
            raise AISProviderConfigError(
                "timeout must be a positive float or a (connect, read) tuple."
            )

        if max_retries < 1:
            raise AISProviderConfigError("max_retries must be at least 1.")
        self.max_retries: int = int(max_retries)

        if backoff_factor < 1.0:
            raise AISProviderConfigError("backoff_factor must be >= 1.0.")
        self.backoff_factor: float = float(backoff_factor)

        # Enforce bounded recovery time for 524 /last-report polling (Requirement 3 & 6)
        if (
            not isinstance(max_recovery_timeout, (int, float))
            or max_recovery_timeout <= 0
            or not np.isfinite(max_recovery_timeout)
        ):
            raise AISProviderConfigError(
                "max_recovery_timeout must be a finite positive number."
            )
        self.max_recovery_timeout: float = float(max_recovery_timeout)

        self._session: requests.Session = session or requests.Session()

    @property
    def name(self) -> str:
        """Unique provider identifier."""
        return "gfw"

    @property
    def api_token(self) -> Optional[str]:
        """Configured GFW API token (for programmatic verification only)."""
        return self._api_token

    def _sanitize(self, msg: Any) -> str:
        """Strip and redact any occurrence of the API token from messages/exceptions (Requirement 7)."""
        s = str(msg)
        if self._api_token and self._api_token in s:
            s = s.replace(self._api_token, "[REDACTED_GFW_TOKEN]")
        return s

    def health_check(self) -> bool:
        """Verify that the provider backend and API token are accessible.

        Does not leak or print the token. Returns True if token exists and
        endpoint probe succeeds.
        """
        if not self._api_token:
            logger.warning("GFW health check failed: GFW_API_TOKEN is not configured.")
            return False

        report_url = f"{self.base_url}/report"
        headers = {"Authorization": f"Bearer {self._api_token}"}
        probe_timeout = (min(5.0, self.timeout[0]), min(10.0, self.timeout[1]))

        try:
            resp = self._session.options(report_url, headers=headers, timeout=probe_timeout)
            if resp.status_code in (200, 204, 405):
                return True
            if resp.status_code in (401, 403):
                logger.error("GFW health check failed: Authorization rejected (HTTP %s)", resp.status_code)
                return False
            if resp.status_code in (400, 422):
                return True
            return False
        except Exception as exc:
            logger.warning("GFW health check exception connecting to %s: %s", report_url, self._sanitize(exc))
            return False

    @classmethod
    def create_red_sea_request(
        cls,
        start_time: Optional[Union[str, pd.Timestamp]] = None,
        end_time: Optional[Union[str, pd.Timestamp]] = None,
    ) -> AISSearchRequest:
        """Generate an AISSearchRequest configured for the 2019-10-14 Red Sea event.

        Default window: 2019-10-11T00:00:00Z to 2019-10-17T23:59:59Z
        Bounding box: min_lat=17.5, max_lat=20.0, min_lon=38.6, max_lon=40.4
        Allows custom sub-window (e.g. 6h or 24h) for faster interactive queries.
        """
        min_lat = RED_SEA_BENCHMARK["min_latitude"]
        max_lat = RED_SEA_BENCHMARK["max_latitude"]
        min_lon = RED_SEA_BENCHMARK["min_longitude"]
        max_lon = RED_SEA_BENCHMARK["max_longitude"]

        center_lat = (min_lat + max_lat) / 2.0
        center_lon = (min_lon + max_lon) / 2.0

        from ais.filtering.spatial import haversine_distance_km

        d_corner = haversine_distance_km(center_lat, center_lon, max_lat, max_lon)

        st = (
            pd.Timestamp(start_time)
            if start_time is not None
            else pd.Timestamp(RED_SEA_BENCHMARK["start_time"])
        )
        et = (
            pd.Timestamp(end_time)
            if end_time is not None
            else pd.Timestamp(RED_SEA_BENCHMARK["end_time"])
        )

        return AISSearchRequest(
            latitude=center_lat,
            longitude=center_lon,
            radius_km=d_corner,
            start_time=st,
            end_time=et,
            buffer_km=0.0,
            bounding_box=(min_lat, max_lat, min_lon, max_lon),
        )

    def _build_geojson_polygon(
        self,
        bounding_box: Tuple[float, float, float, float],
    ) -> Dict[str, Any]:
        """Convert bounding box into a standard GeoJSON Polygon.

        Coordinates order: [longitude, latitude].
        Closed linear ring (5 points: first == last).
        """
        min_lat, max_lat, min_lon, max_lon = bounding_box
        return {
            "type": "Polygon",
            "coordinates": [
                [
                    [min_lon, min_lat],
                    [max_lon, min_lat],
                    [max_lon, max_lat],
                    [min_lon, max_lat],
                    [min_lon, min_lat],
                ]
            ],
        }

    def _format_date_range(self, start_time: pd.Timestamp, end_time: pd.Timestamp) -> str:
        """Format UTC timestamps into GFW ISO 8601 comma-delimited date-range string."""
        start_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        return f"{start_str},{end_str}"

    def _recover_last_report(
        self,
        headers: Dict[str, str],
        max_recovery_timeout: Optional[float] = None,
        poll_interval: float = 3.0,
    ) -> Optional[Dict[str, Any]]:
        """Attempt to recover report result from /last-report endpoint after 524 timeout.

        Guarantees bounded polling time without infinite loops (Requirement 3 & 6).
        According to GFW specifications, when a report request times out (HTTP 524),
        the finished report can be recovered from GET /v3/4wings/last-report within 30 minutes.
        Note: /last-report does NOT guarantee recovery.
        """
        last_report_url = f"{self.base_url}/last-report"
        timeout_limit = max_recovery_timeout or self.max_recovery_timeout
        start_time = time.monotonic()
        current_interval = poll_interval

        # Bounded timeout for individual last-report poll requests
        poll_timeout = (min(5.0, self.timeout[0]), min(15.0, self.timeout[1]))

        while (time.monotonic() - start_time) < timeout_limit:
            try:
                resp = self._session.get(
                    last_report_url,
                    headers=headers,
                    timeout=poll_timeout,
                )

                if resp.status_code == 404:
                    logger.warning("GFW /last-report returned 404: recovery window expired or report not found.")
                    return None

                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict):
                        status = data.get("status")
                        if status == "running":
                            elapsed = time.monotonic() - start_time
                            remaining = timeout_limit - elapsed
                            if remaining <= 0:
                                break
                            sleep_duration = min(current_interval, remaining)
                            logger.info(
                                "GFW last-report still running (elapsed %.1fs / max %.1fs). Waiting %.1fs...",
                                elapsed,
                                timeout_limit,
                                sleep_duration,
                            )
                            time.sleep(sleep_duration)
                            current_interval = min(current_interval * 1.5, 10.0)
                            continue
                        elif isinstance(status, (int, str)) and (status in (400, 422, 500) or "error" in data):
                            logger.error("GFW last-report finished with error: %s", self._sanitize(data))
                            return None
                    return data

                logger.warning("GFW /last-report returned HTTP %s: %s", resp.status_code, self._sanitize(resp.text))
                return None

            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
                elapsed = time.monotonic() - start_time
                remaining = timeout_limit - elapsed
                if remaining <= 0:
                    break
                sleep_duration = min(current_interval, remaining)
                logger.warning(
                    "Transient network error polling /last-report (elapsed %.1fs): %s. Waiting %.1fs...",
                    elapsed,
                    self._sanitize(exc),
                    sleep_duration,
                )
                time.sleep(sleep_duration)
                current_interval = min(current_interval * 1.5, 10.0)

        logger.warning(
            "GFW /last-report recovery reached bounded timeout limit of %.1fs without completing.",
            timeout_limit,
        )
        return None

    def fetch_ais_data(self, request: AISSearchRequest) -> pd.DataFrame:
        """Query and retrieve canonical AIS vessel presence observations from GFW.

        Protected by a concurrency guard to enforce GFW's single-report-per-user limit.
        Dispatches POST to `/v3/4wings/report` with uppercase enums.
        Applies bounded connect/read timeouts and bounded 524 recovery.

        Args:
            request: Spatio-temporal AISSearchRequest defining region and time window.

        Returns:
            A pandas DataFrame adhering to OILTRACE canonical AIS schema, with
            provenance flags indicating grid-cell center vessel presence rather
            than raw sensor trajectory pings.
        """
        if not isinstance(request, AISSearchRequest):
            raise TypeError(
                f"request must be an instance of AISSearchRequest, got {type(request).__name__}"
            )

        if not self._api_token:
            raise AISProviderConfigError(
                "GFW API token is not configured. Please add GFW_API_TOKEN to your .env file "
                "or pass api_token to GlobalFishingWatchAISProvider."
            )

        # 1. Build Query Parameters and Payload
        report_url = f"{self.base_url}/report"
        geojson_polygon = self._build_geojson_polygon(request.bounding_box)
        date_range_str = self._format_date_range(request.start_time, request.end_time)

        params: Dict[str, str] = {
            "datasets[0]": self.dataset,
            "format": "JSON",
            "group-by": self.group_by,
            "temporal-resolution": self.temporal_resolution,
            "spatial-resolution": self.spatial_resolution,
            "spatial-aggregation": "false",
            "date-range": date_range_str,
        }

        headers: Dict[str, str] = {
            "Authorization": f"Bearer {self._api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        body: Dict[str, Any] = {
            "geojson": geojson_polygon,
        }

        # 2. Acquire concurrency guard so concurrent requests do not collide (Requirement 5)
        with _GFW_CONCURRENCY_LOCK:
            resp_json: Optional[Dict[str, Any]] = None
            current_backoff = 1.0

            for attempt in range(1, self.max_retries + 1):
                try:
                    logger.info(
                        "Executing GFW 4Wings report query (attempt %d/%d) for date range %s "
                        "(timeout: connect=%.1fs, read=%.1fs)",
                        attempt,
                        self.max_retries,
                        date_range_str,
                        self.timeout[0],
                        self.timeout[1],
                    )
                    resp = self._session.post(
                        report_url,
                        params=params,
                        json=body,
                        headers=headers,
                        timeout=self.timeout,  # Bounded connect/read timeout (Requirement 2)
                    )

                    # HTTP 200: Successful report generation
                    if resp.status_code == 200:
                        resp_json = resp.json()
                        break

                    # HTTP 401: Unauthorized (Invalid or missing token)
                    if resp.status_code == 401:
                        raise AISProviderConfigError(
                            "GFW API authentication failed (HTTP 401). "
                            "Please verify your GFW_API_TOKEN in .env."
                        )

                    # HTTP 403: Forbidden (Token lacks dataset permission)
                    if resp.status_code == 403:
                        raise AISProviderConnectionError(
                            f"GFW API access forbidden (HTTP 403). "
                            f"Token lacks access permission for dataset '{self.dataset}'."
                        )

                    # HTTP 429: Too Many Requests / Concurrent Report Running (Requirement 4)
                    if resp.status_code == 429:
                        header_val = resp.headers.get("Retry-After")
                        if header_val:
                            try:
                                retry_after = max(float(header_val), 0.0)
                            except (ValueError, TypeError):
                                retry_after = current_backoff + random.uniform(0.1, 0.5)
                        else:
                            # Bounded exponential backoff + jitter
                            jitter = random.uniform(0.1, 0.5)
                            retry_after = min(current_backoff + jitter, 60.0)

                        if attempt < self.max_retries:
                            logger.warning(
                                "GFW 429 Too Many Requests (attempt %d). Waiting %.2f seconds before retry.",
                                attempt,
                                retry_after,
                            )
                            time.sleep(retry_after)
                            current_backoff *= self.backoff_factor
                            continue
                        else:
                            raise AISProviderConnectionError(
                                self._sanitize(
                                    f"GFW API rate limit or concurrency quota exceeded (HTTP 429): {resp.text}"
                                )
                            )

                    # HTTP 524: Gateway Timeout (> 100s processing) (Requirement 3 & 6)
                    if resp.status_code == 524:
                        logger.warning(
                            "GFW report timed out at gateway (HTTP 524). Attempting bounded recovery via /last-report "
                            "(max recovery time: %.1fs). Note: /last-report does not guarantee recovery.",
                            self.max_recovery_timeout,
                        )
                        recovered = self._recover_last_report(headers)
                        if recovered is not None:
                            resp_json = recovered
                            break

                        # Do NOT re-POST the heavy request on 524; raise bounded recovery failure
                        raise AISProviderConnectionError(
                            f"GFW report timed out (HTTP 524) and could not be recovered from /last-report "
                            f"within the bounded recovery limit of {self.max_recovery_timeout:.0f}s. "
                            f"Note: /last-report does not guarantee recovery. "
                            f"For faster interactive queries, consider reducing the time window or spatial area."
                        )

                    # Other HTTP Errors
                    if resp.status_code >= 400:
                        raise AISProviderError(
                            self._sanitize(
                                f"GFW 4Wings report API returned HTTP {resp.status_code}: {resp.text}"
                            )
                        )

                except requests.exceptions.Timeout as timeout_err:
                    logger.warning(
                        "GFW request timed out after %.1fs (attempt %d/%d). Checking /last-report...",
                        self.timeout[1],
                        attempt,
                        self.max_retries,
                    )
                    # Attempt quick recovery check in case report finished on server
                    try:
                        recovered = self._recover_last_report(
                            headers,
                            max_recovery_timeout=min(self.max_recovery_timeout, 15.0),
                        )
                        if recovered is not None:
                            resp_json = recovered
                            break
                    except Exception:
                        pass

                    if attempt < self.max_retries:
                        jitter = random.uniform(0.1, 0.5)
                        delay = min(current_backoff + jitter, 30.0)
                        logger.warning("Retrying GFW request in %.2f seconds...", delay)
                        time.sleep(delay)
                        current_backoff *= self.backoff_factor
                        continue
                    raise AISProviderConnectionError(
                        self._sanitize(
                            f"GFW API request timed out after {self.timeout[1]:.1f}s across {self.max_retries} attempts: {timeout_err}"
                        )
                    ) from timeout_err

                except requests.exceptions.ConnectionError as conn_err:
                    if attempt < self.max_retries:
                        jitter = random.uniform(0.1, 0.5)
                        delay = min(current_backoff + jitter, 30.0)
                        logger.warning(
                            "GFW network error on attempt %d: %s. Retrying in %.2f seconds.",
                            attempt,
                            self._sanitize(conn_err),
                            delay,
                        )
                        time.sleep(delay)
                        current_backoff *= self.backoff_factor
                        continue
                    raise AISProviderConnectionError(
                        self._sanitize(
                            f"Failed to connect to GFW API after {self.max_retries} attempts: {conn_err}"
                        )
                    ) from conn_err

        if resp_json is None:
            raise AISProviderError("GFW API query failed to produce a valid response.")

        # 3. Parse observations
        observations = self._extract_observations_from_json(resp_json)
        if not observations:
            logger.info("GFW query returned 0 matching presence observations.")
            return self._empty_canonical_df()

        # 4. Normalize to Canonical AIS DataFrame
        df_raw = pd.DataFrame(observations)
        df_canonical = self._normalize_to_canonical(df_raw, request)
        return df_canonical

    def _extract_observations_from_json(self, resp_json: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract individual vessel presence records from GFW 4wings response structure.

        Handles nested dataset entries (e.g. entries[0]["public-global-presence:latest"]),
        versioned keys, and flat lists.
        """
        entries = resp_json.get("entries", [])
        if not entries:
            if "data" in resp_json and isinstance(resp_json["data"], list):
                return resp_json["data"]
            return []

        observations: List[Dict[str, Any]] = []

        for entry in entries:
            if isinstance(entry, dict):
                matched_key = False
                for k, val in entry.items():
                    if isinstance(val, list):
                        observations.extend(val)
                        matched_key = True
                if not matched_key:
                    observations.append(entry)
            elif isinstance(entry, list):
                observations.extend(entry)

        return observations

    def _normalize_to_canonical(
        self,
        df: pd.DataFrame,
        request: AISSearchRequest,
    ) -> pd.DataFrame:
        """Transform raw GFW response records into canonical AIS schema.

        Distinguishes:
        1. GFW vessel-presence observations (data_source='gfw_vessel_presence')
        2. Grid-cell center coordinates (is_grid_cell_center=True, is_raw_trajectory=False)
        3. Vessel identity (vessel_id, mmsi, shipName, imo, callsign, vesselType, flag)
        4. Temporal aggregation (temporal_aggregation='HOURLY')
        5. Vessel presence hours (hours, presence_hours)
        """
        if df.empty:
            return self._empty_canonical_df()

        normalized = pd.DataFrame()

        # 1. MMSI resolution (supporting camelCase and snake_case)
        mmsi_series = pd.Series(index=df.index, dtype="object")
        for col in ["mmsi", "MMSI"]:
            if col in df.columns:
                mmsi_series = mmsi_series.combine_first(df[col].dropna())

        if mmsi_series.isna().all():
            vessel_id_series = pd.Series(index=df.index, dtype="object")
            for col in ["vesselId", "vessel_id", "vesselID"]:
                if col in df.columns:
                    vessel_id_series = vessel_id_series.combine_first(df[col].dropna())
            if not vessel_id_series.isna().all():
                extracted = vessel_id_series.astype(str).str.extract(r"(\d{9})")[0]
                mmsi_series = pd.to_numeric(extracted, errors="coerce")

        normalized["mmsi"] = pd.to_numeric(mmsi_series, errors="coerce")
        valid_mmsi = normalized["mmsi"].notna() & (normalized["mmsi"] > 0)
        normalized = normalized[valid_mmsi].copy()
        df = df[valid_mmsi].copy()
        if normalized.empty:
            return self._empty_canonical_df()

        normalized["mmsi"] = normalized["mmsi"].astype(np.int64)

        # 2. Timestamp resolution (preferring entryTimestamp, date, etc.)
        ts_raw = pd.Series(index=df.index, dtype="object")
        for col in ["entryTimestamp", "entry_timestamp", "date", "firstTransmissionDate", "lastTransmissionDate", "timestamp"]:
            if col in df.columns:
                ts_raw = ts_raw.combine_first(df[col].dropna())

        if ts_raw.isna().all():
            return self._empty_canonical_df()

        normalized["timestamp"] = pd.to_datetime(ts_raw, utc=True, errors="coerce")
        valid_ts = normalized["timestamp"].notna()
        normalized = normalized[valid_ts].copy()
        df = df[valid_ts].copy()
        if normalized.empty:
            return self._empty_canonical_df()

        # 3. Coordinate resolution (representing grid-cell centers)
        lat_raw = pd.Series(index=df.index, dtype="object")
        for col in ["lat", "latitude", "LAT"]:
            if col in df.columns:
                lat_raw = lat_raw.combine_first(df[col].dropna())

        lon_raw = pd.Series(index=df.index, dtype="object")
        for col in ["lon", "longitude", "LON"]:
            if col in df.columns:
                lon_raw = lon_raw.combine_first(df[col].dropna())

        if lat_raw.isna().all() or lon_raw.isna().all():
            return self._empty_canonical_df()

        normalized["latitude"] = pd.to_numeric(lat_raw, errors="coerce")
        normalized["longitude"] = pd.to_numeric(lon_raw, errors="coerce")

        valid_coords = (
            normalized["latitude"].notna()
            & normalized["longitude"].notna()
            & (normalized["latitude"] >= LAT_MIN)
            & (normalized["latitude"] <= LAT_MAX)
            & (normalized["latitude"] != LATITUDE_SENTINEL)
            & (normalized["longitude"] >= LON_MIN)
            & (normalized["longitude"] <= LON_MAX)
            & (normalized["longitude"] != LONGITUDE_SENTINEL)
        )

        normalized = normalized[valid_coords].copy()
        df = df[valid_coords].copy()
        if normalized.empty:
            return self._empty_canonical_df()

        # 4. Explicit grid-cell center & trajectory limitation flags
        normalized["is_grid_cell_center"] = True
        normalized["is_raw_trajectory"] = False
        normalized["data_source"] = "gfw_vessel_presence"
        normalized["temporal_aggregation"] = self.temporal_resolution
        normalized["is_suspicious_zero"] = (
            (normalized["latitude"] == 0.0) & (normalized["longitude"] == 0.0)
        )

        # 5. Metadata fields (supporting both camelCase and snake_case row-by-row)
        name_raw = pd.Series(index=df.index, dtype="object")
        for col in ["shipName", "ship_name", "vessel_name", "name"]:
            if col in df.columns:
                name_raw = name_raw.combine_first(df[col].dropna())
        normalized["vessel_name"] = name_raw.astype(str).replace("nan", np.nan)

        imo_raw = pd.Series(index=df.index, dtype="object")
        for col in ["imo", "imo_number", "IMO"]:
            if col in df.columns:
                imo_raw = imo_raw.combine_first(df[col].dropna())
        normalized["imo"] = imo_raw.astype(str).replace("nan", np.nan)

        callsign_raw = pd.Series(index=df.index, dtype="object")
        for col in ["callsign", "call_sign", "callSign"]:
            if col in df.columns:
                callsign_raw = callsign_raw.combine_first(df[col].dropna())
        normalized["callsign"] = callsign_raw.astype(str).replace("nan", np.nan)

        type_raw = pd.Series(index=df.index, dtype="object")
        for col in ["vesselType", "vessel_type", "shiptype", "vesseltype"]:
            if col in df.columns:
                type_raw = type_raw.combine_first(df[col].dropna())
        normalized["vessel_type"] = type_raw.astype(str).replace("nan", np.nan)

        flag_raw = pd.Series(index=df.index, dtype="object")
        for col in ["flag", "flag_state"]:
            if col in df.columns:
                flag_raw = flag_raw.combine_first(df[col].dropna())
        if not flag_raw.isna().all():
            normalized["flag"] = flag_raw.astype(str).replace("nan", np.nan)

        vessel_id_raw = pd.Series(index=df.index, dtype="object")
        for col in ["vesselId", "vessel_id", "vesselID"]:
            if col in df.columns:
                vessel_id_raw = vessel_id_raw.combine_first(df[col].dropna())
        if not vessel_id_raw.isna().all():
            normalized["vessel_id"] = vessel_id_raw.astype(str).replace("nan", np.nan)

        hours_raw = pd.Series(index=df.index, dtype="object")
        for col in ["hours", "presence_hours"]:
            if col in df.columns:
                hours_raw = hours_raw.combine_first(df[col].dropna())
        if not hours_raw.isna().all():
            normalized["hours"] = pd.to_numeric(hours_raw, errors="coerce")
            normalized["presence_hours"] = normalized["hours"]

        exit_raw = pd.Series(index=df.index, dtype="object")
        for col in ["exitTimestamp", "exit_timestamp"]:
            if col in df.columns:
                exit_raw = exit_raw.combine_first(df[col].dropna())
        if not exit_raw.isna().all():
            normalized["exit_timestamp"] = pd.to_datetime(exit_raw, utc=True, errors="coerce")

        # Unreported kinematic fields in GFW grid presence
        for col in ["sog", "cog", "heading", "nav_status", "length", "width", "draught"]:
            if col in df.columns:
                normalized[col] = df[col]
            else:
                normalized[col] = np.nan

        # 6. Exact Temporal Filtering: [request.start_time, request.end_time]
        temporal_mask = (
            (normalized["timestamp"] >= request.start_time)
            & (normalized["timestamp"] <= request.end_time)
        )
        normalized = normalized[temporal_mask].copy()
        if normalized.empty:
            return self._empty_canonical_df()

        # 7. Exact Spatial Radius Filtering (adds geodesic distance_km)
        spatial_filtered = filter_by_radius(
            data=normalized,
            center_latitude=request.latitude,
            center_longitude=request.longitude,
            radius_km=request.radius_km,
            buffer_km=request.buffer_km,
            use_bounding_box=True,
        )

        if spatial_filtered.empty:
            return self._empty_canonical_df()

        # 8. Deduplicate and sort
        deduped = spatial_filtered.drop_duplicates(
            subset=["mmsi", "timestamp"], keep="last"
        )
        sorted_df = deduped.sort_values(by=["mmsi", "timestamp"]).reset_index(drop=True)

        # Attach metadata explaining data limitations
        sorted_df.attrs["data_source"] = "gfw_vessel_presence"
        sorted_df.attrs["is_raw_trajectory"] = False
        sorted_df.attrs["is_grid_cell_center"] = True
        sorted_df.attrs["temporal_aggregation"] = self.temporal_resolution
        sorted_df.attrs["data_limitation_note"] = (
            "GFW public-global-presence is an AIS-derived vessel-presence dataset (~1 position/hr) "
            "aggregated onto a spatial grid. Coordinates represent grid-cell centers rather than point-by-point "
            "raw AIS sensor trajectories. True trajectory kinematics (SOG, COG, Heading) are not present."
        )

        return sorted_df

    def _empty_canonical_df(self) -> pd.DataFrame:
        """Return an empty DataFrame containing canonical schema and provenance columns."""
        cols = REQUIRED_COLUMNS + [
            "sog",
            "cog",
            "heading",
            "vessel_name",
            "imo",
            "callsign",
            "vessel_type",
            "nav_status",
            "length",
            "width",
            "draught",
            "is_suspicious_zero",
            "distance_km",
            "is_grid_cell_center",
            "is_raw_trajectory",
            "data_source",
            "temporal_aggregation",
        ]
        empty_df = pd.DataFrame(columns=cols)
        empty_df.attrs["data_source"] = "gfw_vessel_presence"
        empty_df.attrs["is_raw_trajectory"] = False
        empty_df.attrs["is_grid_cell_center"] = True
        empty_df.attrs["temporal_aggregation"] = self.temporal_resolution
        return empty_df


# Convenience alias matching naming conventions
GFWAISProvider = GlobalFishingWatchAISProvider
