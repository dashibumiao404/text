# 工作区规范

每个需求必须使用独立工作区目录，不能把不同需求的原文、草稿、Excel 和知识沉淀混在同一个 `output/` 文件里。

## 目录结构

```text
workspace/
  <专题名>/
    original_requirement/
      requirement.md
      changes.md
      confirmations.md
      open_questions.to_confirm.md
    test_case/
      cases.json
      sync_plan.json
      sync_result.json
      excel/
        cases.xlsx
    knowledge/
      decisions.md
      rules.md
```

## 命名规则

1. `<专题名>` 必须使用测试管理平台专题名；专题名就是工作区文件夹名。
2. 同一需求持续修订必须复用同一个专题名文件夹。
3. 新需求必须新建独立专题名文件夹，避免覆盖历史产物。
4. 如果用户没有指定专题名，必须先询问用户；不能自行生成文件夹名并提交平台。
5. 历史临时目录如 `task_guard` 只作为迁移前兼容目录；后续继续维护时应迁移到专题名目录，例如 `workspace/1V1控车守护/`。

## 文件职责

1. `original_requirement/`
   - 保存用户原始需求、补充说明、确认记录。
2. `original_requirement/requirement.md`
   - 保存最初需求原文或原始需求摘要。
   - 不写测试用例，不写稳定知识结论，不写平台同步结果。
   - 如果原文很长，可以先保存摘要，但必须标注“原文未完整落盘”。
3. `original_requirement/changes.md`
   - 保存需求后续变更记录。
   - 只记录已经由用户明确提出或确认的变更。
   - 每条变更应能追溯到对用例或知识口径的影响。
4. `original_requirement/confirmations.md`
   - 保存用户对关键口径、同步平台、删除、批量修改等动作的明确确认。
   - 平台二次确认也应记录在这里，例如创建专题名、删除原因、修改数量确认。
5. `original_requirement/open_questions.to_confirm.md`
   - 保存待用户确认的问题。
   - 不允许放入 `knowledge/`。
   - 不允许导入知识库。
   - 问题确认后，应移入 `confirmations.md` 或 `changes.md`，并从本文件删除。
6. `test_case/cases.json`
   - 本地草稿和平台同步账本。
   - 平台同步后由程序写回 `case_id`、`group_id`、`topic_id`、`sync_status`。
7. `test_case/excel/cases.xlsx`
   - 用户确认前的评审产物。
   - Excel 只作为输出，不作为输入。
8. `knowledge/`
   - 保存稳定口径和确认结论。
   - 未确认问题不允许放入 `knowledge/` 并落库。

## 常用命令

```bash
uv run case-draft validate --input workspace/<专题名>/test_case/cases.json
uv run case-draft export --input workspace/<专题名>/test_case/cases.json --output workspace/<专题名>/test_case/excel/cases.xlsx
uv run case-sync --input workspace/<专题名>/test_case/cases.json --topic-id <topic_id>
```
