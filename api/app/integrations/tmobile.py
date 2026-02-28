"""T-Mobile carrier SIM management client."""

from __future__ import annotations

from typing import Any

from app.integrations.base import BaseProviderClient


class TMobileClient(BaseProviderClient):
    provider_name = "tmobile"
    base_url = "https://api.t-mobile.com/iot/v1"

    def _auth_headers(self) -> dict[str, str]:
        # T-Mobile uses API key in a custom header
        return {"X-API-Key": self.api_key}

    # ── SIM Lifecycle ────────────────────────────────────────────

    async def activate_sim(self, iccid: str, plan: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"iccid": iccid}
        if plan:
            payload["plan"] = plan
        return await self.post("/sims/activate", json=payload)

    async def suspend_sim(self, iccid: str) -> dict[str, Any]:
        return await self.post("/sims/suspend", json={"iccid": iccid})

    async def resume_sim(self, iccid: str) -> dict[str, Any]:
        return await self.post("/sims/resume", json={"iccid": iccid})

    async def get_sim_status(self, iccid: str) -> dict[str, Any]:
        return await self.get(f"/sims/{iccid}")

    # ── Usage ────────────────────────────────────────────────────

    async def get_usage(self, iccid: str, **params: Any) -> dict[str, Any]:
        return await self.get(f"/sims/{iccid}/usage", params=params)
