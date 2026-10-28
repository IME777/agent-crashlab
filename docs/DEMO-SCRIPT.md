# Agent CrashLab — 2:45 demonstration

Status: recording script prepared; final video not yet recorded or uploaded. Target runtime is **2 minutes 45 seconds**, with 15 seconds of margin below the competition limit. Public video URL: **PENDING_PUBLIC_YOUTUBE_URL**.

## Recording plan

Record the real local or operator-hosted runtime for the run/start/resume sequence. A public recorded-evidence viewer may be shown for the report close-up, but label that view **“Recorded real run — no new inference during playback.”** A playback control must not be presented as a new model request or a fresh operating-system worker crash.

Use the verified model `nvidia/nemotron-3-super-120b-a12b`, task **Repair half-open pagination ranges**, policy **Resume from checkpoint**, and fault **Worker crash after patch**. Keep the task, model label, and mode visible before starting.

For a fresh recording, show the actual observed counters. The verified example below had one request and 978 reported tokens; a new model response can differ. If a new candidate needs another repair, disclose it or use the clearly labelled verified recording. Do not splice a failed new run into a success from a different run ID.

## Timed narration and screen actions

The narration column contains **295 words**. At approximately 130 words per minute it leaves about 29 seconds for clicks, inspection, and transitions.

| Time | Screen and action | English narration |
|---|---|---|
| 0:00–0:20 | Show the dashboard and pagination task details. Briefly highlight the buggy range in the patch's before view or a prepared source close-up. | A coding agent can produce a good patch and still leave us uncertain when its worker stops. Agent CrashLab helps developers test that boundary: can the agent recover, deliver a correct artifact, and explain the additional work? |
| 0:20–0:50 | Select **Nebius · NVIDIA model**, **Repair half-open pagination ranges**, **Resume from checkpoint**, and **Worker crash after patch**. Click **Run experiment**. | This is a small Python pagination repair. NVIDIA Nemotron runs through Nebius Token Factory and submits a real code patch. The platform owns the acceptance tests; the agent can change the candidate source, but cannot rewrite the tests that decide success. Each run pins its model ID, tracks actual requests separately from fixtures, and keeps credentials on the server. |
| 0:50–1:25 | Show `model_request`, `patch_checkpoint`, and `fault_injected`. Open event data to show exit code **86**. Pause on **INTERRUPTED**. Click **Resume run**. | The patch and known token usage are now saved. The fault terminates the actual worker process with exit code eighty-six. The separate control plane remains available. I resume the same run, which reconstructs its workspace from the committed checkpoint and continues to independent validation. SQLite stores the patch and event history, while the disposable test container receives no model credentials. |
| 1:25–1:55 | Show **PASSED**, the four Docker test results, patch diff, and model-request counter. Use the actual run's counters. | The recovered patch passes all four Docker acceptance tests. In this verified run, the model request count remains one, and the saved candidate hash and reported token totals are unchanged by recovery. The JSON report records those comparisons, rather than asking us to trust the animation. Those checks separate artifact correctness from execution recovery. |
| 1:55–2:25 | Open the final live JSON, then the preserved initial report. Keep run IDs visible when switching. | The first attempt is fully preserved too. Its patch violated our method-call restriction, so validation asked the model to repair it. The task eventually passed, but the strict no-additional-inference check failed. Making the execution contract explicit fixed this example without weakening the tests or supplying a reference answer. |
| 2:25–2:45 | Show the README reproduction commands, evidence links, and final product screen. End on project name and verified repository/demo links. | CrashLab gives developers a reproducible fault, a verifiable artifact, and an inspectable release check. This version covers small pure-function tasks and one verified live fault boundary. Next comes broader task coverage, framework baselines, and more failure windows. |

## Exact evidence close-up

Use [the final live report](../examples/live-check.json), not a recreated result card:

- No-fault run: `097c8237ac76423b`, one model request, 626 input / 283 output tokens, four Docker tests passed.
- Recovery run: `98b9aed5c9bc4f8e`, one model request, 626 input / 352 output tokens, four Docker tests passed.
- Recovery checkpoint hash: `1686e50be9d1a9136d6e7c783629f7a79afc4e1f702889149ca565f829c3633c` before and after.
- Inspect `before_resume`, `recovery_comparison`, and the true checks for `real_worker_exit_86`, `same_saved_candidate`, and `no_additional_model_requests_after_resume`.
- Initial report: [live-check-initial.json](../examples/live-check-initial.json), `passed=false`. Explain why rather than hiding it.

## 中文拍摄与排练说明

1. **先排练操作，再录制旁白。** 保留项目名称、所选 task、provider 和 run ID；不要打开 `.env`、账户 key 页面、请求授权头或含凭据的终端命令。
2. **新运行需要真实额度。** 录制前确认模型和 Docker 就绪；一次排练只启动需要的一条工作流，不反复运行整批真实测试。不要使用 fixture 来代替真实推理镜头。
3. **推荐镜头顺序：** 任务详情 → 模型/策略/故障选择 → Run experiment → INTERRUPTED → 故障事件 exit 86 → Resume run → PASSED → 测试与补丁 → 报告 → README。
4. **无法看到中断时不要补画成功动画。** 固定故障发生在补丁提交之后，页面应停在 INTERRUPTED，等你点击 Resume；确认选中的是同一个 run ID。
5. **录制等待可压缩。** 压缩模型或 Docker 等待时，在画面标注 “Waiting shortened”。剪辑前后必须是同一次运行；不要把回放按钮说成“新启动真实 worker”。
6. **数据跟随画面。** 表中的精确数字来自已保存的真实实验。新录制若计数不同，更新相应旁白或把数据镜头明确标为历史真实运行。
7. **不要宣称全局零成本恢复。** 本次证明的是补丁已提交这个故障位置的复用；外部请求已完成但未持久化的中断，仍可能重复推理与计费。
8. **成片长度建议 2:40–2:50。** 不加长片头、背景音乐或无证据的架构动画。英文旁白或英文字幕覆盖全部实质内容；YouTube 设为公开后，用未登录窗口检查可看和总时长。

## Recording readiness

- [ ] Public repository and actual demo URL inserted into the final frame.
- [ ] Hosted mode and any recorded-evidence playback labelled accurately.
- [ ] Fresh run or historical run IDs match all shown metrics and evidence.
- [ ] No credentials, private browser tabs, or unrelated personal files appear.
- [ ] Any compressed wait has a visible edit label.
- [ ] English narration/subtitles reviewed; final runtime is less than 3 minutes.
- [ ] Public YouTube URL and playback verified; link added to Devpost materials.
