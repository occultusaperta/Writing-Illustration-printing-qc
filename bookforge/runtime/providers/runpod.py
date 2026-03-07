from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

import requests

from bookforge.runtime.providers.base import RuntimeInstance, RuntimeOffer, RuntimeProvider


class RunPodRuntimeProvider(RuntimeProvider):
    """RunPod runtime provider using RunPod's HTTP GraphQL endpoint."""

    name = "runpod"

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self.api_key = (api_key or os.getenv("RUNPOD_API_KEY") or "").strip()
        self.base_url = (base_url or os.getenv("BOOKFORGE_RUNPOD_API_URL") or "https://api.runpod.io").rstrip("/")
        if not self.api_key:
            raise RuntimeError("Missing RUNPOD_API_KEY for runtime provider runpod.")

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _graphql(self, query: str) -> Dict[str, Any]:
        url = f"{self.base_url}/graphql"
        resp = requests.post(url, headers=self._headers(), data=json.dumps({"query": query}), timeout=60)
        resp.raise_for_status()
        payload = resp.json() if resp.content else {}
        errors = payload.get("errors") or []
        if errors:
            raise RuntimeError(f"RunPod API error: {errors[0].get('message', errors[0])}")
        return payload.get("data", {})

    def list_offers(self, *, max_hourly_usd: float, min_gpu_ram_gb: int) -> List[RuntimeOffer]:
        query = """
        query GpuTypes {
          gpuTypes {
            id
            displayName
            memoryInGb
            lowestPrice(input: {gpuCount: 1}) {
              uninterruptablePrice
              minimumBidPrice
            }
          }
        }
        """
        data = self._graphql(query)
        offers: List[RuntimeOffer] = []
        for item in data.get("gpuTypes", []):
            price = float((item.get("lowestPrice") or {}).get("uninterruptablePrice") or 0.0)
            mem = int(item.get("memoryInGb") or 0)
            if mem < min_gpu_ram_gb:
                continue
            if max_hourly_usd > 0 and price and price > max_hourly_usd:
                continue
            offers.append(
                RuntimeOffer(
                    provider=self.name,
                    offer_id=str(item.get("id") or ""),
                    gpu_name=str(item.get("displayName") or "unknown"),
                    gpu_count=1,
                    price_per_hour=price,
                    region="global",
                    raw=item,
                )
            )
        return [o for o in offers if o.offer_id]

    def find_gpu_type_id(self, *, gpu_display_name: str = "NVIDIA B200") -> str:
        offers = self.list_offers(max_hourly_usd=0, min_gpu_ram_gb=0)
        for offer in offers:
            if offer.gpu_name.strip().lower() == gpu_display_name.strip().lower():
                return offer.offer_id
        raise RuntimeError(f"RunPod GPU type not found: {gpu_display_name}")

    def build_create_payload(self, *, gpu_type_id: str, disk_gb: int, image: str, service_port: int) -> Dict[str, Any]:
        return {
            "name": os.getenv("BOOKFORGE_RUNTIME_NAME", "bookforge-runtime"),
            "imageName": image,
            "gpuTypeId": gpu_type_id,
            "cloudType": "ALL",
            "supportPublicIp": True,
            "startSsh": True,
            "gpuCount": 1,
            "containerDiskInGb": int(disk_gb),
            "ports": f"22/tcp,{int(service_port)}/http",
        }

    def _create_mutation(self, payload: Dict[str, Any]) -> str:
        return f"""
        mutation CreatePod {{
          podFindAndDeployOnDemand(input: {{
            name: \"{payload['name']}\"
            imageName: \"{payload['imageName']}\"
            gpuTypeId: \"{payload['gpuTypeId']}\"
            cloudType: {payload['cloudType']}
            supportPublicIp: {str(payload['supportPublicIp']).lower()}
            startSsh: {str(payload['startSsh']).lower()}
            gpuCount: {int(payload['gpuCount'])}
            containerDiskInGb: {int(payload['containerDiskInGb'])}
            ports: \"{payload['ports']}\"
            dataCenterId: null
          }}) {{
            id
            desiredStatus
            machine {{ podHostId }}
          }}
        }}
        """

    def create_instance(self, *, offer_id: str, disk_gb: int, image: Optional[str] = None) -> RuntimeInstance:
        service_port = int(os.getenv("BOOKFORGE_RUNTIME_SERVICE_PORT") or "8188")
        resolved_image = image or os.getenv("BOOKFORGE_RUNTIME_IMAGE", "pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime")
        gpu_type_id = offer_id or self.find_gpu_type_id(gpu_display_name=os.getenv("BOOKFORGE_RUNPOD_GPU_NAME", "NVIDIA B200"))
        payload = self.build_create_payload(gpu_type_id=gpu_type_id, disk_gb=disk_gb, image=resolved_image, service_port=service_port)
        data = self._graphql(self._create_mutation(payload))
        pod = data.get("podFindAndDeployOnDemand") or {}
        instance_id = str(pod.get("id") or "")
        if not instance_id:
            raise RuntimeError(f"Unexpected RunPod create response: {data}")

        status_data = self.wait_until_running(instance_id=instance_id)
        ssh = self.extract_ssh_connection(status_data)

        return RuntimeInstance(
            provider=self.name,
            instance_id=instance_id,
            host=ssh["host"],
            port=ssh["port"],
            ssh_user=ssh["ssh_user"],
            status=str((status_data.get("pod") or {}).get("desiredStatus") or "running"),
            raw={"create": data, "status": status_data},
        )

    def _pod_query(self, pod_id: str) -> str:
        return f"""
        query PodStatus {{
          pod(input: {{podId: \"{pod_id}\"}}) {{
            id
            desiredStatus
            runtime {{
              ports {{
                ip
                isIpPublic
                privatePort
                publicPort
                type
              }}
            }}
            machine {{ gpuDisplayName }}
          }}
        }}
        """

    def instance_status(self, *, instance_id: str) -> Dict[str, Any]:
        data = self._graphql(self._pod_query(instance_id))
        return {"pod": data.get("pod")}

    def wait_until_running(self, *, instance_id: str, timeout_s: int = 900, poll_interval_s: int = 5) -> Dict[str, Any]:
        deadline = time.time() + timeout_s
        last: Dict[str, Any] = {}
        while time.time() < deadline:
            last = self.instance_status(instance_id=instance_id)
            desired = str((last.get("pod") or {}).get("desiredStatus") or "").upper()
            ssh = self.extract_ssh_connection(last)
            if desired in {"RUNNING", "RESUMED", "READY"} and ssh.get("host"):
                return last
            time.sleep(poll_interval_s)
        raise RuntimeError(f"RunPod pod did not reach running state in {timeout_s}s: {last}")

    def extract_ssh_connection(self, status_payload: Dict[str, Any]) -> Dict[str, Any]:
        pod = status_payload.get("pod") or {}
        runtime = pod.get("runtime") or {}
        ports = runtime.get("ports") or []
        for port in ports:
            if int(port.get("privatePort") or 0) == 22:
                host = str(port.get("ip") or "").strip()
                public_port = int(port.get("publicPort") or 22)
                if host:
                    return {"host": host, "port": public_port, "ssh_user": os.getenv("BOOKFORGE_RUNTIME_SSH_USER", "root")}
        return {"host": "", "port": 22, "ssh_user": os.getenv("BOOKFORGE_RUNTIME_SSH_USER", "root")}

    def stop_instance(self, *, instance_id: str) -> Dict[str, Any]:
        query = f"""
        mutation StopPod {{
          podStop(input: {{ podId: \"{instance_id}\" }}) {{
            id
            desiredStatus
          }}
        }}
        """
        data = self._graphql(query)
        return data.get("podStop") or {}

    def destroy_instance(self, *, instance_id: str) -> Dict[str, Any]:
        query = f"""
        mutation TerminatePod {{
          podTerminate(input: {{ podId: \"{instance_id}\" }})
        }}
        """
        data = self._graphql(query)
        return {"terminated": data.get("podTerminate")}
