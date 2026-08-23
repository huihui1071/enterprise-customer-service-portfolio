# Dify 会话记忆接线清单

目标：将 `workflow/memory-normalizer.js` 的已测试逻辑同步到 Dify 草稿。以下步骤完成前，不把多病例歧义和 10 轮过期计为云端通过。

## 1. 归一化与识别

用 `workflow/memory-normalizer.js` 完整覆盖 Code 节点代码，并保留现有输入：

- `query <- sys.query`
- `active_intent <- conversation.active_intent`
- `pending_action <- conversation.pending_action`
- `case_id_candidate <- conversation.case_id_candidate`
- `confirmed_case_id <- conversation.confirmed_case_id`
- `recent_case_ids <- conversation.recent_case_ids`
- `last_case_confirmed_turn <- conversation.last_case_confirmed_turn`
- `dialog_count <- conversation.turn_index`

在现有输出后新增：

| 输出 | 类型 |
|---|---|
| `case_reference_status_next` | string |
| `recent_case_ids_next` | string |
| `next_turn` | number |

## 2. 每轮计数

在归一化节点后增加变量赋值节点 `记忆-轮次递增`：

```text
turn_index = 归一化与识别.next_turn
```

所有业务分支必须从该节点继续，保证知识问答、澄清、失败和高风险轮次都计数，而不只统计病例查询成功轮次。

## 3. 成功查询写入

在病例 API 返回成功且生成回复前，更新：

```text
confirmed_case_id = 归一化与识别.case_id
active_case_id = 归一化与识别.case_id
recent_case_ids = 归一化与识别.recent_case_ids_next
last_case_confirmed_turn = 归一化与识别.next_turn
case_reference_status = confirmed
active_intent = ""
pending_action = ""
```

说明：只有 API 鉴权成功后才能把病例提升为已确认记忆。

## 4. 多病例歧义

在病例状态分流之前增加条件：

```text
case_reference_status_next == "ambiguous"
```

命中后不得调用病例 API，回复：

```text
你最近查询过多个病例，请明确提供要查询的病例号。
```

同时设置 `pending_action=collect_case_id`、`active_intent=case_status`。

## 5. 过期和切换病例

当 `recent_case_ids_next == "[]"` 且本轮未解析病例号时：

```text
active_case_id = ""
confirmed_case_id = ""
recent_case_ids = "[]"
```

“另一个病例”和超过 10 个用户轮次的回指都进入病例号澄清，不调用病例 API。

## 6. 权限撤销

每次恢复病例引用仍调用 Backend 重新鉴权。病例接口返回统一无权访问结果时：

- 清空 `active_case_id` 和 `confirmed_case_id`。
- 从 `recent_case_ids` 删除被拒绝病例；第一版可保守清空整个数组。
- 不透露病例存在性。
- 输出：`无法访问该病例，请检查病例编号或联系管理员。`

## 7. 验收

1. `node evals/runner/run_dify_normalizer_eval.mjs` 为 `7/7`。
2. `python3 evals/runner/run_memory_contract_eval.py` 为 `15/15`。
3. Dify 浏览器逐条通过多病例歧义、10 轮过期和权限撤销。
4. 检查清单无错误，草稿自动保存。
5. 未经用户明确确认不发布。
