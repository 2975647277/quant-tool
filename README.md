# Quant Tool

面向 A 股研究场景的本地量化决策辅助工具。当前版本是 macOS 东方财富伴随侧栏：只读识别当前股票，并调用本机量化服务展示真实历史研究覆盖状态。

## 当前进度

- P0：东方财富进程、股票代码、窗口位置识别与实时跟随已经实现；
- P1：Tauri + Vue 桌面端、FastAPI 本地服务、模拟诊断评分卡和服务异常恢复已经实现；
- P2 研究数据层：真实日线、指数、Point-in-Time 财务数据和 15 个因子已经接入；
- P3 真实研究验证：Walk-Forward、三种排序模型、Top 20 组合和 A 股约束回测已经跑通；
- P4 部分完成：东方财富当前股票已连接到 P2/P3 真实历史研究接口；
- 侧栏会区分“历史 Top 20”“研究池内未入选”和“当前研究池未覆盖”，未覆盖股票不会生成个股分数或上涨概率；
- 当前展示的是截至 `2025-09-26` 的历史样本外验证快照，不是当天行情或实时交易信号；
- 当前模型因数据准入门禁不得成为默认模型，也不提供自动交易。

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

当前构建仍从仓库内启动 Python 环境，只用于本机开发和验证；到 P5 再将服务打包为可分发 sidecar。

## 安全与合规边界

- Accessibility API 仅用于读取当前股票和窗口位置；
- 不读取账号、密码、验证码、资金或真实持仓；
- 不注入、Hook 或模拟东方财富交易操作；
- 本地 API 仅监听回环地址，并使用每次启动生成的会话令牌；
- 当前历史研究快照不是实时信号，不构成证券投资建议。

详细计划见 [TASK.md](./TASK.md)，P2/P3 说明见
[services/quant/P2.md](./services/quant/P2.md) 和
[services/quant/P3.md](./services/quant/P3.md)。
