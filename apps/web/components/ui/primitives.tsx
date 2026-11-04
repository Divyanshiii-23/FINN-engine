"use client";

import { useId, useState } from "react";
import type { InfoClass, Verdict } from "@/lib/types";
import { useStore } from "@/lib/store";

/* ------------------------------------------------------------------ */
/* Info-class tag: shape + colour + words, never colour alone          */
/* ------------------------------------------------------------------ */

const CLASS_META: Record<InfoClass, { label: string; color: string }> = {
  reported: { label: "Reported", color: "text-ink-2" },
  guidance: { label: "Guided", color: "text-guided" },
  assertion: { label: "Management said", color: "text-ink-2" },
  outlook: { label: "Commentary", color: "text-ink-3" },
  computed: { label: "FINN computed", color: "text-ink-2" },
  generated: { label: "FINN analysis (AI)", color: "text-ai" },
};

export function ClassMark({ kind, className = "" }: { kind: InfoClass; className?: string }) {
  const c = `inline-block shrink-0 ${className}`;
  switch (kind) {
    case "reported":
      return <svg aria-hidden className={c} width="8" height="8" viewBox="0 0 8 8"><rect width="8" height="8" rx="1" fill="currentColor" /></svg>;
    case "guidance":
      return <svg aria-hidden className={c} width="8" height="8" viewBox="0 0 8 8"><path d="M1 0.5 L7.5 4 L1 7.5 Z" fill="currentColor" /></svg>;
    case "assertion":
      return <svg aria-hidden className={c} width="8" height="8" viewBox="0 0 8 8"><rect x="0.75" y="0.75" width="6.5" height="6.5" rx="1" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>;
    case "outlook":
      return <svg aria-hidden className={c} width="8" height="8" viewBox="0 0 8 8"><path d="M1.2 1 L7 4 L1.2 7 Z" fill="none" stroke="currentColor" strokeWidth="1.3" /></svg>;
    case "computed":
      return <span aria-hidden className={`${c} font-serif italic text-[11px] leading-none`}>f</span>;
    case "generated":
      return <svg aria-hidden className={c} width="8" height="8" viewBox="0 0 8 8"><path d="M4 0 L8 4 L4 8 L0 4 Z" fill="currentColor" /></svg>;
  }
}

export function ClassTag({ kind, children }: { kind: InfoClass; children?: React.ReactNode }) {
  const m = CLASS_META[kind];
  return (
    <span className={`inline-flex items-center gap-1.5 text-2xs font-medium ${m.color}`}>
      <ClassMark kind={kind} />
      {children ?? m.label}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* Verdicts                                                            */
/* ------------------------------------------------------------------ */

const VERDICT: Record<Verdict | "not_scored", { label: string; cls: string }> = {
  delivered: { label: "Delivered", cls: "text-up border-up/40" },
  ahead: { label: "Ahead", cls: "text-up border-up/40" },
  missed: { label: "Missed", cls: "text-down border-down/45" },
  pending: { label: "Pending", cls: "text-ink-2 border-line-strong" },
  revised: { label: "Revised", cls: "text-alert border-alert/45" },
  dropped: { label: "Dropped", cls: "text-alert border-alert/45" },
  unverifiable: { label: "Unverifiable", cls: "text-ink-3 border-line-strong" },
  consistent: { label: "Consistent", cls: "text-up border-up/40" },
  contradicted: { label: "Contradicted", cls: "text-down border-down/45" },
  not_scored: { label: "Not scored", cls: "text-ink-3 border-line" },
};

export function VerdictPill({ verdict }: { verdict: Verdict | "not_scored" }) {
  const v = VERDICT[verdict];
  return (
    <span className={`inline-flex h-5 items-center rounded-[4px] border px-1.5 text-2xs font-medium ${v.cls}`}>
      {v.label}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* Evidence-backed value: every number opens its source                */
/* ------------------------------------------------------------------ */

export function Sourced({
  id,
  children,
  label,
  className = "",
}: {
  id?: string;
  children: React.ReactNode;
  label: string;
  className?: string;
}) {
  const { openEvidence } = useStore();
  if (!id) return <span className={`num ${className}`}>{children}</span>;
  return (
    <button
      type="button"
      onClick={() => openEvidence(id)}
      aria-label={`Show source for ${label}`}
      className={`num underline decoration-ink-3/70 decoration-dotted underline-offset-[3px] hover:decoration-brass hover:text-ink ${className}`}
    >
      {children}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/* Segmented control (radio group)                                     */
/* ------------------------------------------------------------------ */

export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
  size = "md",
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string }[];
  label: string;
  size?: "sm" | "md";
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-md border border-line bg-surface p-0.5">
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={on}
            onClick={() => onChange(o.value)}
            className={`whitespace-nowrap rounded-[5px] ${size === "sm" ? "h-6 px-2 text-2xs" : "h-7 px-2.5 text-xs"} font-medium transition-colors ${
              on ? "bg-raised text-ink shadow-[inset_0_0_0_1px_var(--color-line-strong)]" : "text-ink-3 hover:text-ink-2"
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Numeric stepper with direct entry                                   */
/* ------------------------------------------------------------------ */

export function Stepper({
  label,
  value,
  onChange,
  min,
  max,
  step,
  prefix,
  suffix,
  hint,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step: number;
  prefix?: string;
  suffix?: string;
  hint?: string;
}) {
  const id = useId();
  // The input holds only the number; units sit outside it, so focusing never
  // rewrites the field under the cursor.
  const [draft, setDraft] = useState<string | null>(null);
  const clamp = (v: number) => Math.min(max, Math.max(min, Math.round(v / step) * step));
  const commit = () => {
    if (draft === null) return;
    const v = Number.parseFloat(draft.replace(",", "."));
    if (Number.isFinite(v)) onChange(Number(clamp(v).toFixed(2)));
    setDraft(null);
  };
  const shown = draft ?? String(Number(value.toFixed(2)));
  const btn =
    "grid h-9 w-9 place-items-center rounded-md border border-line text-ink-2 hover:border-line-strong hover:text-ink disabled:opacity-35";
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="min-w-0">
        <label htmlFor={id} className="block text-sm text-ink">
          {label}
        </label>
        {hint && <p className="text-xs text-ink-3">{hint}</p>}
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        <button type="button" className={btn} aria-label={`Decrease ${label}`} disabled={value <= min} onClick={() => onChange(Number(clamp(value - step).toFixed(2)))}>
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden><path d="M2 6h8" stroke="currentColor" strokeWidth="1.5" /></svg>
        </button>
        <div className="flex h-9 w-[5.25rem] items-center justify-center gap-0.5 rounded-md border border-line bg-surface px-1.5 focus-within:border-brass">
          {prefix && <span aria-hidden className="text-sm text-ink-3">{prefix}</span>}
          <input
            id={id}
            inputMode="decimal"
            aria-describedby={suffix ? `${id}-unit` : undefined}
            className="num w-full min-w-0 bg-transparent text-center text-sm text-ink focus:outline-none"
            value={shown}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === "Enter") (e.target as HTMLInputElement).blur();
              if (e.key === "Escape") setDraft(null);
            }}
          />
          {suffix && (
            <span id={`${id}-unit`} className="text-sm text-ink-3">
              {suffix}
            </span>
          )}
        </div>
        <button type="button" className={btn} aria-label={`Increase ${label}`} disabled={value >= max} onClick={() => onChange(Number(clamp(value + step).toFixed(2)))}>
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden><path d="M2 6h8M6 2v8" stroke="currentColor" strokeWidth="1.5" /></svg>
        </button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Switch                                                              */
/* ------------------------------------------------------------------ */

export function Switch({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={`relative h-5 w-9 shrink-0 rounded-full border transition-colors ${checked ? "border-brass bg-brass/25" : "border-line-strong bg-surface"}`}
    >
      <span className={`absolute top-[3px] h-3 w-3 rounded-full transition-all ${checked ? "left-[19px] bg-brass" : "left-[3px] bg-ink-3"}`} />
    </button>
  );
}

/* ------------------------------------------------------------------ */
/* Section heading                                                     */
/* ------------------------------------------------------------------ */

export function SectionHead({
  title,
  count,
  action,
  id,
}: {
  title: string;
  count?: number | string;
  action?: React.ReactNode;
  id?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-line pb-2">
      <h2 id={id} className="text-sm font-semibold text-ink">
        {title}
        {count !== undefined && <span className="num ml-2 font-normal text-ink-3">{count}</span>}
      </h2>
      {action}
    </div>
  );
}

export function TextButton({
  children,
  onClick,
  tone = "default",
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { tone?: "default" | "accent" }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex h-7 items-center gap-1 rounded-md px-2 text-xs font-medium ${
        tone === "accent" ? "text-brass hover:bg-brass/10" : "text-ink-2 hover:bg-raised hover:text-ink"
      }`}
      {...rest}
    >
      {children}
    </button>
  );
}

export function Chevron({ open }: { open: boolean }) {
  return (
    <svg aria-hidden width="10" height="10" viewBox="0 0 10 10" className={`transition-transform ${open ? "rotate-90" : ""}`}>
      <path d="M3.5 2 L7 5 L3.5 8" fill="none" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}
