# 本地研究数据

这个目录保存 P2 真实数据更新产生的本地工件，数据文件不会提交到 Git。

```text
data/
├── raw/<data-version>/       # 带来源元数据的原始标准化快照
├── curated/<data-version>/   # 数据质量报告与 P2 清洗结果
├── factors/<data-version>/   # 可重算的因子矩阵
└── models/<data-version>/    # 使用该数据版本生成的 P3 报告
```

运行 `pnpm research:p2` 更新数据。在线适配器仅用于本地研究验证；商业使用前必须确认数据源授权或切换到用户已购买的数据服务。
