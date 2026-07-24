# Quant Tool

面向 A 股研究场景的本地量化决策辅助工具。当前版本是 macOS 东方财富伴随侧栏：只读识别当前股票，并调用本机量化服务刷新评分卡。

## 当前进度

- P0：东方财富进程、股票代码、窗口位置识别与实时跟随已经实现；
- P1：Tauri + Vue 桌面端、FastAPI 本地服务、模拟诊断评分卡和服务异常恢复已经实现；
- P2 研究数据层：真实日线、指数、Point-in-Time 财务数据和 15 个因子已经接入；
- P3 真实研究验证：Walk-Forward、三种排序模型、Top 20 组合和 A 股约束回测已经跑通；
- 当前评分为确定性模拟数据，只用于验证产品闭环；
- 真实研究结果尚未接入桌面评分卡，不提供自动交易，当前模型因数据准入门禁不得成为默认模型。

## 本地开发

需要：

- Node.js `24.18.0`；
- pnpm `8.15.4`；
- Rust `1.97.1`；
- [uv](https://docs.astral.sh/uv/)。

```bash
nvm use
pnpm install
pnpm dev
```

`pnpm dev` 会自动：

1. 安装并锁定 Python 3.12 本地服务环境；
2. 启动 Vue 开发服务器；
3. 启动 Tauri 桌面应用；
4. 由 Rust 在随机端口启动只监听 `127.0.0.1` 的 FastAPI 服务。

检查全部代码：

```bash
pnpm check
```

更新 P2 真实研究数据并重新运行 P3：

```bash
pnpm research:p2
```

只使用已经下载的 P2 工件重跑 P3：

```bash
pnpm research:p3:real
```

生成 OpenAPI 和 TypeScript 共享协议：

```bash
pnpm contracts:generate
```

构建 macOS App：

```bash
pnpm build
```

当前 P1 构建仍从仓库内启动 Python 环境，只用于本机开发和验证；到 P5 再将服务打包为可分发 sidecar。

## 安全与合规边界

- Accessibility API 仅用于读取当前股票和窗口位置；
- 不读取账号、密码、验证码、资金或真实持仓；
- 不注入、Hook 或模拟东方财富交易操作；
- 本地 API 仅监听回环地址，并使用每次启动生成的会话令牌；
- 当前模拟评分不构成证券投资建议。

详细计划见 [TASK.md](./TASK.md)，P2/P3 说明见
[services/quant/P2.md](./services/quant/P2.md) 和
[services/quant/P3.md](./services/quant/P3.md)。
