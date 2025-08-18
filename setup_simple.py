#!/usr/bin/env python
# Simplified setup.py that doesn't require the requirements module
from setuptools import setup, find_packages

setup(
    name='volttron',
    version='9.0.4',
    packages=find_packages('.'),
    python_requires='>=3.10',
)