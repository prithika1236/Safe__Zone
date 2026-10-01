"""SafeZone Safe Help Points API.

Provides endpoints for:
- Listing verified and active public Safe Help Points (Hospitals, Police Stations, Police Booths, Emergency Facilities)
- Citizen viewing only verified and active sanctuaries with map links and contact numbers
- Admin CRUD management: create, edit, verify toggle, deactivation toggle, delete
- Admin CSV batch ingestion with schema validation, coordinate range checks, and granular error reporting
- Strict role-based segregation: never leaks PRP data or unverified help points to citizens.
"""

from datetime import datetime
import csv
import io
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from app.database.session import get_async_db
from app.models.help_point import SafeHelpPoint
from app.models.user import User, UserRole
from app.core.security import require_admin, get_optional_current_user

router = APIRouter(prefix="/help-points", tags=["Safe Help Points"])


class SafeHelpPointResponse(BaseModel):
    id: int
    name: str
    facility_type: str
    latitude: float
    longitude: float
    address: Optional[str] = None
    phone_number: Optional[str] = None
    is_verified: bool
    is_active: bool
    map_link: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SafeHelpPointCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    facility_type: str = Field("HOSPITAL", description="HOSPITAL, POLICE_STATION, POLICE_BOOTH, EMERGENCY_FACILITY, WOMEN_SHELTER, FIRE_STATION")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    address: Optional[str] = None
    phone_number: Optional[str] = None
    is_verified: bool = True
    is_active: bool = True


class SafeHelpPointUpdate(BaseModel):
    name: Optional[str] = None
    facility_type: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
    address: Optional[str] = None
    phone_number: Optional[str] = None
    is_verified: Optional[bool] = None
    is_active: Optional[bool] = None


class SHPCSVImportSummary(BaseModel):
    total_rows: int
    imported: int
    skipped_duplicates: int
    errors: List[str]


def _format_shp_response(shp: SafeHelpPoint) -> SafeHelpPointResponse:
    return SafeHelpPointResponse(
        id=shp.id,
        name=shp.name,
        facility_type=shp.facility_type,
        latitude=shp.latitude,
        longitude=shp.longitude,
        address=shp.address,
        phone_number=shp.phone_number,
        is_verified=shp.is_verified,
        is_active=shp.is_active,
        map_link=f"https://maps.google.com/?q={shp.latitude:.6f},{shp.longitude:.6f}",
        created_at=shp.created_at,
        updated_at=shp.updated_at,
    )


# ==========================================
# PUBLIC & CITIZEN ENDPOINTS
# ==========================================

@router.get(
    "/",
    response_model=List[SafeHelpPointResponse],
    summary="List Safe Help Points",
)
async def list_safe_help_points(
    facility_type: Optional[str] = Query(None, description="Filter by facility type (e.g. HOSPITAL, POLICE_STATION)"),
    search: Optional[str] = Query(None, description="Search by name or address"),
    is_verified: Optional[bool] = Query(None, description="Filter by verification state (Admin Only)"),
    is_active: Optional[bool] = Query(None, description="Filter by active state (Admin Only)"),
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Retrieve public emergency help points. Non-admins receive ONLY verified and active facilities."""
    stmt = select(SafeHelpPoint)

    is_admin = current_user is not None and current_user.role == UserRole.ADMIN

    if is_admin:
        if is_verified is not None:
            stmt = stmt.where(SafeHelpPoint.is_verified == is_verified)
        if is_active is not None:
            stmt = stmt.where(SafeHelpPoint.is_active == is_active)
    else:
        # Strict Citizen / Public Rule: ONLY verified AND active Safe Help Points
        stmt = stmt.where(
            and_(
                SafeHelpPoint.is_verified == True,
                SafeHelpPoint.is_active == True,
            )
        )

    if facility_type:
        stmt = stmt.where(SafeHelpPoint.facility_type.ilike(f"%{facility_type.strip()}%"))

    if search:
        search_pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                SafeHelpPoint.name.ilike(search_pattern),
                SafeHelpPoint.address.ilike(search_pattern),
            )
        )

    stmt = stmt.order_by(SafeHelpPoint.name)
    res = await db.execute(stmt)
    points = res.scalars().all()

    return [_format_shp_response(p) for p in points]


@router.get(
    "/{point_id}",
    response_model=SafeHelpPointResponse,
    summary="Get Safe Help Point by ID",
)
async def get_safe_help_point(
    point_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Retrieve a single Safe Help Point. Non-admins can only view if verified and active."""
    stmt = select(SafeHelpPoint).where(SafeHelpPoint.id == point_id)
    res = await db.execute(stmt)
    point = res.scalar_one_or_none()

    if not point:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Safe Help Point #{point_id} not found.",
        )

    is_admin = current_user is not None and current_user.role == UserRole.ADMIN
    if not is_admin and (not point.is_verified or not point.is_active):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Safe Help Point #{point_id} not found or currently unavailable.",
        )

    return _format_shp_response(point)


# ==========================================
# ADMIN MANAGEMENT ENDPOINTS
# ==========================================

@router.post(
    "/",
    response_model=SafeHelpPointResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Safe Help Point (Admin Only)",
)
async def create_safe_help_point(
    payload: SafeHelpPointCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin),
):
    """Admin creates a new Safe Help Point facility."""
    shp = SafeHelpPoint(
        name=payload.name.strip(),
        facility_type=payload.facility_type.strip().upper(),
        latitude=payload.latitude,
        longitude=payload.longitude,
        address=payload.address.strip() if payload.address else None,
        phone_number=payload.phone_number.strip() if payload.phone_number else None,
        is_verified=payload.is_verified,
        is_active=payload.is_active,
    )
    db.add(shp)
    await db.commit()
    await db.refresh(shp)

    return _format_shp_response(shp)


@router.put(
    "/{point_id}",
    response_model=SafeHelpPointResponse,
    summary="Update Safe Help Point (Admin Only)",
)
async def update_safe_help_point(
    point_id: int,
    payload: SafeHelpPointUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin),
):
    """Admin updates an existing Safe Help Point facility."""
    stmt = select(SafeHelpPoint).where(SafeHelpPoint.id == point_id)
    res = await db.execute(stmt)
    shp = res.scalar_one_or_none()
    if not shp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Safe Help Point #{point_id} not found.",
        )

    if payload.name is not None:
        shp.name = payload.name.strip()
    if payload.facility_type is not None:
        shp.facility_type = payload.facility_type.strip().upper()
    if payload.latitude is not None:
        shp.latitude = payload.latitude
    if payload.longitude is not None:
        shp.longitude = payload.longitude
    if payload.address is not None:
        shp.address = payload.address.strip() or None
    if payload.phone_number is not None:
        shp.phone_number = payload.phone_number.strip() or None
    if payload.is_verified is not None:
        shp.is_verified = payload.is_verified
    if payload.is_active is not None:
        shp.is_active = payload.is_active

    shp.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(shp)

    return _format_shp_response(shp)


@router.delete(
    "/{point_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete Safe Help Point (Admin Only)",
)
async def delete_safe_help_point(
    point_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin),
):
    """Admin deletes a Safe Help Point."""
    stmt = select(SafeHelpPoint).where(SafeHelpPoint.id == point_id)
    res = await db.execute(stmt)
    shp = res.scalar_one_or_none()
    if not shp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Safe Help Point #{point_id} not found.",
        )

    await db.delete(shp)
    await db.commit()
    return {"message": f"Safe Help Point #{point_id} deleted successfully."}


@router.post(
    "/{point_id}/verify",
    response_model=SafeHelpPointResponse,
    summary="Toggle Safe Help Point Verification Status (Admin Only)",
)
async def verify_safe_help_point(
    point_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin),
):
    """Admin toggles verification approval status for a Safe Help Point."""
    stmt = select(SafeHelpPoint).where(SafeHelpPoint.id == point_id)
    res = await db.execute(stmt)
    shp = res.scalar_one_or_none()
    if not shp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Safe Help Point #{point_id} not found.",
        )

    shp.is_verified = not shp.is_verified
    shp.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(shp)

    return _format_shp_response(shp)


@router.post(
    "/{point_id}/deactivate",
    response_model=SafeHelpPointResponse,
    summary="Toggle Safe Help Point Active Status / Deactivate (Admin Only)",
)
async def deactivate_safe_help_point(
    point_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin),
):
    """Admin toggles active status for a Safe Help Point (Deactivate / Reactivate)."""
    stmt = select(SafeHelpPoint).where(SafeHelpPoint.id == point_id)
    res = await db.execute(stmt)
    shp = res.scalar_one_or_none()
    if not shp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Safe Help Point #{point_id} not found.",
        )

    shp.is_active = not shp.is_active
    shp.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(shp)

    return _format_shp_response(shp)


@router.post(
    "/import-csv",
    response_model=SHPCSVImportSummary,
    summary="Import Safe Help Points from CSV (Admin Only)",
)
async def import_help_points_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin),
):
    """Admin imports Safe Help Points dataset from CSV with schema and coordinate validation."""
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must be a CSV file (.csv).",
        )

    content = await file.read()
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            decoded = content.decode("utf-8")
        except UnicodeDecodeError:
            decoded = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(decoded))
    raw_fieldnames = reader.fieldnames or []
    fieldnames = {f.strip().lower() for f in raw_fieldnames if f}

    has_name = "name" in fieldnames or "facility_name" in fieldnames or "point_name" in fieldnames
    has_lat = "latitude" in fieldnames or "lat" in fieldnames
    has_lon = "longitude" in fieldnames or "lon" in fieldnames or "lng" in fieldnames

    if not (has_name and has_lat and has_lon):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV missing required columns: name (or facility_name), latitude (or lat), longitude (or lon/lng).",
        )

    # Pre-fetch existing names to prevent duplicate creation
    existing_res = await db.execute(select(SafeHelpPoint.name))
    existing_names = {n.strip().lower() for n in existing_res.scalars().all()}

    imported = 0
    skipped_duplicates = 0
    errors: List[str] = []
    total_rows = 0

    new_points = []

    for row_idx, row in enumerate(reader, start=1):
        total_rows += 1
        name = (row.get("name") or row.get("facility_name") or row.get("point_name") or "").strip()
        if not name:
            errors.append(f"Row {row_idx}: Empty facility name.")
            continue

        if name.lower() in existing_names:
            skipped_duplicates += 1
            continue

        raw_lat = row.get("latitude") or row.get("lat")
        raw_lon = row.get("longitude") or row.get("lon") or row.get("lng")

        try:
            lat = float(raw_lat)
            lon = float(raw_lon)
            if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
                errors.append(f"Row {row_idx} ('{name}'): Coordinate values out of range ({lat}, {lon}).")
                continue
        except (ValueError, TypeError):
            errors.append(f"Row {row_idx} ('{name}'): Invalid numeric coordinates ({raw_lat}, {raw_lon}).")
            continue

        ftype = (row.get("facility_type") or row.get("point_type") or row.get("type") or "EMERGENCY_FACILITY").strip().upper()
        address = (row.get("address") or row.get("location") or "").strip() or None
        phone = (row.get("phone") or row.get("phone_number") or row.get("contact_phone") or "").strip() or None
        
        is_verified_raw = (row.get("is_verified") or "true").strip().lower()
        is_verified = is_verified_raw in ("true", "1", "yes", "t", "y")

        is_active_raw = (row.get("is_active") or "true").strip().lower()
        is_active = is_active_raw in ("true", "1", "yes", "t", "y")

        shp = SafeHelpPoint(
            name=name,
            facility_type=ftype,
            latitude=lat,
            longitude=lon,
            address=address,
            phone_number=phone,
            is_verified=is_verified,
            is_active=is_active,
        )
        new_points.append(shp)
        existing_names.add(name.lower())
        imported += 1

    if new_points:
        db.add_all(new_points)
        await db.commit()

    return SHPCSVImportSummary(
        total_rows=total_rows,
        imported=imported,
        skipped_duplicates=skipped_duplicates,
        errors=errors,
    )
