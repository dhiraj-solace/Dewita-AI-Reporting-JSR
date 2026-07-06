"use client";

import {ReactNode, useEffect, useState} from "react";
import Link from "next/link";
import {Loader2, ShieldCheck} from "lucide-react";
import {UserPublic, getCurrentUser} from "@/lib/api";

type AdminGuardProps = {
  children: ReactNode;
};

export default function AdminGuard({children}: AdminGuardProps) {
  const [user, setUser] = useState<UserPublic | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getCurrentUser()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <main className="admin-access-shell">
        <Loader2 className="spin" size={24} />
        <strong>Checking admin access</strong>
      </main>
    );
  }

  if ((user?.role_name || "").toLowerCase() !== "super admin") {
    return (
      <main className="admin-access-shell denied">
        <ShieldCheck size={28} />
        <strong>Admin access only</strong>
        <span>Only Super Admin can open this page.</span>
        <Link href="/">Go to Reporting UI</Link>
      </main>
    );
  }

  return <>{children}</>;
}
