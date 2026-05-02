# Input Contract (v1.1)

参考 [docs/sub-skill-spec-v1.md 第 4 节](docs/sub-skill-spec-v1.md)。

## 最小调用(总控真实形态)

业务方只需关心 2 个字段:

```json
{
  "ticker": "600519",
  "analysis_date": "2026-04-30"
}
```

## 业务必填

| 字段 | 类型 | 说明 |
|---|---|---|
| `ticker` | string | 股票代码,A 股 6 位数字(如 `600519`) |
| `analysis_date` | string | 数据截止日,YYYY-MM-DD,严禁使用之后数据 |

## 系统字段(总控自动填)

| 字段 | 默认 | 说明 |
|---|---|---|
| `request_id` | `uuid4()` | 一次完整 forecast 的追踪 id |
| `schema_version` | `"module_output_v1"` | 输出 schema 版本 |

子 skill 收到 request 时:
- 这俩字段如果总控传了 → 直接用
- 如果没传 → 用上述默认值
- 输出 JSON 中两字段必须存在

## 业务可选

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `stock_name` | string | 子 skill 从 ticker 反查 | 股票名称 |
| `market` | string | `A股` | 枚举:`A股 / 港股 / 美股`,本 skill v1 仅支持 A 股 |
| `forecast_horizon` | string | `20d` | 枚举:`5d / 20d / 60d / 120d / 250d`(交易日)|
| `current_price` | number | 子 skill 从 daily 取 | 该日收盘价 |

## 完整示例

```json
{
  "request_id": "req_20260430_abc123",
  "schema_version": "module_output_v1",
  "ticker": "600519",
  "stock_name": "贵州茅台",
  "market": "A股",
  "analysis_date": "2026-04-30",
  "forecast_horizon": "60d",
  "current_price": 1680.5
}
```

## 错误处理

| 情况 | 子 skill 响应 |
|---|---|
| `ticker` 缺失或为空 | `status=failed, error.code=INVALID_INPUT` |
| `analysis_date` 缺失或格式错 | `status=failed, error.code=INVALID_INPUT` |
| 系统字段缺失 | 用默认值,**不视为错误** |
| 业务可选字段缺失 | 用默认值,**不视为错误** |
