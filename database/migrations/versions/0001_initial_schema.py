"""Initial schema for OilTrace attribution system.

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-09-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Investigations
    op.create_table(
        'investigations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('investigation_id', sa.String(length=64), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='Active'),
        sa.Column('priority', sa.String(length=16), nullable=False, server_default='Medium'),
        sa.Column('region', sa.String(length=128), nullable=False),
        sa.Column('observation_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('centroid_lat', sa.Float(), nullable=True),
        sa.Column('centroid_lon', sa.Float(), nullable=True),
        sa.Column('spill_area_km2', sa.Float(), nullable=True),
        sa.Column('suspect_vessel', sa.String(length=128), nullable=True),
        sa.Column('match_confidence', sa.Float(), nullable=True),
        sa.Column('evidence_nodes_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('sar_epoch', sa.String(length=32), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('investigation_id')
    )
    op.create_index('idx_investigation_id', 'investigations', ['investigation_id'])
    op.create_index('idx_investigation_status', 'investigations', ['status'])

    # 2. Spill Detections
    op.create_table(
        'spill_detections',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('investigation_id', sa.String(length=64), nullable=False),
        sa.Column('spill_id', sa.String(length=64), nullable=False),
        sa.Column('sensor', sa.String(length=128), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('observation_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('geometry', sa.Text(), nullable=True),
        sa.Column('centroid_geom', sa.Text(), nullable=True),
        sa.Column('centroid_lat', sa.Float(), nullable=False),
        sa.Column('centroid_lon', sa.Float(), nullable=False),
        sa.Column('area_sq_km', sa.Float(), nullable=False),
        sa.Column('area_sq_m', sa.Float(), nullable=True),
        sa.Column('perimeter_km', sa.Float(), nullable=True),
        sa.Column('perimeter_m', sa.Float(), nullable=True),
        sa.Column('bounding_box', sa.JSON(), nullable=True),
        sa.Column('compactness', sa.Float(), nullable=True),
        sa.Column('aspect_ratio', sa.Float(), nullable=True),
        sa.Column('crs', sa.String(length=32), nullable=True, server_default='EPSG:4326'),
        sa.Column('properties', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['investigation_id'], ['investigations.investigation_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('spill_id')
    )
    op.create_index('idx_spill_detection_time', 'spill_detections', ['observation_timestamp'])
    op.create_index('idx_spill_centroid', 'spill_detections', ['centroid_lat', 'centroid_lon'])

    # 3. Drift Runs
    op.create_table(
        'drift_runs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('investigation_id', sa.String(length=64), nullable=False),
        sa.Column('model_name', sa.String(length=128), nullable=False),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('particle_count', sa.Integer(), nullable=True),
        sa.Column('windage', sa.Float(), nullable=True),
        sa.Column('timestep_seconds', sa.Integer(), nullable=True),
        sa.Column('duration_hours', sa.Float(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='COMPLETED'),
        sa.Column('probable_origin_lat', sa.Float(), nullable=True),
        sa.Column('probable_origin_lon', sa.Float(), nullable=True),
        sa.Column('probable_origin_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('uncertainty_radius_km', sa.Float(), nullable=True),
        sa.Column('uncertainty_spread_km', sa.Float(), nullable=True),
        sa.Column('uncertainty_coverage_level', sa.Float(), nullable=True),
        sa.Column('forecast_data', sa.JSON(), nullable=True),
        sa.Column('hindcast_data', sa.JSON(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['investigation_id'], ['investigations.investigation_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_drift_investigation_id', 'drift_runs', ['investigation_id'])

    # 4. Origin Candidates
    op.create_table(
        'origin_candidates',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('investigation_id', sa.String(length=64), nullable=False),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('origin_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('uncertainty_radius_km', sa.Float(), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['investigation_id'], ['investigations.investigation_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_origin_investigation_rank', 'origin_candidates', ['investigation_id', 'rank'])

    # 5. Vessels
    op.create_table(
        'vessels',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('mmsi', sa.BigInteger(), nullable=False),
        sa.Column('imo', sa.String(length=32), nullable=True),
        sa.Column('vessel_name', sa.String(length=128), nullable=False),
        sa.Column('flag', sa.String(length=64), nullable=True),
        sa.Column('vessel_type', sa.String(length=64), nullable=True),
        sa.Column('call_sign', sa.String(length=32), nullable=True),
        sa.Column('length_m', sa.Integer(), nullable=True),
        sa.Column('width_m', sa.Integer(), nullable=True),
        sa.Column('draft_m', sa.Integer(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('mmsi')
    )
    op.create_index('idx_vessel_mmsi', 'vessels', ['mmsi'])
    op.create_index('idx_vessel_imo', 'vessels', ['imo'])

    # 6. AIS Tracks
    op.create_table(
        'ais_tracks',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('investigation_id', sa.String(length=64), nullable=False),
        sa.Column('mmsi', sa.BigInteger(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('speed_knots', sa.Float(), nullable=True),
        sa.Column('course_deg', sa.Float(), nullable=True),
        sa.Column('heading_deg', sa.Float(), nullable=True),
        sa.Column('distance_to_origin_km', sa.Float(), nullable=True),
        sa.Column('geom', sa.Text(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_ais_inv_mmsi', 'ais_tracks', ['investigation_id', 'mmsi'])
    op.create_index('idx_ais_timestamp', 'ais_tracks', ['timestamp'])

    # 7. Attribution Results
    op.create_table(
        'attribution_results',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('investigation_id', sa.String(length=64), nullable=False),
        sa.Column('mmsi', sa.BigInteger(), nullable=False),
        sa.Column('vessel_name', sa.String(length=128), nullable=False),
        sa.Column('imo', sa.String(length=32), nullable=True),
        sa.Column('vessel_type', sa.String(length=64), nullable=True),
        sa.Column('overall_score', sa.Float(), nullable=False),
        sa.Column('spatial_score', sa.Float(), nullable=False),
        sa.Column('temporal_score', sa.Float(), nullable=False),
        sa.Column('trajectory_score', sa.Float(), nullable=False),
        sa.Column('behaviour_score', sa.Float(), nullable=False),
        sa.Column('min_distance_km', sa.Float(), nullable=False),
        sa.Column('time_difference_minutes', sa.Float(), nullable=False),
        sa.Column('transit_speed_knots', sa.Float(), nullable=True),
        sa.Column('rank', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('suspicious_flags_json', sa.JSON(), nullable=True),
        sa.Column('explanation_json', sa.JSON(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['investigation_id'], ['investigations.investigation_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_attr_inv_rank', 'attribution_results', ['investigation_id', 'rank'])

    # 8. Forensic Reports
    op.create_table(
        'reports',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('report_id', sa.String(length=64), nullable=False),
        sa.Column('investigation_id', sa.String(length=64), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('report_type', sa.String(length=64), nullable=False, server_default='Forensic Dossier'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='Final'),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('author', sa.String(length=128), nullable=False),
        sa.Column('target_vessel', sa.String(length=128), nullable=False),
        sa.Column('imo', sa.String(length=32), nullable=True),
        sa.Column('mmsi', sa.BigInteger(), nullable=True),
        sa.Column('attribution_score', sa.Float(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('marpol_violation_risk', sa.String(length=32), nullable=False, server_default='High'),
        sa.Column('sha256_hash', sa.String(length=64), nullable=False),
        sa.Column('jurisdiction', sa.String(length=128), nullable=False),
        sa.Column('location_path', sa.String(length=255), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['investigation_id'], ['investigations.investigation_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('report_id')
    )
    op.create_index('idx_report_id', 'reports', ['report_id'])
    op.create_index('idx_report_investigation_id', 'reports', ['investigation_id'])


def downgrade() -> None:
    op.drop_table('reports')
    op.drop_table('attribution_results')
    op.drop_table('ais_tracks')
    op.drop_table('vessels')
    op.drop_table('origin_candidates')
    op.drop_table('drift_runs')
    op.drop_table('spill_detections')
    op.drop_table('investigations')
