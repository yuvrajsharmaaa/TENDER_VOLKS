from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class VerificationResponse:
    status: str
    source: str
    identifier: str
    verified_value: Optional[Any]
    confidence: float
    explanation: str
    evidence: Dict[str, Any]


class BaseVerificationAdapter:
    source = "UNKNOWN"

    def verify(self, identifier: str) -> VerificationResponse:
        raise NotImplementedError


class GSTNVerificationAdapter(BaseVerificationAdapter):
    source = "GSTN"

    # Demo/sandbox registry.
    MOCK_REGISTRY = {
        "07ABCDE1234F1Z5": {
            "legal_name": "Demo Engineering Pvt Ltd",
            "status": "Active",
            "state": "Delhi",
        }
    }

    def verify(self, identifier: str) -> VerificationResponse:
        data = self.MOCK_REGISTRY.get(identifier.upper())

        if not data:
            return VerificationResponse(
                status="NOT_FOUND",
                source=self.source,
                identifier=identifier,
                verified_value=None,
                confidence=0.60,
                explanation="GSTIN was not found in the configured demo verification registry.",
                evidence={
                    "adapter": "GSTNVerificationAdapter",
                    "environment": "DEMO",
                },
            )

        return VerificationResponse(
            status="VERIFIED",
            source=self.source,
            identifier=identifier,
            verified_value=data,
            confidence=0.99,
            explanation="GSTIN verified against the configured GSTN demo registry.",
            evidence={
                "adapter": "GSTNVerificationAdapter",
                "environment": "DEMO",
                "registry_record": data,
            },
        )


class PANVerificationAdapter(BaseVerificationAdapter):
    source = "INCOME_TAX_PAN"

    MOCK_REGISTRY = {
        "ABCDE1234F": {
            "legal_name": "Demo Engineering Pvt Ltd",
            "status": "VALID",
        }
    }

    def verify(self, identifier: str) -> VerificationResponse:
        data = self.MOCK_REGISTRY.get(identifier.upper())

        if not data:
            return VerificationResponse(
                status="NOT_FOUND",
                source=self.source,
                identifier=identifier,
                verified_value=None,
                confidence=0.60,
                explanation="PAN was not found in the configured demo verification registry.",
                evidence={
                    "adapter": "PANVerificationAdapter",
                    "environment": "DEMO",
                },
            )

        return VerificationResponse(
            status="VERIFIED",
            source=self.source,
            identifier=identifier,
            verified_value=data,
            confidence=0.99,
            explanation="PAN verified against the configured Income Tax demo registry.",
            evidence={
                "adapter": "PANVerificationAdapter",
                "environment": "DEMO",
                "registry_record": data,
            },
        )


class UdyamVerificationAdapter(BaseVerificationAdapter):
    source = "UDYAM"

    MOCK_REGISTRY = {
        "UDYAM-DL-01-0012345": {
            "legal_name": "Demo Engineering Pvt Ltd",
            "status": "ACTIVE",
            "msme": True,
        }
    }

    def verify(self, identifier: str) -> VerificationResponse:
        data = self.MOCK_REGISTRY.get(identifier.upper())

        if not data:
            return VerificationResponse(
                status="NOT_FOUND",
                source=self.source,
                identifier=identifier,
                verified_value=None,
                confidence=0.60,
                explanation="Udyam number was not found in the configured demo verification registry.",
                evidence={
                    "adapter": "UdyamVerificationAdapter",
                    "environment": "DEMO",
                },
            )

        return VerificationResponse(
            status="VERIFIED",
            source=self.source,
            identifier=identifier,
            verified_value=data,
            confidence=0.99,
            explanation="Udyam registration verified against the configured demo registry.",
            evidence={
                "adapter": "UdyamVerificationAdapter",
                "environment": "DEMO",
                "registry_record": data,
            },
        )


class MCAVerificationAdapter(BaseVerificationAdapter):
    source = "MCA21"

    MOCK_REGISTRY = {}

    def verify(self, identifier: str) -> VerificationResponse:
        data = self.MOCK_REGISTRY.get(identifier.upper())

        if not data:
            return VerificationResponse(
                status="NOT_CONFIGURED",
                source=self.source,
                identifier=identifier,
                verified_value=None,
                confidence=0.50,
                explanation="MCA21 verification adapter is present but no demo record is configured for this identifier.",
                evidence={
                    "adapter": "MCAVerificationAdapter",
                    "environment": "DEMO",
                },
            )

        return VerificationResponse(
            status="VERIFIED",
            source=self.source,
            identifier=identifier,
            verified_value=data,
            confidence=0.99,
            explanation="CIN verified against the configured MCA21 demo registry.",
            evidence={
                "adapter": "MCAVerificationAdapter",
                "environment": "DEMO",
                "registry_record": data,
            },
        )


class BlacklistVerificationAdapter(BaseVerificationAdapter):
    source = "BLACKLIST_REGISTRY"

    MOCK_BLACKLIST = set()

    def verify(self, identifier: str) -> VerificationResponse:
        blacklisted = identifier.upper() in self.MOCK_BLACKLIST

        return VerificationResponse(
            status="FAILED" if blacklisted else "VERIFIED",
            source=self.source,
            identifier=identifier,
            verified_value={
                "blacklisted": blacklisted,
            },
            confidence=0.95,
            explanation=(
                "Identifier appears in the configured blacklist demo registry."
                if blacklisted
                else "Identifier is clear in the configured blacklist demo registry."
            ),
            evidence={
                "adapter": "BlacklistVerificationAdapter",
                "environment": "DEMO",
                "blacklisted": blacklisted,
            },
        )


class DebarmentVerificationAdapter(BaseVerificationAdapter):
    source = "DEBARMENT_REGISTRY"

    MOCK_DEBARRED = set()

    def verify(self, identifier: str) -> VerificationResponse:
        debarred = identifier.upper() in self.MOCK_DEBARRED

        return VerificationResponse(
            status="FAILED" if debarred else "VERIFIED",
            source=self.source,
            identifier=identifier,
            verified_value={
                "debarred": debarred,
            },
            confidence=0.95,
            explanation=(
                "Identifier appears in the configured debarment demo registry."
                if debarred
                else "Identifier is clear in the configured debarment demo registry."
            ),
            evidence={
                "adapter": "DebarmentVerificationAdapter",
                "environment": "DEMO",
                "debarred": debarred,
            },
        )


def get_adapter(name: str) -> BaseVerificationAdapter:
    adapters = {
        "GSTN": GSTNVerificationAdapter(),
        "PAN": PANVerificationAdapter(),
        "UDYAM": UdyamVerificationAdapter(),
        "MCA": MCAVerificationAdapter(),
        "BLACKLIST": BlacklistVerificationAdapter(),
        "DEBARMENT": DebarmentVerificationAdapter(),
    }

    if name not in adapters:
        raise ValueError(f"Unknown verification adapter: {name}")

    return adapters[name]


def verify_bidder(bidder) -> list[VerificationResponse]:
    results = []

    checks = [
        ("GSTN", getattr(bidder, "gstin", None)),
        ("PAN", getattr(bidder, "pan", None)),
        ("UDYAM", getattr(bidder, "udyam_number", None)),
        ("MCA", getattr(bidder, "cin", None)),
    ]

    for adapter_name, identifier in checks:
        if identifier:
            adapter = get_adapter(adapter_name)
            results.append(adapter.verify(str(identifier)))

    # Use GSTIN as the primary external identity for sanctions checks.
    primary_identifier = (
        getattr(bidder, "gstin", None)
        or getattr(bidder, "pan", None)
        or getattr(bidder, "udyam_number", None)
        or getattr(bidder, "cin", None)
    )

    if primary_identifier:
        results.append(
            get_adapter("BLACKLIST").verify(str(primary_identifier))
        )
        results.append(
            get_adapter("DEBARMENT").verify(str(primary_identifier))
        )

    return results
