import os
from dotenv import load_dotenv
from fastapi import Header
from pathlib import Path
import json
import shutil
import tempfile
import zipfile

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse
from ai.api.tile_predict import router, register_tile_router
from ai.inference.infer import OilSpillInference

load_dotenv()

raw_api_key = os.getenv("M1_API_KEY")
M1_API_KEY = raw_api_key.strip() if raw_api_key else None

app = FastAPI(
    title="SIH 2026 - Oil Spill Segmentation API",
    version="1.0.0"
)


def resolve_model_path(raw_path: str | None) -> Path:
    default_path = Path("models/unet_best.pth")
    configured = Path(raw_path) if raw_path else default_path

    if configured.is_absolute():
        return configured

    return (PROJECT_ROOT / configured).resolve()


MODEL_PATH = resolve_model_path(os.getenv("M1_MODEL_PATH"))


# Load the model ONCE when the API starts.
try:
    predictor = OilSpillInference(MODEL_PATH)
except Exception as exc:
    predictor = None
    MODEL_LOAD_ERROR = str(exc)

register_tile_router(
    predictor=predictor,
    api_key=M1_API_KEY
)

app.include_router(router)

@app.get("/health")
def health():
    if predictor is None:
        return {
            "status": "error",
            "model_loaded": False,
            "error": MODEL_LOAD_ERROR
        }

    return {
        "status": "ok",
        "model_loaded": True
    }


@app.post("/predict")
async def predict(
    image: UploadFile = File(...),
    metadata: UploadFile = File(...),
    x_api_key: str | None = Header(default=None)
):
    if not M1_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="M1 API key is not configured on the server."
        )

    if x_api_key != M1_API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key."
        )

    if predictor is None:
        raise HTTPException(
            status_code=500,
            detail="Model failed to load."
        )
        
    if not image:
        raise HTTPException(
            status_code=400,
            detail="Satellite TIFF is required."
        )

    if not image.filename.lower().endswith((".tif", ".tiff")):
        raise HTTPException(
            status_code=400,
            detail="Image must be a TIFF file."
        )

    if not metadata.filename.lower().endswith(".json"):
        raise HTTPException(
            status_code=400,
            detail="Metadata must be a JSON file."
        )

    temp_dir = Path(tempfile.mkdtemp(prefix="m1_"))

    try:
        image_path = temp_dir / image.filename
        metadata_path = temp_dir / metadata.filename

        with open(image_path, "wb") as f:
            shutil.copyfileobj(image.file, f)

        with open(metadata_path, "wb") as f:
            shutil.copyfileobj(metadata.file, f)

        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                input_metadata = json.load(f)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400,
                detail="Invalid metadata JSON."
            )

        scene_id = input_metadata.get("scene_id")
        tile_id = input_metadata.get("tile_id")

        output_dir = temp_dir / "output"

        result = predictor.predict(image_path)

        outputs = predictor.save_outputs(
            result,
            output_dir,
            input_metadata=input_metadata
        )

        zip_path = temp_dir / "m1_result.zip"

        with zipfile.ZipFile(
            zip_path,
            "w",
            compression=zipfile.ZIP_DEFLATED
        ) as zip_file:

            zip_file.write(
                outputs["mask_path"],
                arcname="predicted_mask.tif"
            )

            zip_file.write(
                outputs["probability_path"],
                arcname="probability.tif"
            )

            zip_file.write(
                outputs["metadata_path"],
                arcname="metadata.json"
            )

        return FileResponse(
            path=zip_path,
            media_type="application/zip",
            filename="m1_result.zip"
        )

    except HTTPException:
        raise

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc)
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Inference failed: {exc}"
        )