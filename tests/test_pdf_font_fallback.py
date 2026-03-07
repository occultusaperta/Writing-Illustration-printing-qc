from pathlib import Path

import bookforge.layout.pdf as pdf_mod


def test_pdf_layout_engine_falls_back_to_helvetica_on_invalid_ttf(monkeypatch):
    def _raise(*args, **kwargs):
        raise RuntimeError("invalid font")

    monkeypatch.setattr(pdf_mod, "TTFont", _raise)
    engine = pdf_mod.PDFLayoutEngine(Path("assets/fonts/NotoSans-Regular.ttf"))

    assert engine.font_name == "Helvetica"
    assert "falling back to Helvetica" in engine.font_fallback_reason
