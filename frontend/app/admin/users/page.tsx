"use client";

import {FormEvent, useEffect, useState} from "react";
import Link from "next/link";
import {ArrowLeft, Loader2, Menu, Plus, RefreshCw, Save, User, Users} from "lucide-react";
import {
  UserPublic,
  createUser,
  getCurrentUser,
  listUsers,
  updateUser
} from "@/lib/api";
import AdminGuard from "../AdminGuard";

const roleOptions = ["Super Admin", "HR", "Project Manager", "Team Leader", "Team Member"];

export default function AdminUsersPage() {
  const [currentUser, setCurrentUser] = useState<UserPublic | null>(null);
  const [users, setUsers] = useState<UserPublic[]>([]);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [roleName, setRoleName] = useState("Team Member");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    getCurrentUser().then(setCurrentUser).catch(() => setCurrentUser(null));
    load();
  }, []);

  async function load() {
    setLoading(true);
    setError("");
    try {
      setUsers(await listUsers());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load users");
    } finally {
      setLoading(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setStatus("");
    setError("");
    try {
      await createUser({name, email, password, role_name: roleName, is_active: true});
      setName("");
      setEmail("");
      setPassword("");
      setRoleName("Team Member");
      setStatus("User created.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create user");
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive(user: UserPublic) {
    setError("");
    setStatus("");
    if (currentUser?.id === user.id) {
      setError("You cannot deactivate your own admin account.");
      return;
    }
    try {
      await updateUser(user.id, {is_active: !user.is_active});
      setStatus(user.is_active ? "User deactivated." : "User activated.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update user");
    }
  }

  return (
    <AdminGuard>
    <main className="admin-portal-shell">
      <section className="page">
        <header className="topbar">
          <button className="icon-button" title="Menu"><Menu size={26} /></button>
          <div className="top-actions">
            <Link href="/admin" className="admin-report-link"><ArrowLeft size={16} /> Admin Console</Link>
            <Link href="/" className="admin-report-link">Reporting UI</Link>
            <button className="icon-button" onClick={load} disabled={loading} title="Refresh" type="button">
              <RefreshCw className={loading ? "spin" : ""} size={22} />
            </button>
            <span className="user-chip"><User size={18} />{currentUser?.name || "Admin"}</span>
          </div>
        </header>

        <section className="content admin-console-content">
          <header className="admin-console-hero">
            <div>
              <span>Access Management</span>
              <h1>User Management</h1>
              <p>Create users, assign business roles, and control who can receive shared reports.</p>
            </div>
          </header>

          {error && <div className="admin-error">{error}</div>}
          {status && <div className="share-status">{status}</div>}

          <section className="admin-users-layout">
            <form className="admin-user-form" onSubmit={submit}>
              <h2><Plus size={20} /> Add User</h2>
              <label><span>Name</span><input value={name} onChange={(event) => setName(event.target.value)} /></label>
              <label><span>Email</span><input value={email} onChange={(event) => setEmail(event.target.value)} type="email" /></label>
              <label><span>Password</span><input value={password} onChange={(event) => setPassword(event.target.value)} type="password" /></label>
              <label>
                <span>Role</span>
                <select value={roleName} onChange={(event) => setRoleName(event.target.value)}>
                  {roleOptions.map((role) => <option key={role} value={role}>{role}</option>)}
                </select>
              </label>
              <button className="active" disabled={saving} type="submit">
                {saving ? <Loader2 className="spin" size={18} /> : <Save size={18} />}
                {saving ? "Saving" : "Create User"}
              </button>
            </form>

            <section className="admin-users-panel">
              <div className="admin-console-panel-header">
                <h2><Users size={20} /> Users</h2>
                <span>{users.length} total</span>
              </div>
              <div className="admin-user-list">
                {users.map((item) => (
                  <div className="admin-user-row" key={item.id}>
                    <span>
                      <strong>{item.name}</strong>
                      <small>{item.email}</small>
                    </span>
                    <em>{item.role_name}</em>
                    <strong className={item.is_active ? "user-status active" : "user-status inactive"}>
                      {item.is_active ? "Active" : "Inactive"}
                    </strong>
                    <button
                      className={item.is_active ? "deactivate" : "activate"}
                      disabled={currentUser?.id === item.id}
                      onClick={() => toggleActive(item)}
                      type="button"
                    >
                      {item.is_active ? "Deactivate" : "Activate"}
                    </button>
                  </div>
                ))}
                {!loading && users.length === 0 && <div className="attempt-empty">No users found.</div>}
              </div>
            </section>
          </section>
        </section>
      </section>
    </main>
    </AdminGuard>
  );
}
