---
name: knowledge-store
description: 为测试用例生成项目维护和查询 SQLite 知识库，并强制通过封装好的 Python uv 工具初始化、检索、导入和扩展；适用于查询历史知识、确认业务口径、沉淀字段规范、术语定义、统计口径、接口约定、历史结论和场景模板，禁止把临时 SQLite/Python 查询脚本作为常规降级方案。
---

# Knowledge Store

本 skill 定义一个基于 SQLite 的本地知识存储方案，适合和 agent、脚本工具一起工作。

## 为什么这里改用数据库

当前项目需要的不只是保存规则，还需要：
- 固化 agent 的接口调用约定
- 结构化保存用例模式
- 后续支持查询、检索、去重和冲突管理

因此这里优先用 `SQLite`，而不是继续用纯 Markdown/JSONL。

## 存储位置

数据库文件固定为：

`knowledge/knowledge.db`

初始化工具：

`uv run init-knowledge-db`

## 表设计

当前包含以下表：

- `rules`
  保存输出格式、字段规则、统计口径
- `glossary`
  保存术语和别名
- `decisions`
  保存已确认结论
- `case_patterns`
  保存可复用用例模式
- `conflicts`
  保存知识冲突
- `api_conventions`
  保存接口调用约定和返回结构规则
- `tags`
  保存统一标签体系
- `knowledge_tag_links`
  保存标签与知识点的关联关系

## 读取顺序

生成用例前优先读取：

1. `api_conventions`
2. `rules`
3. `glossary`
4. `decisions`
5. `case_patterns`
6. `tags`
7. `knowledge_tag_links`

## 写入原则

1. 只记录稳定、可复用知识。
2. 用户明确确认后，才能把歧义结论写入 `decisions` 或 `rules`。
3. 新旧知识冲突时，先写 `conflicts`，不要静默覆盖。
4. 接口约定变化时，更新 `api_conventions`，不要散落在多个文档里。
5. 所有新知识入库前必须打标签，并建立 `knowledge_tag_links`。

## Workspace 知识落库流程

每个需求先在工作区沉淀 Markdown，再将已确认知识导入 SQLite：

```text
workspace/<requirement_slug>/knowledge/
  decisions.md
  open_questions.md
  rules.md
```

落库规则：

1. `decisions.md`
   - 存放用户已确认口径。
   - 导入 `decisions` 表，`status='confirmed'`。
2. `open_questions.md`
   - 存放待确认问题。
   - 不允许导入数据库。
   - 只要存在未确认条目，`knowledge-store import-workspace` 必须失败并要求先确认。
3. `rules.md`
   - 存放稳定可复用规则。
   - 导入 `rules` 表，`rule_type='requirement_rule'`。
4. 导入时自动创建需求标签：
   - `module.<requirement_slug>`
   - 并写入 `knowledge_tag_links`。
5. 入库前必须先确认：
   - `decisions.md` 中都是已确认结论。
   - `open_questions.md` 为空或不存在。
   - `rules.md` 中都是可复用规则，不是一次性描述。

导入命令：

```bash
uv run knowledge-store import-workspace --workspace workspace/<requirement_slug>
```

查看导入结果：

```bash
uv run knowledge-store list-tag --tag module.<requirement_slug>
```

约束：

1. 不把测试用例全文批量入库；只沉淀稳定规则和确认结论。
2. 未确认问题必须强制向用户确认；确认前不允许落库。
3. 不把用户未确认的推断写成 `confirmed`。
4. 如果新口径与旧知识冲突，先向用户确认冲突结论，再写入 `conflicts` 或更新确认知识；不要静默覆盖。

## 工具约定

本项目通过 `Python + uv` 管理知识库和只读接口工具。

硬约束：

1. 查询知识库必须优先使用 `uv run knowledge-store search ...` 或 `uv run agent-context resolve ...`。
2. 不允许为了省事临时写 `python - <<'PY'`、`sqlite3`、一次性 SQL 脚本来查知识库。
3. 只有在封装工具缺少能力时，先扩展 `tools/knowledge_store.py`，再用工具查询。
4. 如果 `uv run` 因 cache 权限失败，使用 `UV_CACHE_DIR=/tmp/uv-cache uv run ...` 重试；不要因此降级到临时代码。
5. 若工具执行报错，先修工具或补参数；除非用户明确要求临时排障，否则不绕过工具。

当前工具：

- `uv run init-knowledge-db`
  初始化 SQLite 知识库和种子数据
- `uv run knowledge-store import-workspace --workspace workspace/<requirement_slug>`
  将需求工作区中的 `knowledge/` Markdown 导入 SQLite
- `uv run knowledge-store list-tag --tag module.<requirement_slug>`
  查看某个需求标签下的入库知识
- `uv run knowledge-store search --keyword "关键词"`
  查询本地知识库，支持多次传入 `--keyword`
- `uv run knowledge-store search --keyword "无人守护" --keyword "短信" --all --table decisions --status confirmed`
  查询同条知识同时命中多个关键词的已确认结论
- `uv run knowledge-store search --keyword "关键词" --with-tags --format json`
  输出关联标签或机器可读 JSON
- `uv run case-api ...`
  按项目约定查询测试用例相关接口，默认使用 `http://192.168.26.181:10094/` 和 `reporter/reporter`
- `uv run case-api snapshot ...`
  按推荐顺序一次性拉取 agent 所需上下文
- `uv run agent-context infer-tags ...`
  按用户需求推断标签
- `uv run agent-context resolve ...`
  联合知识库和 OpenAPI 做上下文解析
- `uv run export-cases-excel ...`
  只把生成用例输出到本地 Excel，不写平台

## 标签体系

标签采用 `type.name` 结构，当前推荐：

- `domain.*`
- `module.*`
- `action.*`
- `view.*`
- `field.*`

标签设计规则：

1. 一个标签只表达一个稳定概念。
2. 标签名优先英文 key，展示名可中文。
3. 别名写入 `aliases`，不要复制出多个近义标签。
4. 新知识若无法打进现有标签体系，先补标签，再补知识。

## 参考文件

需要了解存储约定时，读取：
- `references/storage_convention.md`
- `references/entry_templates.md`
