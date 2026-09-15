r"""
scripts/run_member1_inference.py

Adapted inference and evaluation script based on Member 1's workflow.
Supports:
- Automatic path resolution for Windows/Project paths
- Safe CPU/CUDA device handling
- Fixed dB normalization [-35, 5] dB as trained by Member 1
- 256x256 patch inference
- Optional ground-truth mask evaluation (computes Dice/IoU/Precision/Recall when mask exists)
- Clean headless matplotlib export without blocking GUI popups
- Outputs predicted mask GeoTIFF, probability GeoTIFF, overlay PNG, comparison PNG, and text report
"""

import argparse
from pathlib import Path
import sys

import cv2
import matplotlib
matplotlib.use("Agg")  # Non-blocking headless backend
import matplotlib.pyplot as plt
import numpy as np
import rasterio
import segmentation_models_pytorch as smp
import torch

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL_PATH = Path(r"E:\SIH26\new pth\best_model.pth")
DEFAULT_IMAGE_PATH = REPO_ROOT / "01_Train_Val_Oil_Spill_images" / "Oil" / "00945.tif"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "demo" / "output" / "member1_results"

PATCH_SIZE = 256
THRESHOLD = 0.5


def normalize_band(band: np.ndarray) -> np.ndarray:
    band = band.astype(np.float32)
    band = np.clip(band, -35.0, 5.0)
    return ((band + 35.0) / 40.0).astype(np.float32)


def main():
    parser = argparse.ArgumentParser(description="Member 1 Oil Spill U-Net Inference")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH, help="Path to best_model.pth")
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE_PATH, help="Path to Sentinel-1 TIFF")
    parser.add_argument("--mask", type=Path, default=None, help="Optional path to ground truth mask TIFF")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Output directory")
    parser.add_argument("--patch-size", type=int, default=PATCH_SIZE)
    parser.add_argument("--threshold", type=float, default=THRESHOLD)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    print("=" * 70)
    print("OILTRACE - MEMBER 1 INFERENCE AND EVALUATION RUNNER")
    print("=" * 70)

    if not args.model.exists():
        raise FileNotFoundError(f"Model checkpoint not found at: {args.model}")
    if not args.image.exists():
        raise FileNotFoundError(f"Satellite image TIFF not found at: {args.image}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Execution Device: {device}")

    print("\nInitializing U-Net (ResNet34, 2 in-channels, 1 class)...")
    model = smp.Unet(
        encoder_name="resnet34",
        encoder_weights=None,
        in_channels=2,
        classes=1,
        activation=None,
    )

    print(f"Loading checkpoint from: {args.model}")
    checkpoint = torch.load(args.model, map_location=device)
    if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:
        model.load_state_dict(checkpoint["model_state_dict"])
        print(f"  Loaded training checkpoint (Epoch {checkpoint.get('epoch')})")
        if "val_dice" in checkpoint:
            print(f"  Recorded Validation Dice: {checkpoint['val_dice']:.4f}")
        if "val_iou" in checkpoint:
            print(f"  Recorded Validation IoU:  {checkpoint['val_iou']:.4f}")
    else:
        model.load_state_dict(checkpoint)
        print("  Loaded raw state dictionary")

    model = model.to(device)
    model.eval()
    print("Model ready in eval mode.")

    print(f"\nReading Sentinel-1 Scene: {args.image.name}")
    with rasterio.open(args.image) as src:
        image = src.read().astype(np.float32)
        profile = src.profile.copy()
        height, width = src.height, src.width
        crs = src.crs

    if image.shape[0] != 2:
        raise ValueError(f"Expected 2 bands (VV, VH), found {image.shape[0]} bands.")

    if not np.all(np.isfinite(image)):
        print("  Warning: Replacing non-finite values with 0.0")
        image = np.nan_to_num(image, nan=0.0, posinf=0.0, neginf=0.0)

    # Check optional ground truth
    has_gt = args.mask is not None and args.mask.exists()
    ground_truth = None
    if has_gt:
        print(f"Ground-truth mask detected: {args.mask.name}")
        with rasterio.open(args.mask) as msrc:
            ground_truth = (msrc.read(1) > 0).astype(np.uint8)
    else:
        print("No ground-truth mask provided (running in pure inference mode).")

    print(f"\nExecuting Tiled Inference (Patch size {args.patch_size}x{args.patch_size}, Stride {args.patch_size})...")
    prob_sum = np.zeros((height, width), dtype=np.float32)
    count_map = np.zeros((height, width), dtype=np.float32)
    total_patches = 0

    with torch.no_grad():
        for y in range(0, height, args.patch_size):
            for x in range(0, width, args.patch_size):
                y_end = min(y + args.patch_size, height)
                x_end = min(x + args.patch_size, width)
                actual_h = y_end - y
                actual_w = x_end - x

                patch = image[:, y:y_end, x:x_end]
                vv_norm = normalize_band(patch[0])
                vh_norm = normalize_band(patch[1])
                norm_patch = np.stack([vv_norm, vh_norm], axis=0)

                padded = np.zeros((2, args.patch_size, args.patch_size), dtype=np.float32)
                padded[:, :actual_h, :actual_w] = norm_patch

                tensor = torch.from_numpy(padded).unsqueeze(0).to(device)
                logits = model(tensor)
                prob = torch.sigmoid(logits)[0, 0].cpu().numpy()

                prob_sum[y:y_end, x:x_end] += prob[:actual_h, :actual_w]
                count_map[y:y_end, x:x_end] += 1.0
                total_patches += 1

    probability_map = prob_sum / np.maximum(count_map, 1.0)
    predicted_mask = (probability_map >= args.threshold).astype(np.uint8)

    oil_pixels = int(predicted_mask.sum())
    total_px = height * width
    oil_pct = (oil_pixels / total_px) * 100.0
    max_conf = float(np.max(probability_map))
    mean_slick_conf = float(np.mean(probability_map[predicted_mask == 1])) if oil_pixels > 0 else 0.0

    print("\nPrediction Summary:")
    print(f"  Scene Dimensions:    {width} x {height}")
    print(f"  Patches Evaluated:   {total_patches}")
    print(f"  Oil Pixels Detected: {oil_pixels:,} px ({oil_pct:.4f}% of scene)")
    print(f"  Max Confidence:      {max_conf:.4f}")
    print(f"  Mean Slick Conf:     {mean_slick_conf:.4f}")

    # Metrics if Ground Truth exists
    metrics = {}
    if has_gt and ground_truth is not None:
        pred_b = predicted_mask.astype(bool)
        true_b = ground_truth.astype(bool)
        intersection = int(np.logical_and(pred_b, true_b).sum())
        union = int(np.logical_or(pred_b, true_b).sum())
        dice = float((2.0 * intersection) / (pred_b.sum() + true_b.sum() + 1e-8))
        iou = float(intersection / (union + 1e-8))
        prec = float(intersection / (pred_b.sum() + 1e-8))
        rec = float(intersection / (true_b.sum() + 1e-8))
        metrics = {"dice": dice, "iou": iou, "precision": prec, "recall": rec}
        print("\nGround Truth Validation Metrics:")
        print(f"  Dice:      {dice:.4f}")
        print(f"  IoU:       {iou:.4f}")
        print(f"  Precision: {prec:.4f}")
        print(f"  Recall:    {rec:.4f}")

    # Save Output Files
    stem = args.image.stem
    mask_tif = args.output_dir / f"{stem}_predicted_mask.tif"
    prob_tif = args.output_dir / f"{stem}_oil_probability.tif"
    overlay_png = args.output_dir / f"{stem}_overlay.png"
    comparison_png = args.output_dir / f"{stem}_comparison.png"
    report_txt = args.output_dir / f"{stem}_analysis.txt"

    # 1. Mask GeoTIFF
    mask_prof = profile.copy()
    mask_prof.update(count=1, dtype="uint8", compress="lzw")
    with rasterio.open(mask_tif, "w", **mask_prof) as dst:
        dst.write(predicted_mask, 1)

    # 2. Probability GeoTIFF
    prob_prof = profile.copy()
    prob_prof.update(count=1, dtype="float32", compress="lzw")
    with rasterio.open(prob_tif, "w", **prob_prof) as dst:
        dst.write(probability_map, 1)

    # 3. High-Contrast Overlay PNG
    vv_disp = normalize_band(image[0])
    plt.figure(figsize=(10, 10))
    plt.imshow(vv_disp, cmap="gray")
    if oil_pixels > 0:
        plt.imshow(predicted_mask, cmap="Reds", alpha=0.45)
    plt.title(f"Detected Oil Spill - {stem} ({oil_pct:.3f}% coverage)")
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(overlay_png, dpi=200, bbox_inches="tight")
    plt.close()

    # 4. Multi-Panel Comparison PNG
    num_cols = 3 if has_gt else 2
    fig, axes = plt.subplots(2, num_cols, figsize=(6 * num_cols, 10))
    axes[0, 0].imshow(vv_disp, cmap="gray")
    axes[0, 0].set_title("Sentinel-1 VV Backscatter")
    axes[0, 0].axis("off")

    axes[0, 1].imshow(normalize_band(image[1]), cmap="gray")
    axes[0, 1].set_title("Sentinel-1 VH Backscatter")
    axes[0, 1].axis("off")

    if has_gt and ground_truth is not None:
        axes[0, 2].imshow(ground_truth, cmap="gray")
        axes[0, 2].set_title(f"Ground Truth Mask ({ground_truth.sum():,} px)")
        axes[0, 2].axis("off")

    im_prob = axes[1, 0].imshow(probability_map, cmap="magma", vmin=0, vmax=1)
    axes[1, 0].set_title("Detection Probability")
    axes[1, 0].axis("off")
    fig.colorbar(im_prob, ax=axes[1, 0], fraction=0.046, pad=0.04)

    axes[1, 1].imshow(predicted_mask, cmap="gray")
    axes[1, 1].set_title(f"Predicted Binary Mask ({oil_pixels:,} px)")
    axes[1, 1].axis("off")

    if has_gt and ground_truth is not None:
        error_map = np.zeros((height, width), dtype=np.uint8)
        pred_b = predicted_mask.astype(bool)
        true_b = ground_truth.astype(bool)
        error_map[true_b & pred_b] = 1   # TP
        error_map[~true_b & pred_b] = 2  # FP
        error_map[true_b & ~pred_b] = 3  # FN
        axes[1, 2].imshow(error_map, cmap="viridis", vmin=0, vmax=3)
        axes[1, 2].set_title(f"Error Map (Dice={metrics.get('dice', 0):.3f}, IoU={metrics.get('iou', 0):.3f})")
        axes[1, 2].axis("off")

    plt.tight_layout()
    plt.savefig(comparison_png, dpi=200, bbox_inches="tight")
    plt.close()

    # 5. Analysis Report Text
    with open(report_txt, "w", encoding="utf-8") as f:
        f.write("SIH 2026 - OIL SPILL AI ANALYSIS (MEMBER 1 WORKFLOW)\n")
        f.write("=" * 55 + "\n\n")
        f.write(f"Model:            {args.model}\n")
        f.write(f"Input Image:      {args.image}\n")
        f.write(f"Ground Truth:     {args.mask if has_gt else 'None (Inference Only)'}\n")
        f.write(f"Scene Dimensions: {width} x {height}\n")
        f.write(f"Patch Size:       {args.patch_size} x {args.patch_size}\n")
        f.write(f"Threshold:        {args.threshold}\n\n")
        f.write("PREDICTION RESULTS:\n")
        f.write(f"  Oil Pixels:     {oil_pixels:,}\n")
        f.write(f"  Oil Coverage:   {oil_pct:.4f}%\n")
        f.write(f"  Max Confidence: {max_conf:.4f}\n")
        f.write(f"  Mean Conf:      {mean_slick_conf:.4f}\n\n")
        if has_gt and metrics:
            f.write("GROUND TRUTH VALIDATION:\n")
            f.write(f"  Dice:           {metrics['dice']:.4f}\n")
            f.write(f"  IoU:            {metrics['iou']:.4f}\n")
            f.write(f"  Precision:      {metrics['precision']:.4f}\n")
            f.write(f"  Recall:         {metrics['recall']:.4f}\n\n")
        f.write("ARTIFACTS GENERATED:\n")
        f.write(f"  Mask GeoTIFF:   {mask_tif}\n")
        f.write(f"  Prob GeoTIFF:   {prob_tif}\n")
        f.write(f"  Overlay PNG:    {overlay_png}\n")
        f.write(f"  Comparison PNG: {comparison_png}\n")

    print("\nArtifacts saved successfully:")
    print(f"  Mask TIFF:      {mask_tif}")
    print(f"  Prob TIFF:      {prob_tif}")
    print(f"  Overlay PNG:    {overlay_png}")
    print(f"  Comparison PNG: {comparison_png}")
    print(f"  Analysis Report:{report_txt}")
    print("=" * 70)


if __name__ == "__main__":
    main()

