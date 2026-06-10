# 条目模板

## `rules` 插入模板

```sql
INSERT INTO rules (rule_type, rule_key, rule_value, source)
VALUES ('field_rule', 'steps_numbering', '步骤使用 [1] [2] [3] 编号', 'user_confirmed');
```

## `glossary` 插入模板

```sql
INSERT INTO glossary (term, definition, aliases, source)
VALUES ('地图统计', '地图页面中的城市/区域/车辆聚合展示', '["地图聚合"]', 'user_confirmed');
```

## `decisions` 插入模板

```sql
INSERT INTO decisions (topic, decision, status, source)
VALUES ('历史任务总数是否包含取消单', '默认不包含', 'confirmed', 'user_confirmed');
```

## `case_patterns` 插入模板

```sql
INSERT INTO case_patterns (
  pattern_key, group_name, trigger_keywords, title_pattern,
  precondition_pattern, step_pattern, expected_pattern, notes, source
) VALUES (
  'task-total-count',
  '监控平台/地图统计',
  '["任务", "取消", "累计"]',
  '任务累计数量与取消逻辑校验',
  '["记录当前历史任务总数", "车辆处于空闲"]',
  '["创建任务并完成", "创建任务并取消", "查看统计数字"]',
  '["完成任务后总数增加", "取消任务后总数保持不变"]',
  '累计统计类模板',
  'user_confirmed'
);
```

## `api_conventions` 插入模板

```sql
INSERT INTO api_conventions (convention_key, convention_value, source)
VALUES ('payload_data', '业务数据统一从 payload.data 读取，不直接取顶层', 'user_confirmed');
```
