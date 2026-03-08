"""backend/spatial — Spatial OCR Context Engine package."""
from .spatial_ocr_engine import SpatialOCREngine
from .layout_analyzer import LayoutAnalyzer
from .label_detector import LabelDetector
from .position_embedder import PositionEmbedder
from .template_matcher import TemplateMatcher
from .context_enricher import ContextEnricher

__all__ = [
    "SpatialOCREngine",
    "LayoutAnalyzer",
    "LabelDetector",
    "PositionEmbedder",
    "TemplateMatcher",
    "ContextEnricher",
]
