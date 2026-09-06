# AIS Dataset Research & Ingestion Specification

## Automatic Identification System (AIS) Data for Marine Oil Spill Attribution

**Project:** Oil Spill Attribution System  
**Module:** AIS Processing & Vessel Attribution (`ais/`, `attribution/`)  
**Task ID:** AIS-01  
**Author:** Member 5 (AIS / Vessel Attribution)  
**Status:** Approved Research Specification  
**Version:** v1.0  
**Target Implementation:** AIS-02 Data Loader (`ais/data_loader/`)  

---

# 1. Purpose and Role of AIS Data in This Project

The Oil Spill Attribution System identifies vessels potentially responsible for marine oil spills detected via satellite imagery (such as Sentinel-1 SAR). 

While satellite segmentation and GIS modules delineate the physical extent of the oil slick, and oceanographic drift models (hindcasting) estimate the slick's probable origin location and time window, the system requires maritime traffic data to identify candidate vessels operating in the vicinity during that critical window.

```text
Satellite Detection (SAR)
         ↓
Oil Slick Segmentation (AI)
         ↓
Spill Geometry & Centroid (GIS)
         ↓
Backward Drift Simulation (Drift Hindcast)
         ↓
Probable Origin Region + Time Window [T_start, T_end]
         ↓
AIS Processing (ais/) <--- [AIS Raw Data]
   - Data Loading & Schema Normalization (AIS-02)
   - Quality Filtering & Cleaning (AIS-03)
   - Trajectory Reconstruction (AIS-04)
   - Kinematic Interpolation (AIS-05)
   - Spatial & Temporal Window Filtering (AIS-06, AIS-07)
         ↓
Candidate Vessels & Trajectories
         ↓
Vessel Attribution Scoring & Ranking (attribution/)
```

### Core Responsibilities of the AIS Module
1. **Ingest and Normalize:** Parse heterogeneous AIS data sources (NOAA, Danish Maritime Authority, etc.) into a consistent, validated canonical representation.
2. **Filter & Clean:** Detect and reject GPS spoofing, transmission errors, invalid coordinates, sentinel values, and duplicate messages.
3. **Reconstruct Trajectories:** Group discrete, asynchronous position broadcasts by vessel identity (MMSI) into ordered, time-indexed kinematic tracks.
4. **Interpolate Positions:** Estimate vessel locations at exact timestamps matching the hindcast release window.
5. **Spatial and Temporal Filtering:** Extract only candidate vessels whose spatial footprint intersects the probable origin envelope within the release time window.

The AIS module does **not** make legal attribution decisions or assign guilt; it prepares scientifically verified, standardized vessel trajectory candidates for evidence-based attribution scoring.

---

# 2. Public AIS Dataset and Source Options

AIS data is collected by coastal base stations (terrestrial AIS / T-AIS) and satellite constellations (satellite AIS / S-AIS). For research, prototyping, and retrospective spill attribution, several open and restricted public datasets exist:

| Provider | Geographic Coverage | Access Type | File Formats | Update / Resolution | Suitability for Project |
|---|---|---|---|---|---|
| **NOAA MarineCadastre** | US Coastal Waters, Exclusive Economic Zone (EEZ), Great Lakes | Fully Open & Free (Direct HTTPS) | Daily/Monthly CSV, Geodatabase | Downsampled (1 min) & Raw | **Primary benchmark:** Clean schema, extensive documentation, verified ground truth. |
| **Danish Maritime Authority (DMA)** | North Sea, Baltic Sea, Danish Waters | Fully Open & Free (Direct HTTPS / FTP) | Daily / Monthly zipped CSV | High-frequency raw broadcasts (T-AIS) | **Primary European benchmark:** Dense shipping traffic, ideal for complex intersection scenarios. |
| **EMSA (SafeSeaNet / EMODnet)** | European Waters, Mediterranean, Black Sea | Restricted / Institutional (EMSA SafeSeaNet); Aggregated open data via EMODnet | CSV, WMS/WFS, GeoPackage | Monthly/Annual ship density; Raw feeds restricted | **Secondary / Contextual:** Useful for shipping density maps; raw historical tracks require institutional credentials. |
| **Global Fishing Watch (GFW)** | Global (fishing and carrier vessels) | Open for research (API & BigQuery after free registration) | CSV, GeoJSON, BigQuery tables | Daily / 10-minute downsampled | **Supplementary:** Excellent for fishing vessel tracking and transshipment monitoring. |
| **Commercial Aggregators** (Spire, MarineTraffic, VesselFinder) | Global (T-AIS + S-AIS) | Paid / Proprietary API | REST API, WebSocket, CSV | Real-time / High frequency | **Not used for open baseline:** Requires enterprise licenses; out of scope for reproducible open research. |

### Source Details & Access Recommendations

#### 1. NOAA MarineCadastre
- **Maintained by:** Bureau of Ocean Energy Management (BOEM) and National Oceanic and Atmospheric Administration (NOAA).
- **URL:** `https://marinecadastre.gov/ais/`
- **Characteristics:** Provides filtered daily AIS data in standard CSV format. Data fields include MMSI, timestamp, WGS84 coordinates, SOG, COG, heading, vessel name, IMO, call sign, vessel type, status, and dimensions.
- **Project Recommendation:** Adopt as the primary reference format for Atlantic/US maritime oil spill evaluation cases.

#### 2. Danish Maritime Authority (DMA)
- **Maintained by:** Danish Maritime Authority.
- **URL:** `https://www.dma.dk/safety-at-sea/navigational-information/ais-data`
- **Characteristics:** Unfiltered, highly detailed European terrestrial AIS data packaged in zipped CSVs.
- **Project Recommendation:** Adopt as the primary European high-density testbed, particularly suited for shallow waters, busy shipping lanes (Skagerrak/Kattegat), and complex route intersections.

#### 3. European Maritime Safety Agency (EMSA) & EMODnet
- **Characteristics:** EMSA operates the SafeSeaNet maritime information exchange network. Full raw position logs are generally restricted to EU member state maritime authorities for search-and-rescue and vessel traffic monitoring. Public European Marine Observation and Data Network (EMODnet) provides vessel density grids rather than raw individual vessel pings.
- **Project Recommendation:** Document as an operational source for potential deployment, but do not rely on raw EMSA downloads for open pipeline testing.

---

# 3. Typical AIS Message Categories

The International Telecommunication Union standard **ITU-R M.1371** ("Technical characteristics for an automatic identification system using time division multiple access in the VHF maritime mobile band") specifies 27 distinct AIS message types. The messages relevant to trajectory reconstruction and vessel attribution fall into two main categories:

```text
               ┌────────────────────────────────────────────────────────┐
               │              ITU-R M.1371 AIS Messages                 │
               └───────────────────────────┬────────────────────────────┘
                                           │
                 ┌─────────────────────────┴─────────────────────────┐
                 ↓                                                   ↓
     ┌───────────────────────┐                           ┌───────────────────────┐
     │ Dynamic Position Pings│                           │ Static & Voyage Data  │
     │  (Class A & Class B)  │                           │  (Identity & Cargo)   │
     └───────────┬───────────┘                           └───────────┬───────────┘
                 │                                                   │
        +--------+--------+                                 +--------+--------+
        ↓                 ↓                                 ↓                 ↓
   Types 1, 2, 3       Type 18                            Type 5           Type 24
(Class A Position) (Class B Position)                  (Class A Static) (Class B Static)
```

### 3.1 Dynamic Position Reports (Types 1, 2, 3, 18, 19)
- **Type 1 (Position Report Class A - Scheduled):** Standard autonomous position report broadcast by commercial vessels subject to SOLAS regulations.
- **Type 2 (Position Report Class A - Assigned):** Broadcast in response to a competent authority base station assignment.
- **Type 3 (Position Report Class A - Special/Interrogated):** Broadcast in response to an interrogation poll.
- **Type 18 (Standard Class B Equipment Position Report):** Broadcast by smaller recreational craft, fishing vessels, and tugs operating Class B transponders.
- **Type 19 (Extended Class B Position Report):** Includes Class B position plus vessel dimensions and ship type.

**Key Dynamic Fields Extracted:**
- MMSI (Maritime Mobile Service Identity)
- Navigational Status (e.g., under way using engine, at anchor, moored, restricted manoeuvrability)
- Latitude and Longitude (WGS84 1/10000 minute resolution)
- Speed Over Ground (SOG) in 0.1 knot increments
- Course Over Ground (COG) in 0.1 degree increments
- True Heading (0 to 359 degrees)
- UTC Timestamp (seconds counter 0–59 in raw message; fully qualified timestamp in processed provider CSVs)

### 3.2 Static and Voyage-Related Data (Type 5)
Broadcast every 6 minutes or upon request by Class A vessels.
- **Identity Fields:** IMO number, Call sign, Vessel Name (up to 20 ASCII characters).
- **Classification:** Ship and Cargo Type (numeric codes 20–89: Tanker, Cargo, Passenger, Tug, etc.).
- **Physical Dimensions:** Length, Beam (width), Maximum present static draught (0.1 m increments).
- **Voyage Fields:** Destination, Estimated Time of Arrival (ETA).

### 3.3 Class B Static Data (Type 24 Parts A and B)
Broadcast in two parts every 6 minutes for Class B stations:
- **Part A:** MMSI, Vessel Name.
- **Part B:** Ship type, Cargo type, Call sign, Dimensions.

### Ingestion Strategy:
In pre-parsed datasets (like NOAA and DMA), dynamic position data and static vessel metadata are typically joined into unified tabular rows. Where separate static feeds are provided, the loader must maintain an MMSI-keyed lookup table to associate vessel metadata with position tracks.

---

# 4. Core Fields Needed by the Attribution Project

To enable spatio-temporal correlation and trajectory analysis, each record ingested by our pipeline must capture or derive the following core fields:

| Field | Required / Optional | Data Type | Physical Unit | Description | Role in Pipeline |
|---|---|---|---|---|---|
| `mmsi` | **Required** | Integer / String | Dimensionless | 9-digit maritime mobile station identifier | Primary entity key for trajectory grouping |
| `timestamp` | **Required** | Timestamp (UTC) | ISO 8601 (UTC) | Time of position fix | Temporal filtering & chronological sorting |
| `latitude` | **Required** | Float | Decimal degrees | WGS84 latitude | Spatial filtering, distance calculations |
| `longitude` | **Required** | Float | Decimal degrees | WGS84 longitude | Spatial filtering, distance calculations |
| `sog` | Optional | Float | Knots | Speed Over Ground | Kinematic plausibility, loitering analysis |
| `cog` | Optional | Float | Degrees `[0, 360)` | Course Over Ground | Heading alignment, trajectory interpolation |
| `heading` | Optional | Float / Int | Degrees `[0, 359]` | True Heading | Vessel orientation vs drift direction |
| `nav_status` | Optional | Int / String | Code `[0, 15]` | Navigational status code | Engine state, operational context |
| `vessel_name` | Optional | String | Text | Transmitted ship name | Human-readable attribution reporting |
| `vessel_type` | Optional | Int / String | Category code | Ship type code (e.g. Tanker, Cargo) | Risk weighting (e.g. oil tanker vs tug) |
| `imo` | Optional | Integer / String | 7-digit identifier | International Maritime Organization number | Cross-referencing vessel registers |
| `draught` | Optional | Float | Meters | Maximum static draught | Vessel displacement / spill risk indicator |

---

# 5. Differences in Source Schemas and Column Naming

Different AIS providers publish CSV files with distinct column naming conventions, date formatting, and missing value encodings.

### Schema Comparison Matrix

| Project Canonical Field | NOAA MarineCadastre | Danish Maritime Authority (DMA) | Generic Decoded Tabular CSV |
|---|---|---|---|
| `mmsi` | `MMSI` | `MMSI` | `mmsi`, `user_id` |
| `timestamp` | `BaseDateTime` | `# Timestamp` | `timestamp`, `time`, `date_time_utc` |
| `latitude` | `LAT` | `Latitude` | `lat`, `latitude` |
| `longitude` | `LON` | `Longitude` | `lon`, `long`, `longitude` |
| `sog` | `SOG` | `SOG` | `sog`, `speed`, `speed_over_ground` |
| `cog` | `COG` | `COG` | `cog`, `course`, `course_over_ground` |
| `heading` | `Heading` | `Heading` | `heading`, `true_heading`, `th` |
| `nav_status` | `Status` | `Navigational status` | `nav_status`, `status` |
| `vessel_name` | `VesselName` | `Name` | `vessel_name`, `ship_name`, `name` |
| `vessel_type` | `VesselType` | `Ship type` | `vessel_type`, `ship_type`, `shiptype` |
| `imo` | `IMO` | `IMO` | `imo`, `imo_number` |
| `callsign` | `CallSign` | `Callsign` | `callsign`, `call_sign` |
| `length` | `Length` | `Length` | `length`, `loa` |
| `width` | `Width` | `Width` | `width`, `beam` |
| `draught` | `Draft` | `Draught` | `draft`, `draught` |

### Ingestion Mapping Architecture
The loader must implement a flexible column alias dictionary:
```python
COLUMN_ALIASES = {
    "mmsi": ["mmsi", "user_id"],
    "timestamp": ["basedatetime", "timestamp", "time", "date_time_utc", "date_time"],
    "latitude": ["lat", "latitude"],
    "longitude": ["lon", "long", "longitude"],
    "sog": ["sog", "speed", "speed_over_ground"],
    "cog": ["cog", "course", "course_over_ground"],
    "heading": ["heading", "true_heading", "th"],
    "nav_status": ["status", "navigational_status", "nav_status"],
    "vessel_name": ["vesselname", "name", "ship_name"],
    "vessel_type": ["vesseltype", "ship_type", "shiptype"],
    "imo": ["imo", "imo_number"],
    "callsign": ["callsign", "call_sign"],
    "draught": ["draft", "draught"],
    "length": ["length", "loa"],
    "width": ["width", "beam"]
}
```
During ingestion, the loader matches source headers case-insensitively against the aliases and maps them directly to canonical fields.

> **Crucial Rule on Coordinate Axis Interpretation:**
> Generic labels such as `"x"` and `"y"` are **intentionally omitted** from automatic latitude/longitude aliases. Coordinate axis interpretation must never be assumed without explicit source schema or CRS metadata confirming axis ordering. As emphasized in [`ARCHITECTURE.md` Section 30](file:///c:/oil-spill-attribution/docs/architecture/ARCHITECTURE.md#L1260-L1277), assuming $x = \text{longitude}$ and $y = \text{latitude}$ without verification introduces severe spatial orientation errors, particularly because standard geodetic specifications (such as EPSG:4326 in WGS84) conventionally define coordinates in Latitude-first (Northing) order while Cartesian GIS formats use Longitude-first (Easting) order. The loader strictly requires explicit geographic labels (`lat`, `latitude`, `lon`, `longitude`).

---

# 6. Timestamp Considerations

Timestamp correctness is critical: a 30-minute timestamp error will completely invalidate trajectory correlation with ocean drift hindcasts.

### 6.1 Strict UTC Requirement
- In compliance with [`ARCHITECTURE.md` Section 29](file:///c:/oil-spill-attribution/docs/architecture/ARCHITECTURE.md#L1226-L1258), **all timestamps within the system must be explicitly in UTC**.
- Naive timestamps must never be assumed to be local time; when parsing ISO or string representations without timezone offsets, they must be localized to UTC.
- All datetime outputs must use timezone-aware `pd.Timestamp(..., tz='UTC')` or ISO 8601 strings ending in `Z` (e.g. `2026-01-15T14:30:00Z`).

### 6.2 Provider-Specific Timestamp Formats
- **NOAA MarineCadastre:** ISO 8601 strings: `YYYY-MM-DDTHH:MM:SS` (e.g., `2024-01-01T00:00:15`). Guaranteed UTC by NOAA specifications.
- **DMA:** Delimited European format: `DD/MM/YYYY HH:MM:SS` (e.g., `31/01/2024 23:59:58`). Explicitly recorded in UTC.
- **Unix Epoch:** Integer or floating-point seconds/milliseconds since `1970-01-01 00:00:00 UTC`.

### 6.3 Common Timestamp Anomalies
1. **Clock Skew / Reversals:** AIS transponders derive time from GPS fixes, but intermittent transmission re-queuing by base stations can produce out-of-order records.
2. **Duplicate Timestamps:** The same vessel may broadcast identical timestamps across different receiving antennas (e.g. received simultaneously by two coastal stations).
3. **Leap Seconds and Roll-Over:** Raw NMEA sentences contain only second counters (0–59), with base stations interpolating the full date. Parsing errors in upstream receivers occasionally generate historical epoch stamps (`1970-01-01`).
4. **Non-chronological ordering:** Multi-station CSV aggregations are rarely sorted by vessel and timestamp. Ingestion must sort by `(mmsi, timestamp)` before downstream trajectory processing.

---

# 7. Coordinate Considerations

Spatial accuracy is governed by [`ARCHITECTURE.md` Section 30](file:///c:/oil-spill-attribution/docs/architecture/ARCHITECTURE.md#L1260-L1277).

### 7.1 Coordinate Reference System (CRS)
- **Standard CRS:** WGS 84 (EPSG:4326), geodetic decimal degrees.
- In geographic calculations, coordinates must be explicitly identified as:
  - `longitude` = Easting (X-axis in Cartesian GIS representations)
  - `latitude` = Northing (Y-axis in Cartesian GIS representations)
- **Axis Order Safeguard:** Generic coordinate labels such as `x` and `y` must not be assumed to map to longitude and latitude without explicit CRS or source metadata confirming axis orientation.

### 7.2 Valid Coordinate Bounds
- **Latitude:** Valid physical domain: `[-90.0, 90.0]`.
- **Longitude:** Valid physical domain: `[-180.0, 180.0]`.

### 7.3 Invalid, Sentinel, and Suspicious Values
The ITU-R M.1371 specification establishes special sentinel values to indicate unmeasured, faulty, or missing sensor data:
- **Latitude Sentinel:** `91.0` (`0x3412140` in raw binary) = Latitude not available / default. Automatically filtered out as an explicit sentinel.
- **Longitude Sentinel:** `181.0` (`0x6791AC0` in raw binary) = Longitude not available / default. Automatically filtered out as an explicit sentinel.
- **Suspicious Zero Coordinates (0.0° N, 0.0° E / "Null Island"):** The coordinates (0.0°, 0.0°) represent a legitimate geographic point in the Gulf of Guinea (South Atlantic). However, in maritime telemetry, uninitialized GNSS receivers or default firmware values often emit (0.0, 0.0) upon losing satellite fix. Therefore, (0.0, 0.0) must **not** be treated as universally invalid or unconditionally rejected by the loader, as doing so would prevent valid analyses in West African maritime corridors. Instead, the loader should preserve the coordinate while providing the ability (via quality indicators or parameter controls) to distinguish legitimate coordinates from suspected missing fixes, enabling downstream spatial filtering (AIS-06) to evaluate context.
- **NaN / Infinity:** Non-numeric or missing coordinate records must be rejected.

---

# 8. Common AIS Data-Quality Problems

Raw AIS data is notoriously noisy, broadcast over unencrypted VHF channels, and subject to sensor failures and human configuration errors:

```text
┌──────────────────────────────┬───────────────────────────────────────────┬──────────────────────────────────────────┐
│ Anomaly Category             │ Observed Symptom                          │ Ingestion & Filtering Action             │
├──────────────────────────────┼───────────────────────────────────────────┼──────────────────────────────────────────┤
│ 1. Coordinate Sentinel       │ lat = 91.0, lon = 181.0                   │ REJECT / FILTER sentinel record          │
│ 2. Suspicious Zero Ping      │ lat = 0.0, lon = 0.0                      │ PRESERVE & FLAG (evaluate vs spill ROI)  │
│ 3. Coordinate Out-of-bounds  │ |lat| > 90.0 or |lon| > 180.0             │ REJECT record                            │
│ 4. Invalid MMSI              │ MMSI = 0, 111111111, or < 200000000       │ REJECT (not a valid MID-assigned ship)   │
│ 5. Duplicate Pings           │ Multiple rows with same (MMSI, timestamp) │ DEDUPLICATE (keep first or highest SOG)  │
│ 6. Speed Sentinel            │ SOG = 102.3 knots (ITU default unavailable│ SET SOG = NaN (preserve position)        │
│ 7. Impossible Speed          │ SOG > 65.0 knots (for commercial cargo)   │ FLAG / SET SOG = NaN                     │
│ 8. Heading Sentinel          │ Heading = 511 (ITU default unavailable)   │ SET Heading = NaN                        │
│ 9. Course Sentinel           │ COG = 360.0 (ITU default unavailable)     │ SET COG = NaN                            │
│ 10. Transmission Blackout    │ Vessel silent for hours, then reappears   │ DETECT track break (AIS-04 gap handling) │
│ 11. Spoofing / Teleportation │ Distance between pings implies Mach speed │ FILTER position jump in trajectory stage │
└──────────────────────────────┴───────────────────────────────────────────┴──────────────────────────────────────────┘
```

### Distinction Between Loader Rejection vs Cleaning / Interpolation:
- **Loader Stage (AIS-02):** Drops records that lack valid identifiers (`mmsi`), valid timestamps, or physically impossible coordinate values ($|\text{lat}| > 90^\circ$ or $|\text{lon}| > 180^\circ$). Automatically filters out explicit ITU sentinels (Lat=91.0, Lon=181.0) and converts sensor sentinels (SOG=102.3, Heading=511, COG=360) to `NaN`. Preserves mathematically valid (0.0, 0.0) coordinates with a quality flag rather than unconditionally dropping them.
- **Cleaning Stage (AIS-03):** Performs domain-specific kinematic validation (calculating Haversine velocity between consecutive pings, detecting jumps, identifying spoofing, evaluating whether (0,0) pings are discontinuous anomalies).
- **Trajectory Stage (AIS-04 / AIS-05):** Handles trajectory segmentation across transmission blackouts and interpolates intermediate positions.

---

# 9. AIS Update and Reporting Frequency Considerations

### 9.1 Authoritative Standard Reporting Intervals (ITU-R M.1371-5)

Under ITU-R M.1371-5, shipborne mobile transponders autonomously regulate their transmission intervals based on dynamic navigational status, speed over ground (SOG), and rate of course change:

| Vessel Dynamic Status / Condition | Class A Nominal Interval | Class B "CS" (CSTDMA) Interval | Class B "SO" (SOTDMA) Interval |
|---|---|---|---|
| At anchor or moored (speed $\le$ 3 knots) | 3 minutes | 3 minutes (speed $\le$ 2 kn) | 3 minutes (speed $\le$ 2 kn) |
| At anchor or moored (speed > 3 knots) | 10 seconds | 30 seconds (speed > 2 kn) | 30 seconds (2 < speed $\le$ 14 kn) |
| Under way (0–14 knots) | 10 seconds | 30 seconds | 30 seconds |
| Under way (0–14 knots, changing course) | $3\frac{1}{3}$ seconds | 30 seconds | 30 seconds |
| Under way (14–23 knots) | 6 seconds | 30 seconds | 15 seconds |
| Under way (14–23 knots, changing course) | 2 seconds | 30 seconds | 15 seconds |
| Under way (> 23 knots) | 2 seconds | 30 seconds | 5 seconds |
| Under way (> 23 knots, changing course) | 2 seconds | 30 seconds | 5 seconds |
| Static & Voyage Data (Class A Type 5 / Class B Type 24) | 6 minutes or on request | 6 minutes or on request | 6 minutes or on request |

### 9.2 Standard Reporting Behavior vs. Real-World Datasets & Project Implementation

It is critical to distinguish the theoretical VHF transmission rates defined above from real-world data characteristics encountered in the project:

1. **Provider Downsampling:** Many public data distributors resample or thin raw position broadcasts to manage dataset volume. For example, NOAA MarineCadastre provides records downsampled to a 1-minute interval for most commercial traffic, whereas Danish Maritime Authority (DMA) publishes un-thinned terrestrial VHF logs containing full multi-second bursts.
2. **Satellite AIS (S-AIS) Detection Latency:** While coastal terrestrial receivers capture continuous VHF updates, satellite AIS receivers orbit at approximately 500–800 km altitude and observe vessels only during constellation orbital passes. This can introduce detection gaps ranging from 15 minutes to several hours in open ocean regions.
3. **Project Implementation Assumptions:**
   - **Asynchronous Arrival:** Because vessels report autonomously at differing rates, observations across distinct candidate vessels are never temporally synchronized.
   - **Need for Trajectory Reconstruction & Interpolation:** A candidate vessel rarely broadcasts a position ping at the exact second or minute corresponding to an estimated oil spill release. Therefore, trajectory reconstruction (AIS-04) and position interpolation (AIS-05) are mathematically mandatory rather than optional conveniences.
   - **Chunked Stream Processing:** A single day of un-thinned coastal data can contain tens of millions of records. The AIS-02 loader must support reading in chunks or streaming subsets to avoid memory exhaustion during trajectory reconstruction.

---

# 10. Recommendations for the AIS-02 Loader

Based on the dataset research, the implementation of AIS-02 (`ais/data_loader/`) should follow these strict design guidelines:

### 10.1 File Formats and Scope
- **Scope Boundary:** The AIS-02 loader is explicitly designed for decoded tabular AIS data (such as CSV archives published by NOAA MarineCadastre and the Danish Maritime Authority). Raw bit-level NMEA 0183 (AIVDM/AIVDO) sentence decoding is intentionally kept outside the initial AIS-02 scope as all primary reference datasets provide standardized decoded tabular data.
- **Formats Supported Initially:**
  - Plain CSV (`.csv`)
  - Gzip-compressed CSV (`.csv.gz`)
  - Zip-compressed CSV (`.zip`)
  - Extensible design to allow Parquet (`.parquet`) in future iterations.

### 10.2 Strict Column Enforcement
- **Required Columns (Must exist or map from aliases):**
  - `mmsi`
  - `timestamp`
  - `latitude`
  - `longitude`
- **Optional Columns (Populated if present, filled with `None`/`NaN` if absent):**
  - `sog`, `cog`, `heading`, `nav_status`, `vessel_name`, `vessel_type`, `imo`, `callsign`, `draught`, `length`, `width`

### 10.3 Ingestion Rules
1. **Header Alias Resolution:** Normalize all column names to lowercase, stripped strings, and map them using the canonical alias dictionary.
2. **Missing Required Columns:** Raise a descriptive `AISDataLoaderError` indicating missing fields.
3. **Timestamp Normalization:** Parse into UTC timezone-aware pandas datetimes (`pd.to_datetime(..., utc=True)`). Reject unparseable rows.
4. **Coordinate Validation & Quality Flagging:**
   - Require $-90.0 \le \text{latitude} \le 90.0$ and $-180.0 \le \text{longitude} \le 180.0$.
   - Automatically filter out standard sentinel values (`lat == 91.0`, `lon == 181.0`).
   - For `(0.0, 0.0)` coordinates, do **not** unconditionally reject the record. Instead, flag it as a suspected missing fix (`is_suspicious_zero=True` or via a quality flags column) while preserving the observation, enabling downstream spatial and cleaning modules to evaluate its legitimacy relative to the region of interest.
5. **Sentinel Conversion:**
   - Convert `sog == 102.3` or `sog < 0` $\rightarrow$ `np.nan`.
   - Convert `cog >= 360.0` or `cog < 0` $\rightarrow$ `np.nan`.
   - Convert `heading == 511` or `heading < 0` or `heading > 359` $\rightarrow$ `np.nan`.
6. **MMSI Validation:**
   - Must be numeric, positive, and formatted as a 9-digit integer (or string representation). Standard maritime MMSIs range from `200000000` to `775999999` (ship stations), with coastal stations beginning with `00`. Zero (`0`) or all-ones (`111111111`) are discarded.
7. **Sorting and Deduplication:**
   - Remove duplicate rows with identical `(mmsi, timestamp)`.
   - Sort output DataFrame deterministically by `['mmsi', 'timestamp']`.
8. **Memory Efficiency:**
   - Provide an optional `chunksize` parameter or bounding-box filter parameter so large daily CSVs can be filtered during stream reading without exhausting host RAM.
9. **Provenance Tracking:**
   - Store metadata on the loaded dataset (file path, row counts before/after cleaning, execution timestamp) to ensure scientific reproducibility.

---

# 11. Canonical AIS Schema Table

The canonical schema represents the standardized internal data structure produced by `ais/data_loader/` and consumed by all subsequent AIS and attribution modules:

| Field Name | Type | Constraints / Valid Range | Nullable | Description |
|---|---|---|---|---|
| `mmsi` | `int64` | 9-digit positive integer | No | Maritime Mobile Service Identity |
| `timestamp` | `datetime64[ns, UTC]` | ISO 8601 UTC | No | Observation time in UTC |
| `latitude` | `float64` | `[-90.0, 90.0]` | No | WGS84 latitude in decimal degrees |
| `longitude` | `float64` | `[-180.0, 180.0]` | No | WGS84 longitude in decimal degrees |
| `sog` | `float64` | `[0.0, 102.2]` | Yes | Speed Over Ground in knots |
| `cog` | `float64` | `[0.0, 360.0)` | Yes | Course Over Ground in degrees |
| `heading` | `float64` | `[0, 359]` | Yes | True Heading in degrees |
| `nav_status` | `int32` / `str` | `0` to `15` or descriptive status | Yes | Navigational status indicator |
| `vessel_name` | `string` | UTF-8 string | Yes | Transmitted vessel name |
| `vessel_type` | `int32` / `str` | Numeric code (e.g. 70-79 Cargo, 80-89 Tanker) | Yes | Vessel category code or description |
| `imo` | `int64` / `string` | 7-digit IMO number | Yes | International Maritime Organization ship ID |
| `callsign` | `string` | Alphanumeric radio callsign | Yes | Vessel radio callsign |
| `length` | `float64` | $> 0.0$ meters | Yes | Overall vessel length |
| `width` | `float64` | $> 0.0$ meters | Yes | Overall vessel beam |
| `draught` | `float64` | $> 0.0$ meters | Yes | Present maximum static draught |

---

# 12. References and Authoritative Sources

1. **ITU-R Recommendation M.1371-5 (02/2014):**  
   *Technical characteristics for an automatic identification system using time division multiple access in the VHF maritime mobile band.*  
   International Telecommunication Union, Geneva.  
   Available: `https://www.itu.int/rec/R-REC-M.1371`

2. **NOAA & BOEM MarineCadastre AIS Documentation:**  
   *National AIS Data Dictionary and User Guide.*  
   Bureau of Ocean Energy Management (BOEM) / National Oceanic and Atmospheric Administration (NOAA).  
   Available: `https://marinecadastre.gov/ais/`

3. **Danish Maritime Authority (DMA):**  
   *AIS Data Description and Download Protocol.*  
   Danish Maritime Authority, Copenhagen.  
   Available: `https://www.dma.dk/safety-at-sea/navigational-information/ais-data`

4. **EMSA (European Maritime Safety Agency):**  
   *SafeSeaNet Maritime Information Exchange System Specifications.*  
   European Maritime Safety Agency, Lisbon.  
   Available: `https://www.emsa.europa.eu/`

5. **IMO Resolution MSC.74(69) Annex 3:**  
   *Recommendation on Performance Standards for Universal Automatic Identification System (AIS).*  
   International Maritime Organization, London.

6. **OpenDRIVE & Global Fishing Watch Research Guidelines:**  
   *Kroodsma, D. A., et al. (2018). Tracking the global footprint of fisheries. Science, 359(6378), 904-908.*  
   DOI: `10.1126/science.aao5646`
