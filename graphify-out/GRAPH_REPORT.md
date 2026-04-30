# Graph Report - Dewita AI Reporting JSR  (2026-04-30)

## Corpus Check
- 21 files · ~26,739 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 124 nodes · 255 edges · 9 communities detected
- Extraction: 71% EXTRACTED · 29% INFERRED · 0% AMBIGUOUS · INFERRED: 73 edges (avg confidence: 0.73)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]

## God Nodes (most connected - your core abstractions)
1. `build_report()` - 15 edges
2. `_execute_with_schema_retries()` - 15 edges
3. `ReportBuildError` - 12 edges
4. `SchemaService` - 12 edges
5. `get_settings()` - 10 edges
6. `AiSqlGenerationError` - 10 edges
7. `SchemaDiagnosis` - 9 edges
8. `SchemaValidationError` - 9 edges
9. `RetryAttempt` - 8 edges
10. `_generate_sql_payload()` - 8 edges

## Surprising Connections (you probably didn't know these)
- `query_report()` --calls--> `build_report()`  [INFERRED]
  backend\app\main.py → backend\app\services\report_runner.py
- `report_feedback()` --calls--> `save_report_feedback()`  [INFERRED]
  backend\app\main.py → backend\app\services\feedback_store.py
- `get_engine()` --calls--> `get_settings()`  [INFERRED]
  backend\app\db.py → backend\app\core\config.py
- `fetch_rows()` --calls--> `_execute_with_schema_retries()`  [INFERRED]
  backend\app\db.py → backend\app\services\report_runner.py
- `fetch_rows()` --calls--> `build_report()`  [INFERRED]
  backend\app\db.py → backend\app\services\report_runner.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.17
Nodes (19): DateResolution, resolve_date_range(), _ai_report_error(), build_report(), _execute_with_schema_retries(), _failed_attempt(), _fallback_sql(), _prepare_sql() (+11 more)

### Community 1 - "Community 1"
Cohesion: 0.17
Nodes (7): get_db_config(), get_mysql_schema_json(), get_mysql_schema_json_legacy(), Exception, SchemaService, main(), ValueError

### Community 2 - "Community 2"
Cohesion: 0.16
Nodes (13): ApiError, runReport(), submitReportFeedback(), buildSummaryItems(), cellClassName(), formatCell(), humanizeColumn(), isDateValue() (+5 more)

### Community 3 - "Community 3"
Cohesion: 0.18
Nodes (9): load_report_catalog(), load_schema_catalog(), fetch_rows(), get_engine(), health(), query_report(), report_catalog(), report_feedback() (+1 more)

### Community 4 - "Community 4"
Cohesion: 0.4
Nodes (11): catalog_context(), AiSqlGenerationError, _build_sql_payload(), _generate_sql_payload(), generate_sql_repair_with_ai(), generate_sql_with_ai(), _generate_sql_with_gemini(), _generate_sql_with_openai() (+3 more)

### Community 5 - "Community 5"
Cohesion: 0.41
Nodes (10): _best_match(), build_schema_index(), diagnose_database_error(), _diagnose_missing_column(), _diagnose_missing_table(), _find_column_locations(), SchemaDiagnosis, SchemaValidationError (+2 more)

### Community 6 - "Community 6"
Cohesion: 0.44
Nodes (8): BaseModel, GeneratedReport, ReportFeedbackRequest, ReportFeedbackResponse, ReportRequest, RetryAttempt, Render named SQLAlchemy placeholders as MySQL literals for copy/paste use., Render named SQLAlchemy placeholders as MySQL literals for copy/paste use.

### Community 7 - "Community 7"
Cohesion: 0.31
Nodes (5): BaseSettings, get_settings(), Settings, _current_model_name(), save_report_feedback()

### Community 8 - "Community 8"
Cohesion: 1.0
Nodes (1): AI reporting backend.

## Knowledge Gaps
- **3 isolated node(s):** `AI reporting backend.`, `Repair common AI SQL drift against the live Devita schema.`, `QueryTemplate`
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 8`** (2 nodes): `__init__.py`, `AI reporting backend.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_execute_with_schema_retries()` connect `Community 0` to `Community 1`, `Community 3`, `Community 5`, `Community 6`, `Community 7`?**
  _High betweenness centrality (0.166) - this node is a cross-community bridge._
- **Why does `build_report()` connect `Community 0` to `Community 3`, `Community 4`, `Community 6`, `Community 7`?**
  _High betweenness centrality (0.156) - this node is a cross-community bridge._
- **Why does `get_settings()` connect `Community 7` to `Community 0`, `Community 1`, `Community 3`, `Community 4`?**
  _High betweenness centrality (0.143) - this node is a cross-community bridge._
- **Are the 10 inferred relationships involving `build_report()` (e.g. with `query_report()` and `resolve_date_range()`) actually correct?**
  _`build_report()` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `_execute_with_schema_retries()` (e.g. with `get_settings()` and `.get_schema()`) actually correct?**
  _`_execute_with_schema_retries()` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `ReportBuildError` (e.g. with `GeneratedReport` and `ReportRequest`) actually correct?**
  _`ReportBuildError` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `get_settings()` (e.g. with `get_engine()` and `get_db_config()`) actually correct?**
  _`get_settings()` has 8 INFERRED edges - model-reasoned connections that need verification._