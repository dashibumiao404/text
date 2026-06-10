# 平台查询约定

如果需要从现有系统中读取测试用例信息，遵循以下规则。

## API 约定

1. 先登录：
   - `POST /api/v1/auth/login`
   - 请求体为 `username` + `password_hash`
2. 登录后所有受保护接口带：
   - `Authorization: Bearer <token>`
3. 业务数据只从 `payload.data` 取。
4. 分页信息统一看 `pagination`。
5. 列表数据默认在 `data.list`，只有用例 excel 视图在 `data.rows`。

## 推荐工具

优先使用项目工具，不要手工拼接口：

```bash
uv run case-api columns
uv run case-api groups
uv run case-api cases
uv run case-api all-cases
uv run case-api snapshot
uv run case-api review-topics
```

如果上层 agent 只是要“按约定拉一份当前系统测试用例全量上下文”，优先使用：

```bash
uv run case-api snapshot --return-type excel
```

如果还要专题信息：

```bash
uv run case-api snapshot --return-type excel --include-review-topics
```

如果还要专题下 case-links / case-reviews / activity：

```bash
uv run case-api snapshot --return-type excel --include-review-topics --include-topic-details
```

如果未发现 OpenAPI JSON，不要伪造接口定义，要明确提示并继续基于已知接口知识与用户输入推进。
