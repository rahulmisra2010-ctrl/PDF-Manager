"""backend/ocr — OCR engine package."""
from .ocr_engine import OCREngine
from .confidence_calculator import ConfidenceCalculator
from .heatmap_generator import HeatmapGenerator

__all__ = ["OCREngine", "ConfidenceCalculator", "HeatmapGenerator"]
