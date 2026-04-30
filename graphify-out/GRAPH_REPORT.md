# Graph Report - Dewita AI Reporting JSR  (2026-04-30)

## Corpus Check
- 20 files · ~19,988 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 96 nodes · 179 edges · 9 communities detected
- Extraction: 71% EXTRACTED · 29% INFERRED · 0% AMBIGUOUS · INFERRED: 52 edges (avg confidence: 0.77)
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
1. `build_report()` - 14 edges
2. `_execute_with_schema_retries()` - 13 edges
3. `SchemaService` - 12 edges
4. `ReportBuildError` - 10 edges
5. `validate_sql_against_schema()` - 8 edges
6. `get_settings()` - 7 edges
7. `_validate_with_current_schema()` - 7 edges
8. `SchemaDiagnosis` - 7 edges
9. `SchemaValidationError` - 7 edges
10. `RetryAttempt` - 6 edges

## Surprising Connections (you probably didn't know these)
- `query_report()` --calls--> `build_report()`  [INFERRED]
  backend\app\main.py → backend\app\services\report_runner.py
- `_execute_with_schema_retries()` --calls--> `fetch_rows()`  [INFERRED]
  backend\app\services\report_runner.py → backend\app\db.py
- `fetch_rows()` --calls--> `build_report()`  [INFERRED]
  backend\app\db.py → backend\app\services\report_runner.py
- `get_settings()` --calls--> `get_db_config()`  [INFERRED]
  backend\app\core\config.py → backend\app\services\db_to_schma.py
- `get_settings()` --calls--> `generate_sql_with_ai()`  [INFERRED]
  backend\app\core\config.py → backend\app\services\llm.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.18
Nodes (18): BaseModel, GeneratedReport, ReportRequest, RetryAttempt, build_report(), _execute_with_schema_retries(), _failed_attempt(), _fallback_sql() (+10 more)

### Community 1 - "Community 1"
Cohesion: 0.24
Nodes (11): catalog_context(), load_report_catalog(), load_schema_catalog(), generate_sql_with_ai(), _generate_sql_with_gemini(), _generate_sql_with_openai(), _generate_sql_with_openrouter(), _parse_ai_json() (+3 more)

### Community 2 - "Community 2"
Cohesion: 0.25
Nodes (3): Exception, SchemaService, main()

### Community 3 - "Community 3"
Cohesion: 0.45
Nodes (9): _best_match(), build_schema_index(), diagnose_database_error(), _diagnose_missing_column(), _diagnose_missing_table(), SchemaDiagnosis, SchemaValidationError, validate_schema_catalog() (+1 more)

### Community 4 - "Community 4"
Cohesion: 0.24
Nodes (6): BaseSettings, get_settings(), Settings, fetch_rows(), get_engine(), health()

### Community 5 - "Community 5"
Cohesion: 0.25
Nodes (3): ApiError, runReport(), submit()

### Community 6 - "Community 6"
Cohesion: 0.47
Nodes (4): get_db_config(), get_mysql_schema_json(), get_mysql_schema_json_legacy(), ValueError

### Community 7 - "Community 7"
Cohesion: 1.0
Nodes (2): DateResolution, resolve_date_range()

### Community 8 - "Community 8"
Cohesion: 1.0
Nodes (1): AI reporting backend.

## Knowledge Gaps
- **3 isolated node(s):** `AI reporting backend.`, `Repair common AI SQL drift against the live Devita schema.`, `QueryTemplate`
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 7`** (3 nodes): `date_resolver.py`, `DateResolution`, `resolve_date_range()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 8`** (2 nodes): `__init__.py`, `AI reporting backend.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `build_report()` connect `Community 0` to `Community 1`, `Community 4`, `Community 7`?**
  _High betweenness centrality (0.243) - this node is a cross-community bridge._
- **Why does `_execute_with_schema_retries()` connect `Community 0` to `Community 2`, `Community 3`, `Community 4`?**
  _High betweenness centrality (0.203) - this node is a cross-community bridge._
- **Why does `get_settings()` connect `Community 4` to `Community 0`, `Community 1`, `Community 6`?**
  _High betweenness centrality (0.133) - this node is a cross-community bridge._
- **Are the 10 inferred relationships involving `build_report()` (e.g. with `query_report()` and `resolve_date_range()`) actually correct?**
  _`build_report()` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `_execute_with_schema_retries()` (e.g. with `get_settings()` and `.get_schema()`) actually correct?**
  _`_execute_with_schema_retries()` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 5 inferred relationships involving `ReportBuildError` (e.g. with `GeneratedReport` and `ReportRequest`) actually correct?**
  _`ReportBuildError` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `validate_sql_against_schema()` (e.g. with `_validate_with_current_schema()` and `_execute_with_schema_retries()`) actually correct?**
  _`validate_sql_against_schema()` has 2 INFERRED edges - model-reasoned connections that need verification._