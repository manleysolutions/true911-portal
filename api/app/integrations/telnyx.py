"""Telnyx provider client — SIP trunking, SIM management, DID ordering."""

from __future__ import annotations

from typing import Any

from app.integrations.base import BaseProviderClient


class TelnyxClient(BaseProviderClient):
    provider_name = "telnyx"
    base_url = "https://api.telnyx.com/v2"

    # ── SIM Management ───────────────────────────────────────────

    async def activate_sim(self, sim_card_id: str) -> dict[str, Any]:
        return await self.post(f"/sim_cards/{sim_card_id}/actions/enable")

    async def deactivate_sim(self, sim_card_id: str) -> dict[str, Any]:
        return await self.post(f"/sim_cards/{sim_card_id}/actions/disable")

    async def get_sim_status(self, sim_card_id: str) -> dict[str, Any]:
        return await self.get(f"/sim_cards/{sim_card_id}")

    # ── DID / Phone Numbers ──────────────────────────────────────

    async def order_phone_number(self, phone_number: str, connection_id: str) -> dict[str, Any]:
        return await self.post("/number_orders", json={
            "phone_numbers": [{"phone_number": phone_number}],
            "connection_id": connection_id,
        })

    async def list_phone_numbers(self, **params: Any) -> dict[str, Any]:
        return await self.get("/phone_numbers", params=params)

    # ── E911 ─────────────────────────────────────────────────────

    async def provision_e911(
        self,
        phone_number_id: str,
        street: str,
        city: str,
        state: str,
        postal_code: str,
        caller_name: str,
    ) -> dict[str, Any]:
        return await self.post("/emergency_addresses", json={
            "phone_number_id": phone_number_id,
            "street_address": street,
            "locality": city,
            "administrative_area": state,
            "postal_code": postal_code,
            "caller_name": caller_name,
            "country_code": "US",
        })
