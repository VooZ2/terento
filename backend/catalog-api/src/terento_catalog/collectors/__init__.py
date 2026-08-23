"""Metadata collectors for map and Garmin device catalogs."""

from .freizeitkarte.collector import FreizeitkarteCollector
from .garmin.collector import GarminCollector

__all__ = ["FreizeitkarteCollector", "GarminCollector"]
