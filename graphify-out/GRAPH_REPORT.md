# Graph Report - Dewita AI Reporting JSR  (2026-04-30)

## Corpus Check
- 20 files · ~22,779 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 103 nodes · 203 edges · 8 communities detected
- Extraction: 70% EXTRACTED · 30% INFERRED · 0% AMBIGUOUS · INFERRED: 61 edges (avg confidence: 0.75)
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

## God Nodes (most connected - your core abstractions)
1. `build_report()` - 14 edges
2. `_execute_with_schema_retries()` - 14 edges
3. `SchemaService` - 12 edges
4. `ReportBuildError` - 10 edges
5. `get_settings()` - 8 edges
6. `_prepare_sql()` - 8 edges
7. `SchemaDiagnosis` - 8 edges
8. `SchemaValidationError` - 8 edges
9. `validate_sql_against_schema()` - 8 edges
10. `RetryAttempt` - 7 edges

## Surprising Connections (you probably didn't know these)
- `query_report()` --calls--> `build_report()`  [INFERRED]
  backend\app\main.py → backend\app\services\report_runner.py
- `get_engine()` --calls--> `health()`  [INFERRED]
  backend\app\db.py → backend\app\main.py
- `fetch_rows()` --calls--> `_execute_with_schema_retries()`  [INFERRED]
  backend\app\db.py → backend\app\services\report_runner.py
- `fetch_rows()` --calls--> `build_report()`  [INFERRED]
  backend\app\db.py → backend\app\services\report_runner.py
- `GeneratedReport` --calls--> `build_report()`  [INFERRED]
  backend\app\models.py → backend\app\services\report_runner.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.17
Nodes (7): get_db_config(), get_mysql_schema_json(), get_mysql_schema_json_legacy(), Exception, SchemaService, main(), ValueError

### Community 1 - "Community 1"
Cohesion: 0.19
Nodes (15): catalog_context(), load_report_catalog(), load_schema_catalog(), _build_sql_payload(), _generate_sql_payload(), generate_sql_repair_with_ai(), generate_sql_with_ai(), _generate_sql_with_gemini() (+7 more)

### Community 2 - "Community 2"
Cohesion: 0.22
Nodes (12): DateResolution, resolve_date_range(), build_report(), _fallback_sql(), _prepare_sql(), _repair_generated_sql(), apply_limit(), normalize_live_schema_sql() (+4 more)

### Community 3 - "Community 3"
Cohesion: 0.31
Nodes (11): BaseModel, GeneratedReport, ReportRequest, RetryAttempt, _execute_with_schema_retries(), _failed_attempt(), Render named SQLAlchemy placeholders as MySQL literals for copy/paste use., _render_terminal_sql() (+3 more)

### Community 4 - "Community 4"
Cohesion: 0.41
Nodes (10): _best_match(), build_schema_index(), diagnose_database_error(), _diagnose_missing_column(), _diagnose_missing_table(), _find_column_locations(), SchemaDiagnosis, SchemaValidationError (+2 more)

### Community 5 - "Community 5"
Cohesion: 0.28
Nodes (5): BaseSettings, get_settings(), Settings, fetch_rows(), get_engine()

### Community 6 - "Community 6"
Cohesion: 0.25
Nodes (3): ApiError, runReport(), submit()

### Community 7 - "Community 7"
Cohesion: 1.0
Nodes (1): AI reporting backend.

## Knowledge Gaps
- **3 isolated node(s):** `AI reporting backend.`, `Repair common AI SQL drift against the live Devita schema.`, `QueryTemplate`
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 7`** (2 nodes): `__init__.py`, `AI reporting backend.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_execute_with_schema_retries()` connect `Community 3` to `Community 0`, `Community 2`, `Community 4`, `Community 5`?**
  _High betweenness centrality (0.222) - this node is a cross-community bridge._
- **Why does `build_report()` connect `Community 2` to `Community 1`, `Community 3`, `Community 5`?**
  _High betweenness centrality (0.205) - this node is a cross-community bridge._
- **Why does `get_settings()` connect `Community 5` to `Community 0`, `Community 1`, `Community 2`, `Community 3`?**
  _High betweenness centrality (0.152) - this node is a cross-community bridge._
- **Are the 10 inferred relationships involving `build_report()` (e.g. with `query_report()` and `resolve_date_range()`) actually correct?**
  _`build_report()` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `_execute_with_schema_retries()` (e.g. with `get_settings()` and `.get_schema()`) actually correct?**
  _`_execute_with_schema_retries()` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 5 inferred relationships involving `ReportBuildError` (e.g. with `GeneratedReport` and `ReportRequest`) actually correct?**
  _`ReportBuildError` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `get_settings()` (e.g. with `get_engine()` and `get_db_config()`) actually correct?**
  _`get_settings()` has 6 INFERRED edges - model-reasoned connections that need verification._