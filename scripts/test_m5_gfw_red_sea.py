"""
scripts/test_m5_gfw_red_sea.py

Executes real GFW AIS API query for the Red Sea benchmark (2019-10-11 to 2019-10-17)
and correlates with the detected spill centroid from Sentinel-1 image 00643.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import dotenv
dotenv.load_dotenv(REPO_ROOT / ".env")

from ais.filtering.spatial import haversine_distance_km
from ais.providers.gfw import GlobalFishingWatchAISProvider


def run_gfw_test():
    print("Initializing GlobalFishingWatchAISProvider...")
    provider = GlobalFishingWatchAISProvider(
        timeout=(10.0, 105.0),
        max_recovery_timeout=120.0,
    )
    healthy = provider.health_check()
    print(f"Provider health_check: {healthy}")
    if not healthy:
        print("Health check failed. Check GFW_API_TOKEN in .env.")
        return None

    # Full benchmark request for Red Sea
    # Latitude: 17.5 to 20.0, Longitude: 38.6 to 40.4
    # Time: 2019-10-11 to 2019-10-17
    req = GlobalFishingWatchAISProvider.create_red_sea_request(
        start_time="2019-10-11T00:00:00Z",
        end_time="2019-10-17T23:59:59Z",
    )
    print(f"Query AOI Bounding Box: {req.bounding_box}")
    print(f"Query Time Range: {req.start_time} to {req.end_time}")
    print("Submitting request to GFW 4Wings API (this may take ~30-100s)...")

    df = provider.fetch_ais_data(req)
    print(f"Received {len(df)} total vessel presence records.")
    if df.empty:
        print("No AIS records returned from GFW.")
        return df

    unique_mmsis = df["mmsi"].nunique()
    print(f"Unique vessels (MMSIs): {unique_mmsis}")

    # Detected spill centroid from M2 U-Net on image 00643
    spill_lat = 18.888269
    spill_lon = 39.280357

    # Calculate distance of every grid cell position to the detected spill centroid
    df["distance_to_spill_km"] = [
        haversine_distance_km(spill_lat, spill_lon, lat, lon)
        for lat, lon in zip(df["latitude"], df["longitude"])
    ]

    # Aggregate per vessel
    vessels = []
    for mmsi, group in df.groupby("mmsi"):
        closest_row = group.loc[group["distance_to_spill_km"].idxmin()]
        vessels.append({
            "mmsi": int(mmsi) if str(mmsi).isdigit() else str(mmsi),
            "vessel_name": str(closest_row.get("vessel_name") or "UNKNOWN"),
            "imo": str(closest_row.get("imo") or "UNKNOWN"),
            "callsign": str(closest_row.get("callsign") or "UNKNOWN"),
            "vessel_type": str(closest_row.get("vessel_type") or "UNKNOWN"),
            "flag": str(closest_row.get("flag") or closest_row.get("flag_code") or "UNKNOWN"),
            "latitude": float(closest_row["latitude"]),
            "longitude": float(closest_row["longitude"]),
            "distance_to_spill_km": float(closest_row["distance_to_spill_km"]),
            "presence_hours": float(group["presence_hours"].sum()) if "presence_hours" in group.columns else float(len(group)),
            "timestamp": str(closest_row["timestamp"]),
            "observation_count": len(group),
        })

    vessel_df = pd.DataFrame(vessels)
    # Sort by minimum distance to spill
    vessel_df = vessel_df.sort_values(by="distance_to_spill_km").reset_index(drop=True)

    print("\n" + "=" * 60)
    print("TOP 5 CANDIDATE VESSELS CLOSEST TO SPILL CENTROID:")
    print("=" * 60)
    for idx, row in vessel_df.head(5).iterrows():
        print(f"Rank {idx+1}:")
        print(f"  Vessel Name: {row['vessel_name']}")
        print(f"  MMSI: {row['mmsi']}")
        print(f"  IMO: {row['imo']}")
        print(f"  Callsign: {row['callsign']}")
        print(f"  Flag: {row['flag']}")
        print(f"  Vessel Type: {row['vessel_type']}")
        print(f"  Closest Coordinates: {row['latitude']:.4f}°N, {row['longitude']:.4f}°E")
        print(f"  Distance to Spill Centroid: {row['distance_to_spill_km']:.2f} km")
        print(f"  Presence Hours: {row['presence_hours']:.1f} h (Observations: {row['observation_count']})")
        print(f"  Timestamp of Closest Grid Fix: {row['timestamp']}")
        print(f"  Reason for Ranking: Closest spatial proximity ({row['distance_to_spill_km']:.2f} km) to detected spill centroid in Red Sea corridor")
        print("-" * 60)

    # Save to disk
    out_json = REPO_ROOT / "demo" / "output" / "m5_gfw_red_sea_candidates.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(vessels[:20], f, indent=2)
    print(f"Saved candidate list to {out_json}")

    return vessel_df


if __name__ == "__main__":
    run_gfw_test()
