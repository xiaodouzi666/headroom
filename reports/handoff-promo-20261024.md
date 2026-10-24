# Headroom Promo 到账与下一步 — 2026-10-24

已在原申请邮箱找到官方 $25 Promo 邮件，并按此前授权在当前 Token Factory 账户兑换。刷新交易记录后确认：AI Builder Program Credits +$30.25（含税），账户余额 $30.25；另列试用余额 $1。邮件面额为 $25，兑换截止 2026-12-31。没有进行银行卡充值。邮件称兑换后不失效，但这不替代未来余额/可用性核验。

原 headroom-azuki 密钥与当前控制台匹配，服务器访问两个官方模型目录均 HTTP200，分别列出4/5个Nemotron模型；无需换密钥或区域地址。本轮只有这两次只读目录请求，没有新增模型推理、Tavily 调用或 GPU 作业。私有.env保持0600和gitignore。

T0.1账号、密钥、仓库及至少25美元额度门槛现已验收。T0.4模型能力、完整修复/评测等原门槛仍未通过；整体goal保持进行中。

已准备首个真实能力检查点：Ultra chat、Super JSON、Super tools各至多一次，不重试，逐次审阅；token费用上限1.25美元，含税和费用预留总上限2美元，只使用赠送额度、不充值。此前明确费用授权仅为0.10美元的试用连通性，因此该检查点正等待新的授权，尚未执行；完整live profile仍未启用。

到账监测已完成并暂停，避免重复提醒。证据：reports/promo-redemption-20261024.json、reports/t0.1-acceptance-promo-20261024.json，以及 reports/tokenfactory-catalogue-promo-20261024T145241Z/report.json。

官方账单说明：https://docs.tokenfactory.nebius.com/other-capabilities/billing-new
官方Nemotron价格：https://nebius.com/services/token-factory/models/nvidia-nemotron-models-inference

所有实现与原始证据仍在azuki；本机仅保存纯文本交接报告。

三个真实CLI dry-run及请求审计已准备，固定token预留合计1.2093952美元；9个产物和3个来源哈希复核一致。原后端148个源码哈希仍与1583项通过的回归版本一致，本轮未重复运行整套测试。准备入口：reports/promo-checkpoint-preparation-20261024/README.md。
