import rasterio
import sys


if __name__ == "__main__":
    source = sys.argv[1]
    mask = sys.argv[2]

    with rasterio.open(source) as src:
        source_info = {
            "width": src.width,
            "height": src.height,
            "crs": src.crs,
            "transform": src.transform,
            "bounds": src.bounds,
            "resolution": src.res
        }

    with rasterio.open(mask) as dst:
        mask_info = {
            "width": dst.width,
            "height": dst.height,
            "crs": dst.crs,
            "transform": dst.transform,
            "bounds": dst.bounds,
            "resolution": dst.res
        }

    print("\nSOURCE TIFF")
    for key, value in source_info.items():
        print(f"{key}: {value}")

    print("\nPREDICTED MASK")
    for key, value in mask_info.items():
        print(f"{key}: {value}")

    print("\nCHECK")

    for key in source_info:
        if source_info[key] == mask_info[key]:
            print(f"PASS: {key}")
        else:
            print(f"FAIL: {key}")