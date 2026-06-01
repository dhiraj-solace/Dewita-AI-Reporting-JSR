# Graph Report - Dewita AI Reporting JSR  (2026-06-01)

## Corpus Check
- 41 files · ~78,145 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 476 nodes · 1164 edges · 15 communities detected
- Extraction: 71% EXTRACTED · 29% INFERRED · 0% AMBIGUOUS · INFERRED: 336 edges (avg confidence: 0.76)
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
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 18|Community 18]]

## God Nodes (most connected - your core abstractions)
1. `get_engine()` - 42 edges
2. `build_report()` - 41 edges
3. `_validate_generated_output_with_retries()` - 30 edges
4. `get_settings()` - 21 edges
5. `validate_user_query_safety()` - 17 edges
6. `ReportBuildError` - 17 edges
7. `validate_sql_safety()` - 16 edges
8. `_run_schedule()` - 15 edges
9. `_execute_with_schema_retries()` - 14 edges
10. `RetryAttempt` - 13 edges

## Surprising Connections (you probably didn't know these)
- `get_engine()` --calls--> `health()`  [INFERRED]
  backend\app\db.py → backend\app\main.py
- `admin_report_permissions()` --calls--> `list_role_report_permissions()`  [INFERRED]
  backend\app\main.py → backend\app\services\report_permissions.py
- `admin_report_audit_logs()` --calls--> `list_audit_logs()`  [INFERRED]
  backend\app\main.py → backend\app\services\audit_log.py
- `admin_ai_sql_attempts()` --calls--> `list_attempts()`  [INFERRED]
  backend\app\main.py → backend\app\services\ai_sql_attempt_store.py
- `admin_ai_sql_attempt()` --calls--> `get_attempt()`  [INFERRED]
  backend\app\main.py → backend\app\services\ai_sql_attempt_store.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.04
Nodes (42): ApiError, createScheduledReport(), getHealth(), getSavedReport(), listAiSqlAttemptEvents(), listAiSqlAttempts(), listReportAuditLogs(), listReportPermissions() (+34 more)

### Community 1 - "Community 1"
Cohesion: 0.1
Nodes (60): _console_attempt_log(), create_attempt(), _dedupe_examples(), ensure_ai_sql_attempts_table(), _ensure_attempt_columns(), _ensure_attempt_events_table(), _filter_similar_examples(), _format_scored_examples() (+52 more)

### Community 2 - "Community 2"
Cohesion: 0.08
Nodes (49): BaseModel, build_validation_payload(), _compact_schema(), _extract_json_object(), _http_error_message(), OutputValidationError, _parse_validation_result(), _reason_from_errors() (+41 more)

### Community 3 - "Community 3"
Cohesion: 0.11
Nodes (40): DateResolution, resolve_date_range(), RetryAttempt, resolve_report_category(), _ai_report_error(), build_report(), _console_attempt_detail(), _console_attempt_log() (+32 more)

### Community 4 - "Community 4"
Cohesion: 0.09
Nodes (32): admin_ai_sql_attempt(), admin_ai_sql_attempts(), admin_create_scheduled_report(), admin_report_audit_logs(), admin_report_permissions(), admin_run_scheduled_report_now(), admin_scheduled_report(), admin_scheduled_report_runs() (+24 more)

### Community 5 - "Community 5"
Cohesion: 0.13
Nodes (28): BaseSettings, get_settings(), Settings, _build_attachments(), _clean_recipients(), _email_body(), is_email_configured(), send_report_email() (+20 more)

### Community 6 - "Community 6"
Cohesion: 0.11
Nodes (29): _classify_intent_with_openrouter(), _console_intent_detail(), _console_intent_log(), _intent_classifier_error_message(), _parse_json_object(), QuerySafetyResult, Classify user intent with OpenRouter instead of keyword blocking., _short_reason() (+21 more)

### Community 7 - "Community 7"
Cohesion: 0.16
Nodes (28): catalog_context(), category_context(), _detect_category_with_openrouter(), load_report_catalog(), load_report_categories(), load_schema_catalog(), resolve_report_category(), resolve_report_category_with_ai() (+20 more)

### Community 8 - "Community 8"
Cohesion: 0.15
Nodes (20): export_saved_report(), _build_pdf(), _cell_text(), _content_types_xml(), _draw_report_table(), _excel_column(), export_filename(), export_report_pdf() (+12 more)

### Community 9 - "Community 9"
Cohesion: 0.17
Nodes (21): report_categories(), _detect_category(), _fallback_category(), list_report_categories(), load_report_categories(), assert_report_permission(), _category_ids(), ensure_role_report_permissions_table() (+13 more)

### Community 10 - "Community 10"
Cohesion: 0.14
Nodes (10): _empty(), preview_attempt_rows(), _with_preview_limit(), get_db_config(), get_mysql_schema_json(), get_mysql_schema_json_legacy(), Exception, admin_ai_sql_attempt_preview() (+2 more)

### Community 11 - "Community 11"
Cohesion: 0.3
Nodes (7): _collection(), _hash_embedding(), HashEmbeddingFunction, is_vector_store_available(), search_gold_examples(), _tokens(), upsert_gold_example()

### Community 12 - "Community 12"
Cohesion: 0.35
Nodes (10): admin_sql_mistake_examples(), _console_log(), create_mistake_example(), ensure_sql_mistake_examples_table(), list_mistake_examples(), _now(), similar_mistake_examples(), _token_similarity() (+2 more)

### Community 13 - "Community 13"
Cohesion: 1.0
Nodes (1): AI reporting backend.

### Community 18 - "Community 18"
Cohesion: 1.0
Nodes (1): Cheap first-pass safety check that inspects only the user query text.

## Knowledge Gaps
- **5 isolated node(s):** `AI reporting backend.`, `Classify user intent with OpenRouter instead of keyword blocking.`, `Repair common AI SQL drift against the live Devita schema.`, `QueryTemplate`, `Cheap first-pass safety check that inspects only the user query text.`
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 13`** (2 nodes): `__init__.py`, `AI reporting backend.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 18`** (1 nodes): `Cheap first-pass safety check that inspects only the user query text.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `build_report()` connect `Community 3` to `Community 1`, `Community 2`, `Community 4`, `Community 5`, `Community 6`, `Community 7`, `Community 9`, `Community 12`?**
  _High betweenness centrality (0.253) - this node is a cross-community bridge._
- **Why does `load()` connect `Community 0` to `Community 10`?**
  _High betweenness centrality (0.252) - this node is a cross-community bridge._
- **Why does `get_settings()` connect `Community 5` to `Community 1`, `Community 2`, `Community 3`, `Community 6`, `Community 7`, `Community 10`?**
  _High betweenness centrality (0.131) - this node is a cross-community bridge._
- **Are the 40 inferred relationships involving `get_engine()` (e.g. with `get_settings()` and `health()`) actually correct?**
  _`get_engine()` has 40 INFERRED edges - model-reasoned connections that need verification._
- **Are the 25 inferred relationships involving `build_report()` (e.g. with `query_report()` and `create_attempt()`) actually correct?**
  _`build_report()` has 25 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `_validate_generated_output_with_retries()` (e.g. with `get_settings()` and `update_attempt()`) actually correct?**
  _`_validate_generated_output_with_retries()` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `get_settings()` (e.g. with `get_engine()` and `_detect_category_with_openrouter()`) actually correct?**
  _`get_settings()` has 19 INFERRED edges - model-reasoned connections that need verification._