from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    AuthLoginRequest,
    AuthRegisterRequest,
    AuthUserListResponse,
    AuthUserResponse,
)
from app.services.user_store import get_user_store

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/users", response_model=AuthUserListResponse)
def list_users() -> AuthUserListResponse:
    rows = get_user_store().list_users()
    items = [AuthUserResponse(**x) for x in rows]
    return AuthUserListResponse(users=items, total=len(items))


@router.post("/register", response_model=AuthUserResponse)
def register(req: AuthRegisterRequest) -> AuthUserResponse:
    try:
        row = get_user_store().create_user(username=req.username, password=req.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AuthUserResponse(**row)


@router.post("/login", response_model=AuthUserResponse)
def login(req: AuthLoginRequest) -> AuthUserResponse:
    try:
        row = get_user_store().authenticate(username=req.username, password=req.password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return AuthUserResponse(**row)

