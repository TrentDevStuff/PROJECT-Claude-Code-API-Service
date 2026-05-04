"""Claude Code API Service CLI"""

__version__ = "0.2.0"

# Version history (in reverse chronological order):
#
# 0.2.0 — 2026-05-04
#   Catch-up bump covering Phase 4c + LLM resilience work shipped on
#   feature branches between 0.1.0 and now. Server-side observability
#   surface expanded; CLI surface unchanged.
#   * feat(phase-4c): forgg-observability v0.3.0 telemetry init [Step 1, 10bcfe9]
#   * feat(phase-4c): forgg.cca_request_id span attr + X-Forgg-CCA-Request-Id
#     response header for ACA↔CCA attribute correlation [Step 2, ae83653]
#   * feat: prompt caching on SDK tool-passthrough path [4da3e92]
#   * fix: CircuitBreaker.status() reentrant-lock deadlock [1840e27]
#   * docs+feat: /v1/process routing precedence [76efd36]
#
# 0.1.0 — 2026-01-31
#   Initial CLI release.
