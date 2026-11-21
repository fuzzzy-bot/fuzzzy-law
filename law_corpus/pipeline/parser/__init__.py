"""Parser sub-package — extracts structured legal content from raw HTML/PDF/DOCX."""

from pipeline.parser.html_parser import HtmlLegalParser
from pipeline.parser.metadata_extractor import MetadataExtractor
from pipeline.parser.structure_extractor import StructureExtractor

__all__ = ["HtmlLegalParser", "StructureExtractor", "MetadataExtractor"]
