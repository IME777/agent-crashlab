# Nebius 本地配置与首次真实实验

本项目使用 **Nebius Token Factory API key**。API 地址固定为
`https://api.tokenfactory.nebius.com/v1/`；不使用 AI Cloud IAM token。

当前本地配置已经通过账户模型列表和真实推理验证；模型为 `nvidia/nemotron-3-super-120b-a12b`。[最终真实实验](../examples/live-check.json) 的无故障修复及 worker 中断恢复均通过 Docker 测试；[初次运行](../examples/live-check-initial.json) 的额外修复情况也保留。下文步骤用于新环境复现，不需要重新创建当前可用的 key。

## 申请与本地保存

1. 在 <https://tokenfactory.nebius.com/> 使用 Google 或 GitHub 登录。首次注册、协议确认和凭据创建由账户持有人完成。
2. 打开 <https://tokenfactory.nebius.com/project/api-keys>，选择 **Create API key**。
3. 名称可以填 `agent-crashlab-local`。复制创建后显示的 key，保存到项目根目录本地 `.env` 的 `NEBIUS_API_KEY` 字段。
4. 完整 key 不应发送到聊天、写进代码、截图或实验报告。`.env` 已被 Git 忽略，并设置为仅当前用户可读写。

`NEBIUS_MODEL` 初步选择 `nvidia/nemotron-3-super-120b-a12b`。它出现在 Nebius 官方工具调用示例中，但账户实际可见性、计费权限与工具调用成功仍须分别验证。

## 检查配置

```bash
python3 -m crashlab doctor
python3 -m crashlab models
```

`models` 只对官方 `/v1/models` 发起一次已认证的读取，输出 NVIDIA 模型 ID 和当前配置是否可见，不打印 key，也不发起推理。

优先用账户可用的 Super 完成最小验收。`nvidia/Nemotron-3_5-Lightning` 是官方当前目录中的另一种选择，可以后续比较延迟与成本。不要用过时文章中的型号替代账户实际目录，也不要为此创建 Dedicated Endpoint。

若账户无可用额度，活动资源页列出 $25 Token Factory 额度申请及 Builders Program 额外额度；领取和到账需以账户实际状态确认。该额度不等同于 AI Cloud GPU 预算。

## 两次受限的真实实验

停止使用同一个数据目录的本地服务，或者选用独立目录，再运行：

```bash
python3 -m scripts.verify_live --task page-slices \
  --data .crashlab-live --output examples/live-check.json
```

脚本只尝试两项实验：

1. **无故障修复**：真实 NVIDIA 模型生成分页函数补丁，Docker 内的独立测试验收。
2. **worker 中断与恢复**：真实生成补丁并提交检查点后，worker 以 86 退出。确认中断状态后只恢复一次，比较恢复前后的候选代码哈希、模型 ID、请求数及已知 token 数。

第一项不通过时，不继续第二项；不会回退到 fixture、自动切换模型或反复运行整批实验。单项内部仍遵守最多两轮候选和每轮最多三次传输尝试的现有限制。

`examples/live-check.json` 只在实际执行脚本后生成。脚本缺凭据或环境不就绪时会保存未通过的检查记录；不能把脚本已实现或单元测试通过当作真实模型实验通过。

推理返回但结果尚未持久保存时，中断仍可能导致重复计费。缺失用量会标为未知；报告不据此推断费用为零。

## 常见阻塞

- **401**：检查是否复制了完整的 Token Factory key。
- **403**：检查 key 所属项目与模型访问权限。
- **型号不可见**：使用 `models` 的精确 ID，创建新实验以保持模型固定。
- **无额度或计费限制**：在官方账户页面检查额度；不要将认证读取成功当作推理计费可用。
- **工具结果缺失或截断**：检查模型实际返回与终止原因，再调整有记录的请求参数；不能用离线答案替代真实输出。

来源：

- [官方 Quickstart](https://docs.tokenfactory.nebius.com/quickstart)
- [API key 认证说明](https://docs.tokenfactory.nebius.com/api-reference/introduction)
- [官方模型列表 API](https://docs.tokenfactory.nebius.com/api-reference/models/list-models)
- [Super 工具调用示例](https://github.com/nebius/token-factory-cookbook/blob/main/models/nemotron/nemotron3-super-120B.md)
- [活动资源与额度](https://nebiusglobalaihackathon.devpost.com/resources)
