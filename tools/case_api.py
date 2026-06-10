from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import httpx


def load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


load_dotenv()

DEFAULT_BASE_URL = os.getenv("CASE_API_BASE_URL", "http://192.168.26.181:10094/")
DEFAULT_USERNAME = os.getenv("CASE_API_USERNAME", "reporter")
DEFAULT_PASSWORD = os.getenv("CASE_API_PASSWORD", "reporter")
DEFAULT_SEMANTIC_EMBED_URL = os.getenv("CASE_SEMANTIC_EMBED_URL", "http://192.168.26.181:18001")
DEFAULT_QDRANT_URL = os.getenv("CASE_QDRANT_URL", "http://192.168.26.181:16333")
DEFAULT_QDRANT_COLLECTION = os.getenv("CASE_QDRANT_COLLECTION", "test_project_semantics")
DEFAULT_VECTOR_PROJECT_ID = os.getenv("CASE_VECTOR_PROJECT_ID", "l4-software")
DEFAULT_VECTOR_SCORE_THRESHOLD = float(os.getenv("CASE_VECTOR_SCORE_THRESHOLD", "0.55"))
DEFAULT_VECTOR_LIMIT = int(os.getenv("CASE_VECTOR_DEFAULT_LIMIT", "50"))


class CaseApiClient:
    def __init__(self, base_url: str, username: str, password: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.client = httpx.Client(timeout=timeout)
        self.token: str | None = None

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def login(self) -> None:
        password_hash = hashlib.sha256(self.password.encode("utf-8")).hexdigest()
        payload = {
            "username": self.username,
            "password_hash": password_hash,
        }
        response = self.client.post(self._url("/api/v1/auth/login"), json=payload)
        response.raise_for_status()
        data = _extract_payload_data(response.json())
        token = data.get("token") or data.get("access_token")
        if not token:
            raise RuntimeError("Login succeeded but token was not found in payload.data")
        self.token = token
        self.client.headers["Authorization"] = f"Bearer {token}"

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.token:
            self.login()
        response = self.client.get(self._url(path), params=params)
        response.raise_for_status()
        return response.json()

    def post(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.token:
            self.login()
        response = self.client.post(self._url(path), json=payload or {})
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"{exc} response={response.text}") from exc
        return response.json()

    def patch(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.token:
            self.login()
        response = self.client.patch(self._url(path), json=payload or {})
        response.raise_for_status()
        return response.json()

    def delete(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.token:
            self.login()
        response = self.client.request("DELETE", self._url(path), json=payload or {})
        response.raise_for_status()
        return response.json()

    def fetch_columns(self) -> dict[str, Any]:
        return self.get("/api/v1/case-columns")

    def fetch_groups(self, tree: bool = True, with_case_num: bool = True) -> dict[str, Any]:
        params = {"tree": str(tree).lower(), "with_case_num": str(with_case_num).lower()}
        return self.get("/api/v1/case-groups", params=params)

    def fetch_cases(
        self,
        page: int = 1,
        size: int = 200,
        return_type: str = "excel",
        keyword: str | None = None,
        group_id: int | None = None,
        include_subgroups: bool | None = None,
        include_deleted: bool | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "page": page,
            "size": size,
            "return_type": return_type,
        }
        if keyword:
            params["keyword"] = keyword
        if group_id is not None:
            params["group_id"] = group_id
        if include_subgroups is not None:
            params["include_subgroups"] = str(include_subgroups).lower()
        if include_deleted is not None:
            params["include_deleted"] = str(include_deleted).lower()
        return self.get("/api/v1/cases", params=params)

    def fetch_all_cases(
        self,
        size: int = 200,
        return_type: str = "excel",
        keyword: str | None = None,
        group_id: int | None = None,
        include_subgroups: bool | None = None,
        include_deleted: bool | None = None,
    ) -> dict[str, Any]:
        page = 1
        pages: list[dict[str, Any]] = []
        header: list[Any] | None = None

        while True:
            payload = self.fetch_cases(
                page=page,
                size=size,
                return_type=return_type,
                keyword=keyword,
                group_id=group_id,
                include_subgroups=include_subgroups,
                include_deleted=include_deleted,
            )
            data = _extract_payload_data(payload)
            pagination = payload.get("pagination") or data.get("pagination") or {}
            if return_type == "excel":
                if header is None:
                    header = data.get("header", [])
                pages.extend(data.get("rows", []))
            else:
                pages.extend(data.get("list", []))

            total_pages = pagination.get("total_pages") or 1
            if page >= total_pages:
                break
            page += 1

        result = {
            "return_type": return_type,
            "total_items": len(pages),
            "items": pages,
        }
        if header is not None:
            result["header"] = header
        return result

    def fetch_review_topics(self) -> dict[str, Any]:
        return self.get("/api/v1/review-topics")

    def create_review_topic(
        self,
        topic_key: str,
        topic_name: str,
        topic_type: str = "requirement",
        status: str = "draft",
        description: str | None = None,
        member_user_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "topic_key": topic_key,
            "topic_name": topic_name,
            "topic_type": topic_type,
            "status": status,
            "description": description,
            "member_user_ids": member_user_ids or [],
        }
        return self.post("/api/v1/review-topics", payload)

    def fetch_topic_case_links(
        self,
        topic_id: int,
        page: int = 1,
        size: int = 200,
        group_id: int | None = None,
        include_subgroups: bool | None = None,
        keyword: str | None = None,
        with_review: bool | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"page": page, "size": size}
        if group_id is not None:
            params["group_id"] = group_id
        if include_subgroups is not None:
            params["include_subgroups"] = str(include_subgroups).lower()
        if keyword:
            params["keyword"] = keyword
        if with_review is not None:
            params["with_review"] = str(with_review).lower()
        return self.get(f"/api/v1/review-topics/{topic_id}/case-links", params=params)

    def fetch_all_topic_case_links(self, topic_id: int, size: int = 200) -> dict[str, Any]:
        page = 1
        items: list[dict[str, Any]] = []
        while True:
            payload = self.fetch_topic_case_links(topic_id=topic_id, page=page, size=size)
            data = _extract_payload_data(payload)
            if not isinstance(data, dict):
                raise RuntimeError("topic case links payload.data must be an object")
            items.extend(data.get("list", []))
            pagination = data.get("pagination") or {}
            total_pages = pagination.get("total_pages") or 1
            if page >= total_pages:
                break
            page += 1
        return {"items": items}

    def fetch_topic_case_reviews(self, topic_id: int, review_status: str | None = None) -> dict[str, Any]:
        params = {"review_status": review_status} if review_status else None
        return self.get(f"/api/v1/review-topics/{topic_id}/case-reviews", params=params)

    def fetch_topic_activity(self, topic_id: int) -> dict[str, Any]:
        return self.get(f"/api/v1/review-topics/{topic_id}/activity")

    def save_cases_batch(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self.post("/api/v1/cases/batch-save", {"items": items})

    def import_cases(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.post("/api/v1/cases/import", payload)

    def delete_case(self, case_id: int, reason: str) -> dict[str, Any]:
        return self.delete(f"/api/v1/cases/{case_id}", {"reason": reason})

    def select_topic_case_links(self, topic_id: int, case_ids: list[int]) -> dict[str, Any]:
        return self.post(f"/api/v1/review-topics/{topic_id}/case-links/select", {"case_ids": case_ids})

    def delete_topic_case_link(self, topic_id: int, case_id: int) -> dict[str, Any]:
        return self.delete(f"/api/v1/review-topics/{topic_id}/case-links/{case_id}")

    def fetch_agent_snapshot(
        self,
        size: int = 200,
        return_type: str = "excel",
        keyword: str | None = None,
        group_id: int | None = None,
        include_subgroups: bool | None = None,
        include_deleted: bool | None = None,
        include_review_topics: bool = False,
        include_topic_details: bool = False,
    ) -> dict[str, Any]:
        columns_payload = self.fetch_columns()
        groups_payload = self.fetch_groups(tree=True, with_case_num=True)
        cases_payload = self.fetch_all_cases(
            size=size,
            return_type=return_type,
            keyword=keyword,
            group_id=group_id,
            include_subgroups=include_subgroups,
            include_deleted=include_deleted,
        )

        snapshot: dict[str, Any] = {
            "meta": {
                "query_order": [
                    "POST /api/v1/auth/login",
                    "GET /api/v1/case-columns",
                    "GET /api/v1/case-groups?tree=true",
                    f"GET /api/v1/cases?return_type={return_type}&page=1&size={size}",
                ],
                "return_type": return_type,
                "size": size,
                "keyword": keyword,
                "group_id": group_id,
                "include_subgroups": include_subgroups,
                "include_deleted": include_deleted,
            },
            "columns": _extract_payload_data(columns_payload),
            "groups": _extract_payload_data(groups_payload),
            "cases": cases_payload,
        }

        if include_review_topics:
            review_topics_payload = self.fetch_review_topics()
            topics_data = _extract_payload_data(review_topics_payload)
            snapshot["review_topics"] = topics_data
            snapshot["meta"]["query_order"].append("GET /api/v1/review-topics")

            if include_topic_details:
                topic_items = topics_data.get("list", [])
                topic_details: list[dict[str, Any]] = []
                for topic in topic_items:
                    topic_id = topic.get("id")
                    if topic_id is None:
                        continue
                    topic_details.append(
                        {
                            "topic_id": topic_id,
                            "case_links": _extract_payload_data(self.fetch_topic_case_links(topic_id)),
                            "case_reviews": _extract_payload_data(self.fetch_topic_case_reviews(topic_id)),
                            "activity": _extract_payload_data(self.fetch_topic_activity(topic_id)),
                        }
                    )
                snapshot["review_topic_details"] = topic_details
                snapshot["meta"]["query_order"].extend(
                    [
                        "GET /api/v1/review-topics/{topic_id}/case-links",
                        "GET /api/v1/review-topics/{topic_id}/case-reviews",
                        "GET /api/v1/review-topics/{topic_id}/activity",
                    ]
                )

        return snapshot


class SemanticCaseClient:
    def __init__(
        self,
        embed_url: str = DEFAULT_SEMANTIC_EMBED_URL,
        qdrant_url: str = DEFAULT_QDRANT_URL,
        collection: str = DEFAULT_QDRANT_COLLECTION,
        project_id: str = DEFAULT_VECTOR_PROJECT_ID,
        score_threshold: float = DEFAULT_VECTOR_SCORE_THRESHOLD,
        timeout: float = 8.0,
    ) -> None:
        self.embed_url = embed_url.rstrip("/")
        self.qdrant_url = qdrant_url.rstrip("/")
        self.collection = collection
        self.project_id = project_id
        self.score_threshold = score_threshold
        self.client = httpx.Client(timeout=timeout)

    def health(self) -> dict[str, Any]:
        response = self.client.get(f"{self.embed_url}/health")
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "ok":
            raise RuntimeError(f"Embedding service is not healthy: {payload}")
        return payload

    def embed(self, text: str) -> list[float]:
        response = self.client.post(
            f"{self.embed_url}/embed",
            json={"texts": [text]},
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()
        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list) or not embeddings or not isinstance(embeddings[0], list):
            raise RuntimeError("Embedding response does not contain embeddings[0]")
        return embeddings[0]

    def search(self, query: str, limit: int = 10) -> dict[str, Any]:
        health_payload = self.health()
        vector = self.embed(query)
        response = self.client.post(
            f"{self.qdrant_url}/collections/{self.collection}/points/search",
            json={
                "vector": vector,
                "limit": limit,
                "with_payload": True,
                "score_threshold": self.score_threshold,
                "filter": {
                    "must": [
                        {
                            "key": "project_id",
                            "match": {"value": self.project_id},
                        }
                    ]
                },
            },
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()
        points = payload.get("result")
        if not isinstance(points, list):
            raise RuntimeError("Qdrant response does not contain result list")
        return {
            "source": "semantic_vector",
            "health": health_payload,
            "query": query,
            "project_id": self.project_id,
            "collection": self.collection,
            "score_threshold": self.score_threshold,
            "total": len(points),
            "items": points,
        }


def semantic_points_to_excel_payload(result: dict[str, Any], page: int, size: int) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(result["items"], start=1):
        payload = item.get("payload") or {}
        source_id = payload.get("source_id")
        case_id = int(source_id) if isinstance(source_id, int) or (isinstance(source_id, str) and source_id.isdigit()) else None
        title = stringify(payload.get("title"))
        module = stringify(payload.get("module"))
        content = stringify(payload.get("content"))
        risk_tags = payload.get("risk_tags")
        rows.append(
            {
                "case_id": case_id,
                "group_id": payload.get("group_id"),
                "sort_order": float(index),
                "semantic_score": item.get("score"),
                "semantic_payload": payload,
                "cells": [
                    {"column_key": "id", "value": case_id or source_id},
                    {"column_key": "title", "value": title},
                    {"column_key": "priority", "value": ""},
                    {"column_key": "precondition", "value": ""},
                    {"column_key": "steps", "value": content},
                    {"column_key": "expected_result", "value": ""},
                    {"column_key": "case_type", "value": ""},
                    {"column_key": "remark", "value": f"semantic_score={item.get('score')}; risk_tags={json.dumps(risk_tags or [], ensure_ascii=False)}"},
                    {"column_key": "1", "value": module},
                ],
            }
        )
    return {
        "code": 0,
        "msg": "success",
        "data": {
            "pagination": {
                "page": page,
                "size": size,
                "total": len(rows),
                "total_pages": 1,
            },
            "header": [],
            "rows": rows,
            "semantic": {
                key: value
                for key, value in result.items()
                if key not in {"items"}
            },
        },
    }


def semantic_candidate_key(item: dict[str, Any]) -> tuple[int | None, str]:
    payload = item.get("payload") or {}
    source_id = payload.get("source_id")
    case_id = int(source_id) if isinstance(source_id, int) or (isinstance(source_id, str) and source_id.isdigit()) else None
    return case_id, stringify(payload.get("title"))


def attach_semantic_metadata(row: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(row)
    payload = item.get("payload") or {}
    enriched["semantic_score"] = item.get("score")
    enriched["semantic_payload"] = payload
    enriched["semantic_source_id"] = payload.get("source_id")
    return enriched


def hydrate_semantic_cases(
    client: CaseApiClient,
    result: dict[str, Any],
    return_type: str = "excel",
    include_deleted: bool | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    missed: list[dict[str, Any]] = []
    seen_case_ids: set[int] = set()
    header: list[Any] | None = None

    for item in result.get("items", []):
        expected_case_id, title = semantic_candidate_key(item)
        if not title:
            missed.append({"reason": "missing_title", "candidate": item})
            continue
        payload = client.fetch_cases(
            page=1,
            size=10,
            return_type=return_type,
            keyword=title,
            include_deleted=include_deleted,
        )
        data = _extract_payload_data(payload)
        if return_type == "excel":
            if header is None:
                header = data.get("header", [])
            candidates = data.get("rows", [])
            matched = find_excel_row(candidates, expected_case_id, title)
        else:
            candidates = data.get("list", [])
            matched = find_simple_case(candidates, expected_case_id, title)
        if not matched:
            missed.append(
                {
                    "reason": "platform_case_not_found",
                    "case_id": expected_case_id,
                    "title": title,
                    "score": item.get("score"),
                }
            )
            continue
        case_id = extract_case_id(matched)
        if isinstance(case_id, int):
            if case_id in seen_case_ids:
                continue
            seen_case_ids.add(case_id)
        rows.append(attach_semantic_metadata(matched, item))

    return {
        "return_type": return_type,
        "total_items": len(rows),
        "items": rows,
        "header": header or [],
        "missed": missed,
    }


def find_excel_row(rows: list[dict[str, Any]], expected_case_id: int | None, title: str) -> dict[str, Any] | None:
    for row in rows:
        if expected_case_id is not None and row.get("case_id") == expected_case_id:
            return row
    for row in rows:
        if cell_value(row, "title") == title:
            return row
    return None


def find_simple_case(rows: list[dict[str, Any]], expected_case_id: int | None, title: str) -> dict[str, Any] | None:
    for row in rows:
        if expected_case_id is not None and row.get("id") == expected_case_id:
            return row
    for row in rows:
        if row.get("title") == title:
            return row
    return None


def extract_case_id(row: dict[str, Any]) -> int | None:
    case_id = row.get("case_id") or row.get("id")
    return case_id if isinstance(case_id, int) else None


def cell_value(row: dict[str, Any], column_key: str) -> Any:
    for cell in row.get("cells", []):
        if cell.get("column_key") == column_key:
            return cell.get("value")
    return None


def hydrated_cases_to_excel_payload(
    semantic_result: dict[str, Any],
    hydrated: dict[str, Any],
    page: int,
    size: int,
) -> dict[str, Any]:
    rows = hydrated.get("items", [])
    return {
        "code": 0,
        "msg": "success",
        "data": {
            "pagination": {
                "page": page,
                "size": size,
                "total": len(rows),
                "total_pages": 1,
            },
            "header": hydrated.get("header", []),
            "rows": rows,
            "semantic": {
                key: value
                for key, value in semantic_result.items()
                if key not in {"items"}
            },
            "semantic_hydration": {
                "source": "case_api",
                "total_items": hydrated.get("total_items", 0),
                "missed": hydrated.get("missed", []),
            },
        },
    }


def semantic_points_to_all_cases_payload(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "return_type": "semantic",
        "total_items": result["total"],
        "items": result["items"],
        "semantic": {
            key: value
            for key, value in result.items()
            if key not in {"items"}
        },
    }


def stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def try_semantic_search(args: argparse.Namespace, limit: int) -> dict[str, Any] | None:
    keyword = getattr(args, "keyword", None)
    if not keyword or getattr(args, "no_semantic", False):
        return None
    client = SemanticCaseClient(
        embed_url=args.semantic_embed_url,
        qdrant_url=args.qdrant_url,
        collection=args.qdrant_collection,
        project_id=args.vector_project_id,
        score_threshold=args.vector_score_threshold,
    )
    return client.search(keyword, limit=limit)


def _extract_payload_data(payload: dict[str, Any]) -> Any:
    data = payload.get("data")
    if isinstance(data, dict | list):
        return data
    raise RuntimeError("Response payload.data is missing or not a supported JSON value")


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Client for case-related APIs. Write commands require explicit use.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"API base URL, default: {DEFAULT_BASE_URL}")
    parser.add_argument("--username", default=DEFAULT_USERNAME, help=f"Login username, default: {DEFAULT_USERNAME}")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Plaintext password; tool hashes it with sha256")
    parser.add_argument("--no-semantic", action="store_true", help="Disable semantic vector search before case API queries")
    parser.add_argument("--semantic-embed-url", default=DEFAULT_SEMANTIC_EMBED_URL)
    parser.add_argument("--qdrant-url", default=DEFAULT_QDRANT_URL)
    parser.add_argument("--qdrant-collection", default=DEFAULT_QDRANT_COLLECTION)
    parser.add_argument("--vector-project-id", default=DEFAULT_VECTOR_PROJECT_ID)
    parser.add_argument("--vector-score-threshold", type=float, default=DEFAULT_VECTOR_SCORE_THRESHOLD)

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("columns", help="Fetch case column definitions")
    subparsers.add_parser("groups", help="Fetch case groups tree")

    cases_parser = subparsers.add_parser("cases", help="Fetch one page of cases")
    cases_parser.add_argument("--page", type=int, default=1)
    cases_parser.add_argument("--size", type=int, default=DEFAULT_VECTOR_LIMIT)
    cases_parser.add_argument("--return-type", choices=["simple", "excel"], default="excel")
    cases_parser.add_argument("--keyword")
    cases_parser.add_argument("--group-id", type=int)
    cases_parser.add_argument("--include-subgroups", action="store_true", default=None)
    cases_parser.add_argument("--include-deleted", action="store_true", default=None)

    all_cases_parser = subparsers.add_parser("all-cases", help="Fetch all case pages")
    all_cases_parser.add_argument("--size", type=int, default=DEFAULT_VECTOR_LIMIT)
    all_cases_parser.add_argument("--return-type", choices=["simple", "excel"], default="excel")
    all_cases_parser.add_argument("--keyword")
    all_cases_parser.add_argument("--group-id", type=int)
    all_cases_parser.add_argument("--include-subgroups", action="store_true", default=None)
    all_cases_parser.add_argument("--include-deleted", action="store_true", default=None)

    subparsers.add_parser("review-topics", help="Fetch review topics")

    create_topic_parser = subparsers.add_parser("create-review-topic", help="Create a review topic")
    create_topic_parser.add_argument("--topic-key", required=True)
    create_topic_parser.add_argument("--topic-name", required=True)
    create_topic_parser.add_argument("--topic-type", choices=["requirement", "version", "special"], default="requirement")
    create_topic_parser.add_argument("--status", choices=["draft", "open", "closed"], default="draft")
    create_topic_parser.add_argument("--description")

    snapshot_parser = subparsers.add_parser("snapshot", help="Fetch agent-oriented full query snapshot")
    snapshot_parser.add_argument("--size", type=int, default=DEFAULT_VECTOR_LIMIT)
    snapshot_parser.add_argument("--return-type", choices=["simple", "excel"], default="excel")
    snapshot_parser.add_argument("--keyword")
    snapshot_parser.add_argument("--group-id", type=int)
    snapshot_parser.add_argument("--include-subgroups", action="store_true", default=None)
    snapshot_parser.add_argument("--include-deleted", action="store_true", default=None)
    snapshot_parser.add_argument("--include-review-topics", action="store_true")
    snapshot_parser.add_argument("--include-topic-details", action="store_true")

    topic_links_parser = subparsers.add_parser("topic-case-links", help="Fetch topic case links")
    topic_links_parser.add_argument("--topic-id", required=True, type=int)

    topic_reviews_parser = subparsers.add_parser("topic-case-reviews", help="Fetch topic case reviews")
    topic_reviews_parser.add_argument("--topic-id", required=True, type=int)
    topic_reviews_parser.add_argument("--review-status", choices=["pending", "in_review", "passed", "rejected"])

    topic_activity_parser = subparsers.add_parser("topic-activity", help="Fetch topic activity")
    topic_activity_parser.add_argument("--topic-id", required=True, type=int)

    select_links_parser = subparsers.add_parser("select-topic-case-links", help="Add cases to a review topic")
    select_links_parser.add_argument("--topic-id", required=True, type=int)
    select_links_parser.add_argument("--case-id", action="append", type=int, required=True)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    client = CaseApiClient(
        base_url=args.base_url,
        username=args.username,
        password=args.password,
    )

    if args.command == "columns":
        _print_json(client.fetch_columns())
        return
    if args.command == "groups":
        _print_json(client.fetch_groups())
        return
    if args.command == "cases":
        try:
            semantic_result = try_semantic_search(args, limit=args.size)
            if semantic_result is not None:
                hydrated = hydrate_semantic_cases(
                    client,
                    semantic_result,
                    return_type=args.return_type,
                    include_deleted=args.include_deleted,
                )
                if args.return_type == "excel":
                    _print_json(hydrated_cases_to_excel_payload(semantic_result, hydrated, page=args.page, size=args.size))
                else:
                    payload = semantic_points_to_all_cases_payload(semantic_result)
                    payload["items"] = hydrated["items"]
                    payload["total_items"] = hydrated["total_items"]
                    payload["semantic_hydration"] = {
                        "source": "case_api",
                        "missed": hydrated.get("missed", []),
                    }
                    _print_json(payload)
                return
        except Exception as exc:
            semantic_error = str(exc)
        else:
            semantic_error = None
        payload = client.fetch_cases(
            page=args.page,
            size=args.size,
            return_type=args.return_type,
            keyword=args.keyword,
            group_id=args.group_id,
            include_subgroups=args.include_subgroups,
            include_deleted=args.include_deleted,
        )
        if args.keyword and semantic_error:
            payload.setdefault("semantic_fallback", {"used": False, "error": semantic_error, "fallback": "case_api"})
        _print_json(payload)
        return
    if args.command == "all-cases":
        try:
            semantic_result = try_semantic_search(args, limit=args.size)
            if semantic_result is not None:
                hydrated = hydrate_semantic_cases(
                    client,
                    semantic_result,
                    return_type=args.return_type,
                    include_deleted=args.include_deleted,
                )
                payload = semantic_points_to_all_cases_payload(semantic_result)
                payload["return_type"] = args.return_type
                payload["items"] = hydrated["items"]
                payload["total_items"] = hydrated["total_items"]
                payload["header"] = hydrated.get("header", [])
                payload["semantic_hydration"] = {
                    "source": "case_api",
                    "missed": hydrated.get("missed", []),
                }
                _print_json(payload)
                return
        except Exception as exc:
            semantic_error = str(exc)
        else:
            semantic_error = None
        payload = client.fetch_all_cases(
            size=args.size,
            return_type=args.return_type,
            keyword=args.keyword,
            group_id=args.group_id,
            include_subgroups=args.include_subgroups,
            include_deleted=args.include_deleted,
        )
        if args.keyword and semantic_error:
            payload.setdefault("semantic_fallback", {"used": False, "error": semantic_error, "fallback": "case_api"})
        _print_json(payload)
        return
    if args.command == "review-topics":
        _print_json(client.fetch_review_topics())
        return
    if args.command == "create-review-topic":
        _print_json(
            client.create_review_topic(
                topic_key=args.topic_key,
                topic_name=args.topic_name,
                topic_type=args.topic_type,
                status=args.status,
                description=args.description,
            )
        )
        return
    if args.command == "snapshot":
        if args.keyword and not args.no_semantic:
            try:
                semantic_result = try_semantic_search(args, limit=args.size)
                if semantic_result is not None:
                    columns_payload = client.fetch_columns()
                    groups_payload = client.fetch_groups(tree=True, with_case_num=True)
                    hydrated = hydrate_semantic_cases(
                        client,
                        semantic_result,
                        return_type=args.return_type,
                        include_deleted=args.include_deleted,
                    )
                    snapshot = {
                        "meta": {
                            "query_order": [
                                "GET /semantic/health",
                                "POST /semantic/embed",
                                "POST /qdrant/collections/{collection}/points/search",
                                "POST /api/v1/auth/login",
                                "GET /api/v1/case-columns",
                                "GET /api/v1/case-groups?tree=true",
                            ],
                            "return_type": args.return_type,
                            "size": args.size,
                            "keyword": args.keyword,
                            "group_id": args.group_id,
                            "include_subgroups": args.include_subgroups,
                            "include_deleted": args.include_deleted,
                            "semantic_search": {
                                "used": True,
                                "fallback": None,
                            },
                        },
                        "columns": _extract_payload_data(columns_payload),
                        "groups": _extract_payload_data(groups_payload),
                        "cases": {
                            "return_type": args.return_type,
                            "total_items": hydrated["total_items"],
                            "items": hydrated["items"],
                            "header": hydrated.get("header", []),
                        },
                    }
                    snapshot["semantic_cases"] = semantic_result
                    snapshot["semantic_hydration"] = {
                        "source": "case_api",
                        "missed": hydrated.get("missed", []),
                    }
                    if args.include_review_topics:
                        review_topics_payload = client.fetch_review_topics()
                        snapshot["review_topics"] = _extract_payload_data(review_topics_payload)
                        snapshot["meta"]["query_order"].append("GET /api/v1/review-topics")
                    _print_json(snapshot)
                    return
            except Exception as exc:
                semantic_error = str(exc)
            else:
                semantic_error = None
        else:
            semantic_error = None
        snapshot = client.fetch_agent_snapshot(
            size=args.size,
            return_type=args.return_type,
            keyword=args.keyword,
            group_id=args.group_id,
            include_subgroups=args.include_subgroups,
            include_deleted=args.include_deleted,
            include_review_topics=args.include_review_topics,
            include_topic_details=args.include_topic_details,
        )
        if args.keyword and semantic_error:
            snapshot["meta"]["semantic_search"] = {
                "used": False,
                "error": semantic_error,
                "fallback": "case_api_keyword",
            }
        _print_json(snapshot)
        return
    if args.command == "topic-case-links":
        _print_json(client.fetch_topic_case_links(topic_id=args.topic_id))
        return
    if args.command == "topic-case-reviews":
        _print_json(
            client.fetch_topic_case_reviews(
                topic_id=args.topic_id,
                review_status=args.review_status,
            )
        )
        return
    if args.command == "topic-activity":
        _print_json(client.fetch_topic_activity(topic_id=args.topic_id))
        return
    if args.command == "select-topic-case-links":
        _print_json(client.select_topic_case_links(topic_id=args.topic_id, case_ids=args.case_id))
        return

    raise RuntimeError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
