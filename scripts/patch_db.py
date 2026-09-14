import json, sqlite3
from pathlib import Path

conn = sqlite3.connect("data/oiltrace.db")
cur = conn.cursor()
cur.execute("SELECT investigation_id, geojson_layers, result_json FROM investigations WHERE geojson_layers IS NOT NULL")
rows = cur.fetchall()
print(f"Found {len(rows)} investigations to patch.")

for inv_id, layers_str, result_str in rows:
    layers = json.loads(layers_str) if layers_str else {}
    result = json.loads(result_str) if result_str else {}

    features = layers.get("features", [])
    spill_feat = None
    for f in features:
        if f.get("properties", {}).get("layer_type") in ("oil_spill", "oil_spill_detection"):
            spill_feat = f
            break

    if not spill_feat:
        continue

    geom = spill_feat.get("geometry", {})
    coords = []
    if geom.get("type") == "Polygon":
        coords = geom.get("coordinates", [[]])[0]
    elif geom.get("type") == "MultiPolygon":
        for poly in geom.get("coordinates", []):
            coords.extend(poly[0])

    if len(coords) < 3:
        continue

    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    slick_min_lon = round(min(lons), 6)
    slick_max_lon = round(max(lons), 6)
    slick_min_lat = round(min(lats), 6)
    slick_max_lat = round(max(lats), 6)

    area_val = spill_feat.get("properties", {}).get("area_sq_km", 0)
    spill_feat["properties"]["layer_type"] = "oil_spill"
    spill_feat["properties"]["layer_id"] = "oil_spill_detection"
    spill_feat["properties"]["name"] = f"Observed Spill Slick ({area_val} km²)"

    gis = result.get("gis_measurement", {})
    old_bbox = gis.get("bounding_box", {})

    scene_bbox = gis.get("scene_bounding_box")
    if not scene_bbox and old_bbox.get("min_lon") is not None:
        if abs(old_bbox["max_lon"] - old_bbox["min_lon"]) > 2 * abs(slick_max_lon - slick_min_lon):
            scene_bbox = {
                "min_lon": old_bbox["min_lon"],
                "min_lat": old_bbox["min_lat"],
                "max_lon": old_bbox["max_lon"],
                "max_lat": old_bbox["max_lat"],
            }

    gis["bounding_box"] = {
        "min_lon": slick_min_lon,
        "min_lat": slick_min_lat,
        "max_lon": slick_max_lon,
        "max_lat": slick_max_lat,
    }
    if scene_bbox:
        gis["scene_bounding_box"] = scene_bbox

    result["gis_measurement"] = gis

    has_scene_layer = any(f.get("properties", {}).get("layer_type") in ("scene_footprint", "scene_bounding_box") for f in features)
    if not has_scene_layer and scene_bbox:
        features.append({
            "type": "Feature",
            "properties": {
                "layer_type": "scene_footprint",
                "name": "Sentinel-1 Scene Footprint",
                "color": "#64748b",
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [scene_bbox["min_lon"], scene_bbox["min_lat"]],
                    [scene_bbox["max_lon"], scene_bbox["min_lat"]],
                    [scene_bbox["max_lon"], scene_bbox["max_lat"]],
                    [scene_bbox["min_lon"], scene_bbox["max_lat"]],
                    [scene_bbox["min_lon"], scene_bbox["min_lat"]],
                ]],
            },
        })

    layers["features"] = features

    cur.execute(
        "UPDATE investigations SET geojson_layers = ?, result_json = ? WHERE investigation_id = ?",
        (json.dumps(layers), json.dumps(result), inv_id),
    )
    print(f"Patched {inv_id}: Slick envelope [{slick_min_lon}, {slick_min_lat}, {slick_max_lon}, {slick_max_lat}], num coords: {len(coords)}")

conn.commit()
conn.close()
print("Done patching database.")
