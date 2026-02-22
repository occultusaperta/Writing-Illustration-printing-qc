#!/usr/bin/env python3
"""Minimal BookForge demo for internal CLI workflow."""

from pathlib import Path

from bookforge.pipeline import BookforgePipeline


if __name__ == "__main__":
    pipeline = BookforgePipeline()
    sample_story = Path("examples/sample_story.txt")
    if not sample_story.exists():
        sample_story.write_text("A small fox learns to share with friends.", encoding="utf-8")
    print(pipeline.doctor(strict=False))
