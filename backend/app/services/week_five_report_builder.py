from dataclasses import dataclass


@dataclass(frozen=True)
class WeekFiveIntent:
    manufacturing_type: str | None = None
    group_by_team_leader: bool = False
    include_project_task_comments: bool = False
    include_section_totals: bool = True
    include_grand_total: bool = True
    detailed_project_product_breakdown: bool = False


def is_week_five_question(question: str) -> bool:
    normalized = question.lower().replace("-", " ")
    return any(term in normalized for term in ("week five", "week 5", "five week", "dai week 5"))


def resolve_week_five_intent(question: str) -> WeekFiveIntent:
    normalized = question.lower().replace("-", " ")
    manufacturing_type = None
    if "bim" in normalized:
        manufacturing_type = "BIM"
    elif "cad" in normalized or "cad cam" in normalized:
        manufacturing_type = "CAD_CAM"

    return WeekFiveIntent(
        manufacturing_type=manufacturing_type,
        group_by_team_leader="team leader" in normalized or "tl" in normalized,
        include_project_task_comments="comment" in normalized,
        detailed_project_product_breakdown=_is_project_product_breakdown_request(normalized),
    )


def build_week_five_sql(intent: WeekFiveIntent) -> str:
    if intent.detailed_project_product_breakdown:
        return _build_project_product_breakdown_sql(intent)

    manufacturing_filter = _manufacturing_filter(intent.manufacturing_type)
    ctes = [_task_rollup_cte()]
    if intent.include_project_task_comments:
        ctes.append(_comment_rollup_cte())
    ctes.append(_project_rows_cte(intent, manufacturing_filter))

    report_queries = [_detail_sql()]
    if intent.group_by_team_leader:
        report_queries.append(_team_leader_total_sql())
    if intent.include_section_totals:
        report_queries.append(_section_total_sql())
    if intent.include_grand_total:
        report_queries.append(_grand_total_sql(intent))

    cte_sql = ",\n".join(ctes)
    report_sql = "\nUNION ALL\n".join(report_queries)
    return f"""
WITH
{cte_sql}
{report_sql}
ORDER BY sort_order, section, team_leader, project_name
""".strip()


def _is_project_product_breakdown_request(normalized: str) -> bool:
    detail_terms = (
        "product",
        "shop ticket",
        "team member",
        "kickoff",
        "kick off",
        "uploaded yesterday",
        "completed yesterday",
    )
    return "project" in normalized and any(term in normalized for term in detail_terms)


def _build_project_product_breakdown_sql(intent: WeekFiveIntent) -> str:
    manufacturing_filter = _manufacturing_filter(intent.manufacturing_type)
    return f"""
WITH
project_task_rollup AS (
  SELECT
    task.project_id,
    COUNT(DISTINCT task.id) AS total_planned_tasks
  FROM product_task task
  WHERE COALESCE(task.is_deleted, 0) = 0
  GROUP BY task.project_id
),
product_task_rollup AS (
  SELECT
    task.project_id,
    task.product_id,
    COUNT(DISTINCT task.id) AS product_shop_tickets,
    COALESCE(GROUP_CONCAT(DISTINCT member.name ORDER BY member.name SEPARATOR ', '), 'Unassigned') AS assigned_team_members,
    COUNT(DISTINCT CASE
      WHEN DATE(ptd.uploaded_date) = CURRENT_DATE - INTERVAL 1 DAY THEN task.id
    END) AS uploaded_yesterday_tasks,
    COUNT(DISTINCT CASE
      WHEN task.task_status = 'Completed' AND DATE(task.updated_at) = CURRENT_DATE - INTERVAL 1 DAY THEN task.id
    END) AS completed_yesterday_tasks
  FROM product_task task
  LEFT JOIN users member ON member.id = task.assign_member
  LEFT JOIN product_task_details ptd ON ptd.task_id = task.id AND COALESCE(ptd.is_deleted, 0) = 0
  WHERE COALESCE(task.is_deleted, 0) = 0
  GROUP BY task.project_id, task.product_id
)
SELECT
  10 AS sort_order,
  'project_product_detail' AS row_type,
  p.project_no,
  p.project_name,
  COALESCE(tl.name, 'Unassigned') AS team_leader,
  COALESCE(product_task_rollup.assigned_team_members, 'Unassigned') AS assigned_team_members,
  COALESCE(prod.name, 'Unassigned Product') AS product_name,
  COALESCE(product_task_rollup.product_shop_tickets, 0) AS product_shop_tickets,
  p.kick_off_meeting_date AS project_kickoff_date,
  p.priority AS project_priority,
  p.project_mfg_type,
  COALESCE(project_task_rollup.total_planned_tasks, 0) AS total_planned_tasks,
  COALESCE(product_task_rollup.uploaded_yesterday_tasks, 0) AS uploaded_yesterday_tasks,
  COALESCE(product_task_rollup.completed_yesterday_tasks, 0) AS completed_yesterday_tasks
FROM projects p
LEFT JOIN users tl ON tl.id = p.primary_team_leader
LEFT JOIN project_task_rollup ON project_task_rollup.project_id = p.id
LEFT JOIN product_task_rollup ON product_task_rollup.project_id = p.id
LEFT JOIN products prod ON prod.id = product_task_rollup.product_id
WHERE p.project_status != 'Completed'
  AND COALESCE(p.client, '') = 'DAI'
  AND {manufacturing_filter}
ORDER BY p.project_name, product_name
""".strip()


def _task_rollup_cte() -> str:
    return """
task_rollup AS (
  SELECT
    task.project_id,
    COUNT(DISTINCT task.id) AS total_tasks,
    SUM(CASE WHEN task.task_status = 'Completed' THEN 1 ELSE 0 END) AS completed_tasks,
    SUM(CASE WHEN COALESCE(task.task_status, '') != 'Completed' THEN 1 ELSE 0 END) AS open_tasks
  FROM product_task task
  WHERE COALESCE(task.is_deleted, 0) = 0
  GROUP BY task.project_id
)""".strip()


def _comment_rollup_cte() -> str:
    return """
comment_rollup AS (
  SELECT
    dpc.project_id,
    GROUP_CONCAT(DISTINCT dpc.comment ORDER BY dpc.created_at SEPARATOR ' | ') AS project_task_comments
  FROM daily_project_comments dpc
  GROUP BY dpc.project_id
)""".strip()


def _project_rows_cte(intent: WeekFiveIntent, manufacturing_filter: str) -> str:
    comments_select = (
        "COALESCE(comment_rollup.project_task_comments, '') AS project_task_comments"
        if intent.include_project_task_comments
        else "NULL AS project_task_comments"
    )
    comments_join = (
        "LEFT JOIN comment_rollup ON comment_rollup.project_id = p.id"
        if intent.include_project_task_comments
        else ""
    )

    return f"""
project_rows AS (
  SELECT
    CASE
      WHEN p.project_mfg_type = 'BIM' THEN 'BIM Projects'
      WHEN p.project_mfg_type = 'CAD_CAM' THEN 'CAD Projects'
      ELSE COALESCE(p.project_mfg_type, 'Unassigned')
    END AS section,
    COALESCE(tl.name, 'Unassigned') AS team_leader,
    p.project_no,
    p.project_name,
    p.project_mfg_type,
    COALESCE(ptype.name, 'Unassigned') AS project_type,
    COALESCE(task_rollup.total_tasks, 0) AS total_tasks,
    COALESCE(task_rollup.completed_tasks, 0) AS completed_tasks,
    COALESCE(task_rollup.open_tasks, 0) AS open_tasks,
    COALESCE(p.total_no_of_shop_tickets, 0) AS total_shop_tickets,
    {comments_select}
  FROM projects p
  LEFT JOIN project_type ptype ON ptype.id = p.project_type_id
  LEFT JOIN users tl ON tl.id = p.primary_team_leader
  LEFT JOIN task_rollup ON task_rollup.project_id = p.id
  {comments_join}
  WHERE p.project_status != 'Completed'
    AND COALESCE(p.client, '') = 'DAI'
    AND {manufacturing_filter}
)""".strip()


def _detail_sql() -> str:
    return """
SELECT
  10 AS sort_order,
  'detail' AS row_type,
  section,
  team_leader,
  project_no,
  project_name,
  project_mfg_type,
  project_type,
  total_tasks,
  completed_tasks,
  open_tasks,
  total_shop_tickets,
  ROUND(
    (completed_tasks / NULLIF(total_tasks, 0)) * 100,
    2
  ) AS completion_percentage,
  project_task_comments
FROM project_rows
""".strip()


def _team_leader_total_sql() -> str:
    return """
SELECT
  80 AS sort_order,
  'team_leader_total' AS row_type,
  section,
  team_leader,
  NULL AS project_no,
  CONCAT('Total (', team_leader, ')') AS project_name,
  project_mfg_type,
  'All Project Types' AS project_type,
  SUM(total_tasks) AS total_tasks,
  SUM(completed_tasks) AS completed_tasks,
  SUM(open_tasks) AS open_tasks,
  SUM(total_shop_tickets) AS total_shop_tickets,
  ROUND(
    (SUM(completed_tasks) / NULLIF(SUM(total_tasks), 0)) * 100,
    2
  ) AS completion_percentage,
  NULL AS project_task_comments
FROM project_rows
GROUP BY section, project_mfg_type, team_leader
""".strip()


def _section_total_sql() -> str:
    return """
SELECT
  90 AS sort_order,
  'section_total' AS row_type,
  CASE
    WHEN project_mfg_type = 'BIM' THEN 'Total (BIM)'
    WHEN project_mfg_type = 'CAD_CAM' THEN 'Total (CAD)'
    ELSE CONCAT('Total (', COALESCE(project_mfg_type, 'Unassigned'), ')')
  END AS section,
  'All Team Leaders' AS team_leader,
  NULL AS project_no,
  CASE
    WHEN project_mfg_type = 'BIM' THEN 'Total (BIM)'
    WHEN project_mfg_type = 'CAD_CAM' THEN 'Total (CAD)'
    ELSE CONCAT('Total (', COALESCE(project_mfg_type, 'Unassigned'), ')')
  END AS project_name,
  project_mfg_type,
  'All Project Types' AS project_type,
  SUM(total_tasks) AS total_tasks,
  SUM(completed_tasks) AS completed_tasks,
  SUM(open_tasks) AS open_tasks,
  SUM(total_shop_tickets) AS total_shop_tickets,
  ROUND(
    (SUM(completed_tasks) / NULLIF(SUM(total_tasks), 0)) * 100,
    2
  ) AS completion_percentage,
  NULL AS project_task_comments
FROM project_rows
GROUP BY project_mfg_type
""".strip()


def _grand_total_sql(intent: WeekFiveIntent) -> str:
    team_leader_label = "All Team Leaders" if intent.group_by_team_leader else "All"
    return f"""
SELECT
  99 AS sort_order,
  'grand_total' AS row_type,
  'Grand Total' AS section,
  '{team_leader_label}' AS team_leader,
  NULL AS project_no,
  'Grand Total' AS project_name,
  COALESCE({ _manufacturing_total_label(intent.manufacturing_type) }, 'All') AS project_mfg_type,
  'All Project Types' AS project_type,
  SUM(total_tasks) AS total_tasks,
  SUM(completed_tasks) AS completed_tasks,
  SUM(open_tasks) AS open_tasks,
  SUM(total_shop_tickets) AS total_shop_tickets,
  ROUND(
    (SUM(completed_tasks) / NULLIF(SUM(total_tasks), 0)) * 100,
    2
  ) AS completion_percentage,
  NULL AS project_task_comments
FROM project_rows
""".strip()


def build_week_five_generated_payload(question: str) -> dict[str, str] | None:
    if not is_week_five_question(question):
        return None
    intent = resolve_week_five_intent(question)
    return {
        "title": _title(intent),
        "sql": build_week_five_sql(intent),
        "explanation": _explanation(intent),
    }


def _manufacturing_filter(manufacturing_type: str | None) -> str:
    if manufacturing_type == "BIM":
        return "p.project_mfg_type = 'BIM'"
    if manufacturing_type == "CAD_CAM":
        return "p.project_mfg_type = 'CAD_CAM'"
    return "p.project_mfg_type IN ('CAD_CAM', 'BIM')"


def _manufacturing_total_label(manufacturing_type: str | None) -> str:
    if manufacturing_type:
        return f"'{manufacturing_type}'"
    return "'CAD_CAM+BIM'"


def _title(intent: WeekFiveIntent) -> str:
    prefix = "BIM " if intent.manufacturing_type == "BIM" else "CAD " if intent.manufacturing_type == "CAD_CAM" else ""
    return f"{prefix}Week Five Report".strip()


def _explanation(intent: WeekFiveIntent) -> str:
    parts = ["Deterministic Week 5 project report generated from the approved Week 5 contract."]
    if intent.manufacturing_type:
        parts.append(f"Filtered to {intent.manufacturing_type} projects.")
    if intent.group_by_team_leader:
        parts.append("Includes team leader grouping.")
    if intent.include_project_task_comments:
        parts.append("Includes project task comments from daily project comments.")
    if intent.include_grand_total:
        parts.append("Includes a grand total row.")
    return " ".join(parts)
