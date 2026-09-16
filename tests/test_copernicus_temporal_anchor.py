"""Tests verifying strict SAR acquisition timestamp temporal anchoring for Copernicus drift.

Ensures that the pipeline and Copernicus client anchor to the SAR acquisition
time (e.g. 2017-03-11, 2019-10-14) and NEVER fall back to the system clock.
"""

from datetime import datetime, timezone, timedelta
import pytest

from ocean.copernicus import (
    CopernicusClient,
    COPERNICUS_MULTIYEAR_DAILY,
    COPERNICUS_ANALYSISFORECAST_DAILY,
    SpatialUnavailableError,
    TemporalUnavailableError,
    SarAcquisitionTimeUnavailableError,
)
from backend.services.temporal_service import resolve_sar_acquisition_time
from backend.adapters.ocean_adapter import OceanAdapter


class TestCopernicusTemporalAnchor:
    """Test suite covering Section 19 test matrix."""

    def test_1_scene_00052_persian_gulf_temporal_anchor(self):
        """TEST 1: Scene 00052 (Persian Gulf)
        - SAR acquisition: 2017-03-11
        - Copernicus query window: 2017-03-08 to 2017-03-12
        - Dataset: MULTIYEAR reanalysis
        - System date (2026-09-14) must NOT appear in query
        """
        sar_time = resolve_sar_acquisition_time(
            image_id="00052",
            filename="00052_S1A_IW_GRDH_1SDV_20170311T021511_015638_019BF7_DE1A.tif",
        )
        assert sar_time is not None
        assert sar_time.year == 2017
        assert sar_time.month == 3
        assert sar_time.day == 11
        assert sar_time.tzinfo == timezone.utc

        client = CopernicusClient()
        hindcast_hours = 72
        start_time = sar_time - timedelta(hours=hindcast_hours)
        end_time = sar_time + timedelta(hours=6)

        dataset = client.select_dataset(
            lat=25.6238,
            lon=54.6108,
            start_time=start_time,
            end_time=end_time,
        )

        assert dataset.temporal_coverage_type == "MULTIYEAR"
        assert dataset.dataset_id == COPERNICUS_MULTIYEAR_DAILY.dataset_id

        # Verify query bounds are 2017 and not 2026
        assert start_time.year == 2017
        assert end_time.year == 2017
        assert "2026" not in start_time.isoformat()
        assert "2026" not in end_time.isoformat()

    def test_2_scene_00643_red_sea_temporal_anchor(self):
        """TEST 2: Scene 00643 (Red Sea)
        - SAR acquisition: 2019-10-14
        - Copernicus query window: 2019-10-11 to 2019-10-15
        - Dataset: MULTIYEAR reanalysis
        - System date must NOT appear in query
        """
        sar_time = resolve_sar_acquisition_time(
            image_id="00643",
            filename="00643_S1A_IW_GRDH_1SDV_20191014T031503_029449_03598F_1F3D.tif",
        )
        assert sar_time is not None
        assert sar_time.year == 2019
        assert sar_time.month == 10
        assert sar_time.day == 14
        assert sar_time.tzinfo == timezone.utc

        client = CopernicusClient()
        hindcast_hours = 72
        start_time = sar_time - timedelta(hours=hindcast_hours)
        end_time = sar_time + timedelta(hours=6)

        dataset = client.select_dataset(
            lat=18.23,
            lon=39.52,
            start_time=start_time,
            end_time=end_time,
        )

        assert dataset.temporal_coverage_type == "MULTIYEAR"
        assert dataset.dataset_id == COPERNICUS_MULTIYEAR_DAILY.dataset_id
        assert start_time.year == 2019
        assert end_time.year == 2019

    def test_3_recent_sar_observation_analysis_forecast(self):
        """TEST 3: Recent SAR observation (e.g. 2026-09-12)
        - Query window: 2026-09-09 to 2026-09-13
        - Dataset: ANALYSIS/FORECAST
        """
        sar_time = datetime(2026, 9, 12, 18, 30, 0, tzinfo=timezone.utc)
        client = CopernicusClient()
        hindcast_hours = 72
        start_time = sar_time - timedelta(hours=hindcast_hours)
        end_time = sar_time + timedelta(hours=6)

        dataset = client.select_dataset(
            lat=55.0653,
            lon=5.7436,
            start_time=start_time,
            end_time=end_time,
        )

        assert dataset.temporal_coverage_type == "ANALYSIS_FORECAST"
        assert dataset.dataset_id == COPERNICUS_ANALYSISFORECAST_DAILY.dataset_id

    def test_4_missing_acquisition_time_blocks_pipeline(self):
        """TEST 4: Missing acquisition time
        - SAR acquisition time is unresolvable
        - Pipeline must raise SarAcquisitionTimeUnavailableError
        - Must NOT fall back to current system date
        """
        # Resolving completely unknown scene with no filename timestamp and raise_if_missing=False
        result = resolve_sar_acquisition_time(
            image_id="unknown_unparseable_99999",
            filename="unnamed_slice.tif",
            allow_fallback=False,
            raise_if_missing=False,
        )
        assert result is None

        # Verify raising error when raise_if_missing=True
        with pytest.raises(SarAcquisitionTimeUnavailableError) as exc_info:
            resolve_sar_acquisition_time(
                image_id="unknown_unparseable_99999",
                filename="unnamed_slice.tif",
                allow_fallback=False,
                raise_if_missing=True,
            )
        assert exc_info.value.code == "SAR_ACQUISITION_TIME_UNAVAILABLE"
        assert "Sentinel-1 acquisition timestamp could not be resolved" in str(exc_info.value)

    def test_5_dataset_temporal_failure(self):
        """TEST 5: Dataset temporal failure
        - Request time outside all Copernicus datasets (e.g., year 1980)
        - Must raise TEMPORAL_UNAVAILABLE with start/end bounds
        """
        client = CopernicusClient()
        start_time = datetime(1980, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(1980, 1, 5, 0, 0, 0, tzinfo=timezone.utc)

        with pytest.raises(TemporalUnavailableError) as exc_info:
            client.select_dataset(
                lat=20.0,
                lon=40.0,
                start_time=start_time,
                end_time=end_time,
            )

        err = exc_info.value
        assert err.code == "TEMPORAL_UNAVAILABLE"
        assert err.required_start is not None
        assert err.required_end is not None
        assert "1980" in err.required_start

    def test_6_spatial_failure(self):
        """TEST 6: Spatial failure
        - Request coordinates outside global coverage (e.g., latitude 95.0)
        - Must raise SPATIAL_UNAVAILABLE
        """
        client = CopernicusClient()
        start_time = datetime(2017, 3, 8, tzinfo=timezone.utc)
        end_time = datetime(2017, 3, 12, tzinfo=timezone.utc)

        with pytest.raises(SpatialUnavailableError) as exc_info:
            client.select_dataset(
                lat=95.5,
                lon=50.0,
                start_time=start_time,
                end_time=end_time,
            )

        err = exc_info.value
        assert err.code == "SPATIAL_UNAVAILABLE"
        assert err.latitude == 95.5

    def test_pipeline_zero_system_clock_fallback(self):
        """Verify that when image metadata has an explicit historical timestamp,
        OceanAdapter uses that exact timestamp and never uses datetime.now().
        """
        adapter = OceanAdapter()
        obs_time = datetime(2017, 3, 11, 2, 15, 11, tzinfo=timezone.utc)

        # Ensure local matching current uses obs_time
        res = adapter.acquire_ocean_currents(
            lat=25.6238,
            lon=54.6108,
            obs_time=obs_time,
            hindcast_hours=72,
            forecast_hours=6,
        )

        assert res.status == "COMPLETED"
        assert res.dataset.temporal_coverage_type == "MULTIYEAR"
        assert res.dataset.dataset_id == COPERNICUS_MULTIYEAR_DAILY.dataset_id
