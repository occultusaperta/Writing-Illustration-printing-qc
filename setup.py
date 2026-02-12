"""Setup script for BookForge"""
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="bookforge",
    version="0.1.0",
    author="BookForge Contributors",
    description="A minimal pipeline for creating KDP-ready children's books",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    package_data={
        "bookforge": [
            "knowledge/*.json",
        ],
    },
    include_package_data=True,
    install_requires=requirements,
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "bookforge=bookforge.__main__:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
