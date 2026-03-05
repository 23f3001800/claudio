"""
Authentication Router
=====================
Handles user registration, login, and profile retrieval.

Endpoints:
  POST /auth/register  → Create a new account
  POST /auth/login     → Get a JWT token
  GET  /auth/me        → View your own profile (requires token)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import timedelta

from database import get_db, User
from auth import (
    hash_password, verify_password,
    create_access_token, get_current_user,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from schemas import RegisterRequest, LoginRequest, TokenResponse, UserResponse

router = APIRouter()


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user account",
)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    """
    Register a new user. Checks for duplicate usernames and emails before
    creating the account. The password is never stored in plaintext.
    """
    # Guard against duplicate usernames
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{payload.username}' is already taken.",
        )

    # Guard against duplicate emails
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Log in and receive a JWT access token",
)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """
    Authenticate with username + password. Returns a Bearer JWT token.
    Include this token in the `Authorization: Bearer <token>` header for
    all protected endpoints.
    """
    user = db.query(User).filter(User.username == payload.username).first()

    # Use a generic error message so we don't reveal whether the username exists
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated.")

    token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get your own profile",
)
def get_me(current_user: User = Depends(get_current_user)):
    """Returns the profile of the currently authenticated user."""
    return current_user
