from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests

from bookforge.runtime.providers.base import RuntimeInstance, RuntimeOffer, RuntimeProvider


class VastAIRuntimeProvider(RuntimeProvider):
    name = "vast_ai"

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self.api_key = (api_key or os.getenv("BOOKFORGE_VAST_API_KEY") or "").strip()
        self.base_url = (base_url or os.getenv("BOOKFORGE_VAST_API_URL") or "https://console.vast.ai/api/v0").rstrip("/")
        if not self.api_key:
            raise RuntimeError("Missing BOOKFORGE_VAST_API_KEY for runtime provider vast_ai.")

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _request(self, method: str, path: str, *, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        resp = requests.request(method, url, headers=self._headers(), json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    def build_search_payload(self, *, max_hourly_usd: float, min_gpu_ram_gb: int) -> Dict[str, Any]:
        # Payload format aligns to Vast filter API. Keep explicit for testability.
        return {
            "verified": {"eq": True},
            "external": {"eq": False},
            "rentable": {"eq": True},
            "dph_total": {"lte": float(max_hourly_usd)},
            "gpu_ram": {"gte": int(min_gpu_ram_gb)},
            "order": [["dph_total", "asc"]],
        }

    def list_offers(self, *, max_hourly_usd: float, min_gpu_ram_gb: int) -> List[RuntimeOffer]:
        payload = self.build_search_payload(max_hourly_usd=max_hourly_usd, min_gpu_ram_gb=min_gpu_ram_gb)
        data = self._request("POST", "/bundles/", payload=payload)
        offers_raw = data.get("offers", data if isinstance(data, list) else [])
        offers: List[RuntimeOffer] = []
        for item in offers_raw:
            offers.append(
                RuntimeOffer(
                    provider=self.name,
                    offer_id=str(item.get("id") or item.get("ask_contract_id") or ""),
                    gpu_name=str(item.get("gpu_name", "unknown")),
                    gpu_count=int(item.get("num_gpus", 1)),
                    price_per_hour=float(item.get("dph_total", item.get("dph", 0.0))),
                    region=str(item.get("geolocation", "unknown")),
                    raw=item,
                )
            )
        return [o for o in offers if o.offer_id]

    def build_create_payload(self, *, offer_id: str, disk_gb: int, image: Optional[str] = None) -> Dict[str, Any]:
        return {
            "ask_id": int(offer_id),
            "image": image or os.getenv("BOOKFORGE_RUNTIME_IMAGE", "pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime"),
            "disk": int(disk_gb),
            "ssh": True,
            "jupyter": False,
            "direct_port_count": 2,
        }

    def create_instance(self, *, offer_id: str, disk_gb: int, image: Optional[str] = None) -> RuntimeInstance:
        payload = self.build_create_payload(offer_id=offer_id, disk_gb=disk_gb, image=image)
        data = self._request("PUT", "/asks/create/", payload=payload)
        host = str(data.get("ssh_host") or data.get("public_ipaddr") or "")
        port = int(data.get("ssh_port", 22))
        ssh_user = str(data.get("ssh_user") or os.getenv("BOOKFORGE_RUNTIME_SSH_USER", "root"))
        instance_id = str(data.get("new_contract") or data.get("id") or "")
        if not host or not instance_id:
            raise RuntimeError(f"Unexpected vast.ai create response: {data}")
        return RuntimeInstance(
            provider=self.name,
            instance_id=instance_id,
            host=host,
            port=port,
            ssh_user=ssh_user,
            status=str(data.get("actual_status", "running")),
            raw=data,
        )

    def stop_instance(self, *, instance_id: str) -> Dict[str, Any]:
        return self._request("PUT", f"/instances/{instance_id}/stop/")

    def destroy_instance(self, *, instance_id: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/instances/{instance_id}/")

    def instance_status(self, *, instance_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/instances/{instance_id}/")
