# 主流程规范

## 总流程

1. 需求下来后，先做需求理解和澄清，不直接落平台。
2. 新需求开始时，先检索已落库知识：
   - `uv run knowledge-store search --keyword "需求关键词"`
   - 关键词覆盖模块、业务对象、关键动作和核心状态。
   - 必须告诉用户命中哪些历史知识、是否未命中、是否需要沿用旧口径。
3. 如果需求涉及现有系统能力，查询测试用例管理平台上下文：
   - `uv run case-api columns`
   - `uv run case-api groups`
   - `uv run case-api cases --return-type excel --keyword "关键词"`
   - 必要时按 `group_id` 查询已有分组下用例。
   - 必须使用项目工具，不允许手动拼平台接口请求。
4. 对复杂需求，先输出需求理解、拟采用分组、关键口径和需确认问题；用户确认后再落本地用例。
5. 澄清到可以产出草稿后，生成本地 JSON 和 Excel：
   - JSON：`workspace/<专题名>/test_case/cases.json`
   - Excel：`workspace/<专题名>/test_case/excel/cases.xlsx`
6. 把用例草稿交给用户确认；如果用户继续澄清或修改，先改 JSON，再重新导出 Excel。
7. 只有用户明确确认“同步平台”后，才生成平台同步计划。
8. 同步计划必须先展示新增、修改、删除、专题关联数量。
9. 满足二次确认闸门后，才执行平台同步。
10. 平台同步后由程序自动回写 `case_id`、`group_id`、`topic_id`、`sync_status`。
11. 同步平台成功后，必须主动提示用户发起知识落库；提示前先检查 `workspace/<专题名>/knowledge/` 是否只有已确认口径。
12. 如果仍存在未确认项，必须明确提示“平台已同步，但知识不能落库”，并列出需要用户确认的问题。

## 知识落库提示

当一个需求的规则、口径和待确认项都已经闭环时，必须主动提示用户发起落库：

```bash
uv run knowledge-store import-workspace --workspace workspace/<专题名>
uv run knowledge-store list-tag --tag module.<专题名>
```

落库前必须确认：

1. `decisions.md` 只包含已确认结论。
2. `rules.md` 只包含稳定可复用规则。
3. `knowledge/` 中不存在未确认问题。
4. 不把测试用例全文批量导入知识库。

平台同步不等于知识已落库；平台同步成功后也必须执行落库检查和提示。

## 持续修订

后续用户持续补充或修改用例时：

1. 先修订本地 JSON 草稿。
2. 重新导出 Excel 供用户确认。
3. 如果该需求已经绑定平台专题，用 `case-sync` 生成平台变更计划。
4. 普通一致性审计使用 `case-sync --input ... --topic-id ...`，不带 `--sync-delete`。
5. 只有用户明确要求检查删除范围或确认删除时，才使用 `--sync-delete`。
6. 不手工拼平台接口请求，不用临时脚本绕过 `case-sync`、`case-draft`、`knowledge-store`。
