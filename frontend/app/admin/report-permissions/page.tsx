"use client";

import {useEffect, useMemo, useState} from "react";
import {RefreshCw, Save, ShieldCheck} from "lucide-react";
import {
  ReportCategory,
  ReportPermissionsMatrix,
  RoleReportPermission,
  listReportPermissions,
  updateReportPermissions
} from "@/lib/api";
import AdminGuard from "../AdminGuard";

const actions: Array<keyof Pick<RoleReportPermission, "can_view" | "can_create" | "can_export" | "can_save" | "can_view_saved">> = [
  "can_view",
  "can_create",
  "can_export",
  "can_save",
  "can_view_saved"
];

const actionLabels: Record<(typeof actions)[number], string> = {
  can_view: "View",
  can_create: "Create",
  can_export: "Export",
  can_save: "Save",
  can_view_saved: "Saved"
};

function permissionKey(role: string, category: string) {
  return `${role}::${category}`;
}

function emptyPermission(role: string, category: string): RoleReportPermission {
  return {
    role_name: role,
    report_category: category,
    can_view: false,
    can_create: false,
    can_export: false,
    can_save: false,
    can_view_saved: false,
    data_scope: "none"
  };
}

function categoryLabel(category: ReportCategory) {
  return category.id === "custom" ? "Custom" : category.label.replace(" Report", "");
}

export default function ReportPermissionsAdminPage() {
  const [embedded, setEmbedded] = useState(false);
  const [matrix, setMatrix] = useState<ReportPermissionsMatrix | null>(null);
  const [permissions, setPermissions] = useState<Record<string, RoleReportPermission>>({});
  const [selectedRole, setSelectedRole] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [savedMessage, setSavedMessage] = useState("");

  useEffect(() => {
    setEmbedded(new URLSearchParams(window.location.search).get("embedded") === "1");
  }, []);

  useEffect(() => {
    load();
  }, []);

  const categories = useMemo(
    () => (matrix?.categories || []).filter((category) => category.id !== "auto"),
    [matrix]
  );
  const roles = matrix?.roles || [];
  const activeRole = selectedRole || roles[0] || "";

  async function load() {
    setLoading(true);
    setError("");
    setSavedMessage("");
    try {
      const data = await listReportPermissions();
      setMatrix(data);
      setSelectedRole((current) => current || data.roles[0] || "");
      setPermissions(Object.fromEntries(data.permissions.map((item) => [permissionKey(item.role_name, item.report_category), item])));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load report permissions");
    } finally {
      setLoading(false);
    }
  }

  function getPermission(role: string, category: string) {
    return permissions[permissionKey(role, category)] || emptyPermission(role, category);
  }

  function updatePermission(role: string, category: string, patch: Partial<RoleReportPermission>) {
    const key = permissionKey(role, category);
    setPermissions((current) => ({
      ...current,
      [key]: {...getPermission(role, category), ...patch}
    }));
    setSavedMessage("");
  }

  async function save() {
    if (!matrix) return;
    setSaving(true);
    setError("");
    try {
      const payload = roles.flatMap((role) => categories.map((category) => getPermission(role, category.id)));
      const updated = await updateReportPermissions(payload, "Super Admin");
      setMatrix(updated);
      setPermissions(Object.fromEntries(updated.permissions.map((item) => [permissionKey(item.role_name, item.report_category), item])));
      setSavedMessage("Permissions saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save report permissions");
    } finally {
      setSaving(false);
    }
  }

  function setAllForCategory(role: string, category: string, enabled: boolean) {
    updatePermission(role, category, {
      can_view: enabled,
      can_create: enabled,
      can_export: enabled,
      can_save: enabled,
      can_view_saved: enabled,
      data_scope: enabled ? "all" : "none"
    });
  }

  return (
    <AdminGuard>
    <main className={embedded ? "admin-shell permission-shell embedded-admin-shell" : "admin-shell permission-shell"}>
      <header className="admin-header">
        <div>
          <h1>Report Role Permissions</h1>
          <p>Assign report categories and actions directly to roles.</p>
        </div>
        <div className="admin-actions">
          <button onClick={load} disabled={loading || saving} type="button">
            <RefreshCw size={18} /> Refresh
          </button>
          <button className="active" onClick={save} disabled={loading || saving || !matrix} type="button">
            <Save size={18} /> {saving ? "Saving" : "Save"}
          </button>
        </div>
      </header>

      {error && <div className="admin-error">{error}</div>}
      {savedMessage && <div className="admin-success">{savedMessage}</div>}

      <section className="permission-layout">
        <aside className="permission-roles">
          <div className="attempt-list-header">
            <span>Roles</span>
            <strong>{roles.length}</strong>
          </div>
          {loading && <div className="attempt-empty">Loading roles...</div>}
          {!loading && roles.map((role) => (
            <button
              className={activeRole === role ? "permission-role active" : "permission-role"}
              key={role}
              onClick={() => setSelectedRole(role)}
              type="button"
            >
              <ShieldCheck size={18} />
              <span>{role}</span>
            </button>
          ))}
        </aside>

        <section className="permission-panel">
          {!loading && activeRole && (
            <>
              <div className="permission-panel-header">
                <div>
                  <span>Selected Role</span>
                  <h2>{activeRole}</h2>
                </div>
                <p>{categories.length} report categories</p>
              </div>

              <div className="permission-table-wrap">
                <table className="permission-table">
                  <thead>
                    <tr>
                      <th>Report Category</th>
                      <th>Quick</th>
                      {actions.map((action) => <th key={action}>{actionLabels[action]}</th>)}
                      <th>Data Scope</th>
                    </tr>
                  </thead>
                  <tbody>
                    {categories.map((category) => {
                      const item = getPermission(activeRole, category.id);
                      const allEnabled = actions.every((action) => item[action]);
                      return (
                        <tr key={category.id}>
                          <td>
                            <strong>{categoryLabel(category)}</strong>
                            <span>{category.id}</span>
                          </td>
                          <td>
                            <input
                              checked={allEnabled}
                              onChange={(event) => setAllForCategory(activeRole, category.id, event.target.checked)}
                              type="checkbox"
                            />
                          </td>
                          {actions.map((action) => (
                            <td key={action}>
                              <input
                                checked={Boolean(item[action])}
                                onChange={(event) => updatePermission(activeRole, category.id, {[action]: event.target.checked})}
                                type="checkbox"
                              />
                            </td>
                          ))}
                          <td>
                            <select
                              value={item.data_scope}
                              onChange={(event) => updatePermission(activeRole, category.id, {data_scope: event.target.value as RoleReportPermission["data_scope"]})}
                            >
                              {(matrix?.scopes || []).map((scope) => <option key={scope} value={scope}>{scope}</option>)}
                            </select>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </section>
      </section>
    </main>
    </AdminGuard>
  );
}
