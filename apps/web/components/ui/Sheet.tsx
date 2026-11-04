"use client";

import { useEffect, useRef } from "react";

/**
 * Modal sheet: bottom sheet on phones, right-hand panel on wide screens.
 * Closes on Escape, backdrop tap or the close button; focus moves in on open
 * and returns to the trigger on close.
 */
export function Sheet({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const lastFocus = useRef<Element | null>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    lastFocus.current = document.activeElement;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") return onClose();
      if (e.key !== "Tab" || !box.current) return;
      // Keep keyboard focus inside the modal while it is open.
      const f = Array.from(box.current.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), select, textarea, input, [tabindex]:not([tabindex="-1"])'));
      if (!f.length) return;
      const [first, last] = [f[0], f[f.length - 1]];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && (document.activeElement === last || !box.current.contains(document.activeElement))) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
      (lastFocus.current as HTMLElement | null)?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50">
      <button type="button" aria-label="Close" tabIndex={-1} onClick={onClose} className="absolute inset-0 bg-[#05080c]/70 backdrop-blur-[2px]" />
      <div
        ref={box}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="sheet-enter absolute inset-x-0 bottom-0 max-h-[85dvh] overflow-y-auto rounded-t-xl border-t border-line-strong bg-surface pb-safe lg:inset-y-0 lg:left-auto lg:right-0 lg:max-h-none lg:w-[440px] lg:rounded-none lg:border-l lg:border-t-0"
      >
        <div className="sticky top-0 z-10 border-b border-line bg-surface px-4 pb-2 pt-2">
          <div className="mx-auto mb-1.5 h-1 w-9 rounded-full bg-line-strong lg:hidden" aria-hidden />
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold">{title}</h2>
            <button
              ref={closeRef}
              type="button"
              onClick={onClose}
              className="grid h-8 w-8 place-items-center rounded-md text-ink-2 hover:bg-raised hover:text-ink"
              aria-label="Close"
            >
              <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.5" /></svg>
            </button>
          </div>
        </div>
        <div className="px-4 pb-6 pt-4">{children}</div>
      </div>
    </div>
  );
}
