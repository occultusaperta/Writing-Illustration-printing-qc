from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Protocol


class ImageProvider(Protocol):
    name: str

    def generate_option_image(self, prompt: str, out_path: Path, image_size_px: tuple[int, int], steps: int = 4) -> None:
        ...

    def generate_page_variants(
        self,
        page_prompts: List[Dict[str, Any]],
        variants_dir: Path,
        image_size_px: tuple[int, int],
        variants: int = 2,
        reference_image: Path | None = None,
        style_image: Path | None = None,
        palette_tile: Path | None = None,
        steps: int = 4,
        seeds: Dict[int, int] | None = None,
        cache_dir: Path | None = None,
        reference_images: List[Path] | None = None,
    ) -> Dict[str, Any]:
        ...

    def build_composite_reference(self, character_img: Path, style_img: Path, out_path: Path, palette_tile: Path | None = None) -> Path:
        ...
