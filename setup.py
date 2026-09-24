#!/usr/bin/env python3
from setuptools import setup

setup(
    name="calysta-data-export",
    version="0.1.0",
    description="Bulk export of Calysta Pro EMR patient records",
    py_modules=["run_export", "watch_export_cli"],
    python_requires=">=3.8",
    install_requires=["playwright", "pyyaml", "aiofiles"],
    entry_points={
        "console_scripts": [
            "run-export=run_export:main",
            "watch-export=watch_export_cli:main",
        ],
    },
)
