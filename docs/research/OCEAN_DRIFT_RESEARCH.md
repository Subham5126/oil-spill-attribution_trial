# Ocean & Drift Modelling

## Technical Research, Architecture and Implementation Specification

**Project:** OCEANTRACE — AI-Based Marine Oil Spill Detection, Drift Analysis and Vessel Attribution
**Module:** Ocean + Drift Modelling
**Folders:** `ocean/`, `drift/`
**Owner:** Member 4
**Status:** Research + implementation specification
**Version:** v0.1

---

# 1. Purpose

The Ocean + Drift module determines how a detected oil spill could have moved through the marine environment.

The module must answer two questions:

### Backward problem

> Given the observed spill location and observation time, where could the spill have originated?

### Forward problem

> Given the observed spill location and environmental conditions, where could the spill move next?

The system must combine:

* ocean surface currents
* wind
* time
* geographic position
* particle-based drift modelling
* uncertainty

The output is not a confirmed source location. It is a **probabilistic origin region and trajectory estimate** that will later be used by the AIS attribution module.

---

# 2. Position in the Overall System

The complete project pipeline is:

```text
Sentinel-1
    ↓
Satellite Processing
    ↓
AI Segmentation
    ↓
GIS Geometry
    ↓
Observed Spill
    ↓
Ocean + Drift
    ↓
Probable Origin + Time Window
    ↓
AIS Filtering
    ↓
Vessel Attribution
    ↓
Backend
    ↓
Frontend
```

The Ocean + Drift module therefore sits between GIS and AIS.

---

# 3. Module Responsibilities

This module owns:

```text
ocean/
├── currents/
├── wind/
├── data_loader/
└── preprocessing/

drift/
├── particle_model/
├── hindcasting/
├── forecasting/
└── probability/
```

The module is responsible for:

* loading ocean-current data
* loading wind data
* synchronizing environmental datasets
* spatial interpolation
* temporal interpolation
* converting environmental data into usable velocity fields
* particle initialization
* forward drift simulation
* backward drift simulation
* hindcasting
* forecasting
* origin probability estimation
* uncertainty estimation
* trajectory output

The module does **not** own:

* Sentinel-1 image processing
* oil-spill segmentation
* mask-to-polygon conversion
* AIS processing
* vessel attribution
* frontend visualization

---

# 4. Inputs

The primary input comes from the GIS module.

Conceptually:

```json
{
  "spill_id": "spill_001",
  "geometry": "...",
  "centroid": [longitude, latitude],
  "area_km2": 18.42,
  "observation_time": "2026-09-05T10:30:00Z"
}
```

Minimum required information:

```text
spill geometry
spill centroid
observation timestamp
```

Optional information:

```text
spill area
spill perimeter
spill orientation
spill bounding box
segmentation uncertainty
```

---

# 5. Outputs

The module must produce structured results.

Example:

```json
{
  "spill_id": "spill_001",
  "observation_time": "2026-09-05T10:30:00Z",
  "simulation": {
    "mode": "backward",
    "duration_hours": 48,
    "time_step_minutes": 30
  },
  "origin": {
    "centroid": [72.18, 18.43],
    "probability": 0.82
  },
  "uncertainty": {
    "radius_km": 14.7
  },
  "particles": [],
  "probability_map": "...",
  "environment": {
    "ocean_source": "Copernicus Marine",
    "wind_source": "ERA5"
  }
}
```

For forecasting:

```json
{
  "spill_id": "spill_001",
  "mode": "forward",
  "forecast_hours": 48,
  "trajectories": [],
  "probability_map": "...",
  "uncertainty": {}
}
```

The exact schema will later be formalized in:

```text
docs/architecture/DATA_CONTRACTS.md
```

---

# 6. Environmental Data

The drift model requires environmental forcing.

The primary environmental variables are:

```text
Surface ocean current
    ├── eastward velocity (u)
    └── northward velocity (v)

Wind
    ├── eastward wind component
    └── northward wind component
```

Additional variables may be incorporated later:

```text
wave-induced Stokes drift
sea surface temperature
mixed-layer depth
tides
ice conditions
```

These are not required for the first baseline.

---

# 7. Primary Ocean Dataset

## Copernicus Marine Global Ocean Physics Analysis and Forecast

Recommended primary ocean-current source:

**Copernicus Marine — Global Ocean Physics Analysis and Forecast**

Product:

```text
GLOBAL_ANALYSISFORECAST_PHY_001_024
```

The current product provides global ocean analysis and forecasts with approximately:

```text
0.083° × 0.083°
```

horizontal resolution.

It provides:

* eastward sea-water velocity
* northward sea-water velocity
* sea-level information
* temperature
* salinity
* mixed-layer information
* wave Stokes drift
* other ocean variables

The product includes hourly surface fields and other temporal products. The global system provides forecasts updated daily.

Copernicus also provides dedicated current datasets, including:

```text
cmems_mod_glo_phy-cur_anfc_0.083deg_PT6H-i
```

for 6-hourly currents and:

```text
cmems_mod_glo_phy_anfc_merged-uv_PT1H-i
```

for hourly surface currents.

---

# 8. Why Copernicus Marine

It is suitable because:

* global coverage
* ocean-current variables are directly available
* surface currents are available
* historical analysis is available
* forecast data is available
* NetCDF format integrates naturally with Python/xarray
* data can be accessed programmatically
* the system is designed for marine environmental analysis

Copernicus Marine describes the global product as a numerical-model product incorporating satellite and in-situ observations.

---

# 9. Ocean Data Variables

For the first implementation, only surface horizontal velocity is required.

Conceptually:

```text
u(x, y, t)
v(x, y, t)
```

where:

```text
u = eastward current velocity
v = northward current velocity
```

The particle model will interpolate these values at the particle's:

```text
longitude
latitude
time
```

---

# 10. Ocean Data Format

The recommended format is:

```text
NetCDF
```

Python stack:

```text
xarray
numpy
scipy
```

Potential geospatial support:

```text
pyproj
rasterio
```

The existing project already includes `xarray` and scientific Python dependencies.

---

# 11. Ocean Data Processing Pipeline

The processing pipeline should be:

```text
Copernicus NetCDF
       ↓
Load with xarray
       ↓
Select geographic region
       ↓
Select time window
       ↓
Select surface current
       ↓
Extract u/v
       ↓
Handle missing values
       ↓
Normalize coordinate conventions
       ↓
Temporal interpolation
       ↓
Spatial interpolation
       ↓
Velocity field
```

Do not load the entire global dataset into memory for every simulation.

Always subset spatially and temporally first.

---

# 12. Spatial Subsetting

Given the spill:

```text
longitude
latitude
```

create a region around the spill.

For example:

```text
spill location
     ↓
bounding region
     ↓
environmental data subset
```

The region should include a margin around the observed spill because backward and forward particles can move outside the initial spill geometry.

The margin should be configurable.

Example:

```yaml
drift:
  spatial_margin_km: 100
```

Do not hard-code this value permanently.

---

# 13. Temporal Subsetting

The environmental data must cover the complete simulation window.

For backward simulation:

```text
observation time
       ↓
observation time - hindcast duration
```

For example:

```text
Observation:
2026-09-05 10:30

48-hour hindcast:
2026-09-03 10:30
        ↓
2026-09-05 10:30
```

For forecasting:

```text
observation time
       ↓
observation time + forecast duration
```

---

# 14. Wind Dataset

Recommended historical wind source:

**ECMWF ERA5 hourly data on single levels.**

ERA5 provides global hourly reanalysis data and is regridded to a regular latitude/longitude grid of approximately:

```text
0.25°
```

for the reanalysis.

ERA5 is therefore appropriate for:

* historical hindcasting
* atmospheric forcing
* wind analysis
* reproducible research

---

# 15. Wind Variables

The model should use horizontal wind components:

```text
u10
v10
```

representing near-surface wind components.

Conceptually:

```text
u_wind
v_wind
```

These must be converted into the units required by the drift model.

Do not assume that wind and current datasets use identical:

* timestamps
* coordinate ordering
* longitude conventions
* spatial resolutions
* units

They must be normalized before use.

---

# 16. Current + Wind Combination

Oil movement is not determined by ocean current alone.

A simplified surface velocity model is:

```text
V_oil = V_current + V_windage + V_other
```

For the first baseline:

```text
V_oil ≈ V_current + α V_wind
```

where:

```text
α = windage coefficient
```

The windage coefficient should be configurable and treated as a model parameter rather than a universal constant.

The first implementation should expose this coefficient in configuration.

Example:

```yaml
drift:
  windage:
    enabled: true
    coefficient: 0.03
```

The exact value should be validated experimentally rather than assumed to be universally correct.

---

# 17. Why Windage Is Necessary

Oil floating at the surface can be affected by wind in addition to the underlying surface current.

Therefore:

```text
current-only model
```

is useful as a baseline, but:

```text
current + wind
```

should be the main model for the project.

This also allows us to perform an experiment:

```text
Model A:
current only

Model B:
current + wind
```

and compare trajectory accuracy.

---

# 18. Lagrangian Particle Model

The recommended modelling approach is **Lagrangian particle tracking**.

Instead of representing the spill as one continuously moving polygon, represent it using many particles.

Example:

```text
Observed spill
      ↓
Generate particles
      ↓
Each particle has:
    longitude
    latitude
    timestamp
      ↓
Move particles using environmental velocity
      ↓
Collect trajectories
      ↓
Generate probability distribution
```

This approach is appropriate because an oil slick is not a single point moving along one deterministic path.

---

# 19. Particle State

A particle should minimally contain:

```text
particle_id
longitude
latitude
timestamp
```

Future versions may include:

```text
mass
oil type
age
weathering state
density
viscosity
emulsification
```

These should not be implemented in the first baseline unless required.

---

# 20. Particle Movement

For each particle:

```text
position(t + Δt)
=
position(t)
+
velocity(position, time) × Δt
```

The velocity is obtained from:

```text
ocean current
+
wind contribution
```

The numerical integration method can initially be simple Euler integration.

Later, compare with a higher-order integrator if required.

---

# 21. Coordinate Handling

The model operates geographically.

Do not directly treat:

```text
1 degree longitude = 1 degree latitude
```

as a constant physical distance.

The conversion depends on latitude.

For trajectory integration, either:

1. use a geographic-aware displacement calculation, or
2. transform locally to a suitable projected coordinate system.

The implementation must explicitly document which approach is used.

For large geographic domains, avoid assuming a single local projection is valid everywhere.

---

# 22. Time Handling

All internal timestamps should use:

```text
UTC
```

Prefer timezone-aware timestamps.

Never mix:

```text
UTC
local time
naive datetime
```

without explicit conversion.

The drift system should internally operate on:

```text
datetime64[ns, UTC]
```

or an equivalent timezone-aware representation.

---

# 23. Temporal Interpolation

Environmental datasets may not have exactly the same timestamps.

Example:

```text
Current:
00:00
06:00
12:00

Wind:
00:00
01:00
02:00
...
```

The drift model may require:

```text
03:30
```

Therefore environmental forcing needs temporal interpolation.

For the baseline:

```text
linear interpolation
```

is acceptable.

The interpolation method must be configurable.

---

# 24. Spatial Interpolation

Environmental data exists on a grid.

A particle may be located between grid points.

Therefore:

```text
grid velocities
      ↓
interpolation
      ↓
velocity at particle position
```

A bilinear/linear interpolation approach is suitable for the initial implementation.

Nearest-neighbor interpolation should not be the default for continuous velocity fields.

---

# 25. Missing Data

Ocean datasets may contain:

```text
NaN
land
coastal gaps
invalid values
```

The system must never silently convert invalid environmental data into zero velocity.

Bad:

```text
NaN → 0
```

because this can create false stationary particles.

Instead:

```text
invalid forcing
      ↓
detect
      ↓
handle explicitly
```

Possible strategies:

* stop particle
* mark particle invalid
* interpolate from valid neighbors
* reject simulation region

The chosen behaviour must be explicit and logged.

---

# 26. Forward Drift

Forward modelling answers:

> Where can the observed oil move from this point?

Input:

```text
observed spill
observation time
current data
wind data
```

Process:

```text
Observed spill
      ↓
Particle initialization
      ↓
Current + wind forcing
      ↓
Particle integration
      ↓
Trajectory
      ↓
Forecast probability distribution
```

Output:

```text
future trajectories
future probability region
uncertainty
```

---

# 27. Backward Drift / Hindcasting

Backward modelling answers:

> Where could the observed spill have originated?

Input:

```text
observed spill geometry
observation time
historical current data
historical wind data
```

The simulation runs backward in time.

Conceptually:

```text
Observed spill
       ↓
Particles
       ↓
Reverse integration
       ↓
t - 1 hour
       ↓
t - 2 hours
       ↓
...
t - N hours
       ↓
Origin probability distribution
```

This is the most important part of your module for the vessel-attribution problem.

---

# 28. Important Limitation of Backward Modelling

Backward particle tracking is not the same as perfectly reversing the real-world oil process.

Real oil movement includes:

* advection
* diffusion
* windage
* waves
* weathering
* evaporation
* emulsification
* uncertainty in environmental forcing
* uncertainty in observation time
* uncertainty in detected spill geometry

Therefore the result must be represented as a **probability/uncertainty region**, not a single exact origin point.

---

# 29. Origin Probability

A single backward simulation is insufficient.

Instead, run many particles.

Example:

```text
10,000 particles
       ↓
Backward simulation
       ↓
Final particle locations
       ↓
Spatial density estimation
       ↓
Probability map
```

Regions containing more particles receive higher probability.

Conceptually:

```text
low probability
      ↓
████████████
███░░░░░███
██░░░██░░██
█░░████░░░█
██░░░░░░███
████████████
      ↓
high probability
```

The actual implementation should use a mathematically defined density/grid method rather than visual heuristics.

---

# 30. Uncertainty Sources

Uncertainty should include:

### Environmental uncertainty

Ocean and wind models are not exact.

### Observation uncertainty

The detected spill boundary may contain segmentation errors.

### Temporal uncertainty

The satellite observation gives an observation time, but the exact spill-release time is unknown.

### Model uncertainty

Different drift assumptions produce different trajectories.

### Initial condition uncertainty

The spill may have existed before the satellite observed it.

---

# 31. Monte Carlo Approach

A practical baseline is Monte Carlo particle simulation.

Instead of one deterministic trajectory:

```text
1 trajectory
```

run:

```text
N trajectories
```

with controlled variation in:

```text
initial location
windage
diffusion
environmental forcing
release time
```

This produces a distribution instead of a single answer.

---

# 32. Release-Time Uncertainty

Suppose the satellite detects oil at:

```text
10:30 UTC
```

The spill may have occurred:

```text
6 hours earlier
12 hours earlier
24 hours earlier
36 hours earlier
48 hours earlier
```

Rather than assuming:

```text
release_time = observation_time
```

the system should eventually evaluate a configurable release-time window.

Example:

```yaml
hindcast:
  release_window_hours:
    min: 6
    max: 48
```

This is especially important for AIS correlation.

---

# 33. Connecting Drift to AIS

The output of your module becomes an input to Member 5.

Your module should provide:

```text
probable origin region
+
probable release-time window
+
uncertainty
```

Then AIS can search:

```text
Which vessels were in/near this region
during this time window?
```

Pipeline:

```text
Satellite observation
       ↓
Observed spill
       ↓
Backward drift
       ↓
Origin probability map
       ↓
Candidate origin locations
       ↓
AIS spatial filtering
       ↓
AIS temporal filtering
       ↓
Vessel ranking
```

This is why your module is critical to the attribution problem.

---

# 34. Candidate Origin Region

Do not pass only:

```text
latitude
longitude
```

to AIS.

Pass a region.

For example:

```json
{
  "origin_region": "...GeoJSON...",
  "time_window": {
    "start": "...",
    "end": "..."
  },
  "uncertainty_km": 15.4
}
```

This prevents the AIS module from searching an unrealistically tiny area.

---

# 35. Recommended Software Architecture

Recommended structure:

```text
ocean/
├── __init__.py
├── currents/
│   ├── __init__.py
│   ├── loader.py
│   └── interpolator.py
├── wind/
│   ├── __init__.py
│   ├── loader.py
│   └── interpolator.py
├── data_loader/
│   ├── __init__.py
│   └── common.py
└── preprocessing/
    ├── __init__.py
    ├── spatial.py
    └── temporal.py

drift/
├── __init__.py
├── particle_model/
│   ├── __init__.py
│   ├── particle.py
│   ├── integrator.py
│   └── velocity.py
├── hindcasting/
│   ├── __init__.py
│   └── backward.py
├── forecasting/
│   ├── __init__.py
│   └── forward.py
└── probability/
    ├── __init__.py
    ├── density.py
    └── uncertainty.py
```

---

# 36. Recommended Development Order

Do not implement everything at once.

## Phase 1 — Environmental Data

```text
OCEAN-01
OCEAN-02
OCEAN-03
OCEAN-04
OCEAN-05
```

Implement:

```text
Copernicus loader
ERA5 loader
spatial subset
temporal subset
interpolation
```

---

## Phase 2 — Basic Particle Model

Implement:

```text
particle representation
velocity lookup
position update
time stepping
```

Use synthetic velocity fields first.

Do not depend on real ocean data during unit testing.

---

## Phase 3 — Forward Drift

Implement:

```text
seed particles
run forward
save trajectories
```

Validate against known synthetic velocity fields.

---

## Phase 4 — Backward Drift

Implement:

```text
observed location
↓
reverse integration
↓
possible origin locations
```

---

## Phase 5 — Probability

Implement:

```text
particle endpoints
↓
density estimation
↓
probability grid
↓
uncertainty region
```

---

## Phase 6 — Integration

Connect:

```text
GIS → Drift
Drift → AIS
```

Only after the individual components are stable.

---

# 37. Recommended Libraries

Use the project's existing Python stack where possible.

### Core

```text
Python
NumPy
SciPy
Pandas
```

### Environmental data

```text
xarray
netCDF4
```

### Geospatial

```text
GeoPandas
Shapely
PyProj
Rasterio
```

### Visualization/testing

```text
Matplotlib
Pytest
```

---

# 38. OpenDrift

**OpenDrift** should be seriously evaluated before building a complete particle engine from scratch.

OpenDrift is an open-source Python framework for Lagrangian ocean drift modelling.

Its documentation provides an `OpenOil` model specifically for oil drift.

OpenDrift's architecture separates environmental readers from the physical/chemical model, allowing environmental data such as currents and wind to drive particle updates.

This makes it highly relevant to this project.

---

# 39. Should We Use OpenDrift?

### Recommended strategy

Do not immediately replace our `drift/` architecture with OpenDrift-specific code.

Instead:

```text
Our project interface
        ↓
Drift engine abstraction
        ↓
 ┌───────────────┐
 │ OpenDrift     │
 │ Custom model  │
 └───────────────┘
```

This allows us to evaluate OpenDrift while keeping the rest of the project independent.

For example:

```python
class DriftEngine:
    def run_forward(...):
        ...

    def run_backward(...):
        ...
```

Then:

```text
OpenDriftEngine
```

can implement the interface.

A custom lightweight engine can be implemented later if required.

---

# 40. Why Not Build Everything From Scratch?

A complete oil-spill model can become scientifically complex.

Real oil models can include:

```text
advection
diffusion
windage
evaporation
emulsification
weathering
oil properties
wave effects
```

OpenDrift/OpenOil already provides a mature modelling framework and oil-specific functionality.

Therefore the SIH implementation should focus engineering effort on:

```text
Satellite detection
+
environmental data integration
+
backward origin estimation
+
AIS attribution
+
uncertainty
+
visualization
```

rather than unnecessarily recreating an established oil-drift engine.

---

# 41. NOAA GNOME

NOAA's GNOME is another established oil-spill trajectory modelling system.

NOAA describes GNOME as a tool for predicting possible pollutant trajectories in water.

However, the traditional desktop GNOME is no longer actively maintained; NOAA directs users toward the newer WebGNOME ecosystem.

Therefore:

```text
GNOME
```

should be treated primarily as:

* scientific reference
* validation/reference model
* conceptual reference

rather than automatically becoming our core Python engine.

---

# 42. Recommended Final Technology Choice

For the SIH implementation:

### Environmental forcing

```text
Ocean:
Copernicus Marine

Wind:
ERA5
```

### Data processing

```text
xarray
NetCDF
NumPy
SciPy
```

### Drift

Primary candidate:

```text
OpenDrift / OpenOil
```

with our own project-level abstraction.

### GIS

```text
GeoPandas
Shapely
PyProj
```

### Testing

```text
Pytest
```

---

# 43. Configuration Design

Do not hard-code model parameters.

Example:

```yaml
environment:
  ocean:
    provider: copernicus
    product: GLOBAL_ANALYSISFORECAST_PHY_001_024

  wind:
    provider: era5

drift:
  engine: opendrift

  timestep_minutes: 30

  forward:
    duration_hours: 48

  backward:
    duration_hours: 48

  spatial_margin_km: 100

  windage:
    enabled: true
    coefficient: 0.03

  uncertainty:
    particles: 10000
```

These values are examples for configuration design, **not scientifically validated final values**.

---

# 44. Important: Do Not Treat Example Parameters as Final

The following must eventually be experimentally validated:

```text
windage coefficient
particle count
time step
diffusion coefficient
release-time window
forecast duration
hindcast duration
uncertainty radius
```

The research code must clearly distinguish:

```text
default configuration
```

from:

```text
validated scientific parameter
```

---

# 45. Testing Strategy

The drift system should not require real Copernicus/ERA5 data for every test.

Use synthetic environmental fields.

Example:

```text
constant eastward current
u = 1 m/s
v = 0 m/s
```

A particle should move east predictably.

Similarly:

```text
u = 0
v = 1 m/s
```

should produce predictable northward movement.

This allows mathematical validation.

---

# 46. Unit Tests

Minimum tests:

```text
test_particle_initialization
test_velocity_interpolation
test_time_interpolation
test_coordinate_conversion
test_forward_motion
test_backward_motion
test_missing_velocity_handling
test_windage_application
test_probability_generation
test_uncertainty_calculation
```

---

# 47. Integration Tests

At least one integration test should verify:

```text
GIS spill input
      ↓
drift model
      ↓
origin output
```

The output should contain:

```text
origin region
time window
probability
uncertainty
```

---

# 48. Validation Strategy

The model should be evaluated using known historical spill events whenever suitable data is available.

Conceptually:

```text
Known spill
      ↓
Satellite observation
      ↓
Run backward model
      ↓
Predicted origin
      ↓
Compare with known/independent reference
```

Possible evaluation metrics:

```text
origin distance error
trajectory distance error
containment probability
forecast displacement error
```

---

# 49. Model Comparison

The project should eventually compare:

### Model A

```text
current only
```

### Model B

```text
current + wind
```

### Model C

```text
current + wind + stochastic uncertainty
```

Potentially:

### Model D

```text
OpenDrift/OpenOil
```

The final model should be selected based on validation results rather than complexity.

---

# 50. Computational Considerations

Particle simulations can become expensive.

Complexity roughly increases with:

```text
number of particles
×
number of time steps
×
number of scenarios
```

Therefore:

```text
10,000 particles × 96 steps
```

is much cheaper than:

```text
100,000 particles × 1,000 steps
```

Start small during development.

Increase particle count after correctness is established.

---

# 51. Caching

Environmental data should not be downloaded repeatedly.

Use:

```text
data/
├── raw/
│   ├── ocean/
│   └── wind/
└── processed/
```

or an equivalent external-data location.

Cache:

* downloaded NetCDF files
* processed subsets
* interpolation-ready fields

Do not commit them to Git.

---

# 52. Data Reproducibility

Every simulation should record:

```text
ocean data source
ocean product ID
wind data source
wind product/version
simulation start
simulation end
time step
particle count
windage coefficient
drift engine
software version
configuration
```

This is critical because environmental datasets change over time.

---

# 53. Logging

A drift run should log:

```text
simulation ID
start time
end time
input spill
environmental datasets
particle count
time step
number of valid particles
number of failed particles
execution time
```

This makes debugging and scientific auditing easier.

---

# 54. Failure Handling

The system must explicitly handle:

```text
missing environmental data
invalid coordinates
invalid timestamps
particles entering land
out-of-bounds environmental fields
NaN velocity
missing dataset
network/API failure
```

Do not silently continue with invalid environmental forcing.

---

# 55. Land Interaction

Particles may encounter land.

The baseline should detect when a particle moves into invalid/non-ocean regions.

Possible future behaviours:

```text
stop particle
reflect particle
mark stranded
continue with coastal interaction model
```

The first implementation should make the behaviour explicit and configurable.

Do not silently treat land as ocean.

---

# 56. Drift Output for GIS

The output should be GIS-compatible.

Recommended formats:

```text
GeoJSON
```

for:

* trajectories
* probability regions
* origin regions

and:

```text
NetCDF
```

for scientific gridded outputs.

---

# 57. Drift Output for AIS

AIS should receive:

```text
origin probability region
origin time window
uncertainty
```

Example:

```json
{
  "origin_region": "GeoJSON",
  "time_start": "2026-09-03T10:30:00Z",
  "time_end": "2026-09-05T10:30:00Z",
  "uncertainty_km": 18.2
}
```

This becomes the spatial-temporal search constraint for candidate vessel generation.

---

# 58. What This Module Must NOT Claim

The model must never state:

```text
"This is definitely where the spill started."
```

Instead:

```text
"The model estimates this region as the most probable origin under the specified environmental and modelling assumptions."
```

Likewise, the AIS system must not interpret the output as proof of vessel responsibility.

---

# 59. Recommended MVP

For the first working prototype, implement only:

```text
1. Copernicus current loader
2. ERA5 wind loader
3. Spatial/temporal subset
4. Interpolation
5. Particle representation
6. Forward particle tracking
7. Backward particle tracking
8. Windage
9. Probability grid
10. Uncertainty region
11. GeoJSON output
12. AIS-compatible origin/time output
```

Do not initially implement:

```text
full oil chemistry
advanced weathering
complex wave physics
deep learning drift model
real-time global data ingestion
large-scale distributed simulation
```

Those are future enhancements.

---

# 60. Recommended Implementation Architecture

```text
                    ┌────────────────────┐
                    │   GIS Spill Input  │
                    └─────────┬──────────┘
                              ↓
                    ┌────────────────────┐
                    │ Simulation Config  │
                    └─────────┬──────────┘
                              ↓
              ┌───────────────┴───────────────┐
              ↓                               ↓
      ┌───────────────┐               ┌───────────────┐
      │ Ocean Current │               │     Wind      │
      │    Loader     │               │    Loader     │
      └───────┬───────┘               └───────┬───────┘
              ↓                               ↓
              └───────────────┬───────────────┘
                              ↓
                    ┌────────────────────┐
                    │ Environmental     │
                    │ Velocity Field     │
                    └─────────┬──────────┘
                              ↓
                    ┌────────────────────┐
                    │ Drift Engine       │
                    │ OpenDrift/Custom   │
                    └─────────┬──────────┘
                              ↓
                    ┌────────────────────┐
                    │ Particle           │
                    │ Trajectories       │
                    └─────────┬──────────┘
                              ↓
                    ┌────────────────────┐
                    │ Probability +      │
                    │ Uncertainty        │
                    └─────────┬──────────┘
                              ↓
              ┌───────────────┴───────────────┐
              ↓                               ↓
      ┌───────────────┐               ┌───────────────┐
      │ GIS / Map     │               │ AIS Attribution│
      │ Visualization │               │ Origin Search  │
      └───────────────┘               └───────────────┘
```

---

# 61. Implementation Rules

Before writing code:

* Do not hard-code geographic coordinates.
* Do not hard-code dataset paths.
* Do not download global datasets inside Python automatically.
* Do not silently convert missing velocity to zero.
* Do not mix local time and UTC.
* Do not assume current and wind datasets have identical grids.
* Do not assume one projection works globally.
* Do not treat deterministic trajectories as certainty.
* Do not couple AIS directly to internal particle-model classes.
* Do not put environmental datasets into Git.

---

# 62. First Coding Milestone

The first coding milestone should **not** be the complete oil model.

Build:

```text
OCEAN-02
Current loader
```

with:

```text
NetCDF
 ↓
xarray
 ↓
spatial subset
 ↓
temporal subset
 ↓
u/v current extraction
```

Then test it using a small environmental subset.

Second:

```text
OCEAN-03
Wind loader
```

Then:

```text
OCEAN-04
Interpolation
```

Only after these work should the particle model be implemented.

---

# 63. First Drift Prototype

The first particle model should use a synthetic velocity field.

Example:

```text
u = constant
v = constant
```

Expected result:

```text
known starting point
      ↓
known velocity
      ↓
predictable ending point
```

This validates the numerical implementation before real environmental data introduces additional complexity.

---

# 64. Recommended Development Milestones

```text
Milestone 1
Environment loaders

Milestone 2
Spatial + temporal interpolation

Milestone 3
Synthetic particle model

Milestone 4
Forward drift

Milestone 5
Backward drift

Milestone 6
Probability + uncertainty

Milestone 7
Real Copernicus + ERA5 integration

Milestone 8
GIS integration

Milestone 9
AIS integration

Milestone 10
Historical validation
```

---

# 65. Final Recommended Stack

```text
Language
Python

Ocean data
Copernicus Marine

Atmospheric data
ERA5

Scientific processing
NumPy
SciPy
xarray
netCDF4

Geospatial
GeoPandas
Shapely
PyProj
Rasterio

Drift
OpenDrift/OpenOil candidate

Testing
Pytest

Output
GeoJSON
NetCDF
JSON

Version control
Git/GitHub
```

---

# 66. Official References

### Copernicus Marine

Global Ocean Physics Analysis and Forecast:

https://data.marine.copernicus.eu/product/GLOBAL_ANALYSISFORECAST_PHY_001_024/description

The product provides global ocean analysis/forecast data, including ocean velocities and hourly surface current fields.

### ECMWF ERA5

ERA5 hourly data on single levels:

https://www.ecmwf.int/en/forecasts/datasets/era5-hourly-data-single-levels-1940-present

ERA5 provides global hourly reanalysis data on a regular grid, with approximately 0.25° resolution for the reanalysis.

### OpenDrift

OpenDrift documentation:

https://opendrift.github.io/tutorial.html

OpenDrift provides a Lagrangian framework and includes an `OpenOil` oil-drift model.

### NOAA GNOME

NOAA GNOME technical documentation:

https://response.restoration.noaa.gov/oil-and-chemical-spills/oil-spills/resources/gnome-technical-docs.html

GNOME is an established oil-spill trajectory modelling system and useful as a scientific/reference model. NOAA notes that the legacy desktop version is no longer maintained.

---

# 67. Final Decision for OCEANTRACE

For the first implementation, use:

```text
Ocean currents
        ↓
Copernicus Marine

Wind
        ↓
ERA5

Data handling
        ↓
xarray + NetCDF + NumPy/SciPy

Drift
        ↓
OpenDrift/OpenOil evaluation
        ↓
project-level DriftEngine abstraction

Backward simulation
        ↓
probable origin

Forward simulation
        ↓
future trajectory

Monte Carlo particles
        ↓
probability + uncertainty

Output
        ↓
GIS + AIS
```

The objective is not to build the world's most complicated oil model.

The objective is to build a **reproducible, scientifically defensible drift component that converts a satellite-observed spill into a probable origin region and time window that can be correlated with AIS vessel trajectories.**
