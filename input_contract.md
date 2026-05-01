# Input Contract

参考 [docs/sub-skill-spec-v1.md 第 4 节](docs/sub-skill-spec-v1.md)。

## 必填字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `request_id` | string | 一次完整 forecast 的追踪 id |
| `schema_version` | string | 输出 schema 版本,目前为 `module_output_v1` |
| `ticker` | string | 股票代码,A 股为 6 位数字(如 `600519`) |
| `analysis_date` | string | 数据截止日,YYYY-MM-DD,严禁使用之后数据 |

## 可选字段

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `stock_name` | string | - | 股票名称(子 skill 应能从 ticker 自查) |
| `market` | string | `A股` | 枚举:`A股 / 港股 / 美股`,本 skill v1 仅支持 `A股` |
| `forecast_horizon` | string | `20d` | 枚举:`5d / 20d / 60d / 120d / 250d`(交易日) |
| `current_price` | number | - | 该日收盘价 |

## 示例

```json
{
  "request_id": "req_20260501_abc123",
  "schema_version": "module_output_v1",
  "ticker": "600519",
  "stock_name": "贵州茅台",
  "market": "A股",
  "analysis_date": "2026-05-01",
  "forecast_horizon": "60d",
  "current_price": 1680.5
}
```
