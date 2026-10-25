# T2.2 当前版本检索边界预研（2026-10-25）

本次仅只读源码、r1 原始 research 元数据及公开主源；没有 Tavily、模型、GPU 调用，没有改生产代码或测试。

**结论：r1 s2 的检索没有完成 T2.2“当前 torch 版本文档”的要求，但没有被完整检索状态误报为成功。** 搜索结果保留新版本并标 `version_match=false` 是显式设计；真正缺口是模型连续搜索未完成 exact-version extract，流程仍可继续 Patch，而报告 Sources 仅列标题/URL、没有逐条显示版本适用性。运行环境元数据 `torch_version=2.5.1+cu124` 不能证明检索返回了 2.5 文档。

## 已核实的实际路径

r1 s2 `runs/evaluation/live/20261025T095016638167Z-ad191318/jobs/d2f6b77c39ad40a0947b2cc84921c771/rounds/01/research-adamw.json`：
- `status=partial`，2 次真实 Tavily API 调用，均为 search；没有 extract。
- 第一次返回 AdamW main（两个官方主机）、2.11、2.12，以及不直接对应 AdamW 的 eig/eigh issue；5 条均 `version_match=false`。第二次 search 为 `failed/no_allowed_nonempty_results`。
- 这证明真实搜索发生，不证明目标版本 API 适用；issue 标题里出现 2.5.1 也不是 AdamW 兼容性证据。
- s1、s5 对应 r1 job 没有 research 文件；本轮既有审计已确认诊断停在 needs-more-info。不是已有 Sources 被漏排版。

源码边界：
- `headroom/research/tavily_tool.py:450–479` 给 query 加运行版本；search allowlist 允许 `/docs/` 下不同版本。解析器 :272–317 逐条保留 `version_match`，extract 严格检查目标 minor 路径、非空正文、failed_results 和完整 URL 集合。
- `ResearchToolLoop.finish`（`tool_loop.py:238–260`）必须有成功 search+extract 且提取了当前 topic 的确切文档 URL，才标 succeeded；仅搜索/issue/最终模型文字不能充数。
- `orchestrator.py:219–227,725–799` 把 status、sources、notes 与有界正文送 Patch；版本字段仍在 sources 中。但没有“匹配文档未提取就不采用该 API”的执行门。
- `report.py:892–907` 显示整体 partial，再只列各 source 的标题/URL，隐藏了逐项 `version_match` 与 search/extract 区别。这是对读者有实际影响的呈现缺口，不是原始日志造假。
- cache key 包含 schema=1、完整 torch_version、method、arguments，TTL 24h；缓存命中重新解析来源，credits_used=0/api_calls=0，原请求来源保留。缓存隔离不能把错误版本变正确，也不代表新鲜网络请求。

## 公开版本规范

[官方版本选择页](https://docs.pytorch.org/docs/versions.html) 将 main 标为 unstable，并把 v2.5.0 链接到 [2.5 文档树](https://docs.pytorch.org/docs/2.5/)。[2.5 checkpoint 文档](https://docs.pytorch.org/docs/2.5/checkpoint.html) 确认该版本 API 和 `use_reentrant` 行为。故运行 2.5.1+cu124 使用 /2.5/ 是合理的 minor 文档约定，但不等于 patch 版本的逐项兼容证明；涉及具体补丁变化仍需 [v2.5.1 源码](https://github.com/pytorch/pytorch/blob/v2.5.1/torch/optim/adamw.py)。

本次浏览工具未能打开 2.5 AdamW 和 CUDA HTML 页，不能据此断言网页不存在，也不能伪称已提取它们。对应的 [v2.5.1 CUDA 官方文档源](https://github.com/pytorch/pytorch/blob/v2.5.1/docs/source/notes/cuda.rst) 已读到缓存/expandable_segments 说明；这是本次人工只读研究来源，**不是 r1 的 Tavily retrieval 收据**。

## 最小后续改进建议（未实施）

1. 保留不匹配搜索记录，但把 `target_documentation_url`、`matched_documentation_extracted`、每条 method/cache/source-version 作为确定性元数据同时显示在工具反馈、Patch 上下文与 Sources。不得只从 query 或运行环境推导“匹配”。
2. 当 search 只有 main/其他版本时，在既有剩余 turn/4-tool quota 内反馈“尚未提取目标 URL”，引导下一次真实 extract；不要无限重搜或增加隐藏 fallback。确切官方地址可以作为**待检索目标**，只有成功 provider 返回的非空正文和保留的操作收据才能成为已检索 Sources。
3. 若 API 使用以版本证据为前提，未完成时明确 research-incomplete，让模型选择有证据的计划或保持未知。是否将其升级为硬规划门需按原任务合同明确定义；不能把新硬门偷偷混进本轮冻结代码。不同版本正文仍可作为标明限制的背景，不可当已验证目标版本 API。
4. 不把任意 GitHub issue 当当前版本缺陷证明；要有主题相关性及适用性标记，找不到应记录未找到。
5. 若缓存语义/解析政策改变，版本化 cache schema 或重新验证旧缓存；不抹除旧操作/费用，也不把旧 partial 追溯变 succeeded。

建议离线测试：main+2.11+2.12 只 search 必须 partial；运行元数据 2.5.1 不能抬高结论；真实 exact 2.5 topic extract 正例；2.5 但错误 topic、issue-only、空/部分提取、伪 URL 文本、返回 URL 不一致负例；旧缓存同样重验；报告逐条版本/方法可见；完整额度耗尽时不额外 dispatch。既有 `tests/test_research.py:225–239` 已明确 main 结果保持 unverified，不能删掉这条保护。

## s1 / s5 Sources 怎样诚实完成

当前 research 位于 ready-for-patch 之后（`orchestrator.py:659–694`），且只为模型所提当前步骤的 API 选 topic（`search.py:375–388`）。因此真实端到端下一轮必须先有合法且有依据的 checkpoint/allocator 计划，再在原额度内实际 search+extract，记录 research 表、操作/缓存 provenance、正文与报告 Sources。不能强制 readiness、在计划里塞关键词或粘贴 URL 来刷门。

若要独立检验检索能力，可另行预登记一个有界、真实的 research-only 验收，复用现有 ResearchSession/explore 与相同版本/来源限制并保存独立收据；它证明该检索路径可用，**不能冒充原 s1/s5 run 的 Sources 已完成**。另一种产品改进是允许诊断在明确 API 文档缺项时发出有界 research 请求，但仍保持原 needs-more-info 与总调用上限；这需要单独实现验证，当前并未存在。本轮没有执行这些调用。
