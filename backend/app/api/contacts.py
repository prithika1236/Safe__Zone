"""SafeZone Citizen Emergency Contacts API.

Provides endpoints for:
- Viewing authenticated citizen's emergency contacts
- Adding new emergency contacts with phone validation and primary contact flag
- Editing contact details
- Deleting contacts
- Enforcing strict ownership isolation (Citizen A cannot access Citizen B's contacts).
"""

from datetime import datetime
import re
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from app.database.session import get_async_db
from app.core.security import get_current_user
from app.models.user import User, EmergencyContact

router = APIRouter(prefix="/contacts", tags=["Emergency Contacts"])


class EmergencyContactCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    phone_number: str = Field(..., min_length=7, max_length=20)
    relationship_type: str = Field(default="Family", max_length=50)
    is_primary: bool = Field(default=False)

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        cleaned = re.sub(r"[\s\-\(\)]", "", v)
        if not re.match(r"^\+?[0-9]{7,15}$", cleaned):
            raise ValueError("Invalid phone number format. Must contain 7-15 digits.")
        return v.strip()


class EmergencyContactUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    phone_number: Optional[str] = Field(None, min_length=7, max_length=20)
    relationship_type: Optional[str] = Field(None, max_length=50)
    is_primary: Optional[bool] = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = re.sub(r"[\s\-\(\)]", "", v)
        if not re.match(r"^\+?[0-9]{7,15}$", cleaned):
            raise ValueError("Invalid phone number format. Must contain 7-15 digits.")
        return v.strip()


class EmergencyContactResponse(BaseModel):
    id: int
    user_id: int
    name: str
    phone_number: str
    relationship_type: str
    is_primary: bool
    created_at: datetime
    updated_at: datetime


@router.get(
    "/",
    response_model=List[EmergencyContactResponse],
    summary="List Citizen Emergency Contacts",
)
async def list_emergency_contacts(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """List all emergency contacts belonging to the authenticated user."""
    stmt = (
        select(EmergencyContact)
        .where(EmergencyContact.user_id == current_user.id)
        .order_by(desc(EmergencyContact.is_primary), EmergencyContact.id)
    )
    res = await db.execute(stmt)
    records = res.scalars().all()

    return [
        EmergencyContactResponse(
            id=c.id,
            user_id=c.user_id,
            name=c.name,
            phone_number=c.phone_number,
            relationship_type=c.relationship_type,
            is_primary=c.is_primary,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in records
    ]


@router.post(
    "/",
    response_model=EmergencyContactResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add New Emergency Contact",
)
async def create_emergency_contact(
    payload: EmergencyContactCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """Add a new emergency contact. If marked primary, unset existing primary contacts."""
    if payload.is_primary:
        # Unset other primary contacts for this user
        existing_stmt = select(EmergencyContact).where(
            and_(EmergencyContact.user_id == current_user.id, EmergencyContact.is_primary == True)
        )
        res_existing = await db.execute(existing_stmt)
        for ec in res_existing.scalars().all():
            ec.is_primary = False

    contact = EmergencyContact(
        user_id=current_user.id,
        name=payload.name.strip(),
        phone_number=payload.phone_number.strip(),
        relationship_type=payload.relationship_type.strip(),
        is_primary=payload.is_primary,
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)

    return EmergencyContactResponse(
        id=contact.id,
        user_id=contact.user_id,
        name=contact.name,
        phone_number=contact.phone_number,
        relationship_type=contact.relationship_type,
        is_primary=contact.is_primary,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
    )


@router.put(
    "/{contact_id}",
    response_model=EmergencyContactResponse,
    summary="Update Emergency Contact",
)
async def update_emergency_contact(
    contact_id: int,
    payload: EmergencyContactUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """Update contact details. Enforces ownership."""
    stmt = select(EmergencyContact).where(EmergencyContact.id == contact_id)
    res = await db.execute(stmt)
    contact = res.scalar_one_or_none()

    if not contact or contact.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Emergency contact #{contact_id} not found.",
        )

    if payload.is_primary is True:
        existing_stmt = select(EmergencyContact).where(
            and_(
                EmergencyContact.user_id == current_user.id,
                EmergencyContact.is_primary == True,
                EmergencyContact.id != contact_id,
            )
        )
        res_existing = await db.execute(existing_stmt)
        for ec in res_existing.scalars().all():
            ec.is_primary = False
        contact.is_primary = True
    elif payload.is_primary is False:
        contact.is_primary = False

    if payload.name is not None:
        contact.name = payload.name.strip()
    if payload.phone_number is not None:
        contact.phone_number = payload.phone_number.strip()
    if payload.relationship_type is not None:
        contact.relationship_type = payload.relationship_type.strip()

    contact.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(contact)

    return EmergencyContactResponse(
        id=contact.id,
        user_id=contact.user_id,
        name=contact.name,
        phone_number=contact.phone_number,
        relationship_type=contact.relationship_type,
        is_primary=contact.is_primary,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
    )


@router.delete(
    "/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Emergency Contact",
)
async def delete_emergency_contact(
    contact_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an emergency contact. Enforces ownership."""
    stmt = select(EmergencyContact).where(EmergencyContact.id == contact_id)
    res = await db.execute(stmt)
    contact = res.scalar_one_or_none()

    if not contact or contact.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Emergency contact #{contact_id} not found.",
        )

    await db.delete(contact)
    await db.commit()
    return None
