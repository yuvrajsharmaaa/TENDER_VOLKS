"""
Root alias for backend.app.services.pqr_credential_matcher.
Provides direct access to CandidateCredential, PqcMatchResult, compute_thresholds,
is_within_window, normalize_scope, and match_credentials.
"""

from backend.app.services.pqr_credential_matcher import (
    CandidateCredential,
    PqcMatchResult,
    compute_thresholds,
    is_within_window,
    has_valid_document,
    normalize_scope,
    match_credentials,
)

__all__ = [
    "CandidateCredential",
    "PqcMatchResult",
    "compute_thresholds",
    "is_within_window",
    "has_valid_document",
    "normalize_scope",
    "match_credentials",
]
