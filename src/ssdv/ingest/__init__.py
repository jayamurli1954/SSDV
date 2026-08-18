from ssdv.ingest.errors import IngestError
from ssdv.ingest.generic import IngestResult, ingest_generic

INGEST_SOURCES = ("generic",)

__all__ = ["INGEST_SOURCES", "IngestError", "IngestResult", "ingest_generic"]
