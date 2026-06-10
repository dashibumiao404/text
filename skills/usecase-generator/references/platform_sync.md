# 平台同步规范

平台专题是正式用例载体，JSON 是本地草稿和同步账本，Excel 是用户确认前的评审产物。

## 默认流程

1. 先生成或修订本地 JSON 草稿：`workspace/<专题名>/test_case/cases.json`。
2. 用户确认草稿后，生成平台同步计划：
   - `uv run case-sync --input workspace/<专题名>/test_case/cases.json --topic-id <topic_id>`
   - 如果平台还没有专题，先让用户确认专题名称；提交时使用 `--create-topic-name "专题名称"` 创建专题并同步。
3. 必须向用户说明同步计划中的新增、修改、删除、专题关联数量。
4. 只有用户明确确认提交平台后，才允许执行：
   - `uv run case-sync --input workspace/<专题名>/test_case/cases.json --topic-id <topic_id> --apply`
5. 平台提交成功后，必须由程序把平台返回的 `case_id`、`group_id`、`topic_id`、`sync_status` 回写到 JSON。

## 二次确认闸门

涉及以下任一情况，必须再次向用户确认，且执行命令必须带对应确认参数：

1. 创建专题：
   - 确认内容：专题名。
   - 参数：`--confirm-create-topic`
2. 删除平台用例：
   - 确认内容：删除范围和删除原因。
   - 参数：`--confirm-delete`
3. 修改平台用例数量大于 5 条：
   - 确认内容：修改数量和影响范围。
   - 参数：`--confirm-large-update`

这些二次确认不能由 agent 自己推断，必须来自用户明确确认。

## 强制约束

1. 没有用户确认，不执行带 `--apply` 的平台写入。
2. 必须使用项目工具，不允许手动拼平台接口请求、手写 HTTP 请求或临时脚本绕过工具。
3. 平台查询必须使用 `case-api` 或 `agent-context`。
4. 平台写入必须使用 `case-sync` 或 `case-api` 已封装命令。
5. 草稿查看、修改、校验、导出必须使用 `case-draft` 或 `export-cases-excel`。
6. 知识检索和落库必须使用 `knowledge-store`。
7. 删除平台用例必须显式启用 `--sync-delete` 并提供删除原因；默认不删除平台数据。
8. 已同步用例必须以平台 `case_id` 为准，不能只靠标题匹配更新。
9. 平台列定义必须通过 `uv run case-api columns` 读取，不硬编码新增列。
10. 平台账号密码从 `.env` 或环境变量读取，不在命令行里明文传账号密码；推荐变量为 `CASE_API_USERNAME`、`CASE_API_PASSWORD`。
11. 平台写入后的 ID 回写必须由 `case-sync` 程序自动完成，agent 不手工编辑 `case_id`、`topic_id`。
12. 普通一致性审计禁止带 `--sync-delete`，避免把“检查是否一致”和“检查删除范围”混在一起。
13. 只有用户明确要求检查删除范围或确认删除时，才允许使用 `--sync-delete`。

## 常用命令

生成同步计划：

```bash
uv run case-sync --input workspace/<专题名>/test_case/cases.json --topic-id <topic_id>
```

普通一致性审计也使用同一条命令，不带删除参数：

```bash
uv run case-sync --input workspace/<专题名>/test_case/cases.json --topic-id <topic_id>
```

检查删除计划时必须单独执行，并先说明这是删除范围检查：

```bash
uv run case-sync \
  --input workspace/<专题名>/test_case/cases.json \
  --topic-id <topic_id> \
  --sync-delete \
  --delete-reason "<删除原因>"
```

用户确认后同步已有专题：

```bash
uv run case-sync --input workspace/<专题名>/test_case/cases.json --topic-id <topic_id> --apply
```

用户确认后创建专题并同步：

```bash
uv run case-sync \
  --input workspace/<专题名>/test_case/cases.json \
  --create-topic-name "<专题名>" \
  --confirm-create-topic \
  --apply
```

仅试探同步一条：

```bash
uv run case-sync --input workspace/<专题名>/test_case/cases.json --only-index 1 --topic-id <topic_id> --apply
```
