from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import JWT_ALGORITHM, JWT_EXPIRE_MINUTES, JWT_SECRET
from .errors import AppError


bearer = HTTPBearer(auto_error=False)


def create_token(user_id):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=JWT_EXPIRE_MINUTES),
        "iss": "portfolio-mock-backend",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def current_user_id(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    if not credentials:
        raise AppError(401, "AUTH_REQUIRED", "请先登录。")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM], issuer="portfolio-mock-backend")
    except jwt.ExpiredSignatureError as exc:
        raise AppError(401, "TOKEN_EXPIRED", "登录状态已过期，请重新登录。") from exc
    except jwt.PyJWTError as exc:
        raise AppError(401, "AUTH_REQUIRED", "登录凭证无效，请重新登录。") from exc
    user_id = payload.get("sub")
    if not user_id:
        raise AppError(401, "AUTH_REQUIRED", "登录凭证无效，请重新登录。")
    return user_id
