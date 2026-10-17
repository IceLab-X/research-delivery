# 研究交付自动检查

本仓库是 Research delivery 检查程序的唯一维护源，供不同组织中的私有论文项目共同调用。只检查材料与协作规则，不判断科研质量，也不代替指导老师批准 L1。

## 使用

在项目 `.github/workflows/research-delivery.yml` 中配置：

```yaml
name: Research delivery
on:
  pull_request:
    types: [opened, edited, synchronize, reopened, ready_for_review]
permissions:
  contents: read
jobs:
  delivery-gate:
    uses: IceLab-X/research-delivery/.github/workflows/research-delivery-reusable.yml@main
```

`@main` 自动使用最新检查规则。项目的 GitHub Actions 策略必须允许本仓库和 actions/checkout。检查在调用方的 runner 中运行，读取调用方的 PR 事件及工作区，不将论文材料上传到本公开仓库，不需要额外密钥。只读检查不执行论文项目代码。

## 维护

- `tools/check_research_delivery.py`：检查实现。
- `tools/test_research_delivery.py`：规则测试。
- `.github/workflows/research-delivery-reusable.yml`：统一调用入口。
- `.github/actions/research-delivery/action.yml`：运行测试与检查器。

验证：`python3 -m unittest discover -s tools -p 'test_*.py'`。

私有 V2 模板的唯一位置是 `IceLab-X/0template-v2`；它仅保存项目结构、说明和调用入口，不复制本检查器。历史项目遗留的检查器副本不作为规则维护源。
