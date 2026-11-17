"""Idempotent Neo4j seeder for JokerArena Leaderboard performance tests."""

from __future__ import annotations

import base64
import json
import os
import random
import urllib.error
import urllib.request
from pathlib import Path


def load_env(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        values[k.strip()] = v.strip()
    return values


def cypher(url: str, auth_header: str, statement: str, parameters: dict | None = None) -> dict:
    payload = json.dumps(
        {"statements": [{"statement": statement, "parameters": parameters or {}}]}
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": auth_header,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("errors"):
        raise RuntimeError(f"Neo4j Cypher error: {data['errors']}")
    return data


def main() -> None:
    env = load_env(Path(__file__).resolve().parent / ".env")
    password = os.environ.get("NEO4J_PASSWORD") or env.get("NEO4J_PASSWORD", "jokerarena_perf_2026")
    http_port = os.environ.get("NEO4J_HTTP_PORT") or env.get("NEO4J_HTTP_PORT", "7474")
    tx_url = f"http://localhost:{http_port}/db/neo4j/tx/commit"
    token = base64.b64encode(f"neo4j:{password}".encode("utf-8")).decode("ascii")
    auth_header = f"Basic {token}"

    count_res = cypher(tx_url, auth_header, "MATCH (p:Player) RETURN count(p) AS c")
    existing_players = count_res["results"][0]["data"][0]["row"][0]
    if existing_players >= 25:
        print(f"Neo4j already seeded ({existing_players} players).")
        return

    rng = random.Random(42)
    players = [
        {"player_id": f"perf-p-{i:03d}", "alias": f"JokerPro_{i:02d}"}
        for i in range(1, 31)
    ]

    cypher(
        tx_url,
        auth_header,
        """
        UNWIND $players AS p
        MERGE (pl:Player {player_id: p.player_id})
        SET pl.alias = p.alias, pl.is_bot = false, pl.created_at = coalesce(pl.created_at, datetime())
        """,
        {"players": players},
    )

    matches = []
    for m_idx in range(1, 121):
        p1, p2 = rng.sample(players, 2)
        s1 = rng.randint(8000, 38000)
        s2 = rng.randint(8000, 38000)
        matches.append(
            {
                "match_id": f"perf-m-{m_idx:04d}",
                "room_code": f"JKR-{1000 + m_idx}",
                "p1": p1["player_id"],
                "s1": s1,
                "w1": s1 >= s2,
                "p2": p2["player_id"],
                "s2": s2,
                "w2": s2 > s1,
            }
        )

    cypher(
        tx_url,
        auth_header,
        """
        UNWIND $matches AS m
        MERGE (match:Match {match_id: m.match_id})
        ON CREATE SET match.room_code = m.room_code, match.is_bot_match = false, match.ended_at = datetime()
        WITH match, m
        MATCH (p1:Player {player_id: m.p1}), (p2:Player {player_id: m.p2})
        MERGE (p1)-[r1:PLAYED]->(match)
        SET r1.score = m.s1, r1.won = m.w1
        MERGE (p2)-[r2:PLAYED]->(match)
        SET r2.score = m.s2, r2.won = m.w2
        """,
        {"matches": matches},
    )

    print("Seeded 30 players and 120 matches into Neo4j.")


if __name__ == "__main__":
    main()
