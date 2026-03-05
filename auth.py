"""
Authentication Utilities
========================
Handles password hashing with bcrypt and JWT token creation/verification.

How it works:
  1. User registers → password is bcrypt-hashed and stored
  2. User logs in  → password verified, a signed JWT is returned
  3. Protected routes → JWT is decoded and the user is retrieved from DB
"""

from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from database import get_db, User
import os


# ── Config ────────────────────────────────────────────────────────────────────
SECRET_KEY  = os.getenv("SECRET_KEY", "CHANGE_ME_USE_A_LONG_RANDOM_STRING_IN_PRODUCTION")
ALGORITHM   = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("TOKEN_EXPIRE_MINUTES", "1440"))  # 24 h

# bcrypt context — handles hashing and verification
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Bearer token extractor for protected routes
bearer_scheme = HTTPBearer()


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """Return a bcrypt hash of a plaintext password."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if the plaintext password matches the stored hash."""
    return pwd_context.verify(plain, hashed)


# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """
    Create a signed JWT token.
    The `sub` claim should be the user's username or ID.
    The token expires after `ACCESS_TOKEN_EXPIRE_MINUTES` by default.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """
    Decode and verify a JWT token.
    Raises HTTPException 401 if the token is invalid or expired.
    """
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is invalid or has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── FastAPI dependency ────────────────────────────────────────────────────────

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency injected into any protected route.
    Extracts the Bearer token, decodes it, and returns the User ORM object.

    Usage in a route:
        @router.get("/me")
        def me(user: User = Depends(get_current_user)):
            ...
    """
    payload = decode_token(credentials.credentials)
    username: str = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return user
