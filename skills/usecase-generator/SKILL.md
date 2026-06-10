---
name: usecase-generator
description: 根据用户提供的需求、补充说明、已有格式样例和 SQLite 知识库生成结构化测试用例；适用于需求澄清、生成或修订测试用例、输出 JSON/Excel、同步测试管理平台专题、复用既有知识口径的场景。
---

# Use Case Generator

用于把需求文本转成固定格式测试用例，并按“需求澄清 -> JSON/Excel 草稿 -> 用户确认 -> 平台同步 -> 知识落库提示”的流程推进。

## 何时使用

当用户提出以下需求时使用：

- 根据需求生成测试用例。
- 根据新增说明补充或修订用例。
- 按既定表头输出测试点。
- 把本地用例同步到测试管理平台专题。
- 复用、检查或沉淀历史知识口径。

## 核心流程

1. 先理解需求，不急着写用例。
2. 新需求开始时，先查历史知识是否已落库：
   - `uv run knowledge-store search --keyword "需求关键词"`
   - 必须告诉用户命中哪些历史知识、是否未命中、是否需要沿用旧口径。
   - 知识查询必须使用 `knowledge-store` 或 `agent-context` 封装工具；如果能力不够，先扩展工具，不能临时写 SQLite/Python 查询脚本作为常规降级。
3. 如果没有专题名，先问用户；专题名就是工作区文件夹名。
4. 澄清到可以产出草稿后，生成本地 JSON 和 Excel：
   - `workspace/<专题名>/test_case/cases.json`
   - `workspace/<专题名>/test_case/excel/cases.xlsx`
5. 用户确认或继续澄清；修改时先改 JSON，再重新导出 Excel。
6. 只有用户明确确认“同步平台”后，才生成平台同步计划。
7. 同步计划必须展示新增、修改、删除、专题关联数量。
8. 满足平台写入二次确认闸门后，才执行平台同步。
9. 平台同步后由 `case-sync` 自动回写 `case_id`、`group_id`、`topic_id`、`sync_status`。
10. 同步平台成功后，必须主动提示用户发起知识落库；如果仍有未确认项，明确提示“平台已同步，但知识不能落库”。

完整流程见 `references/workflow.md`。

## 输出格式

默认表头固定为：

`分组 | 标题 | 等级 | 前置条件 | 步骤 | 预期结果 | 类型 | 备注`

除非用户明确要求，否则不要改动字段顺序，不新增列。

用例格式、讲人话规则和文件位置要求见 `references/usecase_format.md`。

## 工作区

每个需求必须使用独立工作区：

```text
workspace/<专题名>/
  original_requirement/
  test_case/
    cases.json
    sync_plan.json
    sync_result.json
    excel/
      cases.xlsx
  knowledge/
```

专题名就是文件夹名。历史临时目录如 `task_guard` 只作为迁移前兼容目录；后续继续维护应使用平台专题名目录，例如 `workspace/1V1控车守护/`。

详细目录职责见 `references/workspace.md`。

## 用例硬规则

1. 用例必须是可执行 case，不是需求描述。
2. 前置条件必须给出具体样本，例如账号A、账号B、车辆V1、时间60秒、守护人数0。
3. 步骤必须明确执行者、入口、对象和动作。
4. 预期结果必须明确可判定，涉及数量必须给出具体数值。
5. 合用例必须先构造明确输入组合，再给出明确汇总结果。
6. 未确认规则只能临时写入用例 `备注` 供评审，不能写入 `knowledge/` 或导入知识库；必须先找用户强制确认。
7. 用例必须讲人话，面向测试人员执行，不写研发视角、接口视角或代号式表达。
8. 禁止在前置条件、步骤、预期结果中使用导致不可执行或不可判定的泛化词，除非同一单元格内已经给出明确样本：

`多个`、`若干`、`相关`、`正常`、`按需求口径`、`符合需求定义`、`按产品定义`、`需要接收的管理员`、`任意点位`、`至少1名`、`A或B或C`

## 平台同步硬规则

平台专题是正式用例载体，JSON 是本地草稿和同步账本，Excel 是用户确认前的评审产物。

1. 没有用户确认，不执行带 `--apply` 的平台写入。
2. 必须使用项目工具，不允许手动拼平台接口请求、手写 HTTP 请求或临时脚本绕过工具。
3. 平台查询必须使用 `case-api` 或 `agent-context`。
4. 平台写入必须使用 `case-sync` 或 `case-api` 已封装命令。
5. 草稿查看、修改、校验、导出必须使用 `case-draft` 或 `export-cases-excel`。
6. 知识检索和落库必须使用 `knowledge-store`。
   - 如果 `uv run` 因 cache 权限失败，使用 `UV_CACHE_DIR=/tmp/uv-cache uv run ...` 重试；不要因此绕过知识库工具。
7. 创建专题、删除用例、修改超过 5 条用例必须二次确认，并使用 `case-sync` 对应确认参数。
8. 删除平台用例必须显式启用 `--sync-delete` 并提供删除原因；默认不删除平台数据。
9. 已同步用例必须以平台 `case_id` 为准，不能只靠标题匹配更新。
10. 平台账号密码从 `.env` 或环境变量读取，不在命令行里明文传账号密码。
11. 平台写入后的 ID 回写必须由 `case-sync` 程序自动完成，agent 不手工编辑 `case_id`、`topic_id`。
12. 普通一致性审计禁止带 `--sync-delete`；只有用户明确要求检查删除范围或确认删除时，才允许使用。

详细同步命令、二次确认闸门见 `references/platform_sync.md`。

## 常用命令

校验草稿：

```bash
uv run case-draft validate --input workspace/<专题名>/test_case/cases.json
```

导出 Excel：

```bash
uv run case-draft export --input workspace/<专题名>/test_case/cases.json --output workspace/<专题名>/test_case/excel/cases.xlsx
```

生成平台同步计划：

```bash
uv run case-sync --input workspace/<专题名>/test_case/cases.json --topic-id <topic_id>
```

用户确认后同步平台：

```bash
uv run case-sync --input workspace/<专题名>/test_case/cases.json --topic-id <topic_id> --apply
```

查询平台上下文：

```bash
uv run case-api columns
uv run case-api groups
uv run case-api cases --return-type excel --keyword "关键词"
uv run case-api review-topics
```

更多平台查询约定见 `references/api_context.md`。

## 生成规则

1. 分组使用 `模块/子模块` 形式，保持简洁稳定。
2. 标题用一句话描述校验目标，避免空泛标题，如“功能校验”。
3. 等级默认按风险给 `P1/P2/P3`，高风险统计、状态流转、核心链路优先 `P1`。
4. 前置条件只保留执行该用例必需的信息，必须给出明确账号、车辆、数据、状态、时间或配置值。
5. 步骤只写能触发校验结果的关键动作；动作必须可由测试人员实际执行，且能对应到预期结果。
6. 预期结果必须明确、可验证、可回溯到前置条件和步骤。

生成前后必须按 `references/checklist.md` 检查。

## 何时读取 References

- 需求流程、知识落库提示：读 `references/workflow.md`。
- 专题名、目录结构、文件职责：读 `references/workspace.md`。
- 用例表头、讲人话、语义规范：读 `references/usecase_format.md`。
- 平台同步、二次确认、ID 回写：读 `references/platform_sync.md`。
- 平台查询接口和工具：读 `references/api_context.md`。
- 知识标签规则：读 `references/tagging.md`。
- 生成前后自查：读 `references/checklist.md`。

## 结果风格

默认直接输出结果，不加无关解释。
