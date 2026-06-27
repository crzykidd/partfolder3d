"""User management endpoints (admin only).

GET    /api/users           → list all users
POST   /api/users           → create a new user (admin sets password)
GET    /api/users/{user_id} → get user details
PATCH  /api/users/{user_id} → update name/role/is_active
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import csrf_protect, get_db, require_admin
from ..auth.password import hash_password
from ..models.user import User, UserRole

router = APIRouter(prefix="/api/users", tags=["users"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class UserSummary(BaseModel):
    id: int
    email: str
    name: str
    role: str
    is_active: bool

    model_config = {"from_attributes": True}


class UserDetail(UserSummary):
    theme_pref: str


class CreateUserRequest(BaseModel):
    email: EmailStr
    name: str
    password: str
    role: str = "user"


class UpdateUserRequest(BaseModel):
    name: str | None = None
    role: str | None = None
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[UserSummary])
async def list_users(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[UserSummary]:
    result = await db.execute(select(User).order_by(User.id))
    users = result.scalars().all()
    return [
        UserSummary(
            id=u.id, email=u.email, name=u.name, role=u.role.value, is_active=u.is_active
        )
        for u in users
    ]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=UserDetail)
async def create_user(
    body: CreateUserRequest,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserDetail:
    # Check email uniqueness
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")

    try:
        role = UserRole(body.role)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid role: {body.role!r}",
        ) from exc

    if len(body.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters",
        )

    user = User(
        email=body.email,
        name=body.name,
        role=role,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    await db.flush()
    return UserDetail(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role.value,
        is_active=user.is_active,
        theme_pref=user.theme_pref,
    )


@router.get("/{user_id}", response_model=UserDetail)
async def get_user(
    user_id: int,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserDetail:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserDetail(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role.value,
        is_active=user.is_active,
        theme_pref=user.theme_pref,
    )


@router.patch("/{user_id}", response_model=UserDetail)
async def update_user(
    user_id: int,
    body: UpdateUserRequest,
    _admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[None, Depends(csrf_protect)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserDetail:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if body.name is not None:
        user.name = body.name
    if body.role is not None:
        try:
            user.role = UserRole(body.role)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid role: {body.role!r}",
            ) from exc
    if body.is_active is not None:
        user.is_active = body.is_active

    await db.flush()
    return UserDetail(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role.value,
        is_active=user.is_active,
        theme_pref=user.theme_pref,
    )
