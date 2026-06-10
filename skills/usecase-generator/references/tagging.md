# 标签规则

知识点必须带标签，至少包含以下维度中的一类或多类。

## 标签维度

1. `domain.*`
   - 领域，如 `domain.case_management`
2. `module.*`
   - 模块，如 `module.case_list`、`module.case_group`
3. `action.*`
   - 动作，如 `action.query`
4. `view.*`
   - 视图，如 `view.excel`
5. `field.*`
   - 字段或结构，如 `field.pagination`、`field.payload_data`

## 打标签规则

1. 一个知识点至少 2 个标签：
   - 一个业务标签
   - 一个结构或动作标签
2. 接口约定优先打 `field.*` 和 `action.*`。
3. 场景模板优先打 `module.*` 和 `domain.*`。
4. 用户明确的新口径，进入知识库前必须补标签。
5. 不允许只打专题级粗标签，例如只有 `module.1V1控车守护`；必须补充可复用的碎标签。
6. 禁止在代码或 skill 中写固定标签映射规则；标签必须由 AI 基于当前知识内容逐条分析。
7. 分析后的标签写入 `workspace/<专题名>/knowledge/tags.md`，由 `knowledge-store` 读取并落库。
8. 一条知识可以同时打多个碎标签；标签要能支撑后续检索复用。

## tags.md 格式

每条知识按原文匹配 `decisions.md` 中的一条 decision：

```markdown
- decision: 原始知识文本
- tags: domain.xxx, module.xxx, action.xxx, field.xxx
```

`knowledge-store` 只负责读取 `tags.md` 并写入标签关系，不负责推断标签。

## 查标签规则

1. 先从用户原文抽模块词、动作词、结构词。
2. 优先命中 `module.*`。
3. 再补 `action.*` 和 `field.*`。
4. 如果标签命中不足，必须进入追问流程，不直接生成最终用例。
