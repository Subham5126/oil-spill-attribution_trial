import copernicusmarine

copernicusmarine.subset(
    dataset_id="cmems_mod_glo_phy_anfc_merged-uv_PT1H-i",
    variables=["uo", "vo"],
    minimum_longitude=72,
    maximum_longitude=73,
    minimum_latitude=18,
    maximum_latitude=19,
    start_datetime="2025-01-01T00:00:00",
    end_datetime="2025-01-01T06:00:00",
    minimum_depth=0.49402499198913574,
    maximum_depth=0.49402499198913574,
    output_directory="data/sample/copernicus",
    output_filename="current_test.nc",
)