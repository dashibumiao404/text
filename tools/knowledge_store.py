from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.knowledge_db import ensure_knowledge_db


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "knowledge" / "knowledge.db"


SEARCH_TABLES: dict[str, list[str]] = {
    "decisions": ["topic", "decision", "status", "source"],
    "rules": ["rule_type", "rule_key", "rule_value", "source"],
    "glossary": ["term", "definition", "aliases", "source"],
    "case_patterns": [
        "pattern_key",
        "group_name",
        "trigger_keywords",
        "title_pattern",
        "precondition_pattern",
        "step_pattern",
        "expected_pattern",
        "notes",
        "source",
    ],
    "api_conventions": ["convention_key", "convention_value", "source"],
    "conflicts": ["topic", "old_value", "new_value", "resolution_status", "source"],
    "tags": ["tag_key", "tag_name", "tag_type", "description", "aliases", "source"],
}

DEFAULT_SEARCH_TABLES = ["decisions", "rules", "glossary", "case_patterns", "api_conventions"]


@dataclass
class KnowledgeItem:
    topic: str
    value: str
    status: str
    source: str


def slugify(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "_", value.strip()).strip("_")
    return text[:60] or "item"


def parse_markdown_items(path: Path, status: str, source: str) -> list[KnowledgeItem]:
    if not path.exists():
        return []
    items: list[KnowledgeItem] = []
    current_topic = path.stem
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading = re.match(r"^#{1,6}\s+(.+)$", line)
        if heading:
            current_topic = heading.group(1).strip()
            continue
        bullet = re.match(r"^(?:[-*]|\d+[.)])\s+(.+)$", line)
        if bullet:
            value = bullet.group(1).strip()
            if value:
                items.append(KnowledgeItem(current_topic, value, status, source))
    return items


def ensure_tag(conn: sqlite3.Connection, tag_key: str, tag_name: str, tag_type: str, source: str) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO tags (tag_key, tag_name, tag_type, description, aliases, source)
        VALUES (?, ?, ?, ?, '[]', ?)
        """,
        (tag_key, tag_name, tag_type, f"Workspace knowledge tag: {tag_name}", source),
    )


def link_tag(conn: sqlite3.Connection, tag_key: str, target_type: str, target_id: int, source: str) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO knowledge_tag_links (tag_key, target_type, target_id, weight, source)
        VALUES (?, ?, ?, 1.0, ?)
        """,
        (tag_key, target_type, target_id, source),
    )


def insert_decision(conn: sqlite3.Connection, item: KnowledgeItem, tag_key: str) -> tuple[bool, int]:
    existing = conn.execute(
        """
        SELECT id FROM decisions
        WHERE topic = ? AND decision = ? AND status = ? AND source = ?
        """,
        (item.topic, item.value, item.status, item.source),
    ).fetchone()
    if existing:
        link_tag(conn, tag_key, "decisions", int(existing[0]), item.source)
        return False, int(existing[0])
    cursor = conn.execute(
        """
        INSERT INTO decisions (topic, decision, status, source)
        VALUES (?, ?, ?, ?)
        """,
        (item.topic, item.value, item.status, item.source),
    )
    decision_id = int(cursor.lastrowid)
    link_tag(conn, tag_key, "decisions", decision_id, item.source)
    return True, decision_id


def parse_explicit_tags(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    mapping: dict[str, list[str]] = {}
    current_decision: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        decision_match = re.match(r"^(?:[-*]|\d+[.)])\s+decision:\s*(.+)$", line)
        if decision_match:
            current_decision = decision_match.group(1).strip()
            mapping.setdefault(current_decision, [])
            continue
        tags_match = re.match(r"^(?:[-*]|\d+[.)])\s+tags:\s*(.+)$", line)
        if tags_match and current_decision:
            tags = [tag.strip() for tag in tags_match.group(1).split(",") if tag.strip()]
            mapping[current_decision] = tags
    return mapping


def ensure_explicit_tag(conn: sqlite3.Connection, tag_key: str, source: str) -> None:
    tag_type = tag_key.split(".", 1)[0] if "." in tag_key else "custom"
    tag_name = tag_key.split(".", 1)[1] if "." in tag_key else tag_key
    ensure_tag(conn, tag_key, tag_name, tag_type, source)


def link_explicit_tags(
    conn: sqlite3.Connection,
    decision: str,
    target_id: int,
    tags_by_decision: dict[str, list[str]],
    source: str,
) -> int:
    linked = 0
    for tag_key in tags_by_decision.get(decision, []):
        ensure_explicit_tag(conn, tag_key, source)
        link_tag(conn, tag_key, "decisions", target_id, source)
        linked += 1
    return linked


def import_rules(conn: sqlite3.Connection, path: Path, requirement_slug: str, tag_key: str) -> int:
    if not path.exists():
        return 0
    source = f"workspace:{requirement_slug}/knowledge/{path.name}"
    items = parse_markdown_items(path, "confirmed", source)
    count = 0
    for index, item in enumerate(items, start=1):
        key = f"{requirement_slug}.{slugify(item.topic)}.{index}"
        cursor = conn.execute(
            """
            INSERT INTO rules (rule_type, rule_key, rule_value, source)
            VALUES ('requirement_rule', ?, ?, ?)
            ON CONFLICT(rule_type, rule_key) DO UPDATE SET
                rule_value = excluded.rule_value,
                source = excluded.source,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, item.value, source),
        )
        row = conn.execute(
            "SELECT id FROM rules WHERE rule_type = 'requirement_rule' AND rule_key = ?",
            (key,),
        ).fetchone()
        if row:
            link_tag(conn, tag_key, "rules", int(row[0]), source)
        if cursor.rowcount:
            count += 1
    return count


def import_workspace(args: argparse.Namespace) -> None:
    workspace = args.workspace
    requirement_slug = workspace.name
    knowledge_dir = workspace / "knowledge"
    if not knowledge_dir.is_dir():
        raise ValueError(f"Knowledge directory not found: {knowledge_dir}")
    open_questions = parse_markdown_items(
        knowledge_dir / "open_questions.md",
        "pending",
        f"workspace:{requirement_slug}/knowledge/open_questions.md",
    )
    if open_questions:
        questions = "\n".join(f"- {item.value}" for item in open_questions)
        raise ValueError(
            "Unconfirmed knowledge is not allowed. Resolve or remove open_questions.md before importing:\n"
            f"{questions}"
        )

    tag_key = f"module.{requirement_slug}"
    source = f"workspace:{requirement_slug}"
    decisions_source = f"{source}/knowledge/decisions.md"

    with sqlite3.connect(DB_PATH) as conn:
        ensure_tag(conn, tag_key, requirement_slug, "module", source)

        imported = 0
        skipped = 0
        explicit_tag_links = 0
        tags_by_decision = parse_explicit_tags(knowledge_dir / "tags.md")
        if tags_by_decision:
            conn.execute(
                """
                DELETE FROM knowledge_tag_links
                WHERE source = ? AND tag_key != ?
                """,
                (decisions_source, tag_key),
            )
        path = knowledge_dir / "decisions.md"
        for item in parse_markdown_items(path, "confirmed", decisions_source):
            created, decision_id = insert_decision(conn, item, tag_key)
            explicit_tag_links += link_explicit_tags(
                conn,
                item.value,
                decision_id,
                tags_by_decision,
                f"{source}/knowledge/tags.md",
            )
            if created:
                imported += 1
            else:
                skipped += 1

        rules_count = import_rules(conn, knowledge_dir / "rules.md", requirement_slug, tag_key)
        conn.commit()

    print(
        "Imported workspace knowledge: "
        f"decisions={imported}, skipped={skipped}, rules_upserted={rules_count}, "
        f"explicit_tag_links={explicit_tag_links}, tag={tag_key}"
    )


def list_by_tag(args: argparse.Namespace) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT l.target_type, l.target_id
            FROM knowledge_tag_links l
            WHERE l.tag_key = ?
            ORDER BY l.target_type, l.target_id
            """,
            (args.tag,),
        ).fetchall()
        for target_type, target_id in rows:
            if target_type not in SEARCH_TABLES:
                print(f"Skipped unsupported target type: {target_type}#{target_id}")
                continue
            record = conn.execute(f"SELECT * FROM {target_type} WHERE id = ?", (target_id,)).fetchone()
            columns = [col[1] for col in conn.execute(f"PRAGMA table_info({target_type})").fetchall()]
            data = dict(zip(columns, record)) if record else {}
            print(f"{target_type}#{target_id}: {data}")


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [col[1] for col in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def row_to_dict(columns: list[str], row: sqlite3.Row) -> dict[str, Any]:
    return {column: row[column] for column in columns}


def fetch_tags_for_record(conn: sqlite3.Connection, table: str, record_id: int) -> list[str]:
    rows = conn.execute(
        """
        SELECT tag_key
        FROM knowledge_tag_links
        WHERE target_type = ? AND target_id = ?
        ORDER BY tag_key
        """,
        (table, record_id),
    ).fetchall()
    return [row["tag_key"] for row in rows]


def build_keyword_where(columns: list[str], keywords: list[str], match_all: bool) -> tuple[str, list[str]]:
    groups: list[str] = []
    params: list[str] = []
    for keyword in keywords:
        column_checks = [f"{column} LIKE ?" for column in columns]
        groups.append("(" + " OR ".join(column_checks) + ")")
        params.extend([f"%{keyword}%"] * len(columns))
    return f" {'AND' if match_all else 'OR'} ".join(groups), params


def search_records(args: argparse.Namespace) -> list[dict[str, Any]]:
    tables = args.table or DEFAULT_SEARCH_TABLES
    keywords = [keyword for keyword in args.keyword if keyword]
    if not keywords:
        raise ValueError("At least one --keyword value is required.")

    results: list[dict[str, Any]] = []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        for table in tables:
            searchable_columns = SEARCH_TABLES[table]
            columns = table_columns(conn, table)
            where_sql, params = build_keyword_where(searchable_columns, keywords, args.all)
            filters = [where_sql]
            if table == "decisions" and args.status:
                filters.append("status = ?")
                params.append(args.status)
            if args.source:
                filters.append("source LIKE ?")
                params.append(f"%{args.source}%")
            sql = f"""
            SELECT *
            FROM {table}
            WHERE {' AND '.join(filters)}
            ORDER BY id DESC
            LIMIT ?
            """
            params.append(args.limit)
            rows = conn.execute(sql, params).fetchall()
            for row in rows:
                record = row_to_dict(columns, row)
                item = {
                    "table": table,
                    "id": record.get("id"),
                    "record": record,
                }
                if args.with_tags and record.get("id") is not None:
                    item["tags"] = fetch_tags_for_record(conn, table, int(record["id"]))
                results.append(item)
    return results


def compact_record(table: str, record: dict[str, Any]) -> str:
    if table == "decisions":
        return f"{record['topic']} | {record['decision']} | {record['status']} | {record.get('source') or ''}"
    if table == "rules":
        return f"{record['rule_type']} | {record['rule_key']} | {record['rule_value']} | {record.get('source') or ''}"
    if table == "glossary":
        return f"{record['term']} | {record['definition']} | {record.get('aliases') or '[]'} | {record.get('source') or ''}"
    if table == "case_patterns":
        return (
            f"{record['pattern_key']} | {record.get('group_name') or ''} | "
            f"{record['title_pattern']} | {record.get('notes') or ''} | {record.get('source') or ''}"
        )
    if table == "api_conventions":
        return f"{record['convention_key']} | {record['convention_value']} | {record.get('source') or ''}"
    if table == "conflicts":
        return (
            f"{record['topic']} | old={record.get('old_value') or ''} | "
            f"new={record.get('new_value') or ''} | {record['resolution_status']} | {record.get('source') or ''}"
        )
    if table == "tags":
        return f"{record['tag_key']} | {record['tag_name']} | {record['tag_type']} | {record.get('source') or ''}"
    return str(record)


def print_search_results(results: list[dict[str, Any]], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    if not results:
        print("No knowledge hits.")
        return
    for item in results:
        tags = item.get("tags")
        tag_suffix = f" tags={','.join(tags)}" if tags else ""
        print(f"{item['table']}#{item['id']}: {compact_record(item['table'], item['record'])}{tag_suffix}")


def search(args: argparse.Namespace) -> None:
    results = search_records(args)
    print_search_results(results, args.format)


def supersede_decision(args: argparse.Namespace) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT id, decision, status FROM decisions WHERE id = ?", (args.id,)).fetchone()
        if row is None:
            raise ValueError(f"Decision not found: {args.id}")
        conn.execute(
            """
            UPDATE decisions
            SET status = 'superseded'
            WHERE id = ?
            """,
            (args.id,),
        )
        conn.commit()
    print(f"Superseded decision#{args.id}: {row[1]}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import and inspect local workspace knowledge.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser("import-workspace", help="Import workspace/<slug>/knowledge into SQLite")
    import_parser.add_argument("--workspace", required=True, type=Path)
    import_parser.set_defaults(func=import_workspace)

    list_parser = subparsers.add_parser("list-tag", help="List knowledge linked to a tag")
    list_parser.add_argument("--tag", required=True)
    list_parser.set_defaults(func=list_by_tag)

    search_parser = subparsers.add_parser("search", help="Search persisted knowledge by keyword")
    search_parser.add_argument(
        "--keyword",
        required=True,
        action="append",
        help="Keyword to search. Repeat for multiple keywords.",
    )
    search_parser.add_argument(
        "--all",
        action="store_true",
        help="Require every keyword to match somewhere in the same record.",
    )
    search_parser.add_argument(
        "--table",
        action="append",
        choices=sorted(SEARCH_TABLES),
        help="Table to search. Repeat to search multiple tables. Defaults to common knowledge tables.",
    )
    search_parser.add_argument(
        "--status",
        choices=["confirmed", "pending", "superseded"],
        help="Filter decisions by status.",
    )
    search_parser.add_argument("--source", help="Filter records by source substring.")
    search_parser.add_argument("--limit", type=int, default=50, help="Maximum rows per table.")
    search_parser.add_argument("--with-tags", action="store_true", help="Include linked tag keys.")
    search_parser.add_argument("--format", choices=["text", "json"], default="text")
    search_parser.set_defaults(func=search)

    supersede_parser = subparsers.add_parser("supersede-decision", help="Mark a decision as superseded")
    supersede_parser.add_argument("--id", required=True, type=int)
    supersede_parser.set_defaults(func=supersede_decision)

    return parser


def main() -> None:
    ensure_knowledge_db()
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
