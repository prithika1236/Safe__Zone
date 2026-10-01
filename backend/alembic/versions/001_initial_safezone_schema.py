"""Initial SafeZone Core Schema Migration

Revision ID: 001_initial_core
Revises: 
Create Date: 2026-09-21 22:58:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import geoalchemy2

# revision identifiers, used by Alembic.
revision: str = '001_initial_core'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Users
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=False),
        sa.Column('phone_number', sa.String(length=30), nullable=True),
        sa.Column('role', sa.Enum('ADMIN', 'POLICE', 'CITIZEN', name='userrole'), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_role'), 'users', ['role'], unique=False)

    # 2. Emergency Contacts
    op.create_table(
        'emergency_contacts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('phone_number', sa.String(length=30), nullable=False),
        sa.Column('relationship_type', sa.String(length=100), nullable=False),
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_emergency_contacts_user_id'), 'emergency_contacts', ['user_id'], unique=False)

    # 3. Police Officers
    op.create_table(
        'police_officers',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('badge_number', sa.String(length=50), nullable=False),
        sa.Column('rank', sa.String(length=100), nullable=False),
        sa.Column('station_name', sa.String(length=255), nullable=False),
        sa.Column('on_duty', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('is_available', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    op.create_index(op.f('ix_police_officers_badge_number'), 'police_officers', ['badge_number'], unique=True)

    # 4. Patrol Units
    op.create_table(
        'patrol_units',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('unit_code', sa.String(length=50), nullable=False),
        sa.Column('unit_type', sa.String(length=50), nullable=False, server_default='VEHICLE'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='AVAILABLE'),
        sa.Column('current_latitude', sa.Float(), nullable=True),
        sa.Column('current_longitude', sa.Float(), nullable=True),
        sa.Column('location_geom', geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.Column('last_location_update', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_patrol_units_unit_code'), 'patrol_units', ['unit_code'], unique=True)

    # 5. Location Updates
    op.create_table(
        'location_updates',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('patrol_unit_id', sa.Integer(), nullable=True),
        sa.Column('officer_id', sa.Integer(), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('location_geom', geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.Column('recorded_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['officer_id'], ['police_officers.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['patrol_unit_id'], ['patrol_units.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # 6. Crime Incidents
    op.create_table(
        'crime_incidents',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('crime_id', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('crime_category', sa.String(length=100), nullable=False),
        sa.Column('severity', sa.String(length=50), nullable=False),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('location_geom', geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.Column('ward_no', sa.Integer(), nullable=False),
        sa.Column('zone_no', sa.String(length=50), nullable=False),
        sa.Column('zone_name', sa.String(length=100), nullable=False),
        sa.Column('occurred_date', sa.Date(), nullable=False),
        sa.Column('occurred_time', sa.Time(), nullable=False),
        sa.Column('time_period', sa.String(length=50), nullable=False),
        sa.Column('location_type', sa.String(length=100), nullable=False),
        sa.Column('reported_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='REPORTED'),
        sa.Column('classification_status', sa.String(length=50), nullable=False, server_default='AUTO_CLASSIFIED'),
        sa.Column('predicted_category', sa.String(length=100), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_crime_incidents_crime_id'), 'crime_incidents', ['crime_id'], unique=True)
    op.create_index(op.f('ix_crime_incidents_crime_category'), 'crime_incidents', ['crime_category'], unique=False)
    op.create_index(op.f('ix_crime_incidents_ward_no'), 'crime_incidents', ['ward_no'], unique=False)

    # 7. SOS Requests
    op.create_table(
        'sos_requests',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('citizen_id', sa.Integer(), nullable=False),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('location_geom', geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='ACTIVE'),
        sa.Column('assigned_patrol_id', sa.Integer(), nullable=True),
        sa.Column('assigned_officer_id', sa.Integer(), nullable=True),
        sa.Column('triggered_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['assigned_officer_id'], ['police_officers.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['assigned_patrol_id'], ['patrol_units.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['citizen_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # 8. Optimization Runs
    op.create_table(
        'optimization_runs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('run_type', sa.String(length=50), nullable=False),
        sa.Column('parameters', sa.JSON(), nullable=True),
        sa.Column('total_prps_generated', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='COMPLETED'),
        sa.Column('execution_time_seconds', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )

    # 9. PRP Locations
    op.create_table(
        'prp_locations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('optimization_run_id', sa.Integer(), nullable=True),
        sa.Column('prp_type', sa.String(length=50), nullable=False),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('location_geom', geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.Column('ward_no', sa.Integer(), nullable=False),
        sa.Column('zone_no', sa.String(length=50), nullable=False),
        sa.Column('zone_name', sa.String(length=100), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('risk_score', sa.Float(), nullable=False),
        sa.Column('coverage_radius_km', sa.Float(), nullable=False, server_default='3.0'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='RECOMMENDED'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['optimization_run_id'], ['optimization_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # 10. Patrol Assignments
    op.create_table(
        'patrol_assignments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('prp_id', sa.Integer(), nullable=False),
        sa.Column('patrol_unit_id', sa.Integer(), nullable=True),
        sa.Column('officer_id', sa.Integer(), nullable=True),
        sa.Column('shift_start', sa.DateTime(), nullable=False),
        sa.Column('shift_end', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='ASSIGNED'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['officer_id'], ['police_officers.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['patrol_unit_id'], ['patrol_units.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['prp_id'], ['prp_locations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # 11. Risk Scores
    op.create_table(
        'risk_scores',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('ward_no', sa.Integer(), nullable=False),
        sa.Column('zone_no', sa.String(length=50), nullable=False),
        sa.Column('risk_type', sa.String(length=50), nullable=False),
        sa.Column('base_risk', sa.Float(), nullable=False),
        sa.Column('time_period', sa.String(length=50), nullable=True),
        sa.Column('calculated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # 12. Safe Help Points
    op.create_table(
        'safe_help_points',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('facility_type', sa.String(length=100), nullable=False),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('location_geom', geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('phone_number', sa.String(length=50), nullable=True),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('safe_help_points')
    op.drop_table('risk_scores')
    op.drop_table('patrol_assignments')
    op.drop_table('prp_locations')
    op.drop_table('optimization_runs')
    op.drop_table('sos_requests')
    op.drop_table('crime_incidents')
    op.drop_table('location_updates')
    op.drop_table('patrol_units')
    op.drop_table('police_officers')
    op.drop_table('emergency_contacts')
    op.drop_table('users')
    op.execute('DROP TYPE IF EXISTS userrole;')
