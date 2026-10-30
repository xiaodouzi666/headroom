# 新版本部署前检查与候选命令（尚未执行）

范围：Headroom 专用 headroom-public.service。此文只准备步骤，没有重启服务、修改 drop-in、公开 Snapshot 或发起模型请求。不要用“CLI 有终态”替代验收：第一轮 s2 runtime_unavailable/0 calls/$0 已保留，不构成 Snapshot 可开放的成功证据。

## 当前只读观察

systemctl show 只读取安全字段，观察到 ActiveState=active、SubState=running。unit 位于 /home/xiaodouzi/.config/systemd/user/headroom-public.service，已有 final48.conf 与 verified.conf 两个 drop-in。没有打印 Environment、EnvironmentFiles 内容或令牌。源码仓库仍由多名代理完成最后修改，不能在其冻结前构建/提交/重启。

## 发布门槛

1. 等本轮真实 Snapshot 的具体诊断/语义结果、真实调用与费用、snapshot_cleanup_verified 及进程组清理都完成审阅。已知失败与新成功分开保留，不覆盖旧 F3b/原 0/2/R7 1/9。
2. 所有代理声明源码冻结，检查 git diff 与每份 source hash 收据一致。新的诊断/预算源码会令旧 retry proposal 失效；不得重新使用已执行的 once/run ID 或放宽 hash 检查。
3. 现有针对测试、类型/格式/秘密扫描通过；不为部署重复无关全量测试。把所有已审变更统一 commit，并记录完整 commit。构建只能来自这个冻结版本。
4. 检查当前 API 的训练队列 running=false、pending=0、preparing=0，halted=false、closing=false；独立的 retry controller 已终止且结算无未知项；没有正在运行或接收的 Snapshot。当前旧公开 Snapshot 关闭，也要确认没有独立 F3b/controller 子进程。
5. idle 是瞬时观察，不是原子 drain。重启前再次确认；若出现新入队/上传/模型工作就延后，不为了部署杀它、关账或删除任务。根代理应使用已控制的维护窗口处理入口与复核之间的竞态。不要把“CPU/GPU当前空闲”替代模型账务与队列检查。

只读状态命令（在 azuki 项目根目录执行，均不显示秘密）：

    systemctl --user show headroom-public.service \
      -p ActiveState -p SubState -p MainPID -p FragmentPath -p DropInPaths
    curl --fail --silent --show-error --max-time 15 \
      -H 'Host: headroom.tail45186b.ts.net' \
      http://127.0.0.1:8766/api/health

health 输出可包含服务状态，但不能单独证明独立 CLI controller 已结束。保留已存在 controller-summary/settlement 的事实；不要输出 private binding、凭据或完整环境。公开 health 的 queue 字段是 running/pending/preparing，不是 waiting。

## 备份与构建（执行前由根代理确认上述门槛）

以下是候选命令，不是本次执行记录。使用已安装 Node 24.22.1，不下载新工具。先创建独占私密发布目录，备份原 drop-in 与旧 dist；旧凭据文件保持原位、原字节，不复制到公开报告。

    cd /home/xiaodouzi/workspace/headroom
    task_release_dir="$PWD/.cache/snapshot-release-$(date -u +%Y%m%dT%H%M%SZ)"
    umask 077
    mkdir "$task_release_dir"
    cp -a /home/xiaodouzi/.config/systemd/user/headroom-public.service.d \
      "$task_release_dir/old-dropins"
    cp -a web/dist "$task_release_dir/old-dist"
    git rev-parse HEAD > "$task_release_dir/commit.txt"
    PATH="$PWD/.tools/node-web/node-v24.22.1-linux-x64/bin:$PATH" \
      npm --prefix web run build -- --outDir "$task_release_dir/web-dist" --emptyOutDir

生成并核对 dist 文件 hash 清单后再发布。先复制按 hash 命名的新 assets（保留旧 assets），最后在同一文件系统原子替换 index.html，避免新 HTML 引用尚未复制的文件；保留 old-dist 以回滚。不要把 staging build 直接等同公网已更新，也不要静默覆盖其它项目。

## 候选 Snapshot drop-in

现有 final48.conf/verified.conf 不编辑。准备的两份纯配置模板位于本目录：

- snapshot-public.env.example：只包含 HEADROOM_SNAPSHOT_SUBMISSIONS_ENABLED=true。
- zz-snapshot-public.conf.example：只追加一个专用 EnvironmentFile。

**仅在真实 CLI 结果审阅满足发布门槛之后**，把 env 示例安装到 .cache/snapshot-public-flags.env，权限 0600；把 conf 示例安装到专用 unit 的 zz-snapshot-public.conf。先检查目标不存在，若已经存在就先核对并单独备份，不盲目覆盖。

不要只写 Environment= 来期待覆盖原 EnvironmentFile 同名值；systemd 的 EnvironmentFile 值优先，新的专用文件必须作为最后追加的 EnvironmentFile。既有 receipt/profile/token/budget 环境文件不得改写或清空。该新文件只控制 Snapshot 开关，未授权新资金或创建凭据。

    install -m 600 reports/snapshot-repair-20261030/snapshot-public.env.example \
      .cache/snapshot-public-flags.env
    install -m 600 reports/snapshot-repair-20261030/zz-snapshot-public.conf.example \
      /home/xiaodouzi/.config/systemd/user/headroom-public.service.d/zz-snapshot-public.conf
    systemctl --user daemon-reload

daemon-reload 还不等于运行中的应用读取新开关。完成最后 idle 检查后才执行专用服务重启，绝不操作 headroom-tailscaled 或其它项目：

    systemctl --user restart headroom-public.service

## 重启后仅 GET 的验证

对 origin 与真实 Funnel URL 分别检查：

- Home、/run、/verified、/results、/about HTTP 200，HTML引用的新版 CSS/JS可GET且hash与冻结dist一致。
- /api/config 匿名200，run_submissions仍保持原设计；Snapshot若计划开放则 enabled=true、requires_judge_token=true、runs_per_ip_per_hour=null。这是表单可见，不是匿名上传授权。
- /api/health 匿名200，旧匿名训练仍1/IP/hour；有效现有令牌200，judge无小时次数限制；错误令牌与显式空 Authorization 都401。
- 有效令牌只通过既有安全检查脚本在内存读入并放在 Header，不把它写进URL、shell argv、报告或日志。不要输出 Cookie/Set-Cookie/Authorization。
- Token 的 GET 检查只证明读端鉴权；Snapshot POST缺token/错误token在离线77项测试中拒绝。此部署检查不发送 POST、不试传恶意pickle、不花模型费，也不冒充真实公网功能实测。
- 浏览器只观察 Home 的 loading/错误状态、Snapshot必填令牌提示和原字体；不要点击 Start 或 Analyze。
- 记录重启时间、完整commit、dist资产hash、安全HTTP状态与model/GPU新增数0。服务active不替代真实公网200。

## 回退

如果启动或只读检查失败，保持 Snapshot 不开放，恢复本次备份的旧 dist 和本次添加前的 drop-in 状态，然后在确认空闲后重启同一专用服务。只移除本次新加且已确认身份的 zz-snapshot-public.conf；已有配置不能凭文件名盲删。保留所有业务历史、失败日志、once marker和账本，不回滚金融数据、不触碰凭据。

即便部署成功，也只能报告“新版已开放并通过GET检查”。首次真实公网上传需要单独的受控输入、费用和owner结果证据；第一次s2诊断通过不自动代表nanoGPT或完整Snapshot验收全绿。
