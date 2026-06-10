from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from tools.case_api import (
    DEFAULT_BASE_URL,
    DEFAULT_PASSWORD,
    DEFAULT_QDRANT_COLLECTION,
    DEFAULT_QDRANT_URL,
    DEFAULT_SEMANTIC_EMBED_URL,
    DEFAULT_USERNAME,
    DEFAULT_VECTOR_LIMIT,
    DEFAULT_VECTOR_PROJECT_ID,
    DEFAULT_VECTOR_SCORE_THRESHOLD,
    SemanticCaseClient,
)
from tools.knowledge_db import ensure_knowledge_db


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "knowledge" / "knowledge.db"

OPENAPI_CANDIDATES = [
    "/openapi.json",
    "/api/openapi.json",
    "/swagger.json",
    "/api/swagger.json",
    "/v3/api-docs",
    "/api-docs",
]


@dataclass
class TagRecord:
    tag_key: str
    tag_name: str
    tag_type: str
    description: str | None
    aliases: list[str]


def load_tags(conn: sqlite3.Connection) -> list[TagRecord]:
    rows = conn.execute(
        "SELECT tag_key, tag_name, tag_type, description, aliases FROM tags ORDER BY tag_type, tag_key"
    ).fetchall()
    tags: list[TagRecord] = []
    for row in rows:
        aliases = json.loads(row[4] or "[]")
        tags.append(TagRecord(row[0], row[1], row[2], row[3], aliases))
    return tags


def normalize_text(text: str) -> str:
    return text.lower().strip()


def infer_tags(text: str, tags: list[TagRecord]) -> list[dict[str, Any]]:
    normalized = normalize_text(text)
    scored: list[dict[str, Any]] = []
    for tag in tags:
        score = 0.0
        candidates = [tag.tag_name, tag.tag_key]
        candidates.extend(tag.aliases)
        if tag.description:
            candidates.append(tag.description)
        for candidate in candidates:
            token = normalize_text(str(candidate))
            if token and token in normalized:
                score += 1.0
        if score > 0:
            scored.append(
                {
                    "tag_key": tag.tag_key,
                    "tag_name": tag.tag_name,
                    "tag_type": tag.tag_type,
                    "score": score,
                }
            )
    scored.sort(key=lambda item: (-item["score"], item["tag_key"]))
    return scored


def fetch_knowledge_by_tags(conn: sqlite3.Connection, tag_keys: list[str]) -> list[dict[str, Any]]:
    if not tag_keys:
        return []
    placeholders = ",".join("?" for _ in tag_keys)
    query = f"""
    SELECT l.tag_key, l.target_type, l.target_id, l.weight
    FROM knowledge_tag_links l
    WHERE l.tag_key IN ({placeholders})
    ORDER BY l.weight DESC, l.target_type, l.target_id
    """
    links = conn.execute(query, tag_keys).fetchall()
    results: list[dict[str, Any]] = []
    for tag_key, target_type, target_id, weight in links:
        table = target_type
        row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (target_id,)).fetchone()
        if not row:
            continue
        columns = [col[1] for col in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        record = dict(zip(columns, row))
        results.append(
            {
                "tag_key": tag_key,
                "target_type": target_type,
                "target_id": target_id,
                "weight": weight,
                "record": record,
            }
        )
    return results


def discover_openapi(base_url: str, username: str | None, password: str | None) -> dict[str, Any]:
    auth = (username, password) if username and password else None
    with httpx.Client(timeout=10.0, auth=auth, follow_redirects=True) as client:
        attempts: list[dict[str, Any]] = []
        for path in OPENAPI_CANDIDATES:
            url = f"{base_url.rstrip('/')}{path}"
            try:
                response = client.get(url)
                content_type = response.headers.get("content-type", "")
                payload: Any
                is_openapi = False
                if "json" in content_type:
                    payload = response.json()
                    is_openapi = isinstance(payload, dict) and ("openapi" in payload or "swagger" in payload)
                else:
                    payload = response.text[:400]
                attempts.append(
                    {
                        "url": url,
                        "status_code": response.status_code,
                        "content_type": content_type,
                        "is_openapi": is_openapi,
                    }
                )
                if is_openapi:
                    return {
                        "found": True,
                        "url": url,
                        "attempts": attempts,
                        "spec": payload,
                    }
            except Exception as exc:  # pragma: no cover
                attempts.append({"url": url, "error": str(exc), "is_openapi": False})
        return {"found": False, "attempts": attempts}


def filter_openapi(spec: dict[str, Any], query_text: str, tag_keys: list[str]) -> dict[str, Any]:
    paths = spec.get("paths", {})
    normalized = normalize_text(query_text)
    matched_paths: list[dict[str, Any]] = []
    keywords = [normalize_text(tag) for tag in tag_keys]
    for path, methods in paths.items():
        haystack = normalize_text(path + " " + json.dumps(methods, ensure_ascii=False))
        score = 0
        if path.lower() in normalized:
            score += 2
        for keyword in keywords:
            if keyword and keyword.split(".")[-1] in haystack:
                score += 1
        for token in normalized.split():
            if token and token in haystack:
                score += 1
        if score > 0:
            matched_paths.append({"path": path, "score": score, "methods": methods})
    matched_paths.sort(key=lambda item: (-item["score"], item["path"]))
    return {"matched_paths": matched_paths[:20], "total_matches": len(matched_paths)}


def build_questions(query_text: str, matched_tags: list[dict[str, Any]], openapi_found: bool) -> list[str]:
    questions: list[str] = []
    normalized = normalize_text(query_text)
    if "分组" not in normalized and "group" not in normalized:
        questions.append("当前需求对应哪个分组或模块路径？")
    if "优先级" not in normalized and "p1" not in normalized and "p2" not in normalized and "p3" not in normalized:
        questions.append("这批用例的优先级是否有明确口径，例如默认 P1/P2/P3？")
    if not any(tag["tag_key"].startswith("module.") for tag in matched_tags):
        questions.append("当前需求更偏向用例列表、分组、列定义还是专题评审？")
    if not openapi_found:
        questions.append("当前地址未发现可直接访问的 OpenAPI JSON，是否有准确的 spec 地址或文档入口？")
    return questions


def resolve_context(args: argparse.Namespace) -> dict[str, Any]:
    with sqlite3.connect(DB_PATH) as conn:
        tags = load_tags(conn)
        matched_tags = infer_tags(args.query, tags)
        tag_keys = [item["tag_key"] for item in matched_tags[:8]]
        knowledge = fetch_knowledge_by_tags(conn, tag_keys)

    semantic_cases: dict[str, Any] | None = None
    semantic_error: str | None = None
    if not args.no_semantic:
        try:
            semantic_client = SemanticCaseClient(
                embed_url=args.semantic_embed_url,
                qdrant_url=args.qdrant_url,
                collection=args.qdrant_collection,
                project_id=args.vector_project_id,
                score_threshold=args.vector_score_threshold,
            )
            semantic_cases = semantic_client.search(args.query, limit=args.semantic_limit)
        except Exception as exc:
            semantic_error = str(exc)

    openapi_result = discover_openapi(args.base_url, args.username, args.password)
    openapi_summary: dict[str, Any]
    if openapi_result["found"]:
        openapi_summary = filter_openapi(openapi_result["spec"], args.query, tag_keys)
        openapi_summary["url"] = openapi_result["url"]
        openapi_summary["attempts"] = openapi_result["attempts"]
    else:
        openapi_summary = {"url": None, "matched_paths": [], "total_matches": 0, "attempts": openapi_result["attempts"]}

    questions = build_questions(args.query, matched_tags, openapi_result["found"])
    return {
        "workflow": [
            "理解需求",
            "按标签检索本地知识库",
            "发现候选接口并过滤相关 OpenAPI 信息",
            "识别缺口和偏差",
            "向用户追问关键信息",
        ],
        "input_query": args.query,
        "matched_tags": matched_tags,
        "knowledge_hits": knowledge,
        "semantic_case_candidates": semantic_cases,
        "semantic_case_error": semantic_error,
        "openapi": openapi_summary,
        "follow_up_questions": questions,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resolve agent context from query, tags, and OpenAPI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    tags_parser = subparsers.add_parser("infer-tags", help="Infer tags from a natural-language query")
    tags_parser.add_argument("--query", required=True)

    resolve_parser = subparsers.add_parser("resolve", help="Resolve knowledge and OpenAPI context for a query")
    resolve_parser.add_argument("--query", required=True)
    resolve_parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    resolve_parser.add_argument("--username", default=DEFAULT_USERNAME)
    resolve_parser.add_argument("--password", default=DEFAULT_PASSWORD)
    resolve_parser.add_argument("--no-semantic", action="store_true")
    resolve_parser.add_argument("--semantic-limit", type=int, default=DEFAULT_VECTOR_LIMIT)
    resolve_parser.add_argument("--semantic-embed-url", default=DEFAULT_SEMANTIC_EMBED_URL)
    resolve_parser.add_argument("--qdrant-url", default=DEFAULT_QDRANT_URL)
    resolve_parser.add_argument("--qdrant-collection", default=DEFAULT_QDRANT_COLLECTION)
    resolve_parser.add_argument("--vector-project-id", default=DEFAULT_VECTOR_PROJECT_ID)
    resolve_parser.add_argument("--vector-score-threshold", type=float, default=DEFAULT_VECTOR_SCORE_THRESHOLD)

    return parser


def main() -> None:
    ensure_knowledge_db()
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "infer-tags":
        with sqlite3.connect(DB_PATH) as conn:
            tags = load_tags(conn)
            print(json.dumps(infer_tags(args.query, tags), ensure_ascii=False, indent=2))
        return
    if args.command == "resolve":
        print(json.dumps(resolve_context(args), ensure_ascii=False, indent=2))
        return
    raise RuntimeError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
