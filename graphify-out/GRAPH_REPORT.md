# Graph Report - Dewita AI Reporting JSR  (2026-05-26)

## Corpus Check
- 34 files · ~46,239 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 339 nodes · 768 edges · 13 communities detected
- Extraction: 73% EXTRACTED · 27% INFERRED · 0% AMBIGUOUS · INFERRED: 204 edges (avg confidence: 0.75)
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
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]

## God Nodes (most connected - your core abstractions)
1. `build_report()` - 37 edges
2. `_validate_generated_output_with_retries()` - 29 edges
3. `get_engine()` - 18 edges
4. `ReportBuildError` - 16 edges
5. `validate_sql_safety()` - 16 edges
6. `get_settings()` - 15 edges
7. `_execute_with_schema_retries()` - 14 edges
8. `RetryAttempt` - 12 edges
9. `AiSqlGenerationError` - 12 edges
10. `SchemaService` - 12 edges

## Surprising Connections (you probably didn't know these)
- `get_engine()` --calls--> `get_settings()`  [INFERRED]
  backend\app\db.py → backend\app\core\config.py
- `get_engine()` --calls--> `health()`  [INFERRED]
  backend\app\db.py → backend\app\main.py
- `preview_attempt_rows()` --calls--> `fetch_rows()`  [INFERRED]
  backend\app\services\admin_attempt_preview.py → backend\app\db.py
- `fetch_rows()` --calls--> `build_report()`  [INFERRED]
  backend\app\db.py → backend\app\services\report_runner.py
- `fetch_rows()` --calls--> `_execute_with_schema_retries()`  [INFERRED]
  backend\app\db.py → backend\app\services\report_runner.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.09
Nodes (47): _console_attempt_log(), create_attempt(), _dedupe_examples(), ensure_ai_sql_attempts_table(), _ensure_attempt_columns(), _filter_similar_examples(), _format_scored_examples(), get_attempt() (+39 more)

### Community 1 - "Community 1"
Cohesion: 0.09
Nodes (42): BaseSettings, get_settings(), Settings, DateResolution, resolve_date_range(), RetryAttempt, _ai_report_error(), build_report() (+34 more)

### Community 2 - "Community 2"
Cohesion: 0.07
Nodes (23): ApiError, getSavedReport(), listAiSqlAttempts(), listSavedReports(), listSqlMistakeExamples(), previewAiSqlAttempt(), reviewAiSqlAttempt(), runReport() (+15 more)

### Community 3 - "Community 3"
Cohesion: 0.16
Nodes (27): catalog_context(), category_context(), load_report_catalog(), load_report_categories(), load_schema_catalog(), resolve_report_category(), AiSqlGenerationError, build_sql_generation_payload_preview() (+19 more)

### Community 4 - "Community 4"
Cohesion: 0.16
Nodes (26): BaseModel, AiSqlAttempt, AiSqlAttemptPreview, AiSqlAttemptReviewRequest, GeneratedReport, ReportRequest, SavedReportSummary, SqlMistakeExample (+18 more)

### Community 5 - "Community 5"
Cohesion: 0.15
Nodes (20): export_saved_report(), _build_pdf(), _cell_text(), _content_types_xml(), _draw_report_table(), _excel_column(), export_filename(), export_report_pdf() (+12 more)

### Community 6 - "Community 6"
Cohesion: 0.14
Nodes (22): QuerySafetyResult, Cheap first-pass safety check that inspects only the user query text., validate_user_query_safety(), _basic_sql_safety(), _mistake_type(), _requires_limit(), _risk_for_error(), SafetyValidationResult (+14 more)

### Community 7 - "Community 7"
Cohesion: 0.14
Nodes (10): _empty(), preview_attempt_rows(), _with_preview_limit(), get_db_config(), get_mysql_schema_json(), get_mysql_schema_json_legacy(), Exception, admin_ai_sql_attempt_preview() (+2 more)

### Community 8 - "Community 8"
Cohesion: 0.26
Nodes (18): build_cache_identity(), _cache_path(), _canonical_tokens(), _date_tokens(), _delete_entry(), generate_cache_key(), get_cached_sql(), _has_value_metric() (+10 more)

### Community 9 - "Community 9"
Cohesion: 0.3
Nodes (7): _collection(), _hash_embedding(), HashEmbeddingFunction, is_vector_store_available(), search_gold_examples(), _tokens(), upsert_gold_example()

### Community 10 - "Community 10"
Cohesion: 0.35
Nodes (10): build_validation_payload(), _compact_schema(), _extract_json_object(), _http_error_message(), OutputValidationError, _parse_validation_result(), _reason_from_errors(), _referenced_table_names() (+2 more)

### Community 11 - "Community 11"
Cohesion: 0.33
Nodes (6): report_categories(), _detect_category(), _fallback_category(), list_report_categories(), load_report_categories(), resolve_report_category()

### Community 12 - "Community 12"
Cohesion: 1.0
Nodes (1): AI reporting backend.

## Knowledge Gaps
- **4 isolated node(s):** `AI reporting backend.`, `Cheap first-pass safety check that inspects only the user query text.`, `Repair common AI SQL drift against the live Devita schema.`, `QueryTemplate`
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 12`** (2 nodes): `__init__.py`, `AI reporting backend.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `build_report()` connect `Community 1` to `Community 0`, `Community 3`, `Community 4`, `Community 6`, `Community 8`, `Community 11`?**
  _High betweenness centrality (0.284) - this node is a cross-community bridge._
- **Why does `get_settings()` connect `Community 1` to `Community 0`, `Community 3`, `Community 7`, `Community 8`, `Community 10`?**
  _High betweenness centrality (0.088) - this node is a cross-community bridge._
- **Why does `_validate_generated_output_with_retries()` connect `Community 1` to `Community 0`, `Community 3`, `Community 6`, `Community 10`, `Community 11`?**
  _High betweenness centrality (0.087) - this node is a cross-community bridge._
- **Are the 22 inferred relationships involving `build_report()` (e.g. with `query_report()` and `validate_user_query_safety()`) actually correct?**
  _`build_report()` has 22 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `_validate_generated_output_with_retries()` (e.g. with `get_settings()` and `validate_sql_safety()`) actually correct?**
  _`_validate_generated_output_with_retries()` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 16 inferred relationships involving `get_engine()` (e.g. with `get_settings()` and `health()`) actually correct?**
  _`get_engine()` has 16 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `ReportBuildError` (e.g. with `GeneratedReport` and `ReportRequest`) actually correct?**
  _`ReportBuildError` has 8 INFERRED edges - model-reasoned connections that need verification._