"""Server-side operator identity contract for sensitive API routes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from fastapi import HTTPException, Request

StaffRole = Literal["PLANNER", "REVIEWER"]
VALID_STAFF_ROLES = frozenset({"PLANNER", "REVIEWER"})


def authenticated_staff_roles(request: Request) -> frozenset[str]:
    """Read identity set by trusted authentication middleware, never request fields.

    The application does not currently configure an authentication provider. Until one
    sets ``request.state.authenticated_principal``, sensitive operator APIs fail closed.
    The principal must contain a stable ``subject`` (or ``sub``) and server-verified roles.
    """
    principal = getattr(request.state, "authenticated_principal", None)
    if isinstance(principal, Mapping):
        subject = principal.get("subject") or principal.get("sub")
        roles = principal.get("roles")
    else:
        subject = getattr(principal, "subject", None) or getattr(principal, "sub", None)
        roles = getattr(principal, "roles", None)

    if (
        not isinstance(subject, str)
        or not subject.strip()
        or not isinstance(roles, (list, tuple, set, frozenset))
    ):
        raise HTTPException(
            status_code=401,
            detail={"code": "STAFF_AUTH_REQUIRED", "message": "운영자 인증이 필요합니다."},
        )
    verified_roles = frozenset(
        role for role in roles if isinstance(role, str) and role in VALID_STAFF_ROLES
    )
    if not verified_roles:
        raise HTTPException(
            status_code=403,
            detail={"code": "STAFF_ROLE_REQUIRED", "message": "운영 권한이 없습니다."},
        )
    return verified_roles


def require_claimed_staff_role(claimed_role: str, verified_roles: frozenset[str]) -> StaffRole:
    """Allow a workflow role only when the authenticated principal holds that role."""
    if claimed_role not in VALID_STAFF_ROLES or claimed_role not in verified_roles:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "STAFF_ROLE_NOT_PERMITTED",
                "message": "이 역할로 작업할 권한이 없습니다.",
            },
        )
    return claimed_role  # type: ignore[return-value]
