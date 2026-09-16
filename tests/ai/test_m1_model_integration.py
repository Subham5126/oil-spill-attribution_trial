"""Regression tests for M1 model integration into OilSpillInference.

Tests cover:
1. Default provider is 'current'
2. M1 provider loads without errors
3. Invalid provider raises ValueError
4. Strict state_dict loading succeeds for M1 checkpoint
5. M1 preprocessing: dB clipping [-35, 5] and linear normalization
6. Current preprocessing: 2nd-98th percentile scaling
7. M1 predict output contract: mask, probability, oil_pixel_count, oil_percentage, profile
8. M1 predict produces uint8 binary mask
9. M1 predict probability in [0.0, 1.0]
10. M1 predict produces reasonable oil coverage (not extreme false-positive saturation)
11. Current predict output contract matches M1 contract keys
12. Config settings default model_provider is 'current'
13. Config settings OILTRACE_MODEL_PATH defaults to unet_best.pth
"""

import os
import sys
from pathlib import Path

import numpy as np
import pytest
import torch

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.inference.infer import OilSpillInference

M1_MODEL_PATH = REPO_ROOT / "ai" / "training" / "checkpoints" / "best_model.pth"
CURRENT_MODEL_PATH = REPO_ROOT / "unet_best.pth"

# Sample test images
TEST_IMAGES_DIR = REPO_ROOT / "01_Train_Val_Oil_Spill_images" / "Oil"
SAMPLE_IMAGE_52 = TEST_IMAGES_DIR / "00052.tif"
SAMPLE_IMAGE_643 = TEST_IMAGES_DIR / "00643.tif"

M1_EXISTS = M1_MODEL_PATH.exists()
CURRENT_EXISTS = CURRENT_MODEL_PATH.exists()
SAMPLE_IMAGE_EXISTS = SAMPLE_IMAGE_52.exists() or SAMPLE_IMAGE_643.exists()


# ============================================================
# Test 1: Default provider is 'current'
# ============================================================
@pytest.mark.skipif(not CURRENT_EXISTS, reason="unet_best.pth not found")
def test_default_provider_is_current():
    infer = OilSpillInference(CURRENT_MODEL_PATH)
    assert infer.model_provider == "current"


# ============================================================
# Test 2: M1 provider loads without errors
# ============================================================
@pytest.mark.skipif(not M1_EXISTS, reason="best_model.pth not found")
def test_m1_provider_loads():
    infer = OilSpillInference(M1_MODEL_PATH, model_provider="m1")
    assert infer.model_provider == "m1"
    assert infer.model is not None


# ============================================================
# Test 3: Invalid provider raises ValueError
# ============================================================
@pytest.mark.skipif(not CURRENT_EXISTS, reason="unet_best.pth not found")
def test_invalid_provider_raises():
    with pytest.raises(ValueError, match="Unknown model_provider"):
        OilSpillInference(CURRENT_MODEL_PATH, model_provider="nonexistent")


# ============================================================
# Test 4: Strict state_dict loading succeeds for M1 checkpoint
# ============================================================
@pytest.mark.skipif(not M1_EXISTS, reason="best_model.pth not found")
def test_m1_strict_state_dict_load():
    import segmentation_models_pytorch as smp
    model = smp.Unet(encoder_name="resnet34", encoder_weights=None, in_channels=2, classes=1, activation=None)
    ckpt = torch.load(M1_MODEL_PATH, map_location="cpu")
    sd = ckpt["model_state_dict"] if isinstance(ckpt, dict) and "model_state_dict" in ckpt else ckpt
    result = model.load_state_dict(sd, strict=True)
    assert len(result.missing_keys) == 0
    assert len(result.unexpected_keys) == 0


# ============================================================
# Test 5: M1 preprocessing: dB clipping [-35, 5] and linear normalization
# ============================================================
def test_m1_normalize_band():
    band = np.array([-50.0, -35.0, -15.0, 0.0, 5.0, 20.0], dtype=np.float32)
    result = OilSpillInference.normalize_band_m1(band)
    assert result.dtype == np.float32
    # -50 should clip to -35 -> (0)/40 = 0.0
    assert np.isclose(result[0], 0.0, atol=1e-5)
    # -35 -> (0)/40 = 0.0
    assert np.isclose(result[1], 0.0, atol=1e-5)
    # -15 -> (20)/40 = 0.5
    assert np.isclose(result[2], 0.5, atol=1e-5)
    # 0 -> (35)/40 = 0.875
    assert np.isclose(result[3], 0.875, atol=1e-5)
    # 5 -> (40)/40 = 1.0
    assert np.isclose(result[4], 1.0, atol=1e-5)
    # 20 should clip to 5 -> 1.0
    assert np.isclose(result[5], 1.0, atol=1e-5)


# ============================================================
# Test 6: Current preprocessing: 2nd-98th percentile scaling
# ============================================================
def test_current_normalize_band():
    band = np.random.uniform(-25.0, 5.0, (256, 256)).astype(np.float32)
    result = OilSpillInference.normalize_band(band)
    assert result.dtype == np.float32
    assert result.min() >= 0.0
    assert result.max() <= 1.0


# ============================================================
# Test 7-9: M1 predict output contract, mask type, probability range
# ============================================================
@pytest.mark.skipif(not M1_EXISTS or not SAMPLE_IMAGE_EXISTS, reason="M1 model or test images not found")
def test_m1_predict_output_contract():
    img_path = SAMPLE_IMAGE_643 if SAMPLE_IMAGE_643.exists() else SAMPLE_IMAGE_52
    infer = OilSpillInference(M1_MODEL_PATH, model_provider="m1")
    result = infer.predict(img_path)

    # Test 7: output contract keys
    required_keys = {"mask", "probability", "oil_pixel_count", "oil_percentage", "profile"}
    assert required_keys.issubset(set(result.keys())), f"Missing keys: {required_keys - set(result.keys())}"

    # Test 8: mask is uint8 binary
    mask = result["mask"]
    assert mask.dtype == np.uint8
    unique_vals = set(np.unique(mask))
    assert unique_vals.issubset({0, 1}), f"Mask contains non-binary values: {unique_vals}"

    # Test 9: probability in [0, 1]
    prob = result["probability"]
    assert prob.dtype == np.float32
    assert prob.min() >= 0.0
    assert prob.max() <= 1.0

    # oil_pixel_count and oil_percentage are numeric
    assert isinstance(result["oil_pixel_count"], int)
    assert isinstance(result["oil_percentage"], float)


# ============================================================
# Test 10: M1 does not saturate - oil percentage under 50%
# ============================================================
@pytest.mark.skipif(not M1_EXISTS or not SAMPLE_IMAGE_EXISTS, reason="M1 model or test images not found")
def test_m1_not_extreme_false_positive():
    img_path = SAMPLE_IMAGE_643 if SAMPLE_IMAGE_643.exists() else SAMPLE_IMAGE_52
    infer = OilSpillInference(M1_MODEL_PATH, model_provider="m1")
    result = infer.predict(img_path)
    # M1 with correct preprocessing should not produce >50% oil on any scene
    assert result["oil_percentage"] < 50.0, (
        f"M1 produced {result['oil_percentage']:.2f}% oil on {img_path.name} - likely false positive saturation"
    )


# ============================================================
# Test 11: Current predict output contract matches M1 keys
# ============================================================
@pytest.mark.skipif(not CURRENT_EXISTS or not SAMPLE_IMAGE_EXISTS, reason="Current model or test images not found")
def test_current_predict_output_contract():
    img_path = SAMPLE_IMAGE_643 if SAMPLE_IMAGE_643.exists() else SAMPLE_IMAGE_52
    infer = OilSpillInference(CURRENT_MODEL_PATH, model_provider="current")
    result = infer.predict(img_path)
    required_keys = {"mask", "probability", "oil_pixel_count", "oil_percentage", "profile"}
    assert required_keys.issubset(set(result.keys()))


# ============================================================
# Test 12: Config default model_provider is 'current'
# ============================================================
def test_config_default_model_provider():
    # Clear env so we get actual defaults
    saved = os.environ.pop("OILTRACE_MODEL_PROVIDER", None)
    try:
        # Re-import to get fresh defaults
        from backend.core.config import Settings
        s = Settings()
        assert s.OILTRACE_MODEL_PROVIDER == "current"
    finally:
        if saved is not None:
            os.environ["OILTRACE_MODEL_PROVIDER"] = saved


# ============================================================
# Test 13: Config default OILTRACE_MODEL_PATH points to unet_best.pth
# ============================================================
def test_config_default_model_path():
    saved = os.environ.pop("OILTRACE_MODEL_PATH", None)
    try:
        from backend.core.config import Settings, REPO_ROOT as CONFIG_REPO_ROOT
        s = Settings()
        assert s.OILTRACE_MODEL_PATH == CONFIG_REPO_ROOT / "unet_best.pth"
    finally:
        if saved is not None:
            os.environ["OILTRACE_MODEL_PATH"] = saved
