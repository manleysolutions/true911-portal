"""VolaCloud / Flying Voice hardware provisioning client."""

from __future__ import annotations

from typing import Any

from app.integrations.base import BaseProviderClient


class VolaClient(BaseProviderClient):
    provider_name = "vola"
    base_url = "https://api.volacloud.com/v1"

    # ── Device Provisioning ──────────────────────────────────────

    async def provision_device(
        self,
        mac_address: str,
        template_id: str,
        *,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "mac_address": mac_address,
            "template_id": template_id,
        }
        if config:
            payload["config"] = config
        return await self.post("/devices", json=payload)

    async def get_device_status(self, device_id: str) -> dict[str, Any]:
        return await self.get(f"/devices/{device_id}")

    async def update_device_config(
        self, device_id: str, config: dict[str, Any]
    ) -> dict[str, Any]:
        return await self.patch(f"/devices/{device_id}", json={"config": config})

    async def reboot_device(self, device_id: str) -> dict[str, Any]:
        return await self.post(f"/devices/{device_id}/actions/reboot")
