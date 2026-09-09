"""Train and evaluate the U-Net baseline on Dataset 1 (80% train scenes / 20% val scenes)."""

from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

from ai.models.unet.model import build_unet
from ai.preprocessing.dataset import OilSpillPatchDataset


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def dice_loss(logits: torch.Tensor, targets: torch.Tensor, eps: float = 1e-6) -> torch.Tensor:
    probabilities = torch.sigmoid(logits)
    intersection = (probabilities * targets).sum(dim=(1, 2, 3))
    denominator = probabilities.sum(dim=(1, 2, 3)) + targets.sum(dim=(1, 2, 3))
    dice = (2 * intersection + eps) / (denominator + eps)
    return 1.0 - dice.mean()


def segmentation_loss(logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
    bce = torch.nn.functional.binary_cross_entropy_with_logits(logits, targets)
    return bce + dice_loss(logits, targets)


def compute_metrics(logits: torch.Tensor, targets: torch.Tensor, threshold: float = 0.5) -> tuple[float, float, float, float]:
    probabilities = torch.sigmoid(logits)
    predictions = (probabilities >= threshold).float()

    tp = (predictions * targets).sum().item()
    fp = (predictions * (1.0 - targets)).sum().item()
    fn = ((1.0 - predictions) * targets).sum().item()

    dice = (2.0 * tp) / (2.0 * tp + fp + fn + 1e-8)
    iou = tp / (tp + fp + fn + 1e-8)
    precision = tp / (tp + fp + 1e-8)
    recall = tp / (tp + fn + 1e-8)

    return dice, iou, precision, recall


def run_epoch(
    model: torch.nn.Module,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer | None,
    device: torch.device,
    training: bool,
) -> tuple[float, tuple[float, float, float, float]]:
    model.train(training)
    total_loss = 0.0
    totals = np.zeros(4, dtype=np.float64)
    total_samples = 0

    for images, masks in loader:
        batch_size = images.size(0)
        images = images.to(device, non_blocking=True)
        masks = masks.to(device, non_blocking=True)

        with torch.set_grad_enabled(training):
            logits = model(images)
            loss = segmentation_loss(logits, masks)
            if training and optimizer is not None:
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                optimizer.step()

        total_loss += loss.item() * batch_size
        totals += np.asarray(compute_metrics(logits.detach(), masks)) * batch_size
        total_samples += batch_size

    if total_samples == 0:
        return 0.0, (0.0, 0.0, 0.0, 0.0)

    avg_loss = total_loss / total_samples
    avg_metrics = tuple((totals / total_samples).tolist())
    return avg_loss, avg_metrics


def pair_files(images_dir: Path, masks_dir: Path) -> tuple[list[Path], list[Path]]:
    if not images_dir.exists():
        raise FileNotFoundError(f"Images directory not found: {images_dir}")
    if not masks_dir.exists():
        raise FileNotFoundError(f"Masks directory not found: {masks_dir}")

    images = sorted(list(images_dir.glob("*.tif")) + list(images_dir.glob("*.tiff")))
    image_paths, mask_paths = [], []

    for image in images:
        candidates = [
            masks_dir / image.name,
            masks_dir / f"{image.stem}.tif",
            masks_dir / f"{image.stem}.tiff",
        ]
        mask = next((p for p in candidates if p.is_file()), None)
        if mask is None:
            raise FileNotFoundError(f"No corresponding mask found for {image.name} in {masks_dir}")
        image_paths.append(image)
        mask_paths.append(mask)

    if not image_paths:
        raise RuntimeError(f"No TIFF images found in {images_dir}")

    return image_paths, mask_paths


def split_scenes(
    images: list[Path],
    masks: list[Path],
    val_ratio: float = 0.2,
    seed: int = 42,
) -> tuple[list[Path], list[Path], list[Path], list[Path]]:
    """Split paired images and masks at the scene level to prevent data leakage."""
    indices = list(range(len(images)))
    rng = random.Random(seed)
    rng.shuffle(indices)

    num_val = int(len(images) * val_ratio)
    val_idx = set(indices[:num_val])
    train_idx = [i for i in indices if i not in val_idx]

    train_imgs = [images[i] for i in train_idx]
    train_msks = [masks[i] for i in train_idx]
    val_imgs = [images[i] for i in val_idx]
    val_msks = [masks[i] for i in val_idx]

    return train_imgs, train_msks, val_imgs, val_msks


def main() -> None:
    parser = argparse.ArgumentParser(description="Train U-Net baseline on Dataset 1 SAR imagery.")
    parser.add_argument(
        "--dataset1-images",
        type=Path,
        default=Path(r"C:\Users\User\Desktop\SIH_2026\01_Train_Val_Oil_Spill_images\Oil"),
        help="Path to Dataset 1 image directory",
    )
    parser.add_argument(
        "--dataset1-masks",
        type=Path,
        default=Path(r"C:\Users\User\Desktop\SIH_2026\01_Train_Val_Oil_Spill_mask\Mask_oil"),
        help="Path to Dataset 1 mask directory",
    )
    parser.add_argument("--patch-size", type=int, default=512, help="Patch size (default: 512)")
    parser.add_argument("--stride", type=int, default=512, help="Patch stride (default: 512)")
    parser.add_argument("--val-ratio", type=float, default=0.2, help="Validation scene ratio (default: 0.2)")
    parser.add_argument("--bg-keep-ratio", type=float, default=0.3, help="Fraction of background patches to keep in training")
    parser.add_argument("--batch-size", type=int, default=4, help="Training batch size (default: 4)")
    parser.add_argument("--epochs", type=int, default=30, help="Number of training epochs")
    parser.add_argument("--lr", type=float, default=1e-4, help="Learning rate")
    parser.add_argument("--num-workers", type=int, default=2, help="DataLoader workers")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("ai/training/checkpoints/unet_best.pth"),
        help="Output path for best checkpoint",
    )
    args = parser.parse_args()

    seed_everything(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    print("Pairing Dataset 1 scenes...")
    image_paths, mask_paths = pair_files(args.dataset1_images, args.dataset1_masks)
    print(f"Found {len(image_paths)} total scene pairs.")

    print(f"Splitting scenes: {1 - args.val_ratio:.0%} Train / {args.val_ratio:.0%} Validation at scene level...")
    train_imgs, train_msks, val_imgs, val_msks = split_scenes(
        image_paths, mask_paths, val_ratio=args.val_ratio, seed=args.seed
    )
    print(f"Train scenes: {len(train_imgs)} | Validation scenes: {len(val_imgs)}")

    print("Building patch indices...")
    train_ds = OilSpillPatchDataset(
        train_imgs,
        train_msks,
        patch_size=args.patch_size,
        stride=args.stride,
        normalize=True,
        filter_background=True,
        bg_keep_ratio=args.bg_keep_ratio,
        seed=args.seed,
    )
    val_ds = OilSpillPatchDataset(
        val_imgs,
        val_msks,
        patch_size=args.patch_size,
        stride=args.stride,
        normalize=True,
        filter_background=False,
    )

    print(f"Train patches (balanced): {len(train_ds)} | Val patches (full): {len(val_ds)}")

    train_loader = DataLoader(
        train_ds,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
        pin_memory=True if torch.cuda.is_available() else False,
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=True if torch.cuda.is_available() else False,
    )

    print("Initializing U-Net model (in_channels=2, classes=1, no pretrained weights)...")
    model = build_unet(encoder_name="resnet34", encoder_weights=None).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)

    best_dice = -1.0
    args.output.parent.mkdir(parents=True, exist_ok=True)

    print("\nStarting training loop...")
    for epoch in range(1, args.epochs + 1):
        train_loss, (t_dice, t_iou, t_prec, t_rec) = run_epoch(model, train_loader, optimizer, device, training=True)
        val_loss, (v_dice, v_iou, v_prec, v_rec) = run_epoch(model, val_loader, None, device, training=False)

        print(
            f"Epoch {epoch:03d}/{args.epochs:03d} | "
            f"Train Loss: {train_loss:.4f} | Dice: {t_dice:.4f} | IoU: {t_iou:.4f} | "
            f"Val Loss: {val_loss:.4f} | Dice: {v_dice:.4f} | IoU: {v_iou:.4f} | "
            f"Prec: {v_prec:.4f} | Rec: {v_rec:.4f}"
        )

        if v_dice > best_dice:
            best_dice = v_dice
            torch.save(
                {
                    "epoch": epoch,
                    "model_state_dict": model.state_dict(),
                    "optimizer_state_dict": optimizer.state_dict(),
                    "val_dice": v_dice,
                    "val_iou": v_iou,
                    "val_precision": v_prec,
                    "val_recall": v_rec,
                },
                args.output,
            )
            print(f"  --> Saved new best checkpoint to {args.output} (Val Dice: {v_dice:.4f})")

    print(f"\nTraining complete. Best Validation Dice score: {best_dice:.4f}")


if __name__ == "__main__":
    main()
