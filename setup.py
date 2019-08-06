#!/usr/bin/env python

from setuptools import setup

setup(
    use_scm_version=True,
    name="sstable_tools",
    description="Scylla SStable Tools",
    packages=["sstable_tools"],
    scripts=[
        "sstable-compressioninfo.py",
        "sstable-index.py",
        "sstable-statistics.py",
        "sstable-summary.py",
    ],
)
