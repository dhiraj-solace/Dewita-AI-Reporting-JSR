from dataclasses import dataclass


@dataclass(frozen=True)
class QueryTemplate:
    title: str
    keywords: tuple[str, ...]
    sql: str
    explanation: str
    categories: tuple[str, ...] = ()


TEMPLATES: tuple[QueryTemplate, ...] = (
    QueryTemplate(
        title="Attendance Report",
        keywords=("attendance", "present", "absent", "check in", "check out", "hr"),
        sql="""
SELECT
  u.id AS user_id,
  u.name AS employee_name,
  a.date,
  a.status,
  a.check_in,
  a.check_out,
  TIMEDIFF(a.check_out, a.check_in) AS work_hours
FROM attendances a
LEFT JOIN users u ON u.id = a.user_id
WHERE (:start_date IS NULL OR a.date >= :start_date)
  AND (:end_date IS NULL OR a.date <= :end_date)
ORDER BY a.date DESC, u.name
        """.strip(),
        explanation="Attendance with calculated work hours from check-in and check-out.",
        categories=("attendance",),
    ),
    QueryTemplate(
        title="Team Timesheet Report",
        keywords=("timesheet", "time spent", "weekly time", "team time", "hours worked"),
        sql="""
SELECT
  u.id AS user_id,
  u.name AS employee_name,
  p.project_name,
  tr.date,
  tr.work_type,
  tr.role_type,
  tr.time_spent,
  tr.description
FROM timelog_records tr
LEFT JOIN users u ON u.id = tr.user_id
LEFT JOIN projects p ON p.id = tr.project_id
WHERE (:start_date IS NULL OR tr.date >= :start_date)
  AND (:end_date IS NULL OR tr.date <= :end_date)
ORDER BY tr.date DESC, employee_name, p.project_name
        """.strip(),
        explanation="Time entries joined to employee and project context.",
        categories=("timesheet",),
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
