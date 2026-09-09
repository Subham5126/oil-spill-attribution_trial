import os
from pathlib import Path

from dotenv import load_dotenv
from infer import OilSpillInference


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = PROJECT_ROOT.parent
load_dotenv(PROJECT_ROOT / ".env")

MODEL_PATH = Path(
    os.getenv("M1_MODEL_PATH", str(PROJECT_ROOT / "models" / "unet_best.pth"))
)
IMAGE_PATH = Path(
    os.getenv(
        "M1_IMAGE_PATH",
        str(WORKSPACE_ROOT / "01_Train_Val_Oil_Spill_images" / "Oil" / "00395.tif"),
    )
)
OUTPUT_DIR = Path(
    os.getenv("M1_OUTPUT_DIR", str(PROJECT_ROOT / "outputs" / "test_scene"))
)


def main():
    predictor = OilSpillInference(MODEL_PATH)

    result = predictor.predict(IMAGE_PATH)

    outputs = predictor.save_outputs(
        result,
        OUTPUT_DIR,
        input_metadata={
            "scene_id": "test_scene",
            "tile_id": "test_tile"
        }
    )

    print("Inference successful.")
    print(outputs)


if __name__ == "__main__":
    main()