from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.core.errors import AppError, error_body
from app.core.ratelimit import client_ip, hit, limit_by_ip
from app.core.security import AccessClaims
from app.deps import ClaimsDep, CurrentUserDep, SessionDep, get_optional_claims
from app.repositories import users as user_repo
from app.schemas.auth import (
    AuthOut,
    InviteAcceptIn,
    InvitePreviewOut,
    LoginIn,
    MeOut,
    SignupIn,
    SwitchTenantIn,
)
from app.services import auth as auth_service
from app.services import tenants as tenant_service

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "bz_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"
RefreshCookie = Annotated[str | None, Cookie(alias=REFRESH_COOKIE)]


def set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.refresh_token_ttl_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


def clear_refresh_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        REFRESH_COOKIE,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )


@router.post(
    "/signup",
    response_model=AuthOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account and a business",
    dependencies=[Depends(limit_by_ip("signup", 3))],
)
async def signup(data: SignupIn, response: Response, session: SessionDep) -> AuthOut:
    result = await auth_service.signup(session, data)
    set_refresh_cookie(response, result.refresh_token)
    return result.body


@router.post("/login", response_model=AuthOut, summary="Sign in with email and password")
async def login(
    data: LoginIn, request: Request, response: Response, session: SessionDep
) -> AuthOut:
    await hit("login", f"{client_ip(request)}:{data.email.lower()}", 5, 60)
    result = await auth_service.login(session, data.email, data.password)
    set_refresh_cookie(response, result.refresh_token)
    return result.body


@router.post(
    "/refresh",
    response_model=AuthOut,
    summary="Rotate the refresh cookie and get a new access token",
    dependencies=[Depends(limit_by_ip("refresh", 30))],
)
async def refresh(
    response: Response, session: SessionDep, token: RefreshCookie = None
) -> AuthOut | Response:
    try:
        result = await auth_service.refresh(session, token)
    except AppError as exc:
        # A dead session must also drop the cookie, so build the error response here.
        out = JSONResponse(error_body(exc.code, exc.message), status_code=exc.status_code)
        clear_refresh_cookie(out)
        return out
    set_refresh_cookie(response, result.refresh_token)
    return result.body


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke the refresh token")
async def logout(response: Response, session: SessionDep, token: RefreshCookie = None) -> Response:
    await auth_service.logout(session, token)
    out = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_refresh_cookie(out)
    return out


@router.get("/me", response_model=MeOut, summary="Current user, memberships and active tenant")
async def me(claims: ClaimsDep, user: CurrentUserDep, session: SessionDep) -> MeOut:
    return await auth_service.me(session, user, claims.tenant_id)


@router.post("/switch-tenant", response_model=AuthOut, summary="Switch the active business")
async def switch_tenant(
    data: SwitchTenantIn, user: CurrentUserDep, session: SessionDep, token: RefreshCookie = None
) -> AuthOut:
    return await auth_service.switch_tenant(session, user, data.tenant_id, token)


@router.get(
    "/invites/{token}",
    response_model=InvitePreviewOut,
    summary="Preview a staff invite",
    dependencies=[Depends(limit_by_ip("invite", 30))],
)
async def preview_invite(token: str, session: SessionDep) -> InvitePreviewOut:
    return await tenant_service.preview_invite(session, token)


@router.post(
    "/invites/{token}/accept",
    response_model=AuthOut,
    summary="Accept a staff invite (new account, existing login, or signed-in user)",
    dependencies=[Depends(limit_by_ip("invite", 30))],
)
async def accept_invite(
    token: str,
    data: InviteAcceptIn,
    response: Response,
    session: SessionDep,
    claims: Annotated[AccessClaims | None, Depends(get_optional_claims)],
) -> AuthOut:
    current = await user_repo.get_by_id(session, claims.user_id) if claims else None
    result = await tenant_service.accept_invite(session, token, data, current)
    set_refresh_cookie(response, result.refresh_token)
    return result.body
