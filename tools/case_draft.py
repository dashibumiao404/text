from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tools.export_cases_excel import DEFAULT_HEADERS, export_cases, load_cases


DEFAULT_INPUT = Path("output/task_guard_cases.json")
DEFAULT_OUTPUT = Path("output/task_guard_cases.xlsx")


def read_cases(path: Path) -> list[dict[str, Any]]:
    return load_cases(path)


def write_cases(path: Path, cases: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def find_indexes(cases: list[dict[str, Any]], title: str) -> list[int]:
    return [index for index, case in enumerate(cases) if case.get("标题") == title]


def ensure_unique_title(cases: list[dict[str, Any]], title: str) -> int:
    indexes = find_indexes(cases, title)
    if not indexes:
        raise ValueError(f"Case title not found: {title}")
    if len(indexes) > 1:
        raise ValueError(f"Case title is not unique: {title}")
    return indexes[0]


def normalize_case(raw: dict[str, Any]) -> dict[str, str]:
    normalized: dict[str, Any] = {header: stringify(raw.get(header, "")) for header in DEFAULT_HEADERS}
    for key, value in raw.items():
        if key not in normalized:
            normalized[key] = value
    return normalized


def stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    return str(value)


def parse_fields(values: list[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise ValueError(f"Field must use key=value format: {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        if key not in DEFAULT_HEADERS:
            raise ValueError(f"Unsupported field: {key}. Allowed fields: {', '.join(DEFAULT_HEADERS)}")
        fields[key] = value
    return fields


def print_case(case: dict[str, Any]) -> None:
    print(json.dumps(normalize_case(case), ensure_ascii=False, indent=2))


def cmd_summary(args: argparse.Namespace) -> None:
    cases = read_cases(args.input)
    groups: dict[str, int] = {}
    priorities: dict[str, int] = {}
    for case in cases:
        groups[case["分组"]] = groups.get(case["分组"], 0) + 1
        priorities[case["等级"]] = priorities.get(case["等级"], 0) + 1
    print(json.dumps({"total": len(cases), "groups": groups, "priorities": priorities}, ensure_ascii=False, indent=2))


def cmd_list(args: argparse.Namespace) -> None:
    cases = read_cases(args.input)
    for index, case in enumerate(cases, start=1):
        if args.group and case["分组"] != args.group:
            continue
        if args.keyword and args.keyword not in case["标题"] and args.keyword not in case["预期结果"]:
            continue
        print(f"{index}. [{case['等级']}] {case['分组']} - {case['标题']}")


def cmd_show(args: argparse.Namespace) -> None:
    cases = read_cases(args.input)
    if args.index is not None:
        if args.index < 1 or args.index > len(cases):
            raise ValueError(f"Index out of range: {args.index}")
        print_case(cases[args.index - 1])
        return
    print_case(cases[ensure_unique_title(cases, args.title)])


def cmd_add(args: argparse.Namespace) -> None:
    cases = read_cases(args.input)
    raw = json.loads(args.case_json)
    if not isinstance(raw, dict):
        raise ValueError("--case-json must be a JSON object")
    case = normalize_case(raw)
    if not case["标题"]:
        raise ValueError("标题 is required")
    if find_indexes(cases, case["标题"]):
        raise ValueError(f"Case title already exists: {case['标题']}")
    cases.append(case)
    write_cases(args.input, cases)
    print(f"Added case: {case['标题']}")


def cmd_update(args: argparse.Namespace) -> None:
    cases = read_cases(args.input)
    index = args.index - 1 if args.index is not None else ensure_unique_title(cases, args.title)
    if index < 0 or index >= len(cases):
        raise ValueError(f"Index out of range: {args.index}")
    updates = parse_fields(args.set)
    cases[index].update(updates)
    cases[index] = normalize_case(cases[index])
    write_cases(args.input, cases)
    print(f"Updated case: {cases[index]['标题']}")


def cmd_delete(args: argparse.Namespace) -> None:
    cases = read_cases(args.input)
    index = args.index - 1 if args.index is not None else ensure_unique_title(cases, args.title)
    if index < 0 or index >= len(cases):
        raise ValueError(f"Index out of range: {args.index}")
    removed = cases.pop(index)
    write_cases(args.input, cases)
    print(f"Deleted case: {removed['标题']}")


def cmd_validate(args: argparse.Namespace) -> None:
    cases = read_cases(args.input)
    titles: dict[str, int] = {}
    errors: list[str] = []
    for index, case in enumerate(cases, start=1):
        for header in DEFAULT_HEADERS:
            if header not in case:
                errors.append(f"{index}: missing field {header}")
        case_id = case.get("case_id")
        if case_id not in {None, ""} and not isinstance(case_id, int):
            errors.append(f"{index}: case_id must be an integer when present")
        topic_id = case.get("topic_id")
        if topic_id not in {None, ""} and not isinstance(topic_id, int):
            errors.append(f"{index}: topic_id must be an integer when present")
        title = case.get("标题", "")
        if not title:
            errors.append(f"{index}: 标题 is empty")
        titles[title] = titles.get(title, 0) + 1
        if case.get("等级") not in {"P0", "P1", "P2", "P3", "P4"}:
            errors.append(f"{index}: unsupported 等级 {case.get('等级')}")
    duplicates = sorted(title for title, count in titles.items() if title and count > 1)
    for title in duplicates:
        errors.append(f"duplicate title: {title}")
    if errors:
        print(json.dumps({"valid": False, "errors": errors}, ensure_ascii=False, indent=2))
        raise SystemExit(1)
    print(json.dumps({"valid": True, "total": len(cases)}, ensure_ascii=False, indent=2))


def cmd_export(args: argparse.Namespace) -> None:
    cases = read_cases(args.input)
    export_cases(cases, args.output)
    print(f"Exported {len(cases)} cases to {args.output}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Edit generated case drafts stored as local JSON.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help=f"Draft JSON path, default: {DEFAULT_INPUT}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("summary", help="Show case counts by group and priority").set_defaults(func=cmd_summary)

    list_parser = subparsers.add_parser("list", help="List draft cases")
    list_parser.add_argument("--group")
    list_parser.add_argument("--keyword")
    list_parser.set_defaults(func=cmd_list)

    show_parser = subparsers.add_parser("show", help="Show one case by 1-based index or exact title")
    show_target = show_parser.add_mutually_exclusive_group(required=True)
    show_target.add_argument("--index", type=int)
    show_target.add_argument("--title")
    show_parser.set_defaults(func=cmd_show)

    add_parser = subparsers.add_parser("add", help="Append a case from a JSON object")
    add_parser.add_argument("--case-json", required=True)
    add_parser.set_defaults(func=cmd_add)

    update_parser = subparsers.add_parser("update", help="Update one case by 1-based index or exact title")
    update_target = update_parser.add_mutually_exclusive_group(required=True)
    update_target.add_argument("--index", type=int)
    update_target.add_argument("--title")
    update_parser.add_argument("--set", action="append", required=True, help="Field update in key=value format")
    update_parser.set_defaults(func=cmd_update)

    delete_parser = subparsers.add_parser("delete", help="Delete one case by 1-based index or exact title")
    delete_target = delete_parser.add_mutually_exclusive_group(required=True)
    delete_target.add_argument("--index", type=int)
    delete_target.add_argument("--title")
    delete_parser.set_defaults(func=cmd_delete)

    subparsers.add_parser("validate", help="Validate draft structure").set_defaults(func=cmd_validate)

    export_parser = subparsers.add_parser("export", help="Export draft JSON to Excel")
    export_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help=f"Output xlsx path, default: {DEFAULT_OUTPUT}")
    export_parser.set_defaults(func=cmd_export)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
