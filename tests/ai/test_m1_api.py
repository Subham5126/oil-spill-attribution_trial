import os
import zipfile
from pathlib import Path

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = PROJECT_ROOT.parent
load_dotenv(PROJECT_ROOT / ".env")

API_KEY = os.getenv("M1_API_KEY")
M1_URL = "http://127.0.0.1:8001/predict"

IMAGE_PATH = Path(
    os.getenv(
        "M1_IMAGE_PATH",
        str(WORKSPACE_ROOT / "01_Train_Val_Oil_Spill_images" / "Oil" / "00002.tif"),
    )
)
METADATA_PATH = Path(
    os.getenv(
        "M1_METADATA_PATH",
        str(WORKSPACE_ROOT / "drive" / "model_results" / "metadata.json"),
    )
)

OUTPUT_ZIP = Path(
    os.getenv("M1_OUTPUT_ZIP", str(PROJECT_ROOT / "tests" / "ai" / "m1_result.zip"))
)


def main():
    with open(IMAGE_PATH, "rb") as image_file, \
         open(METADATA_PATH, "rb") as metadata_file:

        files = {
            "image": (
                IMAGE_PATH.name,
                image_file,
                "image/tiff"
            ),
            "metadata": (
                METADATA_PATH.name,
                metadata_file,
                "application/json"
            )
        }

        response = requests.post(
            M1_URL,
            files=files,
            headers={
                 "X-API-Key": API_KEY
            }
        )

    print("Status:", response.status_code)

    if response.status_code != 200:
        print(response.text)
        return

    OUTPUT_ZIP.write_bytes(response.content)

    print("Saved:", OUTPUT_ZIP)

    with zipfile.ZipFile(OUTPUT_ZIP) as z:
        print("Files returned:")
        for name in z.namelist():
            print(" -", name)


if __name__ == "__main__":
    main()