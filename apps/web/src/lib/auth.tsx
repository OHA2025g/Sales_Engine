"use client";

import { api, getApiBase, readToken, writeToken } from "@agrayian/sdk";
import type { TokenUser } from "@agrayian/types";
import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";

type AuthState = {
  user: TokenUser | null;
  loading: boolean;
  can: (permission: string) => boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

type SessionPayload = { access_token: string; user: TokenUser };

const AuthContext = createContext<AuthState | null>(null);
const RESTORE_MS = 8000;

let cachedSession: SessionPayload | null | undefined;
let restoreInFlight: Promise<SessionPayload | null> | null = null;

function clearSessionCache() {
  cachedSession = undefined;
  restoreInFlight = null;
}

async function readJson<T>(response: Response): Promise<T | null> {
  try {
    const json = (await response.json()) as { data?: T };
    return json.data ?? null;
  } catch {
    return null;
  }
}

async function restoreSession(): Promise<SessionPayload | null> {
  if (cachedSession !== undefined) return cachedSession;
  if (restoreInFlight) return restoreInFlight;
  restoreInFlight = (async () => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), RESTORE_MS);
    try {
      const token = readToken();
      if (token) {
        const me = await fetch(`${getApiBase()}/api/v1/auth/me`, {
          headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
          credentials: "include",
          signal: controller.signal,
        });
        if (me.ok) {
          const data = await readJson<SessionPayload>(me);
          if (data?.access_token && data.user) {
            cachedSession = data;
            return data;
          }
        }
      }
      const refreshed = await fetch(`${getApiBase()}/api/v1/auth/refresh`, {
        method: "POST",
        headers: { Accept: "application/json" },
        credentials: "include",
        signal: controller.signal,
      });
      if (!refreshed.ok) {
        cachedSession = null;
        return null;
      }
      const data = await readJson<SessionPayload>(refreshed);
      cachedSession = data?.access_token && data.user ? data : null;
      return cachedSession;
    } catch {
      cachedSession = null;
      return null;
    } finally {
      window.clearTimeout(timer);
      restoreInFlight = null;
    }
  })();
  return restoreInFlight;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<TokenUser | null>(null);
  const [loading, setLoading] = useState(true);
  const generation = useRef(0);

  useEffect(() => {
    let alive = true;
    void restoreSession().then((session) => {
      if (!alive) return;
      if (session) {
        writeToken(session.access_token);
        setUser(session.user);
      } else {
        writeToken(null);
        setUser(null);
      }
      setLoading(false);
    });
    return () => {
      alive = false;
    };
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      can: (permission) => Boolean(user?.permissions.includes(permission)),
      login: async (email, password) => {
        generation.current += 1;
        writeToken(null);
        clearSessionCache();
        const res = await api<SessionPayload>("/api/v1/auth/login", {
          method: "POST",
          body: JSON.stringify({ email, password }),
        });
        if (!res.data) throw new Error("Login failed");
        writeToken(res.data.access_token);
        cachedSession = res.data;
        setUser(res.data.user);
        setLoading(false);
      },
      logout: async () => {
        generation.current += 1;
        await api("/api/v1/auth/logout", { method: "POST" }).catch(() => undefined);
        writeToken(null);
        clearSessionCache();
        setUser(null);
      },
    }),
    [user, loading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("AuthProvider missing");
  return ctx;
}
