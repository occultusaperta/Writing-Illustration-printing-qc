from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class RuntimeOffer:
    provider: str
    offer_id: str
    gpu_name: str
    gpu_count: int
    price_per_hour: float
    region: str
    raw: Dict[str, Any]


@dataclass
class RuntimeInstance:
    provider: str
    instance_id: str
    host: str
    port: int
    ssh_user: str
    status: str
    raw: Dict[str, Any]


class RuntimeProvider(ABC):
    name: str

    @abstractmethod
    def list_offers(self, *, max_hourly_usd: float, min_gpu_ram_gb: int) -> List[RuntimeOffer]:
        raise NotImplementedError

    @abstractmethod
    def create_instance(self, *, offer_id: str, disk_gb: int, image: Optional[str] = None) -> RuntimeInstance:
        raise NotImplementedError

    @abstractmethod
    def stop_instance(self, *, instance_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def destroy_instance(self, *, instance_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def instance_status(self, *, instance_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    def wait_until_running(self, *, instance_id: str, timeout_s: int = 600, poll_interval_s: int = 5) -> Dict[str, Any]:
        """Optional provider hook to block until an instance is running."""
        raise NotImplementedError(f"{self.name} does not implement wait_until_running")
