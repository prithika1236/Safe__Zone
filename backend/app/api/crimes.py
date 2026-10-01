import csv
import io
import math
import uuid
from datetime import datetime, date, time
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.database.session import get_async_db
from app.models.crime import CrimeIncident
from app.models.user import User
from app.core.security import require_admin, get_current_user
from app.ml.crime_classifier import classify_crime_description
from app.schemas.crime import (
    CrimeIncidentCreate,
    CrimeIncidentUpdate,
    CrimeIncidentVerify,
    CrimeIncidentResponse,
    CrimeListResponse,
    CrimeClassifyPreviewRequest,
    CrimeClassifyPreviewResponse,
    CSVImportSummary,
    SEVERITY_POLICY,
    derive_time_period,
)

router = APIRouter(prefix="/crimes", tags=["Crimes"])


@router.get("/status")
def crimes_status():
    return {"module": "crimes", "status": "ready"}


@router.post("/classify-preview", response_model=CrimeClassifyPreviewResponse)
def preview_crime_classification(
    payload: CrimeClassifyPreviewRequest,
    current_user: User = Depends(get_current_user),
):
    """Run DL BiLSTM classification on a raw incident description without saving."""
    res = classify_crime_description(payload.description)
    return CrimeClassifyPreviewResponse(
        description=payload.description,
        predicted_category=res["predicted_category"],
        confidence=res["confidence"],
        classification_status=res["classification_status"],
        probabilities=res.get("probabilities", {}),
    )


@router.get("/", response_model=CrimeListResponse)
async def list_crimes(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    start_date: Optional[date] = Query(None, description="Filter occurred_date >= start_date"),
    end_date: Optional[date] = Query(None, description="Filter occurred_date <= end_date"),
    crime_category: Optional[str] = Query(None, description="Filter crime category"),
    severity: Optional[str] = Query(None, description="Filter severity"),
    ward_no: Optional[int] = Query(None, description="Filter ward number"),
    zone_no: Optional[str] = Query(None, description="Filter zone number"),
    status: Optional[str] = Query(None, description="Filter status"),
    classification_status: Optional[str] = Query(None, description="Filter classification status"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """List crime incidents with pagination and multi-criteria filtering."""
    filters = []

    if start_date:
        filters.append(CrimeIncident.occurred_date >= start_date)
    if end_date:
        filters.append(CrimeIncident.occurred_date <= end_date)
    if crime_category:
        filters.append(CrimeIncident.crime_category == crime_category)
    if severity:
        filters.append(CrimeIncident.severity == severity)
    if ward_no:
        filters.append(CrimeIncident.ward_no == ward_no)
    if zone_no:
        filters.append(CrimeIncident.zone_no == zone_no)
    if status:
        filters.append(CrimeIncident.status == status)
    if classification_status:
        filters.append(CrimeIncident.classification_status == classification_status)

    where_clause = and_(*filters) if filters else True

    # Count total
    count_stmt = select(func.count(CrimeIncident.id)).where(where_clause)
    total_result = await db.execute(count_stmt)
    total_count = total_result.scalar_one()

    # Query page
    offset = (page - 1) * page_size
    query_stmt = (
        select(CrimeIncident)
        .where(where_clause)
        .order_by(CrimeIncident.occurred_date.desc(), CrimeIncident.occurred_time.desc())
        .offset(offset)
        .limit(page_size)
    )
    items_result = await db.execute(query_stmt)
    items = items_result.scalars().all()

    total_pages = math.ceil(total_count / page_size) if total_count > 0 else 1

    return CrimeListResponse(
        items=[CrimeIncidentResponse.model_validate(item) for item in items],
        total=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{crime_id_or_pk}", response_model=CrimeIncidentResponse)
async def get_crime_incident(
    crime_id_or_pk: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve a single crime incident by primary key integer or crime_id string."""
    if crime_id_or_pk.isdigit():
        stmt = select(CrimeIncident).where(CrimeIncident.id == int(crime_id_or_pk))
    else:
        stmt = select(CrimeIncident).where(CrimeIncident.crime_id == crime_id_or_pk)

    result = await db.execute(stmt)
    incident = result.scalar_one_or_none()

    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crime incident '{crime_id_or_pk}' not found.",
        )
    return incident


@router.post("/", response_model=CrimeIncidentResponse, status_code=status.HTTP_201_CREATED)
async def create_crime_incident(
    payload: CrimeIncidentCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin),
):
    """Create a new crime incident.

    If crime_category is not provided, the BiLSTM classifier automatically
    classifies the description and assigns confidence/status.
    """
    # Unique crime_id generation
    unique_suffix = uuid.uuid4().hex[:6].upper()
    generated_crime_id = f"CR-MANUAL-{unique_suffix}"

    # DL Classification logic
    if payload.crime_category:
        category = payload.crime_category
        predicted_cat = None
        conf = None
        class_status = "ADMIN_VERIFIED"
    else:
        dl_res = classify_crime_description(payload.description)
        category = dl_res["predicted_category"]
        predicted_cat = dl_res["predicted_category"]
        conf = dl_res["confidence"]
        class_status = dl_res["classification_status"]

    severity = payload.severity or SEVERITY_POLICY.get(category, "MEDIUM")
    time_period = payload.time_period or derive_time_period(payload.occurred_time.hour)
    reported_date = payload.reported_date or payload.occurred_date

    new_incident = CrimeIncident(
        crime_id=generated_crime_id,
        description=payload.description,
        crime_category=category,
        severity=severity,
        latitude=payload.latitude,
        longitude=payload.longitude,
        ward_no=payload.ward_no,
        zone_no=payload.zone_no,
        zone_name=payload.zone_name,
        occurred_date=payload.occurred_date,
        occurred_time=payload.occurred_time,
        time_period=time_period,
        location_type=payload.location_type,
        reported_date=reported_date,
        status=payload.status or "REPORTED",
        classification_status=class_status,
        predicted_category=predicted_cat,
        confidence=conf,
    )

    db.add(new_incident)
    await db.commit()
    await db.refresh(new_incident)
    return new_incident


@router.put("/{incident_id}", response_model=CrimeIncidentResponse)
async def update_crime_incident(
    incident_id: int,
    payload: CrimeIncidentUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin),
):
    """Update a crime incident."""
    stmt = select(CrimeIncident).where(CrimeIncident.id == incident_id)
    result = await db.execute(stmt)
    incident = result.scalar_one_or_none()

    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crime incident ID {incident_id} not found.",
        )

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            setattr(incident, field, value)

    # Re-derive time_period if occurred_time was updated
    if "occurred_time" in update_data and "time_period" not in update_data:
        incident.time_period = derive_time_period(incident.occurred_time.hour)

    await db.commit()
    await db.refresh(incident)
    return incident


@router.post("/{incident_id}/verify", response_model=CrimeIncidentResponse)
async def verify_crime_classification(
    incident_id: int,
    payload: CrimeIncidentVerify,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin),
):
    """Admin review & verification workflow.

    Confirms or corrects the crime category and sets status to ADMIN_VERIFIED.
    """
    stmt = select(CrimeIncident).where(CrimeIncident.id == incident_id)
    result = await db.execute(stmt)
    incident = result.scalar_one_or_none()

    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crime incident ID {incident_id} not found.",
        )

    incident.crime_category = payload.crime_category
    incident.classification_status = "ADMIN_VERIFIED"
    incident.severity = payload.severity or SEVERITY_POLICY.get(payload.crime_category, incident.severity)

    await db.commit()
    await db.refresh(incident)
    return incident


@router.delete("/{incident_id}", status_code=status.HTTP_200_OK)
async def delete_crime_incident(
    incident_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin),
):
    """Delete a crime incident."""
    stmt = select(CrimeIncident).where(CrimeIncident.id == incident_id)
    result = await db.execute(stmt)
    incident = result.scalar_one_or_none()

    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crime incident ID {incident_id} not found.",
        )

    await db.delete(incident)
    await db.commit()
    return {"message": f"Crime incident {incident.crime_id} successfully deleted."}


@router.post("/import-csv", response_model=CSVImportSummary)
async def import_crimes_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin),
):
    """Import crime dataset from CSV with schema validation and duplicate prevention."""
    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must be a CSV file.",
        )

    content = await file.read()
    try:
        decoded = content.decode("utf-8")
    except UnicodeDecodeError:
        decoded = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(decoded))
    required_fields = {
        "crime_id", "description", "crime_category", "severity",
        "latitude", "longitude", "ward_no", "zone_no", "zone_name",
        "occurred_date", "occurred_time", "time_period",
        "location_type", "reported_date", "status"
    }

    fieldnames = set(reader.fieldnames or [])
    if not required_fields.issubset(fieldnames):
        missing = required_fields - fieldnames
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CSV schema validation failed. Missing required columns: {list(missing)}",
        )

    # Fetch existing crime_ids in database to avoid duplicates
    existing_stmt = select(CrimeIncident.crime_id)
    existing_res = await db.execute(existing_stmt)
    existing_ids = set(existing_res.scalars().all())

    imported_count = 0
    skipped_duplicates = 0
    failed_rows = 0
    errors = []
    new_records = []

    for row_idx, row in enumerate(reader, start=2):
        c_id = row.get("crime_id", "").strip()
        if not c_id:
            failed_rows += 1
            errors.append(f"Row {row_idx}: Missing crime_id")
            continue

        if c_id in existing_ids:
            skipped_duplicates += 1
            continue

        try:
            occ_d = datetime.strptime(row["occurred_date"].strip(), "%Y-%m-%d").date()
            rep_d = datetime.strptime(row["reported_date"].strip(), "%Y-%m-%d").date()
            occ_t_parts = [int(p) for p in row["occurred_time"].strip().split(":")]
            occ_t = time(hour=occ_t_parts[0], minute=occ_t_parts[1], second=occ_t_parts[2] if len(occ_t_parts) > 2 else 0)
            lat = float(row["latitude"].strip())
            lon = float(row["longitude"].strip())
            ward = int(row["ward_no"].strip())
        except Exception as e:
            failed_rows += 1
            if len(errors) < 10:
                errors.append(f"Row {row_idx} ({c_id}): Data parsing error - {str(e)}")
            continue

        incident = CrimeIncident(
            crime_id=c_id,
            description=row["description"].strip(),
            crime_category=row["crime_category"].strip(),
            severity=row["severity"].strip(),
            latitude=lat,
            longitude=lon,
            ward_no=ward,
            zone_no=row["zone_no"].strip(),
            zone_name=row["zone_name"].strip(),
            occurred_date=occ_d,
            occurred_time=occ_t,
            time_period=row["time_period"].strip(),
            location_type=row["location_type"].strip(),
            reported_date=rep_d,
            status=row["status"].strip(),
            classification_status="AUTO_CLASSIFIED",
        )
        new_records.append(incident)
        existing_ids.add(c_id)
        imported_count += 1

        # Commit in batches of 1000
        if len(new_records) >= 1000:
            db.add_all(new_records)
            await db.commit()
            new_records = []

    if new_records:
        db.add_all(new_records)
        await db.commit()

    total_rows = imported_count + skipped_duplicates + failed_rows
    return CSVImportSummary(
        total_rows=total_rows,
        imported=imported_count,
        skipped_duplicates=skipped_duplicates,
        failed_rows=failed_rows,
        errors=errors[:10],
    )
