"""Starter components for the LPS palette (Change 007 — Bloco C).

Provides a small curated set of pre-built :class:`LpsComponent`s
that the GUI shows the first time the user opens the palette. The
user can drag them straight onto the canvas; they're also useful
as reference examples for LLM-assisted expansion.

Why ship them? Without a starter set, the first-run experience is a
blank palette — confusing. With 5-6 ready-to-use components the user
can build a working feature model in under a minute and discover the
flow.

Idempotency: ``seed_default_components(service)`` checks for each
component by its deterministic UUID; if it exists, it's skipped. Safe
to call on every app start.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.lps_service import LpsService


@dataclass(frozen=True)
class _StarterComponent:
    """A seed row used by :func:`seed_default_components`."""

    id: str
    name: str
    category: str
    description: str
    code_snippet: str | None
    jinja_template: str | None
    metadata: dict[str, object]


# Stable UUIDs (hand-picked so re-running the seed is idempotent).
_STARTERS: tuple[_StarterComponent, ...] = (
    _StarterComponent(
        id="00000000-0000-4000-8000-000000000a01",
        name="FastAPI Service",
        category="service",
        description=(
            "Servidor HTTP baseado em FastAPI com endpoints / e /health "
            "pré-configurados. Use como ponto de partida para qualquer API."
        ),
        code_snippet=None,
        jinja_template="services/fastapi_app.py.j2",
        metadata={
            "tags": ["api", "http", "fastapi"],
            "requirements": ["fastapi>=0.110", "uvicorn>=0.27"],
            "ports": ["8000:8000"],
        },
    ),
    _StarterComponent(
        id="00000000-0000-4000-8000-000000000a02",
        name="CLI Tool",
        category="service",
        description=(
            "Ferramenta de linha de comando com argparse, --version e "
            "subcommand hello. Estenda adicionando novos subparsers via "
            "metadata.extra_subcommands."
        ),
        code_snippet=None,
        jinja_template="services/cli_app.py.j2",
        metadata={
            "tags": ["cli", "tooling"],
            "requirements": [],
        },
    ),
    _StarterComponent(
        id="00000000-0000-4000-8000-000000000a03",
        name="OAuth2 Provider",
        category="architecture",
        description=(
            "Provedor OAuth 2.0 com fluxos authorization_code, "
            "client_credentials e refresh_token. Requer DB."
        ),
        code_snippet=(
            "class OAuth2Provider:\n"
            "    \"\"\"Stub — implementação real vem do componente.\"\"\"\n"
            "    def __init__(self, db):\n"
            "        self.db = db\n"
        ),
        jinja_template=None,
        metadata={
            "tags": ["auth", "oauth", "security"],
            "requires": ["database"],
        },
    ),
    _StarterComponent(
        id="00000000-0000-4000-8000-000000000a04",
        name="JWT Token",
        category="architecture",
        description=(
            "Autenticação stateless via JWT (PyJWT). Requer DB para "
            "refresh-token rotation; exclui Basic Auth."
        ),
        code_snippet=(
            "import jwt\n\n"
            "def issue_token(user_id: str, secret: str) -> str:\n"
            "    return jwt.encode({'sub': user_id}, secret, algorithm='HS256')\n"
        ),
        jinja_template=None,
        metadata={
            "tags": ["auth", "jwt"],
            "requirements": ["pyjwt>=2.8"],
        },
    ),
    _StarterComponent(
        id="00000000-0000-4000-8000-000000000a05",
        name="SQLite Database",
        category="database",
        description=(
            "Banco SQLite local — arquivo único, zero config. Adequado "
            "para apps single-user e protótipos."
        ),
        code_snippet=None,
        jinja_template=None,
        metadata={
            "tags": ["database", "sqlite", "storage"],
            "requirements": [],
        },
    ),
    _StarterComponent(
        id="00000000-0000-4000-8000-000000000a06",
        name="Docker Compose",
        category="infra",
        description=(
            "Stack docker-compose com healthcheck. Gera "
            "docker-compose.yml pronto para docker compose up."
        ),
        code_snippet=None,
        jinja_template="infra/docker_compose.yml.j2",
        metadata={
            "tags": ["docker", "infra", "deployment"],
        },
    ),
    _StarterComponent(
        id="00000000-0000-4000-8000-000000000a07",
        name="Primary Button (UI)",
        category="ui_ux",
        description=(
            "Botão primário reutilizável em React/TSX. Use como bloco "
            "base para CTAs em landing pages."
        ),
        code_snippet=(
            "export function PrimaryButton({ children, onClick }: Props) {\n"
            "  return <button className=\"btn-primary\" onClick={onClick}>{children}</button>;\n"
            "}\n"
        ),
        jinja_template=None,
        metadata={
            "tags": ["ui", "button", "react"],
        },
    ),
    _StarterComponent(
        id="00000000-0000-4000-8000-000000000a08",
        name="Strategy Pattern",
        category="design_pattern",
        description=(
            "Padrão Strategy em Python: define uma família de "
            "algoritmos encapsulados e intercambiáveis."
        ),
        code_snippet=(
            "from abc import ABC, abstractmethod\n\n"
            "class Strategy(ABC):\n"
            "    @abstractmethod\n"
            "    def execute(self, data): ...\n"
        ),
        jinja_template=None,
        metadata={
            "tags": ["patterns", "oop"],
        },
    ),
)


def seed_default_components(service: "LpsService") -> int:
    """Insert starter components if they don't already exist.

    Returns the number of components inserted (0 if all were
    already there). Safe to call on every app start.
    """
    inserted = 0
    for starter in _STARTERS:
        if service.get_component(starter.id) is not None:
            continue
        try:
            service.create_component(
                id=starter.id,
                name=starter.name,
                category=starter.category,
                description=starter.description,
                code_snippet=starter.code_snippet,
                jinja_template=starter.jinja_template,
                metadata=dict(starter.metadata),
            )
            inserted += 1
        except Exception:
            # Inserting a starter is best-effort: if a user has
            # deleted one and we crash on re-create, just skip it.
            continue
    return inserted


def list_starter_uuids() -> list[str]:
    """Return the deterministic UUIDs of the starter set (for tests)."""
    return [s.id for s in _STARTERS]
