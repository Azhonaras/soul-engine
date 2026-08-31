"""Shim: all metadata lives in pyproject.toml (PEP 621).

setup.py exists only so legacy tooling (`pip install -e . --no-use-pep517`,
old virtualenv helpers) keeps working. Edit pyproject.toml, not this file.
"""
from setuptools import setup

setup()
