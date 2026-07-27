"""RV-C (CAN) telemetry: spec-driven decoder/encoder and the MQTT bridge.

Per ADR-012, the decode table is the vendored community ``rvc-spec.yml``
(Apache-2.0, see NOTICE); the typed engine around it is ours. Requires the
``rvc`` extra (``pip install astrocyte[rvc]``); the bridge daemon additionally
requires Linux (SocketCAN).
"""

from astrocyte.rvc.decoder import DecodedField, DecodedMessage, RvcDecoder
from astrocyte.rvc.spec import DgnDefinition, ParameterDef, RvcSpec

__all__ = [
    "DecodedField",
    "DecodedMessage",
    "DgnDefinition",
    "ParameterDef",
    "RvcDecoder",
    "RvcSpec",
]
