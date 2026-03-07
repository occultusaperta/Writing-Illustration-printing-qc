from pathlib import Path

from PIL import Image

from bookforge.qc.visual_integrity import _load_rgb


def test_load_rgb_downsamples_large_images_for_qc(tmp_path: Path):
    img = tmp_path / "large.png"
    Image.new("RGB", (4000, 3000), (128, 128, 128)).save(img)
    arr = _load_rgb(img)
    assert max(arr.shape[0], arr.shape[1]) <= 320
