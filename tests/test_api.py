"""Integration tests for ArcticAI API endpoints."""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import AUTH_UNVERIFIED, AUTH_USER1, AUTH_USER2


# ── Auth ──


@pytest.mark.asyncio
async def test_auth_me(client: AsyncClient):
    r = await client.get("/api/v1/auth/me", headers=AUTH_USER1)
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == "test@example.com"
    assert data["is_verified"] is True
    assert data["tier"] == "free"


@pytest.mark.asyncio
async def test_auth_no_token(client: AsyncClient):
    r = await client.get("/api/v1/auth/me")
    assert r.status_code in (401, 422)


@pytest.mark.asyncio
async def test_auth_bad_token(client: AsyncClient):
    r = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalid"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_forgot_password(client: AsyncClient):
    r = await client.post("/api/v1/auth/forgot-password", json={"email": "anyone@example.com"})
    assert r.status_code == 200
    assert "reset link" in r.json()["message"].lower()


@pytest.mark.asyncio
async def test_forgot_password_bad_email(client: AsyncClient):
    r = await client.post("/api/v1/auth/forgot-password", json={"email": "not-an-email"})
    assert r.status_code == 422


# ── Unverified user blocked ──


@pytest.mark.asyncio
async def test_unverified_blocked_from_companies(client: AsyncClient):
    r = await client.get("/api/v1/companies", headers=AUTH_UNVERIFIED)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_unverified_blocked_from_outreach(client: AsyncClient):
    r = await client.get("/api/v1/outreach", headers=AUTH_UNVERIFIED)
    assert r.status_code == 403


# ── Companies CRUD ──


@pytest.mark.asyncio
async def test_companies_empty(client: AsyncClient):
    r = await client.get("/api/v1/companies", headers=AUTH_USER1)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_create_and_list_company(client: AsyncClient):
    r = await client.post("/api/v1/companies", headers=AUTH_USER1, json={
        "name": "Acme", "website": "https://acme.com", "location": "NYC", "field": "SaaS",
    })
    assert r.status_code == 200
    assert r.json()["name"] == "Acme"

    r = await client.get("/api/v1/companies", headers=AUTH_USER1)
    assert r.status_code == 200
    names = [c["name"] for c in r.json()]
    assert "Acme" in names


# ── Ownership isolation ──


@pytest.mark.asyncio
async def test_user2_cannot_see_user1_companies(client: AsyncClient):
    # User 1 creates
    await client.post("/api/v1/companies", headers=AUTH_USER1, json={"name": "Secret Corp"})

    # User 2 sees nothing
    r = await client.get("/api/v1/companies", headers=AUTH_USER2)
    assert r.status_code == 200
    names = [c["name"] for c in r.json()]
    assert "Secret Corp" not in names


# ── Outreach CRUD ──


@pytest.mark.asyncio
async def test_outreach_create_and_list(client: AsyncClient):
    r = await client.post("/api/v1/outreach", headers=AUTH_USER1, json={
        "company_name": "Beta Inc",
        "company_website": "https://beta.io",
        "to_email": "ceo@beta.io",
        "subject": "Hello",
        "body": "Let's connect.",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "pending"
    assert data["email"] == "ceo@beta.io"
    outreach_id = data["id"]

    r = await client.get("/api/v1/outreach", headers=AUTH_USER1)
    assert r.status_code == 200
    ids = [o["id"] for o in r.json()["items"]]
    assert outreach_id in ids


@pytest.mark.asyncio
async def test_outreach_update(client: AsyncClient):
    r = await client.post("/api/v1/outreach", headers=AUTH_USER1, json={
        "company_name": "Gamma", "to_email": "a@gamma.io", "subject": "Old", "body": "Old body",
    })
    oid = r.json()["id"]

    r = await client.patch(f"/api/v1/outreach/{oid}", headers=AUTH_USER1, json={"subject": "New Subject"})
    assert r.status_code == 200
    assert r.json()["message_subject"] == "New Subject"


@pytest.mark.asyncio
async def test_outreach_approve_reject(client: AsyncClient):
    r = await client.post("/api/v1/outreach", headers=AUTH_USER1, json={
        "company_name": "Delta", "to_email": "x@delta.io", "subject": "S", "body": "B",
    })
    oid = r.json()["id"]

    r = await client.post(f"/api/v1/outreach/{oid}/approve", headers=AUTH_USER1)
    assert r.status_code == 200
    assert r.json()["status"] == "approved"

    r = await client.post(f"/api/v1/outreach/{oid}/reject", headers=AUTH_USER1)
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"


# ── Outreach ownership ──


@pytest.mark.asyncio
async def test_outreach_ownership_404(client: AsyncClient):
    # User 1 creates
    r = await client.post("/api/v1/outreach", headers=AUTH_USER1, json={
        "company_name": "Private", "to_email": "p@priv.io", "subject": "S", "body": "B",
    })
    oid = r.json()["id"]

    # User 2 can't approve it
    r = await client.post(f"/api/v1/outreach/{oid}/approve", headers=AUTH_USER2)
    assert r.status_code == 404

    # User 2 doesn't see it in their list
    r = await client.get("/api/v1/outreach", headers=AUTH_USER2)
    ids = [o["id"] for o in r.json()["items"]]
    assert oid not in ids


@pytest.mark.asyncio
async def test_outreach_nonexistent_404(client: AsyncClient):
    r = await client.post("/api/v1/outreach/99999/approve", headers=AUTH_USER1)
    assert r.status_code == 404


# ── Request ID header ──


@pytest.mark.asyncio
async def test_request_id_header(client: AsyncClient):
    r = await client.get("/api/v1/auth/me", headers=AUTH_USER1)
    assert "x-request-id" in r.headers
    assert len(r.headers["x-request-id"]) == 12
