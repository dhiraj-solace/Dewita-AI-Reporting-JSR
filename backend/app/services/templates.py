from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QueryTemplate:
    title: str
    keywords: tuple[str, ...]
    sql: str
    explanation: str
    categories: tuple[str, ...] = ()
    blueprint: dict[str, Any] | None = None


WEEK_FIVE_BLUEPRINT: dict[str, Any] = {
    "layout": "week_matrix",
    "purpose": "Operational Week 5 project planning report matching the legacy Devita DAI Week Five report layout.",
    "contract": [
        "Preserve project-level detail rows grouped into business sections.",
        "Include section subtotal rows and one grand total row.",
        "Include dynamic week buckets for the selected year/week window.",
        "Include project task comments and revision project task comments when requested or available.",
        "User filters may narrow rows, but must not flatten the report into only aggregate totals unless explicitly asked.",
        "Do not use timelog_records.is_deleted; that column is not present in the live schema.",
    ],
    "schema_hints": {
        "task_source": "Use product_task for task rows and product_task.is_deleted for task soft-delete filtering.",
        "time_log_source": "timelog_records has hours, minutes, task_id, project_id, user_id, and date, but no is_deleted column.",
        "project_comments_source": "Use daily_project_comments or weekly_task_comments for project task comments when those tables are in schema.",
        "revision_comments_source": "Use revision_task_comments for revision comment detail rows.",
        "team_leader_source": "Use projects.primary_team_leader and projects.team_leader with users for team leader names.",
    },
    "sections": [
        "CAD Projects",
        "BIM Projects",
        "E-Dwg Review",
        "REVISION",
        "Steel Cards",
    ],
    "base_columns": [
        "dei_coord",
        "dai_coord",
        "priority",
        "project_no",
        "project_name",
        "project_type",
        "client",
        "mnfg",
        "kickoff_date",
        "kickoff_done",
        "dei_scope",
        "till_date",
        "till_last_weekend",
        "current_week_progress",
        "goal",
        "open",
    ],
    "week_bucket": {
        "column_pattern": "week_{number}",
        "label_pattern": "Week {number} ({start_date} - {end_date})",
        "default_window": "selected week and visible future weeks from the legacy report",
        "value": "task quantity or revision quantity planned/completed in that week",
    },
    "summary_rows": [
        "CAD + BIM Projects Total",
        "Total (CAD)",
        "Total (BIM)",
        "Total E-Dwg Review",
        "Total (REVISION)",
        "Total (Steel Cards)",
        "Grand Total",
    ],
    "color_rules": {
        "project_in_process": "Project name cell is green for in-process projects.",
        "project_not_started": "Project name cell is yellow for not-started/planned projects.",
        "out_for_approval": "Week cell is gray when the out-for-approval date falls in that week.",
        "production_date": "Week cell is magenta when project production date falls in that week.",
        "active_week_quantity": "Week cells with active/current work quantities are highlighted orange.",
        "section_total": "Section subtotal rows are blue.",
        "grand_total": "Grand total row is green.",
    },
    "filters": [
        "year",
        "week",
        "project",
        "team_leader",
        "dei_coord",
        "dai_coord",
        "show_completed",
        "previous_week",
    ],
    "related_detail_sections": [
        {
            "name": "Project Task Comments",
            "columns": ["id", "project_name", "user_name", "comment", "week_id", "created_at"],
        },
        {
            "name": "Revision Project Task Comments",
            "columns": ["id", "project_name", "changerequest_id", "user_name", "comment", "effective_percentage", "created_at"],
        },
    ],
}


DAILY_REPORT_BLUEPRINT: dict[str, Any] = {
    "layout": "daily_progress_matrix",
    "purpose": "Daily progress report for active CAD_CAM, BIM, and E-Drawing project work.",
    "contract": [
        "Preserve project-level detail rows grouped by manufacturing/report section.",
        "Segregate CAD_CAM, BIM, and E-Drawing work when those dimensions are available.",
        "Include team leader assignment analysis with primary versus secondary/assigned leader classification.",
        "Include daily task movement and weekly task count metrics; do not collapse the report into only project_name and task_count.",
        "Filter active projects with projects.project_status != 'Completed' and projects.project_type_id IS NOT NULL.",
        "Use product_task.is_deleted for task soft-delete filtering.",
        "Customize filters from the user question, such as BIM-only, CAD_CAM-only, team leader, project, or date.",
    ],
    "schema_hints": {
        "project_source": "Use projects for project status, manufacturing type, project type, primary team leader, priority, and E-Drawing applicability.",
        "task_source": "Use product_task for project tasks, assigned team leader, assigned member, task_status, created_at, updated_at, and is_deleted.",
        "task_detail_source": "Use product_task_details for uploaded_date and actual_hr when uploaded task/detail metrics are requested.",
        "team_leader_source": "Use product_task.assign_team_leader for task-level team leader analysis and projects.primary_team_leader for primary leader classification.",
        "edrawing_source": "Use projects.is_edrawing_applicable when the report asks for E-Drawing segregation and no dedicated E-Drawing task table is required.",
    },
    "sections": [
        "CAD_CAM Projects",
        "BIM Projects",
        "E-Drawing Projects",
    ],
    "base_columns": [
        "section",
        "leader_type",
        "team_leader",
        "project_type",
        "project_no",
        "project_name",
        "project_mfg_type",
        "priority",
        "project_status",
        "total_tasks",
        "completed_tasks",
        "open_tasks",
        "daily_created_tasks",
        "daily_completed_tasks",
        "daily_uploaded_task_details",
        "weekly_created_tasks",
    ],
    "default_date_behavior": "If no date is supplied, use today as the daily reporting window.",
    "summary_rows": [
        "Team leader totals",
        "Section totals",
        "Grand Total",
    ],
}


TEMPLATES: tuple[QueryTemplate, ...] = (
    QueryTemplate(
        title="Attendance Report",
        keywords=("attendance", "present", "absent", "check in", "check out", "hr"),
        sql="""
SELECT
  a.employee_id,
  COALESCE(u.name, a.name) AS employee_name,
  a.department,
  a.designation,
  a.date,
  a.day,
  a.status,
  a.total_hours AS work_hours,
  a.for_month
FROM attendances a
LEFT JOIN users u ON u.employee_id = a.employee_id
WHERE (:start_date IS NULL OR a.date >= :start_date)
  AND (:end_date IS NULL OR a.date <= :end_date)
ORDER BY a.date DESC, employee_name
        """.strip(),
        explanation="Attendance rows using live attendance total hours and employee details.",
        categories=("attendance",),
    ),
    QueryTemplate(
        title="Team Timesheet Report",
        keywords=("timesheet", "time spent", "weekly time", "team time", "hours worked"),
        sql="""
SELECT
  u.id AS user_id,
  u.name AS employee_name,
  u.employee_id,
  YEARWEEK(tr.date, 1) AS week_key,
  p.project_name,
  tr.work_type,
  tr.user_type,
  SUM(COALESCE(tr.hours, 0) + (COALESCE(tr.minutes, 0) / 60)) AS total_hours,
  SUM(
    CASE
      WHEN tr.non_billable_reason IS NOT NULL
      THEN COALESCE(tr.hours, 0) + (COALESCE(tr.minutes, 0) / 60)
      ELSE 0
    END
  ) AS non_billable_hours,
  COUNT(*) AS entry_count
FROM timelog_records tr
LEFT JOIN users u ON u.id = tr.user_id
LEFT JOIN projects p ON p.id = tr.project_id
WHERE (:start_date IS NULL OR tr.date >= :start_date)
  AND (:end_date IS NULL OR tr.date <= :end_date)
GROUP BY
  u.id,
  u.name,
  u.employee_id,
  YEARWEEK(tr.date, 1),
  p.project_name,
  tr.work_type,
  tr.user_type
ORDER BY week_key DESC, employee_name, p.project_name
        """.strip(),
        explanation="Weekly team timesheet hours by employee, project, work type, and user type using live hours/minutes.",
        categories=("timesheet",),
    ),
    QueryTemplate(
        title="Daily Report",
        keywords=("daily report", "daily progress", "daily task", "daily task completion", "daily imp", "daily-report"),
        sql="""
SELECT
  CASE
    WHEN p.project_mfg_type = 'CAD_CAM' THEN 'CAD_CAM Projects'
    WHEN p.project_mfg_type = 'BIM' THEN 'BIM Projects'
    WHEN COALESCE(p.is_edrawing_applicable, 0) = 1 THEN 'E-Drawing Projects'
    ELSE COALESCE(p.project_mfg_type, 'Unassigned')
  END AS section,
  CASE
    WHEN assigned_tl.id IS NULL THEN 'Unassigned'
    WHEN CAST(assigned_tl.id AS CHAR) = CAST(p.primary_team_leader AS CHAR) THEN 'Primary Team Leader'
    ELSE 'Secondary Team Leader'
  END AS leader_type,
  COALESCE(assigned_tl.name, primary_tl.name, 'Unassigned') AS team_leader,
  COALESCE(ptype.name, 'Unassigned') AS project_type,
  p.project_no,
  p.project_name,
  p.project_mfg_type,
  p.priority,
  p.project_status,
  COUNT(DISTINCT pt.id) AS total_tasks,
  COUNT(DISTINCT CASE WHEN pt.task_status = 'Completed' THEN pt.id END) AS completed_tasks,
  COUNT(DISTINCT CASE WHEN pt.id IS NOT NULL AND COALESCE(pt.task_status, '') != 'Completed' THEN pt.id END) AS open_tasks,
  COUNT(DISTINCT CASE WHEN DATE(pt.created_at) BETWEEN :start_date AND :end_date THEN pt.id END) AS daily_created_tasks,
  COUNT(DISTINCT CASE WHEN pt.task_status = 'Completed' AND DATE(pt.updated_at) BETWEEN :start_date AND :end_date THEN pt.id END) AS daily_completed_tasks,
  COUNT(DISTINCT CASE WHEN DATE(ptd.uploaded_date) BETWEEN :start_date AND :end_date THEN ptd.id END) AS daily_uploaded_task_details,
  COUNT(DISTINCT
    CASE
      WHEN DATE(pt.created_at) BETWEEN DATE_SUB(:start_date, INTERVAL WEEKDAY(:start_date) DAY) AND DATE_ADD(DATE_SUB(:start_date, INTERVAL WEEKDAY(:start_date) DAY), INTERVAL 6 DAY)
      THEN pt.id
    END
  ) AS weekly_created_tasks
FROM projects p
LEFT JOIN project_type ptype ON ptype.id = p.project_type_id
LEFT JOIN users primary_tl ON CAST(primary_tl.id AS CHAR) = CAST(p.primary_team_leader AS CHAR)
LEFT JOIN product_task pt ON pt.project_id = p.id AND COALESCE(pt.is_deleted, 0) = 0
LEFT JOIN users assigned_tl ON assigned_tl.id = pt.assign_team_leader
LEFT JOIN product_task_details ptd ON ptd.task_id = pt.id AND COALESCE(ptd.is_deleted, 0) = 0
WHERE p.project_status != 'Completed'
  AND p.project_type_id IS NOT NULL
  AND (
    p.project_mfg_type IN ('CAD_CAM', 'BIM')
    OR COALESCE(p.is_edrawing_applicable, 0) = 1
  )
GROUP BY
  section,
  leader_type,
  team_leader,
  ptype.name,
  p.project_no,
  p.project_name,
  p.project_mfg_type,
  p.priority,
  p.project_status
ORDER BY section, team_leader, p.project_name
        """.strip(),
        explanation="Daily active project progress for CAD_CAM, BIM, and E-Drawing work with team leader classification and daily/weekly task metrics.",
        categories=("task", "project"),
        blueprint=DAILY_REPORT_BLUEPRINT,
    ),
    QueryTemplate(
        title="Week Five Report",
        keywords=("week five", "week 5", "week-five", "5 week", "five week", "five-week", "project type"),
        sql="""
SELECT
  COALESCE(ptype.name, 'Unassigned') AS project_type,
  p.project_mfg_type,
  COUNT(DISTINCT p.id) AS total_projects,
  SUM(COALESCE(p.total_no_of_shop_tickets, 0)) AS total_shop_tickets,
  COUNT(DISTINCT task.id) AS total_tasks,
  SUM(CASE WHEN task.task_status = 'Completed' THEN 1 ELSE 0 END) AS completed_tasks,
  ROUND(
    (SUM(CASE WHEN task.task_status = 'Completed' THEN 1 ELSE 0 END) / NULLIF(COUNT(DISTINCT task.id), 0)) * 100,
    2
  ) AS completion_percentage
FROM projects p
LEFT JOIN project_type ptype ON ptype.id = p.project_type_id
LEFT JOIN product_task task ON task.project_id = p.id AND COALESCE(task.is_deleted, 0) = 0
WHERE p.project_status != 'Completed'
  AND COALESCE(p.client, '') != 'DAI'
  AND p.project_mfg_type IN ('CAD_CAM', 'BIM')
  AND (:start_date IS NULL OR DATE(p.created_at) >= :start_date)
  AND (:end_date IS NULL OR DATE(p.created_at) <= :end_date)
GROUP BY ptype.name, p.project_mfg_type
ORDER BY total_projects DESC, project_type
        """.strip(),
        explanation="Five-week planning summary grouped by project type and manufacturing type for active non-DAI CAD/BIM projects.",
        categories=("project",),
        blueprint=WEEK_FIVE_BLUEPRINT,
    ),
    QueryTemplate(
        title="Project Summary Report",
        keywords=("project summary", "project status", "budget variance", "active projects", "project progress"),
        sql="""
SELECT
  p.id,
  p.project_no,
  p.client,
  p.project_name,
  p.project_status,
  p.start_date,
  p.actual_end_date,
  p.total_budgeted_man_hrs,
  p.actual_man_hrs_utilized,
  (p.actual_man_hrs_utilized - p.total_budgeted_man_hrs) AS hour_variance,
  COUNT(pt.id) AS total_tasks,
  SUM(CASE WHEN pt.task_status = 'Completed' THEN 1 ELSE 0 END) AS completed_tasks,
  ROUND(
    (SUM(CASE WHEN pt.task_status = 'Completed' THEN 1 ELSE 0 END) / NULLIF(COUNT(pt.id), 0)) * 100,
    2
  ) AS progress_percentage
FROM projects p
LEFT JOIN product_task pt ON pt.project_id = p.id AND COALESCE(pt.is_deleted, 0) = 0
WHERE (:start_date IS NULL OR p.start_date >= :start_date)
  AND (:end_date IS NULL OR p.start_date <= :end_date)
GROUP BY p.id
ORDER BY p.start_date DESC, p.project_name
        """.strip(),
        explanation="Project-level status, budgeted vs actual hours, and task volume.",
        categories=("project", "finance"),
    ),
    QueryTemplate(
        title="Post Error Report",
        keywords=("bug", "post error", "defect", "quality issue"),
        sql="""
SELECT
  tbm.id,
  tbm.bug_id,
  p.project_name,
  tbm.task_id,
  tbm.severity,
  tbm.status,
  creator.name AS reported_by,
  assignee.name AS assigned_to,
  tbm.created_at
FROM task_bug_management tbm
LEFT JOIN product_task pt ON pt.id = tbm.task_id
LEFT JOIN projects p ON p.id = pt.project_id
LEFT JOIN users creator ON creator.id = tbm.bug_created_by
LEFT JOIN users assignee ON assignee.id = tbm.bug_assigned_to
WHERE (:start_date IS NULL OR DATE(tbm.created_at) >= :start_date)
  AND (:end_date IS NULL OR DATE(tbm.created_at) <= :end_date)
ORDER BY tbm.created_at DESC, tbm.severity
        """.strip(),
        explanation="Bug/error records with project, severity, status, and ownership.",
        categories=("quality",),
    ),
    QueryTemplate(
        title="Revision Summary by Project and Team Leader",
        keywords=("revision summary", "change request summary", "cr summary", "revision", "change request", "cr report", "cr ", "approval rate"),
        sql="""
SELECT
  p.project_name AS project,
  COALESCE(
    NULLIF(GROUP_CONCAT(DISTINCT tl.name ORDER BY tl.name SEPARATOR ', '), ''),
    primary_tl.name,
    'Unassigned'
  ) AS team_leader,
  COUNT(DISTINCT cr.id) AS total_revisions,
  SUM(CASE WHEN cr.changerequest_status = 'Approved' THEN 1 ELSE 0 END) AS approved_revisions,
  SUM(CASE WHEN cr.changerequest_status = 'Pending' THEN 1 ELSE 0 END) AS pending_revisions,
  SUM(CASE WHEN cr.changerequest_status = 'Rejected' THEN 1 ELSE 0 END) AS rejected_revisions
FROM changerequest_management cr
LEFT JOIN projects p ON p.id = cr.project_id
LEFT JOIN users primary_tl ON primary_tl.id = p.primary_team_leader
LEFT JOIN users tl
  ON FIND_IN_SET(
    CAST(tl.id AS CHAR),
    REPLACE(REPLACE(REPLACE(COALESCE(p.team_leader, ''), '[', ''), ']', ''), '"', '')
  ) > 0
WHERE (:start_date IS NULL OR cr.date >= :start_date)
  AND (:end_date IS NULL OR cr.date <= :end_date)
GROUP BY p.id, p.project_name, primary_tl.name
ORDER BY total_revisions DESC, p.project_name
        """.strip(),
        explanation="Counts change requests as revisions, grouped by project and project team leader for the requested period.",
        categories=("revision",),
    ),
)

def find_template(question: str, category_id: str | None = None) -> QueryTemplate | None:
    normalized = question.lower().replace("-", " ")
    scored: list[tuple[int, QueryTemplate]] = []
    for template in TEMPLATES:
        score = sum(1 for keyword in template.keywords if keyword in normalized)
        if category_id and category_id in template.categories:
            score += 3
        if score:
            scored.append((score, template))
    if not scored:
        return None
    return sorted(scored, key=lambda item: item[0], reverse=True)[0][1]
