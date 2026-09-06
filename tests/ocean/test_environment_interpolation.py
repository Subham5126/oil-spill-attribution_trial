"""Tests for environmental field interpolation."""

from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from ocean.currents import load_currents
from ocean.interpolation import (
    InterpolationError,
    interpolate_currents,
    interpolate_wind,
)
from ocean.wind import load_wind


def _field_dataset(first_name: str, second_name: str) -> xr.Dataset:
    """Create a linear field whose exact interpolated values are known."""
    time = np.array(["2025-01-01T00", "2025-01-01T02"], dtype="datetime64[h]")
    latitude = np.array([10.0, 20.0])
    longitude = np.array([70.0, 80.0])
    time_component = np.array([0.0, 20.0])[:, None, None]
    latitude_component = np.array([0.0, 100.0])[None, :, None]
    longitude_component = np.array([0.0, 10.0])[None, None, :]
    first = time_component + latitude_component + longitude_component
    second = first + 1000.0
    return xr.Dataset(
        {
            first_name: (("time", "latitude", "longitude"), first, {"units": "m/s"}),
            second_name: (("time", "latitude", "longitude"), second, {"units": "m/s"}),
        },
        coords={"time": time, "latitude": latitude, "longitude": longitude},
    )


def _currents() -> xr.Dataset:
    return _field_dataset("uo", "vo")


def _wind() -> xr.Dataset:
    return _field_dataset("u10", "v10")


def test_exact_grid_point_current_query_returns_expected_components() -> None:
    u, v = interpolate_currents(_currents(), 80.0, 20.0, "2025-01-01T02")

    assert (u, v) == (130.0, 1130.0)


def test_exact_grid_point_wind_query_returns_expected_components() -> None:
    u, v = interpolate_wind(_wind(), 70.0, 10.0, "2025-01-01T00")

    assert (u, v) == (0.0, 1000.0)


def test_spatial_interpolation_is_linear() -> None:
    u, v = interpolate_currents(_currents(), 75.0, 15.0, "2025-01-01T00")

    assert (u, v) == (55.0, 1055.0)


def test_temporal_interpolation_is_linear() -> None:
    u, v = interpolate_currents(_currents(), 70.0, 10.0, "2025-01-01T01")

    assert (u, v) == (10.0, 1010.0)


def test_combined_spatial_and_temporal_interpolation_is_linear() -> None:
    u, v = interpolate_wind(_wind(), 75.0, 15.0, "2025-01-01T01")

    assert (u, v) == (65.0, 1065.0)


def test_multiple_particle_queries_preserve_order() -> None:
    u, v = interpolate_currents(
        _currents(),
        longitude=[80.0, 70.0, 75.0],
        latitude=[20.0, 10.0, 15.0],
        time=["2025-01-01T02", "2025-01-01T00", "2025-01-01T01"],
    )

    np.testing.assert_array_equal(u, [130.0, 0.0, 65.0])
    np.testing.assert_array_equal(v, [1130.0, 1000.0, 1065.0])


@pytest.mark.parametrize(
    ("longitude", "latitude", "time", "message"),
    [
        (69.0, 10.0, "2025-01-01T00", "longitude is outside"),
        (70.0, 9.0, "2025-01-01T00", "latitude is outside"),
        (70.0, 10.0, "2024-12-31T23", "time is outside"),
    ],
)
def test_out_of_domain_query_raises_clear_error(
    longitude: float, latitude: float, time: str, message: str
) -> None:
    with pytest.raises(InterpolationError, match=message):
        interpolate_currents(_currents(), longitude, latitude, time)


def test_missing_required_current_variable_raises_clear_error() -> None:
    with pytest.raises(InterpolationError, match="'uo' is missing"):
        interpolate_currents(_currents().drop_vars("uo"), 70.0, 10.0, "2025-01-01")


def test_missing_required_wind_variable_raises_clear_error() -> None:
    with pytest.raises(InterpolationError, match="'v10' is missing"):
        interpolate_wind(_wind().drop_vars("v10"), 70.0, 10.0, "2025-01-01")


def test_invalid_units_raise_clear_error() -> None:
    dataset = _currents()
    dataset["uo"].attrs["units"] = "knots"

    with pytest.raises(InterpolationError, match="'uo' must use metres-per-second"):
        interpolate_currents(dataset, 70.0, 10.0, "2025-01-01")


def test_non_monotonic_coordinates_raise_clear_error() -> None:
    dataset = _currents().interp(latitude=[10.0, 20.0, 15.0])

    with pytest.raises(InterpolationError, match="Coordinate 'latitude' must be monotonic"):
        interpolate_currents(dataset, 70.0, 10.0, "2025-01-01")


def test_nan_interpolation_result_raises_instead_of_returning_zero() -> None:
    dataset = _currents()
    dataset["uo"][0, 0, 0] = np.nan

    with pytest.raises(InterpolationError, match="produced NaN"):
        interpolate_currents(dataset, 70.0, 10.0, "2025-01-01")


def test_interpolation_does_not_modify_original_dataset() -> None:
    dataset = _currents()
    original = dataset.copy(deep=True)

    interpolate_currents(dataset, 75.0, 15.0, "2025-01-01T01")

    xr.testing.assert_identical(dataset, original)


def test_values_remain_in_metres_per_second() -> None:
    u, v = interpolate_wind(_wind(), 75.0, 15.0, "2025-01-01T01")

    assert (u, v) == (65.0, 1065.0)
    assert _wind()["u10"].attrs["units"] == "m/s"
    assert _wind()["v10"].attrs["units"] == "m/s"


@pytest.mark.parametrize(
    ("path", "loader", "interpolator"),
    [
        (
            Path("data/sample/copernicus/current_test.nc"),
            load_currents,
            interpolate_currents,
        ),
        (Path("data/sample/era5/wind_test.nc"), load_wind, interpolate_wind),
    ],
)
def test_real_environmental_sample_interpolates_when_available(
    path: Path, loader: object, interpolator: object
) -> None:
    if not path.is_file():
        pytest.skip(f"Sample NetCDF is not available: {path}")

    dataset = loader(path)  # type: ignore[operator]
    longitude = float(dataset["longitude"].values.mean())
    latitude = float(dataset["latitude"].values.mean())
    time = dataset["time"].values[len(dataset["time"]) // 2]
    u, v = interpolator(dataset, longitude, latitude, time)  # type: ignore[operator]

    assert isinstance(u, float)
    assert isinstance(v, float)
    assert np.isfinite(u)
    assert np.isfinite(v)
