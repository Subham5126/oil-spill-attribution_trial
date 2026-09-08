"""Unit tests for AttributionScoringConfig."""

from dataclasses import FrozenInstanceError
import pytest

from attribution.scoring.config import AttributionScoringConfig


def test_config_defaults():
    """Verify default parameters match the approved specification."""
    cfg = AttributionScoringConfig()
    assert cfg.spatial_weight == 0.40
    assert cfg.temporal_weight == 0.35
    assert cfg.trajectory_weight == 0.15
    assert cfg.behaviour_weight == 0.10
    assert cfg.max_distance_km == 25.0
    assert cfg.spatial_decay == "linear"
    assert cfg.acceptable_window_seconds == 1800.0
    assert cfg.max_time_diff_seconds == 7200.0
    assert cfg.temporal_decay == "linear"
    assert cfg.min_transit_sog_knots == 6.0
    assert cfg.max_transit_sog_knots == 18.0
    assert cfg.gap_threshold_seconds == 1800.0
    assert cfg.neutral_speed_score == 0.70
    assert cfg.tie_breaker == "spatial"


def test_config_immutability():
    """Verify that AttributionScoringConfig is frozen and immutable."""
    cfg = AttributionScoringConfig()
    with pytest.raises(FrozenInstanceError):
        cfg.spatial_weight = 0.5  # type: ignore


def test_config_validation_rejects_negative_weights():
    """Verify negative weights raise ValueError."""
    for field_name in [
        "spatial_weight",
        "temporal_weight",
        "trajectory_weight",
        "behaviour_weight",
    ]:
        with pytest.raises(ValueError, match=field_name):
            AttributionScoringConfig(**{field_name: -0.1})


def test_config_validation_rejects_boolean_weights():
    """Verify booleans are not accepted as numeric weights."""
    with pytest.raises(ValueError, match="spatial_weight"):
        AttributionScoringConfig(spatial_weight=True)  # type: ignore


def test_config_validation_rejects_zero_sum_weights():
    """Verify all-zero weights raise ValueError."""
    with pytest.raises(ValueError, match="Sum of attribution scoring weights"):
        AttributionScoringConfig(
            spatial_weight=0.0,
            temporal_weight=0.0,
            trajectory_weight=0.0,
            behaviour_weight=0.0,
        )


def test_config_validation_spatial_parameters():
    """Verify bounds and validations on spatial cutoff and decay methods."""
    with pytest.raises(ValueError, match="max_distance_km"):
        AttributionScoringConfig(max_distance_km=0.0)
    with pytest.raises(ValueError, match="max_distance_km"):
        AttributionScoringConfig(max_distance_km=-10.0)
    with pytest.raises(ValueError, match="spatial_decay"):
        AttributionScoringConfig(spatial_decay="exponential")


def test_config_validation_temporal_parameters():
    """Verify bounds and validations on temporal window and decay methods."""
    with pytest.raises(ValueError, match="acceptable_window_seconds"):
        AttributionScoringConfig(acceptable_window_seconds=-100.0)
    with pytest.raises(ValueError, match="max_time_diff_seconds"):
        AttributionScoringConfig(
            acceptable_window_seconds=3600.0,
            max_time_diff_seconds=1800.0,
        )
    with pytest.raises(ValueError, match="temporal_decay"):
        AttributionScoringConfig(temporal_decay="step")


def test_config_validation_kinematic_parameters():
    """Verify bounds on transit speeds, gaps, and neutral score."""
    with pytest.raises(ValueError, match="min_transit_sog_knots"):
        AttributionScoringConfig(min_transit_sog_knots=-1.0)
    with pytest.raises(ValueError, match="max_transit_sog_knots"):
        AttributionScoringConfig(min_transit_sog_knots=15.0, max_transit_sog_knots=10.0)
    with pytest.raises(ValueError, match="gap_threshold_seconds"):
        AttributionScoringConfig(gap_threshold_seconds=0.0)
    with pytest.raises(ValueError, match="neutral_speed_score"):
        AttributionScoringConfig(neutral_speed_score=1.5)


def test_config_validation_tie_breaker():
    """Verify unsupported tie_breaker raises ValueError."""
    with pytest.raises(ValueError, match="tie_breaker"):
        AttributionScoringConfig(tie_breaker="random")


def test_config_to_dict():
    """Verify serialization to dictionary."""
    cfg = AttributionScoringConfig(spatial_weight=0.5, temporal_weight=0.5, trajectory_weight=0.0, behaviour_weight=0.0)
    d = cfg.to_dict()
    assert isinstance(d, dict)
    assert d["spatial_weight"] == 0.5
    assert d["temporal_weight"] == 0.5
    assert d["trajectory_weight"] == 0.0
    assert d["behaviour_weight"] == 0.0
    assert d["max_distance_km"] == 25.0
