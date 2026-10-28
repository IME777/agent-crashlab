# Agent CrashLab：10 月 30 日参赛版

计划基线：2026-10-27。截止：**2026-10-30 10:00 PDT（America/Los_Angeles）**。

本文件定义交付范围；勾选与验证记录见 [TASKS.md](TASKS.md)。当前已完成真实 Nebius Nemotron 修复及中断恢复：`page-slices` 的两次最终运行各调用模型一次，均通过四项 Docker 验收；恢复没有新增推理，补丁哈希与 token 数保持不变。离线测试、18/18 smoke 配置及真实 Docker 清理也有独立证据。公开仓库、评委访问和视频仍待交付。

## 产品与用户

**给准备发布 coding agent 的开发者，一个可重复的故障演练与发布检查工具。**

输入一项小型代码修复任务，agent 读取有缺陷的代码、提交补丁、运行独立测试。CrashLab 在指定位置中断 worker，随后根据配置恢复或重新执行，记录是否交付正确补丁以及增加了多少工作。

比赛演示的核心画面：**真实 Nemotron 修复 → worker 中断 → 恢复 → 独立测试结果 → 可下载报告**。

## P0：参赛必须具备

| 交付物 | 范围 | 验收标准 |
| --- | --- | --- |
| 真实模型闭环 | 通过 Nebius Token Factory 调用一个 NVIDIA 开源模型；型号由 `NEBIUS_MODEL` 配置 | 保存真实响应的模型标识与已知用量；得到可通过独立测试的补丁 |
| 任务集 | 内置 3 个纯 Python 小型修复任务 | 每项 starter 均不能通过验收；正确修复可以通过；模型不能改验收测试 |
| 受控执行 | 模型候选补丁只在受限 Docker 容器中测试 | 无网络、无宿主凭据、资源与运行时间有限制；环境不可用时明确停止 |
| 故障与恢复 | `worker_crash_after_patch`；真实 worker 进程退出 | 页面看到中断；`resume` 复用已保存补丁和工作状态；最终报告保留故障事件 |
| 明确对照 | `resume` 与 `restart` 两种策略 | 同一任务、同一模型与故障位置；重启策略清除执行检查点但保留累计指标 |
| 产品界面 | 任务、模式、故障、运行／恢复；时间线、代码、测试与用量 | 页面展示实际运行结果；离线模式始终可辨认；无预填成功数据 |
| 检查报告 | 单次运行 JSON、命令行退出状态；当前已有有界 smoke matrix 命令 | 测试失败或运行中断不能被报告为通过；包含模式、配置、事件和测量边界 |
| 可复现交付 | 英文 README、许可、运行说明、参赛演示与材料 | 新环境按说明可以运行；参赛版本可固定；评委有访问方式 |

## P1：有余力再做

- `model_429_once`：在代理调用边界注入一次明确标注的模拟 429，展示有界重试与事件。
- 多次重复运行和简单结果汇总；比赛前先保留逐例数据，避免用极少样本解释尾延迟。
- 录制时可压缩等待过程，但标明剪辑，不用离线结果冒充模型实测。

P1 的缺失不应阻止核心 worker 故障演示；它不能挤占真实模型验证、部署或提交材料的时间。

当前模拟 429 和一次遍历的 18 配置离线矩阵已通过；统计重复实验和真实模型矩阵仍在后续范围内。

## 截止前明确排除

任意 GitHub 仓库导入、自动向外发布 PR、任意 shell 工具、多 agent 协作、多租户、计费、Kubernetes、通用 workflow 编辑器、模型训练、GPU 自托管与推理优化、完整统计 benchmark、对任意外部工具的 exactly-once 保证。当前 `check` 命令的 18 项小型 smoke matrix 不等同于完整 benchmark。

## 两种运行模式

| 模式 | 用途 | 能证明什么 |
| --- | --- | --- |
| `fixture` | 无需 API 的本地开发与恢复流程验证；只执行内置可信 starter/solution | 页面、状态机、事件与进程恢复链路的正确性 |
| `nebius` | 真实 Nebius 模型调用；候选代码在 Docker 中测试 | NVIDIA 模型实际修复任务，以及运行时故障与恢复行为 |

**Fixture 是离线预览，不满足比赛的模型使用要求。** 两种模式的记录、用量与结果必须分别标注。fixture 用量为零；预览结果不能转写成真实模型 benchmark。

## 发布检查的含义

“通过”只表示这次运行的独立测试通过，并且报告中的故障检查得到预期结果。它不证明任意任务、任意故障或生产环境下都可靠。

恢复复用已经持久化的补丁。模型请求已完成、结果尚未落盘时发生中断，仍可能重新推理并增加费用；用量缺失应标成未知。不能把已知 token 之和写成完整账单。

## 首轮演示验收

- [x] 一个不带故障的真实模型任务完成并通过独立测试。
- [x] 同样的任务在补丁已保存后实际退出 worker。
- [x] `resume` 不再次生成已保存补丁，恢复后测试并交付结果。
- [ ] `restart` 重新执行模型步骤，累计调用和事件仍然可见。
- [x] 导出的报告能区分正确交付、失败、中断和环境阻塞。
- [ ] 视频、界面、README 对离线和真实模型的描述一致。

以上保留为**真实模型参赛演示**的验收项。已完成的本地证据包括：

- 53 项离线测试通过；[18/18 smoke 报告](../examples/offline-check.json) 的 `gate_passed=true`、累计 `model_calls=0`。
- [真实模型报告](../examples/live-check.json) 两项最终验收均通过；[首次记录](../examples/live-check-initial.json) 也保留，说明执行约束不匹配导致一次额外修复及严格恢复检查失败。
- [真实 Docker 报告](../examples/docker-check.json)：3 个 starter 均失败、可信 solution 均通过；测试中 kill worker 后未留下该 run 的容器，模型请求数为零。
- 浏览器已完成创建→中断→恢复→通过，服务重启后记录仍保留；见[界面截图](assets/mvp-preview.png)。
- [HTTP smoke](../examples/http-check.json) 14 项通过，包括下载报告、真实中断恢复和请求边界。完整证据见 [VERIFICATION.md](VERIFICATION.md)。

当前模型为 `nvidia/nemotron-3-super-120b-a12b`；真实响应模型 ID 已核对。此证据仅覆盖一个小型任务和指定中断位置；真实 `restart` 策略对照、公开仓库、评委访问与视频仍待交付。

## 当前可运行入口

在项目根目录执行：

```bash
python3 -m crashlab serve
python3 -m crashlab doctor
python3 -m crashlab tasks
```

浏览器入口为 `http://127.0.0.1:8765`。服务和 CLI 对同一数据目录只允许一个控制进程；服务运行时，CLI 演练使用另一个目录：

```bash
python3 -m crashlab --data /tmp/crashlab-demo demo
python3 -m crashlab --data /tmp/crashlab-check check --output /tmp/crashlab-check/report.json
```

`demo` 固定使用离线 fixture；`check` 默认也为 fixture。真实模型命令是：

```bash
python3 -m crashlab run capped-backoff --provider nebius --policy resume \
  --fault worker_crash_after_patch --auto-resume
```

运行之前须配置本地 `.env`、重启服务，并准备 Docker 镜像。`doctor` 只检查配置和容器前提，不会发送推理请求，也不证明模型账户可用。完整命令与退出码见 [架构文档](ARCHITECTURE.md#cli-and-outcomes)。

## 后续求职版本

第一阶段扩充独立任务集、框架默认策略对照、错误分类、取消、并发、背压和重复产物检查。第二阶段另行规划 Nebius GPU 自部署模型、推理并发与首 token 延迟实验。托管 API 集成先支持 agent infrastructure 经历；GPU serving 的能力要在真实自部署实验完成后另行表述。

## 官方依据

- [活动与赛道](https://nebiusglobalaihackathon.devpost.com/)
- [官方规则](https://nebiusglobalaihackathon.devpost.com/rules)
- [官方 FAQ：平台调用与额度](https://nebiusglobalaihackathon.devpost.com/details/faqs)

参赛材料要求以官方页面为准；提交检查集中在 [SUBMISSION.md](SUBMISSION.md)。
