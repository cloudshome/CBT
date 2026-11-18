"""
core/security/__init__.py
=========================
Security and egress governance module for SKY / CBT.
"""

from __future__ import annotations

from core.security.egress_firewall_verifier import OutboundEgressPolicy

__all__ = ["OutboundEgressPolicy"]
