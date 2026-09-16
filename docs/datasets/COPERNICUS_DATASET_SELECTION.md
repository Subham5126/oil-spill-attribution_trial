# Copernicus Marine Dataset Selection & Hydrodynamic Drift Architecture

## 1. Overview & Forensic Motivation

The OILTRACE Member 4 Ocean Current Ingestion and Lagrangian Drift Subsystem reconstructs backward slick drift (-72 hours) and forward slick dispersion (+24 hours) using numerical hydrodynamic models.

Accurate drift modeling requires physical ocean surface current vectors ($u_o$, $v_o$) matching the exact spatiotemporal bounding box of the observed Synthetic Aperture Radar (SAR) slick. Because satellite acquisitions can span both historical decades and near-real-time observations, OILTRACE implements an intelligent, automated Copernicus Marine Service (CMEMS) dataset routing engine.

---

## 2. Product Catalog & Temporal Envelopes

CMEMS partitions global hydrodynamic model data across two primary operational products:

| Parameter | Historical Reanalysis Product | Operational Analysis & Forecast Product |
| :--- | :--- | :--- |
| **Product Identifier** | `GLOBAL_MULTIYEAR_PHY_001_030` | `GLOBAL_ANALYSISFORECAST_PHY_001_024` |
| **Primary Dataset ID** | `cmems_mod_glo_phy_my_0.083deg_P1D-m` | `cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m` |
| **Hourly Dataset ID** | N/A | `cmems_mod_glo_phy_anfc_0.083deg_PT1H-m` |
| **Temporal Span** | `1993-01-01` to `2026-06-23` | `2022-06-01` to rolling present + 10 days |
| **Spatial Grid** | Global ($[-80.0^\circ\text{S}, 90.0^\circ\text{N}]$, $[-180.0^\circ\text{E}, 180.0^\circ\text{E}]$) | Global ($[-80.0^\circ\text{S}, 90.0^\circ\text{N}]$, $[-180.0^\circ\text{E}, 180.0^\circ\text{E}]$) |
| **Grid Resolution** | $0.083^\circ \times 0.083^\circ$ (~1/12°, ~9 km) | $0.083^\circ \times 0.083^\circ$ (~1/12°, ~9 km) |
| **Surface Depth Level** | $0.494\text{ m}$ (Level 0) | $0.494\text{ m}$ (Level 0) |
| **Standard Variables** | `uo` (Eastward velocity, m/s), `vo` (Northward velocity, m/s) | `uo` (Eastward velocity, m/s), `vo` (Northward velocity, m/s) |

---

## 3. Dataset Selection Algorithm

Given target coordinates $(\text{lat}, \text{lon})$, observation timestamp $t_{\text{obs}}$, hindcast duration $H = 72\text{ h}$, and forecast duration $F = 24\text{ h}$:

1. **Calculate Simulation Window**:
   $$t_{\text{start}} = t_{\text{obs}} - 72\text{ hours}$$
   $$t_{\text{end}} = t_{\text{obs}} + 24\text{ hours}$$
2. **Spatial Envelope Validation**:
   - Check if $\text{lat} \in [-80.0, 90.0]$ and $\text{lon} \in [-180.0, 180.0]$.
   - If outside, raise `SpatialUnavailableError` (`SPATIAL_UNAVAILABLE`).
3. **Temporal Envelope Validation**:
   - If $t_{\text{start}} < 1993\text{-}01\text{-}01$, raise `TemporalUnavailableError` (`TEMPORAL_UNAVAILABLE`).
   - If $t_{\text{end}} > t_{\text{now}} + 10\text{ days}$, raise `TemporalUnavailableError` (`TEMPORAL_UNAVAILABLE`).
4. **Dataset Routing Rules**:
   - **Historical Rule**: If $t_{\text{end}} \le 2026\text{-}06\text{-}23$, select `GLOBAL_MULTIYEAR_PHY_001_030` (`cmems_mod_glo_phy_my_0.083deg_P1D-m`).
   - **Operational Rule**: If $t_{\text{start}} \ge 2022\text{-}06\text{-}01$, select `GLOBAL_ANALYSISFORECAST_PHY_001_024` (`cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m`).
   - Note: The temporal range $2022\text{-}06\text{-}01$ to $2026\text{-}06\text{-}23$ is covered by both datasets. Reanalysis is preferred for historical stability.

```
                      1993-01-01                  2022-06-01             2026-06-23       Now + 10d
MULTIYEAR REANALYSIS: |====================================================|
ANALYSIS & FORECAST:                             |============================================|
ROUTING DECISION:     |----- ROUTE TO MULTIYEAR -----|--- ROUTE TO MULTIYEAR ---|-- ROUTE TO ANFC ---|
```

---

## 4. Intelligent Caching Engine

Before making any remote Copernicus API call, the `OceanDataCache` inspects existing NetCDF files in `data/sample/copernicus/` and `data/cache/ocean/`.

### Containment Verification
A local NetCDF is reused if and only if:
1. It contains required variables (`uo`, `vo`).
2. Its geographic extent encompasses the target bounding box with a grid tolerance $\le 0.10^\circ$ (1 Copernicus grid cell):
   $$\text{file}.\text{lat}_{\min} \le \text{req}.\text{lat}_{\min} + 0.10^\circ \quad\text{and}\quad \text{file}.\text{lat}_{\max} \ge \text{req}.\text{lat}_{\max} - 0.10^\circ$$
   $$\text{file}.\text{lon}_{\min} \le \text{req}.\text{lon}_{\min} + 0.10^\circ \quad\text{and}\quad \text{file}.\text{lon}_{\max} \ge \text{req}.\text{lon}_{\max} - 0.10^\circ$$
3. Its temporal range encompasses the full simulation window with a 24-hour margin for daily discretization centerpoints:
   $$\text{file}.t_{\min} \le t_{\text{start}} + 24\text{h} \quad\text{and}\quad \text{file}.t_{\max} \ge t_{\text{end}} - 24\text{h}$$

### Deterministic Filename Generation
Downloaded subsets are cached with standard naming:
`{dataset_id}_{lat_min}_{lat_max}_{lon_min}_{lon_max}_{YYYYMMDD_start}_{YYYYMMDD_end}.nc`

---

## 5. Granular Error Classification

When hydrodynamic data cannot be acquired, OILTRACE emits granular, actionable diagnostics rather than generic failure messages:

| Error Code | Class | Cause & Meaning |
| :--- | :--- | :--- |
| `SPATIAL_UNAVAILABLE` | `SpatialUnavailableError` | Coordinates lie outside CMEMS global oceanic boundaries. |
| `TEMPORAL_UNAVAILABLE` | `TemporalUnavailableError` | Observation date is earlier than 1993 or beyond the forecast horizon. |
| `INSUFFICIENT_TIME_WINDOW` | `InsufficientTimeWindowError` | Requested window cannot be satisfied by continuous hydrodynamic forcing. |
| `AUTHENTICATION_FAILED` | `AuthenticationFailedError` | Invalid Copernicus Marine credentials or unauthenticated session. |
| `NETWORK_ERROR` | `NetworkError` | Connection timeout or remote CMEMS server unavailability. |
| `INVALID_NETCDF` | `InvalidNetCDFError` | Downloaded NetCDF file is corrupted or failed CF metadata contract. |
| `DOWNLOAD_FAILED` | `DownloadFailedError` | Subset extraction failure on Copernicus service. |

---

## 6. Investigation Data Isolation

Every investigation strictly isolates its hydrodynamic results:
- Results are saved to `investigation.result_json["ocean_drift"]` and `investigation.result_json["provenance"]`.
- The exact `copernicus_dataset`, `copernicus_product`, `temporal_window`, and `is_cached` status are recorded.
- Fallback coordinates or demo values (such as Persian Gulf coordinates) are never assigned to North Sea or other ocean scenes. If Copernicus acquisition fails, M4 is marked `BLOCKED` with the truthful error reason.
