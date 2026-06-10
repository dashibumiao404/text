from __future__ import annotations

import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "knowledge" / "knowledge.db"


SCHEMA_SQL = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_type TEXT NOT NULL,
    rule_key TEXT NOT NULL,
    rule_value TEXT NOT NULL,
    source TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(rule_type, rule_key)
);

CREATE TABLE IF NOT EXISTS glossary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    term TEXT NOT NULL UNIQUE,
    definition TEXT NOT NULL,
    aliases TEXT DEFAULT '[]',
    source TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    decision TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'confirmed',
    source TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS case_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_key TEXT NOT NULL UNIQUE,
    group_name TEXT,
    trigger_keywords TEXT NOT NULL DEFAULT '[]',
    title_pattern TEXT NOT NULL,
    precondition_pattern TEXT NOT NULL DEFAULT '[]',
    step_pattern TEXT NOT NULL DEFAULT '[]',
    expected_pattern TEXT NOT NULL DEFAULT '[]',
    notes TEXT,
    source TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conflicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    resolution_status TEXT NOT NULL DEFAULT 'open',
    source TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS api_conventions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    convention_key TEXT NOT NULL UNIQUE,
    convention_value TEXT NOT NULL,
    source TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_key TEXT NOT NULL UNIQUE,
    tag_name TEXT NOT NULL,
    tag_type TEXT NOT NULL,
    description TEXT,
    aliases TEXT DEFAULT '[]',
    source TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS knowledge_tag_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_key TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    source TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tag_key, target_type, target_id)
);
"""


SEED_SQL = [
    (
        "INSERT OR IGNORE INTO rules (rule_type, rule_key, rule_value, source) VALUES (?, ?, ?, ?)",
        (
            "output_format",
            "case_table_header",
            "分组 | 标题 | 等级 | 前置条件 | 步骤 | 预期结果 | 类型 | 备注",
            "project_init",
        ),
    ),
    (
        "INSERT OR IGNORE INTO rules (rule_type, rule_key, rule_value, source) VALUES (?, ?, ?, ?)",
        (
            "field_rule",
            "preconditions_numbering",
            "前置条件使用 1. 2. 3. 自然编号",
            "project_init",
        ),
    ),
    (
        "INSERT OR IGNORE INTO rules (rule_type, rule_key, rule_value, source) VALUES (?, ?, ?, ?)",
        (
            "field_rule",
            "steps_numbering",
            "步骤使用 [1] [2] [3] 编号",
            "project_init",
        ),
    ),
    (
        "INSERT OR IGNORE INTO rules (rule_type, rule_key, rule_value, source) VALUES (?, ?, ?, ?)",
        (
            "field_rule",
            "expected_numbering",
            "预期结果使用 [1] [2] [3] 编号",
            "project_init",
        ),
    ),
    (
        "INSERT OR IGNORE INTO glossary (term, definition, aliases, source) VALUES (?, ?, ?, ?)",
        (
            "分组",
            "用例所属模块路径，推荐格式为 一级模块/二级模块",
            '["模块路径"]',
            "project_init",
        ),
    ),
    (
        "INSERT OR IGNORE INTO glossary (term, definition, aliases, source) VALUES (?, ?, ?, ?)",
        (
            "等级",
            "测试优先级，当前使用 P1/P2/P3",
            '["优先级"]',
            "project_init",
        ),
    ),
    (
        "INSERT OR IGNORE INTO case_patterns (pattern_key, group_name, trigger_keywords, title_pattern, precondition_pattern, step_pattern, expected_pattern, notes, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "map-aggregation-basic",
            "监控平台/地图统计",
            '["聚合", "统计", "地图"]',
            "维度聚合数据校验",
            '["存在多个维度的基础数据"]',
            '["执行触发动作", "查看地图或统计面板"]',
            '["目标维度统计正确", "各维度汇总值与总数一致"]',
            "聚合统计通用模板",
            "project_init",
        ),
    ),
    (
        "INSERT OR IGNORE INTO decisions (topic, decision, status, source) VALUES (?, ?, ?, ?)",
        (
            "初始知识库方案",
            "采用 SQLite 作为知识库存储，配合 Python uv 工具读写与检索",
            "confirmed",
            "project_init",
        ),
    ),
    (
        "INSERT OR IGNORE INTO api_conventions (convention_key, convention_value, source) VALUES (?, ?, ?)",
        (
            "login_first",
            "先 POST /api/v1/auth/login，后续所有受保护接口都带 Authorization: Bearer <token>",
            "user_input",
        ),
    ),
    (
        "INSERT OR IGNORE INTO api_conventions (convention_key, convention_value, source) VALUES (?, ?, ?)",
        (
            "payload_data",
            "业务数据统一从 payload.data 读取，不直接取顶层",
            "user_input",
        ),
    ),
    (
        "INSERT OR IGNORE INTO api_conventions (convention_key, convention_value, source) VALUES (?, ?, ?)",
        (
            "pagination_rule",
            "分页接口统一包含 pagination",
            "user_input",
        ),
    ),
    (
        "INSERT OR IGNORE INTO api_conventions (convention_key, convention_value, source) VALUES (?, ?, ?)",
        (
            "list_shape_rule",
            "列表返回大多是 data.list，只有用例 excel 视图是 data.rows",
            "user_input",
        ),
    ),
    (
        "INSERT OR IGNORE INTO tags (tag_key, tag_name, tag_type, description, aliases, source) VALUES (?, ?, ?, ?, ?, ?)",
        (
            "domain.case_management",
            "用例管理",
            "domain",
            "测试用例的查询、导入、编辑、删除、评审相关知识域",
            '["测试用例", "case"]',
            "project_init",
        ),
    ),
    (
        "INSERT OR IGNORE INTO tags (tag_key, tag_name, tag_type, description, aliases, source) VALUES (?, ?, ?, ?, ?, ?)",
        (
            "module.case_list",
            "用例列表",
            "module",
            "测试用例列表、excel 视图、分页、筛选、检索",
            '["cases", "列表", "excel视图"]',
            "project_init",
        ),
    ),
    (
        "INSERT OR IGNORE INTO tags (tag_key, tag_name, tag_type, description, aliases, source) VALUES (?, ?, ?, ?, ?, ?)",
        (
            "module.case_group",
            "用例分组",
            "module",
            "测试用例分组树、脑图、group_id 映射",
            '["分组", "group", "脑图"]',
            "project_init",
        ),
    ),
    (
        "INSERT OR IGNORE INTO tags (tag_key, tag_name, tag_type, description, aliases, source) VALUES (?, ?, ?, ?, ?, ?)",
        (
            "module.case_column",
            "用例列定义",
            "module",
            "extra_data 对应的动态列定义",
            '["列", "column", "extra_data"]',
            "project_init",
        ),
    ),
    (
        "INSERT OR IGNORE INTO tags (tag_key, tag_name, tag_type, description, aliases, source) VALUES (?, ?, ?, ?, ?, ?)",
        (
            "module.review_topic",
            "专题评审",
            "module",
            "专题、评审状态、活动轨迹、case-links",
            '["review", "topic", "评审"]',
            "project_init",
        ),
    ),
    (
        "INSERT OR IGNORE INTO tags (tag_key, tag_name, tag_type, description, aliases, source) VALUES (?, ?, ?, ?, ?, ?)",
        (
            "action.query",
            "查询",
            "action",
            "查询、读取、查看、检索类操作",
            '["读取", "查看", "检索", "搜索"]',
            "project_init",
        ),
    ),
    (
        "INSERT OR IGNORE INTO tags (tag_key, tag_name, tag_type, description, aliases, source) VALUES (?, ?, ?, ?, ?, ?)",
        (
            "view.excel",
            "Excel视图",
            "view",
            "用例 excel 返回结构 data.header + data.rows",
            '["excel", "rows"]',
            "project_init",
        ),
    ),
    (
        "INSERT OR IGNORE INTO tags (tag_key, tag_name, tag_type, description, aliases, source) VALUES (?, ?, ?, ?, ?, ?)",
        (
            "field.pagination",
            "分页",
            "field",
            "分页接口统一包含 pagination",
            '["page", "size", "pagination"]',
            "project_init",
        ),
    ),
    (
        "INSERT OR IGNORE INTO tags (tag_key, tag_name, tag_type, description, aliases, source) VALUES (?, ?, ?, ?, ?, ?)",
        (
            "field.payload_data",
            "payload.data",
            "field",
            "业务数据统一从 payload.data 提取",
            '["data", "payload.data"]',
            "project_init",
        ),
    ),
    (
        "INSERT OR IGNORE INTO knowledge_tag_links (tag_key, target_type, target_id, weight, source) VALUES (?, ?, ?, ?, ?)",
        ("field.payload_data", "api_conventions", 2, 1.0, "project_init"),
    ),
    (
        "INSERT OR IGNORE INTO knowledge_tag_links (tag_key, target_type, target_id, weight, source) VALUES (?, ?, ?, ?, ?)",
        ("field.pagination", "api_conventions", 3, 1.0, "project_init"),
    ),
    (
        "INSERT OR IGNORE INTO knowledge_tag_links (tag_key, target_type, target_id, weight, source) VALUES (?, ?, ?, ?, ?)",
        ("view.excel", "api_conventions", 4, 1.0, "project_init"),
    ),
    (
        "INSERT OR IGNORE INTO knowledge_tag_links (tag_key, target_type, target_id, weight, source) VALUES (?, ?, ?, ?, ?)",
        ("module.case_list", "case_patterns", 1, 0.8, "project_init"),
    ),
]


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA_SQL)
        for sql, params in SEED_SQL:
            conn.execute(sql, params)
        conn.commit()
    print(f"Initialized knowledge DB at {DB_PATH}")


if __name__ == "__main__":
    main()
