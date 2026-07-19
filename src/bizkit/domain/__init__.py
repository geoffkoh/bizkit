"""Pure domain model for bizkit.

This package holds the business model only: no I/O, no SQLAlchemy, no
FastAPI. Allowed dependencies are the standard library and pydantic. Ports
(protocols implemented by the store and backends) live in
:mod:`bizkit.domain.ports`.
"""
