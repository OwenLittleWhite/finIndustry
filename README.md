# industry-analysis

stock-forecast-system 的行业分析子 skill。输入 A 股股票代码,输出该股所属行业的走势、龙头、景气度分析。

## 架构

参考 [docs/industry-analysis-design-v1.md](docs/industry-analysis-design-v1.md)

## 安装

```bash
pip install -e ".[dev]"
```

## 测试

```bash
pytest                              # 跑单元测试
pytest -m integration               # 跑集成测试(需要 Tushare 账号)
```

## 数据源

- Tushare PRO(2000+ 积分)
- akshare(免费,东方财富/同花顺数据)

## 模块契约

参考 [docs/sub-skill-spec-v1.md](docs/sub-skill-spec-v1.md)
