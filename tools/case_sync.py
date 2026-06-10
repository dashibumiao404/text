from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.case_api import CaseApiClient, DEFAULT_BASE_URL, DEFAULT_PASSWORD, DEFAULT_USERNAME, _extract_payload_data
from tools.case_draft import write_cases
from tools.export_cases_excel import load_cases


DEFAULT_INPUT = Path("workspace/1V1控车守护/test_case/cases.json")

FIELD_MAP = {
    "前置条件": "precondition",
    "步骤": "steps",
    "预期结果": "expected_result",
    "类型": "case_type",
    "备注": "remark",
}


@dataclass
class PlatformCase:
    case_id: int
    group_id: int
    title: str
    priority: str | None
    extra_data: dict[str, Any]


def read_cases(path: Path) -> list[dict[str, Any]]:
    return load_cases(path)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def default_plan_path(input_path: Path) -> Path:
    return input_path.parent / "sync_plan.json"


def default_result_path(input_path: Path) -> Path:
    return input_path.parent / "sync_result.json"


def draft_to_import_item(case: dict[str, Any], sort_order: float, group_path_mode: str = "full") -> dict[str, Any]:
    group_path = str(case.get("分组") or "").strip()
    if group_path_mode == "leaf":
        group_path = group_path.rsplit("/", 1)[-1]
    elif group_path_mode == "empty":
        group_path = ""
    item: dict[str, Any] = {
        "group_path": group_path,
        "title": str(case.get("标题") or "").strip(),
        "priority": str(case.get("等级") or "").strip() or None,
        "sort_order": sort_order,
        "extra_data": {platform_key: case.get(draft_key, "") for draft_key, platform_key in FIELD_MAP.items()},
    }
    case_id = case.get("case_id")
    if isinstance(case_id, int) and case_id > 0:
        item["case_id"] = case_id
    return item


def draft_to_batch_item(case: dict[str, Any], sort_order: float, group_id: int) -> dict[str, Any]:
    item = draft_to_import_item(case, sort_order, group_path_mode="empty")
    item["group_id"] = group_id
    item.pop("group_path", None)
    return item


def platform_signature(item: dict[str, Any]) -> dict[str, Any]:
    signature = {
        "title": item.get("title") or "",
        "priority": item.get("priority") or "",
        "extra_data": {key: stringify(item.get("extra_data", {}).get(key, "")) for key in FIELD_MAP.values()},
    }
    if item.get("group_id") is not None:
        signature["group_id"] = item.get("group_id")
    return signature


def stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    return str(value)


def parse_platform_cases(payload: dict[str, Any]) -> dict[int, PlatformCase]:
    data = _extract_payload_data(payload)
    items = data.get("list", []) if isinstance(data, dict) else []
    parsed: dict[int, PlatformCase] = {}
    for item in items:
        case_id = item.get("id")
        if isinstance(case_id, int):
            parsed[case_id] = PlatformCase(
                case_id=case_id,
                group_id=int(item.get("group_id") or 0),
                title=str(item.get("title") or ""),
                priority=item.get("priority"),
                extra_data=item.get("extra_data") or {},
            )
    return parsed


def parse_topic_case_ids(payload: dict[str, Any]) -> set[int]:
    if "items" in payload:
        items = payload.get("items") or []
    else:
        data = _extract_payload_data(payload)
        items = data.get("list", []) if isinstance(data, dict) else []
    return {int(item["id"]) for item in items if isinstance(item.get("id"), int)}


def find_saved_case_by_title(client: CaseApiClient, title: str, group_id: int | None) -> dict[str, Any] | None:
    payload = client.fetch_cases(return_type="simple", keyword=title, group_id=group_id, include_deleted=False)
    data = _extract_payload_data(payload)
    items = data.get("list", []) if isinstance(data, dict) else []
    exact_matches = [item for item in items if item.get("title") == title and isinstance(item.get("id"), int)]
    if not exact_matches:
        return None
    exact_matches.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    return exact_matches[0]


def ensure_topic(args: argparse.Namespace, client: CaseApiClient) -> int | None:
    if args.topic_id:
        return args.topic_id
    if not args.create_topic_name:
        return None
    if not args.confirm_create_topic:
        raise ValueError("Creating a review topic requires --confirm-create-topic")
    topic_key = args.create_topic_key or args.create_topic_name
    payload = client.create_review_topic(
        topic_key=topic_key,
        topic_name=args.create_topic_name,
        topic_type=args.create_topic_type,
        status=args.create_topic_status,
        description=args.create_topic_description,
    )
    data = _extract_payload_data(payload)
    if not isinstance(data, dict) or not isinstance(data.get("id"), int):
        raise RuntimeError("create review topic response did not include data.id")
    return data["id"]


def build_plan(args: argparse.Namespace, client: CaseApiClient) -> dict[str, Any]:
    all_cases = read_cases(args.input)
    indexed_cases = [
        (index, case)
        for index, case in enumerate(all_cases, start=1)
        if args.only_index is None or index == args.only_index
    ]
    cases = [case for _, case in indexed_cases]
    if args.only_index is not None and not cases:
        raise ValueError(f"--only-index is out of range: {args.only_index}")
    known_case_ids = [case["case_id"] for case in cases if isinstance(case.get("case_id"), int)]
    platform_cases: dict[int, PlatformCase] = {}
    if known_case_ids:
        payload = client.fetch_all_cases(return_type="simple", include_deleted=True, size=200)
        for item in payload.get("items", []):
            case_id = item.get("id")
            if isinstance(case_id, int) and case_id in known_case_ids:
                platform_cases[case_id] = PlatformCase(
                    case_id=case_id,
                    group_id=int(item.get("group_id") or 0),
                    title=str(item.get("title") or ""),
                    priority=item.get("priority"),
                    extra_data=item.get("extra_data") or {},
                )

    topic_case_ids: set[int] = set()
    if args.topic_id:
        topic_case_ids = parse_topic_case_ids(client.fetch_all_topic_case_links(args.topic_id))

    creates: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    unchanged: list[dict[str, Any]] = []
    links: list[int] = []
    draft_case_ids: set[int] = set()

    for index, case in indexed_cases:
        if case.get("sync_status") == "deleted":
            continue
        item = draft_to_import_item(case, sort_order=float(index * 1000), group_path_mode=args.group_path_mode)
        case_id = item.get("case_id")
        if isinstance(case_id, int):
            draft_case_ids.add(case_id)
            platform_case = platform_cases.get(case_id)
            if platform_case is None:
                updates.append({"index": index, "reason": "case_id_not_found_locally", "item": item})
            else:
                current = {
                    "group_id": platform_case.group_id,
                    "title": platform_case.title,
                    "priority": platform_case.priority,
                    "extra_data": platform_case.extra_data,
                }
                if isinstance(case.get("group_id"), int):
                    item["group_id"] = case["group_id"]
                if platform_signature(item) != platform_signature(current):
                    updates.append({"index": index, "item": item})
                else:
                    unchanged.append({"index": index, "case_id": case_id, "title": item["title"]})
            if args.topic_id and case_id not in topic_case_ids:
                links.append(case_id)
        else:
            creates.append({"index": index, "item": item})

    deletes: list[dict[str, Any]] = []
    if args.sync_delete and args.topic_id:
        for case_id in sorted(topic_case_ids - draft_case_ids):
            deletes.append({"case_id": case_id, "reason": args.delete_reason})

    return {
        "input": str(args.input),
        "only_index": args.only_index,
        "topic_id": args.topic_id,
        "selected_group_id": args.selected_group_id,
        "counts": {
            "create": len(creates),
            "update": len(updates),
            "delete": len(deletes),
            "link": len(links),
            "unchanged": len(unchanged),
        },
        "create": creates,
        "update": updates,
        "delete": deletes,
        "link": links,
        "unchanged": unchanged,
    }


def apply_plan(args: argparse.Namespace, client: CaseApiClient, plan: dict[str, Any]) -> dict[str, Any]:
    if not args.apply:
        return {"applied": False, "message": "Dry run only. Re-run with --apply to write platform data."}
    if plan["counts"]["update"] > 5 and not args.confirm_large_update:
        raise ValueError("Updating more than 5 cases requires --confirm-large-update")
    if plan["counts"]["delete"] > 0 and not args.confirm_delete:
        raise ValueError("Deleting platform cases requires --confirm-delete")

    save_entries = plan["create"] + plan["update"]
    save_items = [entry["item"] for entry in save_entries]
    saved_cases: list[dict[str, Any]] = []
    if save_items:
        if args.use_batch_save:
            if plan["create"] and plan["update"]:
                raise ValueError("--use-batch-save does not support mixed create and update plans")
            if not isinstance(args.selected_group_id, int):
                raise ValueError("--use-batch-save requires --selected-group-id")
            all_cases = read_cases(args.input)
            batch_items = [
                draft_to_batch_item(all_cases[entry["index"] - 1], entry["item"]["sort_order"], args.selected_group_id)
                for entry in save_entries
            ]
            client.save_cases_batch(batch_items)
            for entry in save_entries:
                saved = find_saved_case_by_title(client, entry["item"]["title"], args.selected_group_id)
                if saved:
                    saved_cases.append(saved)
        else:
            payload = client.import_cases(
                {
                    "mode": "incremental",
                    "items": save_items,
                    "selected_group_id": args.selected_group_id,
                }
            )
            data = _extract_payload_data(payload)
            saved_cases = data.get("list", []) if isinstance(data, dict) else []

    saved_by_title = {item.get("title"): item for item in saved_cases}
    cases = read_cases(args.input)
    for entry in save_entries:
        index = entry["index"] - 1
        title = entry["item"]["title"]
        saved = saved_by_title.get(title)
        if not saved or not isinstance(saved.get("id"), int):
            continue
        cases[index]["case_id"] = saved["id"]
        cases[index]["group_id"] = saved.get("group_id")
        cases[index]["sync_status"] = "synced"
        if args.topic_id:
            cases[index]["topic_id"] = args.topic_id

    saved_ids = [item["id"] for item in saved_cases if isinstance(item.get("id"), int)]
    link_ids = sorted(set(plan.get("link", []) + saved_ids))
    link_result = None
    if args.topic_id and link_ids:
        link_result = client.select_topic_case_links(args.topic_id, link_ids)

    delete_results: list[dict[str, Any]] = []
    if plan.get("delete"):
        if not args.sync_delete:
            raise ValueError("Delete plan exists but --sync-delete was not provided")
        if not args.delete_reason:
            raise ValueError("--delete-reason is required for platform delete")
        for item in plan["delete"]:
            delete_results.append(client.delete_case(int(item["case_id"]), args.delete_reason))

    write_cases(args.input, cases)
    return {
        "applied": True,
        "saved_count": len(saved_cases),
        "linked_count": len(link_ids),
        "deleted_count": len(delete_results),
        "saved_case_ids": saved_ids,
        "link_result": link_result,
        "delete_results": delete_results,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan and apply local JSON test cases to the case management platform.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--plan-output", type=Path)
    parser.add_argument("--result-output", type=Path)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--username", default=DEFAULT_USERNAME)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--topic-id", type=int, help="Review topic to link synced cases into")
    parser.add_argument("--only-index", type=int, help="Sync only one 1-based local case index")
    parser.add_argument("--create-topic-name", help="Create a review topic when --apply is used and --topic-id is absent")
    parser.add_argument("--create-topic-key")
    parser.add_argument("--create-topic-type", choices=["requirement", "version", "special"], default="requirement")
    parser.add_argument("--create-topic-status", choices=["draft", "open", "closed"], default="draft")
    parser.add_argument("--create-topic-description")
    parser.add_argument("--confirm-create-topic", action="store_true", help="Required when --create-topic-name creates a topic")
    parser.add_argument("--confirm-large-update", action="store_true", help="Required when updating more than 5 cases")
    parser.add_argument("--confirm-delete", action="store_true", help="Required when deleting platform cases")
    parser.add_argument("--selected-group-id", type=int, help="Optional import root group_id")
    parser.add_argument("--group-path-mode", choices=["full", "leaf", "empty"], default="full", help="How to send group_path to import")
    parser.add_argument("--use-batch-save", action="store_true", help="Use batch-save for create-only plans; requires --selected-group-id")
    parser.add_argument("--sync-delete", action="store_true", help="Plan platform deletes for cases linked to topic but absent locally")
    parser.add_argument("--delete-reason", default="agent sync delete")
    parser.add_argument("--apply", action="store_true", help="Write platform data and update local case_id metadata")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.plan_output is None:
        args.plan_output = default_plan_path(args.input)
    if args.result_output is None:
        args.result_output = default_result_path(args.input)
    client = CaseApiClient(args.base_url, args.username, args.password)
    if args.apply and not args.topic_id and args.create_topic_name:
        args.topic_id = ensure_topic(args, client)
    plan = build_plan(args, client)
    write_json(args.plan_output, plan)
    result = apply_plan(args, client, plan)
    write_json(args.result_output, result)
    print(json.dumps({"plan": plan["counts"], "result": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
