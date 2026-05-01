# Output Contract

参考 [docs/sub-skill-spec-v1.md 第 5 节](docs/sub-skill-spec-v1.md) 和 [docs/industry-analysis-design-v1.md 第 8 节](docs/industry-analysis-design-v1.md)。

JSON Schema 校验文件:`shared_schemas/module_output_v1.schema.json`(将在 Task 4.1 创建)。

## 必备字段示例

```json
{
  "module_id": "industry_analysis",
  "module_name": "行业分析模块",
  "module_version": "1.0.0",
  "schema_version": "module_output_v1",
  "request_id": "req_20260501_abc123",
  "analysis_date": "2026-05-01",
  "status": "success",
  "signal": "看多",
  "score": 65,
  "confidence": 0.78,
  "reasons": ["...", "...", "..."],
  "risks": ["...", "..."],
  "summary": "白酒景气度回升,龙头领涨,贵州茅台位居核心受益位置。",
  "metrics": {
    "latency_ms": 12500,
    "data_sources_used": ["tushare", "akshare"]
  }
}
```

## 完整字段(含 `module_specific`)

参考 [docs/industry-analysis-design-v1.md 第 8 节](docs/industry-analysis-design-v1.md)。
