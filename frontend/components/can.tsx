"use client";
import type { ReactNode } from "react";
import type { Permission } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/** Renders its children only for users holding the permission; the API enforces it regardless. */
export function Can({ permission, children }: { permission: Permission; children: ReactNode }) {
  const { can } = useAuth();
  return can(permission) ? <>{children}</> : null;
}
