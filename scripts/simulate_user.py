#!/usr/bin/env python3
"""Replay a persona's scripted event sequence against a real profile.

Powers `make simulate PERSONA=macro` and is the same replay path the
"View as" switcher uses server-side (app/attention/personas.py) — this
script exists so a persona's resulting layout/vector can be inspected from
the command line without going through the API, e.g. to eyeball a new
persona's event script before wiring it into the frontend.

Run with apps/api's venv (has asyncpg/pydantic/pyyaml): from the repo root,
    apps/api/.venv/bin/python scripts/simulate_user.py --persona macro
"""

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.attention.layout import compute_layout  # noqa: E402
from app.attention.personas import list_personas, load_persona, replay_persona  # noqa: E402
from app.attention.service import get_scores  # noqa: E402
from app.attention.taxonomy import load_taxonomy  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import create_pool, init_schema  # noqa: E402


async def main(persona_name: str, keep: bool) -> None:
    settings = get_settings()
    pool = await create_pool(settings)
    await init_schema(pool)
    taxonomy = load_taxonomy()
    persona = load_persona(persona_name)
    profile_id = uuid.uuid4()

    async with pool.acquire() as conn:
        await replay_persona(conn, taxonomy, profile_id, persona)
        vector = await get_scores(conn, profile_id)
        layout = compute_layout(vector)
        if not keep:
            await conn.execute("DELETE FROM profiles WHERE id = $1", profile_id)

    await pool.close()

    print(f"persona: {persona.name} — {persona.description}")
    print(f"profile_id: {profile_id}{'' if keep else ' (discarded — pass --keep to persist)'}")
    print("\nvector:")
    print(json.dumps(vector, indent=2, sort_keys=True))
    print("\nlayout:")
    print(layout.model_dump_json(indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--persona",
        required=True,
        choices=[p.name for p in list_personas()],
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="persist the simulated profile instead of deleting it afterward",
    )
    args = parser.parse_args()
    asyncio.run(main(args.persona, args.keep))
