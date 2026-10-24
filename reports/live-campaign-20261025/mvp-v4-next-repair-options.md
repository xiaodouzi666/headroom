# MVP v4 后续修复选项（只读提案，等待 Frank 决定）

记录时间：2026-10-24T23:30:48.985738+00:00。检查基点为 source 78a83df，campaign 20261024T231940915002Z-2098d11d。只分析已结束的 s1–s4；v4 **仍在执行**，不预判整战役结果。原 PLAN §0.6（40–43行）允许的三轮修复额度已经用到最后一轮：若本轮仍不达标须停止等 Frank，本文不授权第4轮、实施改动或新调用。

## 先区分事实与推论

- 已查看的响应有真实行数组，故本次问题不再是v3的“整份diff没有换行”。合法JSON/逐行运输不等于合法unified diff。
- s1第三轮有真实apply+compile成功，但候选仍OOM、0步；s2–s4已有终态均target=false。这里不把静态成功、模型意图、次数或HTTP200推为修复效果。
- 以下机制来自原wire/normalized diff、固定baseline、实际candidate和保存的Git/Lab结果。仅用本地parser在内存重读选中字符串以取得原始错误，未重跑Git、编译、用户代码、模型或GPU。

## 1. 优先保留可行动的格式诊断，而不是只回传“invalid unified diff”

**已证实：** E1的第6个wire元素为无diff前缀的「import argparse」；原parser明确报「Hunk diff line expected: import argparse」。E2头为「@@ -100,7 +100,6 @@」，下方6条context+1条remove+1条add意味着旧侧7、新侧7，声明的新侧6不符，报「Hunk is longer than expected」。E3更隐蔽：两个拟修改行都以空格开头，parser统计added=0/removed=0，Git报「corrupt patch at line 11」；不能自动把空格猜成“+”。
当前 headroom/patch.py:170–173 把这些parser错误统一压成「invalid unified diff」，734–740只把这一detail和原proposal交给fixer；prompt patch.md:7 / patch_fix.md:7 已说明前缀，所以“再重复同一句规则”没有新实证依据。

**建议：** 保留有界结构化诊断：file/hunk/数组索引、expected/observed old/new counts、非法前缀、zero-change hunk；归类后供既有fixer读取。仍拒绝原补丁，不自动补前缀/改计数/剥编号，不增加4000 cap或初次+3fixer次数。预期是提高反馈信息量，尚未证明能提高模型成功率。

**对应验证：** 用独立通用文件构造缺context前缀、计数差1、纯context无改动、正常多hunk；真实MockTransport→router→engine断言错误结构到下一请求、有效修复可apply/compile、四次上限不变。旧E1–E3只作回归负例，不把其正确修复作为模型提示答案。

## 2. 将展示行号与可编辑原文分开，并验证具体源锚点

**已证实：** headroom/patch.py:250–252 当前只传「0001: ...」拼接的源码；prompt patch.md:5–7却要求从未编号原文精确复制、不得带展示标签。E5将「 0003: import argparse」等标签实际复制进diff，Git不能匹配原文件。E4声明「@@ -84,1 +84,1 @@」，其删除文本在该attempt冻结baseline中仅匹配第86行，第84行是注释；无上下文的声明位置不符，实际Git返回「patch failed: train.py:84」。日志里的missing-blob后紧跟正常direct fallback，不能仅据此认定3way基础设施坏了。

**建议：** 在原128KiB来源预算内，将源码变成独立原文/行号元数据（例如带start_line和source SHA的原文块），不让编号成为可复制源码的一部分；不叠加两份完整源码扩大请求。若 Frank 允许下一版协议，再评估模型返回“路径+基线hash+精确旧块/新块”的锚定编辑，由host确定性生成标准diff及hunk计数；旧块不存在/多处匹配/重叠时明确拒绝，绝不模糊替换。这是待审的通用协议选项，不是已证明有效或已获实施许可。

**对应验证：** 重复相似函数、错误行号、stale hash、缩进/Unicode/空白行、多个不重叠编辑等通用夹具；精确匹配后生成diff仍须通过原path/policy/Git/compile门。真实provider效果只有在Frank决定后、受共享额度和停止规则约束的新组件实测才能确认。

## 3. 核对实际应用位置，避免“编译成功但改到了失效路径”

**已证实：** E6是14个零context插入hunk，首个「@@ -91,0 +92 @@」，其余声明到原106行；Git实际candidate新增代码全部位于124–137行。candidate的117行已调用 main()，123行是异常分支的 raise，原main内的前向/训练逻辑没有被替换。该结果记录 STATIC_CHECKS_PASSED、compile_exit_code=0、three_way_command_direct_fallback；保存的Lab结果仍在原前向OOM，steps=0、peak=24.750424064GB。因此“语法能编译”在此确实不足；本文不推断其他未执行新代码的数值正确性。

**建议：** 对每个应用后的实际变更区间生成可审计映射（原/新行、前后锚点、所在函数/类/模块），并核对它与声明的源锚点一致；没有可验证锚点的零context插入应明确拒绝/请求重出，不能接受Git漂移后的位置为模型本意。将实际位置及Lab异常作为数据交回规划器。仅位置/语法检查不能保证内存或数值正确，原20步/数值/参数量/吞吐与keep门全部保留。

**对应验证：** 通用多函数文件、已有 if __name__ 入口、重复锚点和合法显式EOF插入，断言声明位置漂移可被识别且合法EOF不误拒；有界CPU Lab验证新增语句是否在目标调用前执行，不用scenario专用规则，也不添加固定修复答案。只有之后真实验证通过才能计为修复，不能把静态通过算target。

## 精确证据索引（私有运行记录，不作为公开demo）

所有E项的 parsed.diff_lines 与 normalized_diff 均保留在原私有response；下列仅引用路径/哈希，不复制整份模型输出。
- **E1 s3/r01/a1**：runs/evaluation/live/20261024T231940915002Z-2098d11d/jobs/716fe9f9b3844031a3aa4bb9a9d04d0d/rounds/01/patches/patch-engine-59b5f9833e514d5a960a60c1dbae75b0/attempt-1-response.json；SHA256 89fe1aea3f33d2f54ed947489016eb52d1d0013458f201027fb255e2123ecad6。
- **E2 s4/r01/a1**：runs/evaluation/live/20261024T231940915002Z-2098d11d/jobs/77a60dc674f2491fb4cb44db8c441b08/rounds/01/patches/patch-engine-ede4f8cf1ec54d2588f5363de0574c0d/attempt-1-response.json；SHA256 efc0a75a97accb08a010fe4e42a17dc826975965dcb36f7880f9946050798898。
- **E3 s4/r05/a1**：runs/evaluation/live/20261024T231940915002Z-2098d11d/jobs/77a60dc674f2491fb4cb44db8c441b08/rounds/05/patches/patch-engine-d1c454934de248dd85c5b8355eb47ada/attempt-1-response.json；SHA256 146b4d0df851ddba0fae4191749a9c79d0fa027dbbd2a8c571bb1e06942272b8。
- **E4 s2/r01/a1**：runs/evaluation/live/20261024T231940915002Z-2098d11d/jobs/c23a1768850d49c993a891427d4d9c24/rounds/01/patches/patch-engine-4d41da47b8d34b489ce7a692e45c2cf0/attempt-1-response.json；SHA256 9195a90851a4973bccb61e338329b8a2ff60f967a56f3b22de131592b377beb4。
- **E5 s4/r06/a1**：runs/evaluation/live/20261024T231940915002Z-2098d11d/jobs/77a60dc674f2491fb4cb44db8c441b08/rounds/06/patches/patch-engine-4c828765910d459f8d19dc2df9621aae/attempt-1-response.json；SHA256 6732acee622565c83de54aa102c8246bfbb8ef167f57c269e108a3f2e4c4d79c。
- **E6 s1/r03/a1**：runs/evaluation/live/20261024T231940915002Z-2098d11d/jobs/52d7c368ccca4f639599eedaf0995893/rounds/03/patches/patch-engine-a783b9738f94484e9b31adf972707f26/attempt-1-response.json；SHA256 dbd41352709925ca5f1c02de945b43bc18eaa9a84168c090465b3916bc815344。
- **E6位置/运行核对**：runs/evaluation/live/20261024T231940915002Z-2098d11d/jobs/52d7c368ccca4f639599eedaf0995893/rounds/03/patches/patch-engine-a783b9738f94484e9b31adf972707f26/attempt-1/patch-5b201bb3064e4a1f9b0e66838fc88bf3/candidate/train.py 第115–137行；SHA256 0ecd1483f12e01fc6e393c507fe5e53a6e11e358fc63ef15c653ea55b00ff069；runs/evaluation/live/20261024T231940915002Z-2098d11d/jobs/52d7c368ccca4f639599eedaf0995893/rounds/03/verification.json（after.status=oom/steps=0）。

本提案没有修改source/prompt/tests/PLAN、profile或ledger，没有网络/API/GPU调用；未降低原验收阈值。三个选项均等待Frank决定，不自动开始后续修复。
