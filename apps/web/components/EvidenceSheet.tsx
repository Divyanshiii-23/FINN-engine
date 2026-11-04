"use client";

import { useStore } from "@/lib/store";
import { currentReport, DOC_KIND, docHref, docOf, factOf, openSource } from "@/lib/research";
import { dayIST } from "@/lib/format";
import { Sheet } from "./ui/Sheet";
import { ClassTag } from "./ui/primitives";

const SOURCE: Record<string, string> = { bse: "BSE filing", nse: "NSE filing", company_ir: "Company IR site", fixture: "Synthetic fixture" };

// The source behind any number or quote in a research report. Inputs of a
// computed figure open in turn, so a chain can be followed to the filing.
export function EvidenceSheet() {
  const { evidenceId, closeEvidence, openEvidence } = useStore();
  const f = factOf(evidenceId);
  const d = docOf(f?.doc_id);
  const href = docHref(d, f?.page);
  return (
    <Sheet open={Boolean(evidenceId)} onClose={closeEvidence} title="Source">
      {!f ? (
        <p className="text-sm text-ink-2">No source record exists for this item.</p>
      ) : (
        <div className="space-y-4">
          <div className="space-y-1.5">
            <ClassTag kind={f.info_class} />
            <p className="text-sm font-medium text-ink">{f.label}</p>
            {f.display && <p className="num text-lg text-ink">{f.display}</p>}
          </div>

          {d && (
            <div className="space-y-0.5 rounded-md border border-line bg-base p-3">
              <p className="text-sm text-ink">{d.title}</p>
              <p className="text-xs text-ink-2">
                {DOC_KIND[d.kind]}
                {d.period ? `, ${d.period}` : ""}
                {d.filed_at ? `. Filed ${dayIST(d.filed_at)} ${new Date(d.filed_at).getFullYear()}` : ""}
              </p>
              <p className="num text-xs text-ink-3">
                {[f.page ? `Page ${f.page}` : null, f.section, f.speaker && f.speaker !== "Company document" ? f.speaker : null, f.column ? `Column ${f.column}` : null]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
              <p className="text-2xs text-ink-3">
                {SOURCE[d.source] ?? d.source}
                {d.source_id ? `, id ${d.source_id}` : ""}
                {d.parse.downloaded_from ? `, read from the ${d.parse.downloaded_from}` : ""}
              </p>
            </div>
          )}

          {f.quote && (
            <blockquote className="border-l-2 border-line-strong pl-3 text-sm leading-relaxed text-ink">“{f.quote}”</blockquote>
          )}

          {f.row_text && (
            <div className="space-y-1">
              <p className="text-xs text-ink-3">Row as printed{f.basis ? ` (${f.basis})` : ""}</p>
              <p className="num rounded-md border border-line bg-base p-3 text-xs leading-relaxed text-ink-2">{f.row_text}</p>
            </div>
          )}

          {f.formula && (
            <div className="space-y-1">
              <p className="text-xs text-ink-3">Formula</p>
              <p className="num rounded-md border border-line bg-base p-3 text-sm text-ink">{f.formula}</p>
            </div>
          )}

          {f.inputs && f.inputs.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs text-ink-3">Inputs</p>
              <ul className="divide-y divide-line rounded-md border border-line">
                {f.inputs.map((id) => {
                  const x = factOf(id);
                  return (
                    <li key={id}>
                      <button type="button" onClick={() => openEvidence(id)} className="flex w-full items-baseline justify-between gap-3 px-3 py-2 text-left hover:bg-raised">
                        <span className="min-w-0 text-xs text-ink-2">
                          <ClassTag kind={x?.info_class ?? "reported"}>{x?.label ?? id}</ClassTag>
                        </span>
                        <span className="num shrink-0 text-xs text-brass">{x?.display ?? "open"}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          {f.note && <p className="text-xs leading-relaxed text-ink-2">{f.note}</p>}

          {d && f.page && currentReport() && (
            <button
              type="button"
              onClick={() => {
                closeEvidence();
                openSource({ symbol: currentReport()!.identity.symbol, docId: d.id, page: f.page });
              }}
              className="text-xs text-brass hover:underline"
            >
              Read page {f.page} in the document ›
            </button>
          )}

          <p className="border-t border-line pt-3 text-xs text-ink-3">
            {href ? (
              <a href={href} target="_blank" rel="noreferrer" className="text-brass hover:underline">
                Open the filing{f.page ? ` at page ${f.page}` : ""} ↗
              </a>
            ) : d?.fixture ? (
              "Synthetic test document: fictional company, so there is no exchange filing to open."
            ) : d ? (
              "No public link was recorded for this document."
            ) : f.info_class === "computed" ? (
              "Computed by FINN in code from the inputs above."
            ) : (
              "Exchange market data, not a company document."
            )}
          </p>
        </div>
      )}
    </Sheet>
  );
}
