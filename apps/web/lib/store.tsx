"use client";

// Per-device state: alert rules, triage, read alerts, "last looked".
// Persisted to localStorage (wrapped: storage can be unavailable). In
// production these map to /api/v1 settings, triage and alert-state endpoints.

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { Rules } from "./types";
import { defaultRules } from "./taxonomy";
import { DEMO_LAST_LOOKED, DEMO_NOW } from "./demo/companies";

interface Persisted {
  rules: Rules;
  lastLooked: string;
  triage: Record<string, "noted" | "snoozed">;
  read: string[];
}

interface Store extends Persisted {
  hydrated: boolean;
  setRules: (r: Rules) => void;
  markAllSeen: (at?: string) => void;
  setTriage: (eventId: string, action: "noted" | "snoozed" | null) => void;
  markRead: (keys: string[]) => void;
  markUnread: (key: string) => void;
  resetDemo: () => void;
  evidenceId: string | null;
  openEvidence: (id: string) => void;
  closeEvidence: () => void;
}

const KEY = "finn.device.v1";

function initial(): Persisted {
  return { rules: defaultRules(), lastLooked: DEMO_LAST_LOOKED, triage: {}, read: [] };
}

function load(): Persisted {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return initial();
    const p = JSON.parse(raw) as Partial<Persisted>;
    const base = initial();
    return {
      rules: { ...base.rules, ...p.rules, categories: { ...base.rules.categories, ...p.rules?.categories } },
      lastLooked: p.lastLooked ?? base.lastLooked,
      triage: p.triage ?? {},
      read: p.read ?? [],
    };
  } catch {
    return initial();
  }
}

function save(p: Persisted) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(p));
  } catch {
    /* storage unavailable: state stays in memory for this session */
  }
}

const Ctx = createContext<Store | null>(null);

export function StoreProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<Persisted>(initial);
  const [hydrated, setHydrated] = useState(false);
  const [evidenceId, setEvidenceId] = useState<string | null>(null);

  useEffect(() => {
    setState(load());
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (hydrated) save(state);
  }, [state, hydrated]);

  const update = useCallback((fn: (p: Persisted) => Persisted) => setState((p) => fn(p)), []);

  const value = useMemo<Store>(
    () => ({
      ...state,
      hydrated,
      setRules: (rules) => update((p) => ({ ...p, rules })),
      markAllSeen: (at) => update((p) => ({ ...p, lastLooked: at ?? DEMO_NOW })),
      setTriage: (id, action) =>
        update((p) => {
          const triage = { ...p.triage };
          if (action) triage[id] = action;
          else delete triage[id];
          return { ...p, triage };
        }),
      markRead: (keys) => update((p) => ({ ...p, read: [...new Set([...p.read, ...keys])] })),
      markUnread: (key) => update((p) => ({ ...p, read: p.read.filter((k) => k !== key) })),
      resetDemo: () => update(() => initial()),
      evidenceId,
      openEvidence: setEvidenceId,
      closeEvidence: () => setEvidenceId(null),
    }),
    [state, hydrated, evidenceId, update],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useStore(): Store {
  const s = useContext(Ctx);
  if (!s) throw new Error("useStore must be used inside StoreProvider");
  return s;
}
