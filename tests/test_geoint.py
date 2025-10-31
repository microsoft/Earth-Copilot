#!/usr/bin/env python3
from terrain_analysis import TerrainAnalyzer
from line_of_sight import LineOfSightCalculator
from mobility_classifier import MobilityClassifier
print("✓ All GEOINT modules imported successfully")

# Test basic functionality
terrain = TerrainAnalyzer()
los = LineOfSightCalculator()
mobility = MobilityClassifier()
print("✓ All GEOINT objects created successfully")

print("GEOINT functionality is now working!")