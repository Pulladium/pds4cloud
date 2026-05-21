"""
Stub out the kafka-python package so modules that import from `kafka` at the
top level can be loaded without the library being installed.
Only the names actually used by production code are mocked; everything else
resolves to a generic MagicMock.
"""
import sys
from unittest.mock import MagicMock

# Create a stub `kafka` package and the names our code imports from it.
_kafka_stub = MagicMock()
_kafka_stub.KafkaProducer = MagicMock
_kafka_stub.KafkaConsumer = MagicMock

sys.modules.setdefault("kafka", _kafka_stub)

# Stub jobs.pdf_gen only when fpdf is unavailable.
try:
    import fpdf  # noqa: F401
except ImportError:
    _pdf_gen_stub = MagicMock()
    _pdf_gen_stub.generate_pdf_bytes = MagicMock(return_value=b"%PDF-stub")
    _pdf_gen_stub.upload_pdf = MagicMock(return_value="http://stub/report.pdf")
    sys.modules.setdefault("jobs.pdf_gen", _pdf_gen_stub)

# Stub graph_single so image_worker can be imported without langgraph/nodes installed.
_graph_single_stub = MagicMock()
_graph_single_stub.process_product = MagicMock(return_value={"status": "ok"})
sys.modules.setdefault("graph_single", _graph_single_stub)
