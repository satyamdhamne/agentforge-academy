import { createContext, useContext, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import type { User } from "./types";

interface AuthState {
  user: User | null;
  loading: boolean;
  isStaff: boolean;
  isReviewer: boolean;
  isAdmin: boolean;
  refresh: () => Promise<unknown>;
  setUser: (u: User | null) => void;
  logout: () => Promise<void>;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await api.get<User>("/auth/me");
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 60_000,
    retry: false,
  });
  const user = q.data ?? null;
  const roles = new Set(user?.roles ?? []);
  const value: AuthState = {
    user,
    loading: q.isLoading,
    isAdmin: roles.has("admin"),
    isReviewer: roles.has("reviewer") || roles.has("admin"),
    isStaff: roles.has("author") || roles.has("reviewer") || roles.has("admin"),
    refresh: () => q.refetch(),
    setUser: (u) => qc.setQueryData(["me"], u),
    logout: async () => {
      await api.post("/auth/logout");
      qc.clear();
      qc.setQueryData(["me"], null);
    },
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth must be used inside AuthProvider");
  return v;
}
