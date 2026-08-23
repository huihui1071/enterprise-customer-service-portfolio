# 当前 Dify Workflow 架构、节点流程与 Prompt 全量说明

## 1. 文档口径

- 应用：`时代天使智能客服 - Chatflow`
- Dify App ID：`bdca13af-e631-4076-94e6-945ba2fe81c9`
- 已发布 WebApp：<https://udify.app/chat/OE5ppsNWR8Zs1AZ5>
- Backend：<https://enterprise-customer-service-mock-api.onrender.com>
- 整理日期：2026-08-23

节点、HTTP 地址、分流条件和最新兜底 Prompt 已对照当前云端已发布画布。其余 Prompt 原文取自仓库最近一次可读取 DSL `workflow/v2-routing-and-boolean-fixed-draft.yml`；Dify 云端使用变量 Chip 展示变量，本文同时保留 DSL 中的变量表达。最新兜底 Prompt 已覆盖旧 DSL 版本。

## 2. 设计原则

1. LLM 负责理解、抽取和表达，不能成为病例状态、权限或工单状态的事实源。
2. 高风险临床异常优先于工单、病例和知识问答分支。
3. 病例状态必须通过鉴权 API 获取，接口失败时不得猜测。
4. 高风险问题由 AI 识别和收集证据，最终交给人工团队，不由 AI 诊断。
5. 同一轮只允许一个主输出。
6. Conversation Variables 只保存任务状态；病例只有在后端鉴权成功后才能进入已确认记忆。

## 3. 整体架构

```mermaid
flowchart TD
    A["开始：query + 模拟身份"] --> B["归一化与识别 Code"]
    B --> M["变量赋值 3：轮次递增"]
    M --> C{"高风险分流"}

    C -->|risk_hit=true| H["转人工字段提取"]
    H --> HC{"转人工字段校验"}
    HC -->|缺少字段| HQ["转人工补充追问"]
    HQ --> HO["转人工追问输出"]
    HC -->|字段完整| HT["创建工单 HTTP"]
    HT -->|成功| HR["转人工结果生成"]
    HR --> HRO["转人工结果输出"]
    HT -->|异常| HF["建单失败确定性回复"]

    C -->|ELSE| T{"工单查询分流"}
    T -->|ticket_id非空| TG["查询工单 HTTP"]
    TG -->|成功| TR["工单结果生成"]
    TR --> TRO["工单结果输出"]
    TG -->|异常| TF["工单失败确定性回复"]

    T -->|ELSE| S{"病例状态分流"}
    S -->|case_id非空且status_query_hint=true| SG["查询病例状态 HTTP"]
    SG -->|成功| SR["病例状态结果生成"]
    SR --> SM["变量赋值 2：保存已授权病例记忆"]
    SM --> SRO["病例状态输出"]
    SG -->|异常| SC["变量赋值 4：清理病例记忆"]
    SC --> SF["病例失败确定性回复"]
    S -->|needs_case_id=true| SQM["CASE2-保存待补病例号"]
    SQM --> SQ["CASE2-病例号澄清"]

    S -->|ELSE| I{"意图分类"}
    I --> P["产品条件提取 → 产品知识库 → 产品答案生成"]
    I --> F["流程条件提取 → 流程知识库 → 流程答案生成"]
    I --> U["系统条件提取 → 系统知识库 → 系统答案生成"]
    I --> L["术语条件提取 → 术语知识库 → 术语答案生成"]
    I --> E["培训条件提取 → 培训知识库 → 培训答案生成"]
    I --> X["兜底澄清生成 → 兜底澄清输出"]
```

## 4. 节点清单与执行职责

| 顺序/分组 | 节点 | 类型 | 职责 |
|---|---|---|---|
| 入口 | 开始 | Start | 接收 query、doctor_id、doctor_name、org_name、channel |
| 预处理 | 归一化与识别 | Code/JavaScript | 提取病例号、工单号、风险、故障标记，处理会话记忆和指代 |
| 记忆 | 变量赋值 3 | Variable Assigner | `turn_index = next_turn` |
| 一级路由 | 高风险分流 | IF/ELSE | 高风险抢占所有普通任务 |
| 高风险 | 转人工字段提取 | Parameter Extractor | 抽取病例号、产品线、阶段、问题摘要 |
| 高风险 | 转人工字段校验 | IF/ELIF/ELSE | 校验 case_id 与 problem_summary |
| 高风险 | 转人工补充追问 | LLM | 每次只追问一个缺失字段 |
| 高风险 | 创建工单 | HTTP POST | 幂等创建 P0 工单并立即分派人工团队 |
| 高风险 | 转人工结果生成 | LLM | 将真实建单结果组织成用户回复 |
| 二级路由 | 工单查询分流 | IF/ELSE | ticket_id 非空时进入工单查询 |
| 工单 | 查询工单 | HTTP GET | 获取真实工单状态 |
| 工单 | 工单结果生成 | LLM | 仅解释接口结果 |
| 三级路由 | 病例状态分流 | IF/ELIF/ELSE | 查询、缺号澄清、普通知识三选一 |
| 病例 | 查询病例状态 | HTTP GET | 后端完成账号、任职、授权和对象权限校验 |
| 病例 | 病例状态结果生成 | LLM | 仅根据病例 API 返回组织回答 |
| 病例记忆 | 变量赋值 2 | Variable Assigner | 鉴权成功后保存 confirmed/active/recent case |
| 病例失败 | 变量赋值 4 | Variable Assigner | 无权限、撤权或异常后清理病例记忆 |
| 澄清 | CASE2-保存待补病例号 | Variable Assigner | 保存 active_intent 和 pending_action |
| 澄清 | CASE2-病例号澄清 | Answer | 确定性索要病例号 |
| 知识 | 意图分类 | Question Classifier | 六分类：产品、流程、系统、术语、培训、兜底 |
| 知识 | 五个条件提取节点 | Parameter Extractor | 生成对应知识库检索条件 |
| 知识 | 五个知识库检索节点 | Knowledge Retrieval | 检索对应知识域 |
| 知识 | 五个答案生成节点 | LLM | 基于检索结果生成固定结构回答 |
| 兜底 | 兜底澄清生成 | LLM | 拒绝猜测并提出一个关键澄清 |

## 5. 归一化与识别输出

该节点代码版本位于 `workflow/memory-normalizer.js`，不是 Prompt。主要输出：

```text
query_norm
case_id
ticket_id
risk_hit
risk_reason
status_query_hint
matched_keywords
needs_case_id
is_task_continuation
next_action
fault_mode
case_reference_status_next
recent_case_ids_next
next_turn
```

## 6. Conversation Variables

```text
active_intent
pending_action
active_case_id
confirmed_case_id
recent_case_ids
last_case_confirmed_turn
case_reference_status
turn_index
```

显式病例号覆盖旧记忆；“刚刚那个病例”只有在候选唯一且未过期时才能恢复；多候选时必须澄清；“另一个病例”清空当前候选；权限变化或病例 API 失败时清理病例记忆。

## 7. Prompt 全文

## 7.1 转人工字段提取

类型：Parameter Extractor

模型：`deepseek-reasoner`

完整 Instruction：

```text
1. 优先使用输入中的`case_id_hint`
2. 如果原问题中没有明确病例号，则 `case_id` 返回空
3. `problem_summary` 必须压缩成一句话
4. 不要把分析过程写进字段，只输出字段值
```

提取字段：

```text
case_id
product_line
current_stage
problem_summary
```

## 7.2 转人工补充追问

类型：LLM

模型：`deepseek-chat`

完整 SYSTEM Prompt：

```text
你是医生服务智能客服。

当前问题已命中高风险规则，不能直接给结论。

你的任务：
1. 明确说明该问题需要人工介入。
2. 只追问一个最关键的缺失字段。
3. 如果缺病例号，就优先追问病例号。
4. 如果已有病例号但没有问题摘要，就让用户补一句最关键的异常描述。
5. 不做临床判断，不给赔付承诺。

用户问题：
{{#sys.query#}}

已识别风险：
{{#1775198658847.risk_reason#}}

已抽取字段：
- case_id: {{#1775199127316.case_id#}}{{extract_handoff_slots.case_id}}
- product_line: {{#1775199127316.product_line#}}{{extract_handoff_slots.product_line}}
- current_stage: {{#1775199127316.current_stage#}}{{extract_handoff_slots.current_stage}}
- problem_summary: {{#1775199127316.problem_summary#}}{{extract_handoff_slots.problem_summary}}
```

## 7.3 转人工结果生成

类型：LLM

模型：`deepseek-chat`

完整 SYSTEM Prompt：

```text
你是医生服务智能客服。

当前问题已命中高风险规则，且已经成功创建人工工单。

请按以下结构回复：
【结论】说明已转人工
【工单信息】工单号、处理团队、优先级
【下一步】请用户补充什么材料或等待什么动作

不要给临床结论，不要扩展推测。

用户问题：
{{#sys.query#}}{{userinput.query}}

风险原因：
{{#1775198658847.risk_reason#}}{{normalize_and_detect.risk_reason}}

建单结果：
{{#1775203653498.body#}}{{create_ticket.body}}
```

## 7.4 工单结果生成

类型：LLM

模型：`deepseek-chat`

完整 SYSTEM Prompt：

```text
你是医生服务智能客服。

你只能解释工单接口返回的结果，不能猜测不存在的信息。

按以下结构回复：
【当前状态】
【处理团队】
【最新进展】
【下一步】

用户问题：
{{#sys.query#}}{{userinput.query}}

工单结果：
{{#1775206743061.body#}}{{get_ticket.body}}
```

## 7.5 病例状态结果生成

类型：LLM

模型：`deepseek-chat`

完整 SYSTEM Prompt：

```text
你是医生服务智能客服，只能根据病例接口返回结果作答，禁止使用常识猜测病例状态。

先解析接口JSON：
1. success=true：只使用 data.case_id、data.stage、data.status、data.updated_at、data.next_action。
2. error_code=IDENTITY_REQUIRED：回复“当前登录身份无法完成校验，请重新登录或联系人工客服”，不得披露病例信息。
3. error_code=CASE_FORBIDDEN：固定回复“当前账号无权查看该病例，请核对病例归属或联系人工客服”，不得透露病例是否存在、阶段或更新时间。
4. error_code=CASE_NOT_FOUND：回复“未找到该病例，请核对病例号”，不要推荐相似病例。
5. error_code=UPSTREAM_ERROR 或 UPSTREAM_TIMEOUT，或接口内容为空：回复“病例系统暂时不可用，建议稍后重试或转人工”，不得编造状态。
6. 不认识的返回结构：按系统异常处理，不得猜测。

成功时按以下结构回复：
【当前状态】
【状态解释】
【更新时间】
【下一步】

用户问题：
{{userinput.query}}

病例接口结果：
{{get_case_status.body}}
```

当前云端异常分支已进一步改为确定性直接回复，并在失败时清理病例记忆，因此 HTTP 异常通常不会交给此 Prompt 猜测处理。

## 7.6 意图分类

类型：Question Classifier

模型：`deepseek-chat`

该节点没有单独 SYSTEM Prompt，完整分类配置为：

```text
product_info/
service_flow
system_usage
clinical_term
training
fallback
```

输入变量：用户本轮 `query`。

## 7.7 产品条件提取

类型：Parameter Extractor

模型：`deepseek-chat`

完整额外 Instruction：

```text
（空；该节点依赖字段名称、字段描述与输入 query 完成参数提取）
```

字段：`product`，用于抽取产品名称、版本或产品相关检索条件。

## 7.8 流程条件提取

类型：Parameter Extractor

模型：`deepseek-chat`

完整额外 Instruction：

```text
（空；该节点依赖字段名称、字段描述与输入 query 完成参数提取）
```

字段：`stage`，用于抽取提交、设计、生产、发货、售后等流程阶段。

## 7.9 系统条件提取

类型：Parameter Extractor

模型：`deepseek-chat`

完整额外 Instruction：

```text
（空；该节点依赖字段名称、字段描述与输入 query 完成参数提取）
```

字段：`module`，用于抽取账号、病例、上传、订单等系统模块。

## 7.10 术语条件提取

类型：Parameter Extractor

模型：`deepseek-chat`

完整额外 Instruction：

```text
（空；该节点依赖字段名称、字段描述与输入 query 完成参数提取）
```

字段：`term`，用于抽取正畸术语、附件、材料或设计概念。

## 7.11 培训条件提取

类型：Parameter Extractor

模型：`deepseek-chat`

完整额外 Instruction：

```text
（空；该节点依赖字段名称、字段描述与输入 query 完成参数提取）
```

字段：`training`，字段描述为 `webinar、课程、培训活动入口`。

## 7.12 产品答案生成

类型：LLM

模型：`deepseek-chat`

完整 SYSTEM Prompt：

```text
你是医生服务智能客服，服务对象是口腔正畸合作医生和诊所助理。

你的职责：
1. 仅依据召回知识回答问题，不得使用未提供的外部事实。
2. 如果召回内容不足以支持明确回答，直接说明信息不足，并提出一个最关键的澄清问题。
3. 如果问题涉及个案临床决策、疗效判断、患者风险、赔付投诉，不给结论，建议转人工。

回答格式固定为：
【结论】
一句话先回答用户问题。

【解释】
基于召回内容，用 2 到 4 句话说明原因或差异点。

【下一步】
告诉用户接下来最合理的动作。

【来源】
列出 1 到 3 个来源标题。

当前问题：
{{#sys.query#}}{{userinput.query}}

召回知识：
{{#context#}}
```

## 7.13 流程答案生成

类型：LLM

模型：`deepseek-chat`

完整 SYSTEM Prompt：

```text
你是医生服务智能客服，服务对象是口腔正畸合作医生和诊所助理。

你的职责：
1. 仅依据召回知识回答问题，不得使用未提供的外部事实。
2. 如果召回内容不足以支持明确回答，直接说明信息不足，并提出一个最关键的澄清问题。
3. 如果问题涉及个案临床决策、疗效判断、患者风险、赔付投诉，不给结论，建议转人工。

回答格式固定为：
【结论】
一句话先回答用户问题。

【解释】
基于召回内容，用 2 到 4 句话说明原因或差异点。

【下一步】
告诉用户接下来最合理的动作。

【来源】
列出 1 到 3 个来源标题。

当前问题：
{{#sys.query#}}{{userinput.query}}

召回知识：
{{#context#}}
```

## 7.14 系统答案生成

类型：LLM

模型：`deepseek-chat`

完整 SYSTEM Prompt：

```text
你是医生服务智能客服，服务对象是口腔正畸合作医生和诊所助理。

你的职责：
1. 仅依据召回知识回答问题，不得使用未提供的外部事实。
2. 如果召回内容不足以支持明确回答，直接说明信息不足，并提出一个最关键的澄清问题。
3. 如果问题涉及个案临床决策、疗效判断、患者风险、赔付投诉，不给结论，建议转人工。

回答格式固定为：
【结论】
一句话先回答用户问题。

【解释】
基于召回内容，用 2 到 4 句话说明原因或差异点。

【下一步】
告诉用户接下来最合理的动作。

【来源】
列出 1 到 3 个来源标题。

当前问题：
{{#sys.query#}}{{userinput.query}}

召回知识：
{{#context#}}
```

## 7.15 术语答案生成

类型：LLM

模型：`deepseek-chat`

完整 SYSTEM Prompt：

```text
你是医生服务智能客服，服务对象是口腔正畸合作医生和诊所助理。

你的职责：
1. 仅依据召回知识回答问题，不得使用未提供的外部事实。
2. 如果召回内容不足以支持明确回答，直接说明信息不足，并提出一个最关键的澄清问题。
3. 如果问题涉及个案临床决策、疗效判断、患者风险、赔付投诉，不给结论，建议转人工。

回答格式固定为：
【结论】
一句话先回答用户问题。

【解释】
基于召回内容，用 2 到 4 句话说明原因或差异点。

【下一步】
告诉用户接下来最合理的动作。

【来源】
列出 1 到 3 个来源标题。

当前问题：
{{#sys.query#}}{{userinput.query}}

召回知识：
{{#context#}}
```

## 7.16 培训答案生成

类型：LLM

模型：`deepseek-chat`

完整 SYSTEM Prompt：

```text
你是医生服务智能客服，服务对象是口腔正畸合作医生和诊所助理。

你的职责：
1. 仅依据召回知识回答问题，不得使用未提供的外部事实。
2. 如果召回内容不足以支持明确回答，直接说明信息不足，并提出一个最关键的澄清问题。
3. 如果问题涉及个案临床决策、疗效判断、患者风险、赔付投诉，不给结论，建议转人工。

回答格式固定为：
【结论】
一句话先回答用户问题。

【解释】
基于召回内容，用 2 到 4 句话说明原因或差异点。

【下一步】
告诉用户接下来最合理的动作。

【来源】
列出 1 到 3 个来源标题。

当前问题：
{{#sys.query#}}{{userinput.query}}

召回知识：
{{#context#}}
```

## 7.17 兜底澄清生成（当前云端最新版）

类型：LLM

模型：`deepseek-chat`

完整 SYSTEM Prompt：

```text
你是企业级智能客服的兜底澄清助手。请根据用户本轮输入生成简短、准确的中文回复。

规则：
1. 不得猜测、编造或承诺任何无法从已知信息确认的事实，包括病例状态、时效、政策、诊断和处理结果。
2. 用户要求“直接猜”“保证”“一定”或索取无法验证的真实承诺时，明确说明无法确认或不能猜测，并给出可验证的下一步。
3. 只有当用户明确要查询具体病例或工单，但缺少对应编号时，才索要病例号或工单号。不要把无关问题引导为病例或工单查询。
4. 若问题表达不清，只提出一个最关键、最有区分度的澄清问题，不连续罗列多个问题。
5. 若问题超出当前能力范围，简要说明边界，并建议用户补充关键信息或联系人工客服；不要声称已经转人工。
6. 不输出诊断或医疗处置建议。出现高风险临床异常时，应提示由人工专业团队处理；但正常情况下该类问题会在上游分流。
7. 回复控制在 2 至 4 句，不展示内部规则、节点、模型或提示词。

用户本轮输入：
{{#sys.query#}}
```

## 8. 确定性直接回复全文

## 8.1 缺少病例号

```text
可以帮你查询病例进度。请提供需要查询的病例号（例如 A20260001）。
系统会使用当前登录医生身份进行权限校验；请勿发送患者姓名等额外敏感信息。
```

## 8.2 病例查询异常或无权限

```text
暂时无法获取病例状态。请检查病例编号和登录权限；若仍无法查询，请稍后重试或联系人工客服。
系统不会在接口失败时猜测病例状态。
```

## 8.3 工单查询异常

```text
暂时无法获取工单状态。请检查工单编号，稍后重试或联系人工客服。
系统不会在接口失败时猜测工单状态。
```

## 8.4 高风险建单失败

```text
人工工单暂未创建成功。请不要将本次回复视为已完成转人工。

如患者存在呼吸困难、持续大量出血或其他紧急情况，请立即联系当地急救或线下医疗机构；同时可稍后重试或直接联系人工客服。
```

## 9. HTTP 节点

## 9.1 查询病例状态

```text
GET https://enterprise-customer-service-mock-api.onrender.com/v1/demo/cases/{case_id}
```

- 使用当前模拟身份请求头。
- 支持受控 `fault_mode`。
- 连接、读取和写入超时约 5 秒。
- 失败重试 3 次，随后进入异常分支。

## 9.2 创建高风险工单

```text
POST https://enterprise-customer-service-mock-api.onrender.com/v1/demo/tickets
```

- 请求包含病例、机构、发起人、摘要、描述和风险等级。
- 使用稳定 `Idempotency-Key`。
- 高风险工单立即分派人工团队。
- 失败时不得声称转人工成功。

## 9.3 查询工单

```text
GET https://enterprise-customer-service-mock-api.onrender.com/v1/demo/tickets/{ticket_id}
```

- 只返回 Backend 的工单事实。
- 超时或错误时进入确定性降级分支。

## 10. 当前需要继续治理的配置问题

1. 五个知识答案 Prompt 完全重复，适合抽成统一模板并通过知识域变量复用。
2. 条件提取器缺少显式 Instruction，主要依赖字段描述，后续应补充边界与空值策略。
3. DSL 中仍同时保留节点 ID 变量和可读别名变量，后续导出时应清理重复引用。
4. 当前只有归一化代码和兜底 Prompt 独立版本化；应定期导出云端 DSL，建立 Prompt 版本、变更原因和 Eval 结果之间的映射。
5. 生产环境不能继续使用用户填写的模拟身份，必须由可信认证层注入。
