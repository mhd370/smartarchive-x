"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { AUTH_EVENT, get, post, type Permission, type User } from "./api";

type AuthState = { user: User | null; checking: boolean; can: (permission: Permission) => boolean;
  signedIn: (user: User) => void; signOut: () => Promise<void> };
const AuthContext = createContext<AuthState | null>(null);
export const PUBLIC_PATHS = ["/login"];

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  const router = useRouter(), path = usePathname();
  const isPublic = PUBLIC_PATHS.includes(path);

  const toLogin = useCallback(() => {
    setUser(null);
    if (!PUBLIC_PATHS.includes(window.location.pathname)) {
      const next = window.location.pathname + window.location.search;
      router.replace(`/login?next=${encodeURIComponent(next)}`);
    }
  }, [router]);

  useEffect(() => {
    let active = true;
    get<User>("/auth/me").then(value => { if (active) setUser(value); })
      .catch(() => { if (active) toLogin(); })
      .finally(() => { if (active) setChecking(false); });
    return () => { active = false; };
  }, [toLogin]);

  useEffect(() => {
    window.addEventListener(AUTH_EVENT, toLogin);
    return () => window.removeEventListener(AUTH_EVENT, toLogin);
  }, [toLogin]);

  const signOut = useCallback(async () => {
    await post("/auth/logout").catch(() => undefined);
    setUser(null);
    router.replace("/login");
  }, [router]);

  const value: AuthState = {
    user, checking: checking && !isPublic, signedIn: setUser, signOut,
    can: permission => !!user?.permissions.includes(permission),
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}

export const roleNames: Record<User["role"], string> = {
  admin: "مدير النظام", archivist: "موظف أرشيف", reviewer: "مراجع", viewer: "مطّلع",
};
