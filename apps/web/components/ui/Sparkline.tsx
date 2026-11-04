// A small trend line. Single series: neutral ink; the last point's dot
// carries direction. Decorative summary only: the exact value sits beside it.

export function Sparkline({
  values,
  width = 72,
  height = 22,
  label,
}: {
  values: number[];
  width?: number;
  height?: number;
  label: string;
}) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pad = 2.5;
  const x = (i: number) => pad + (i / (values.length - 1)) * (width - pad * 2);
  const y = (v: number) => pad + (1 - (v - min) / span) * (height - pad * 2);
  const d = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join("");
  const up = values[values.length - 1] >= values[0];
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label} className="block overflow-visible">
      <path d={d} fill="none" stroke="var(--color-ink-3)" strokeWidth="1.25" strokeLinejoin="round" strokeLinecap="round" />
      <circle
        cx={x(values.length - 1)}
        cy={y(values[values.length - 1])}
        r="2.25"
        fill={up ? "var(--color-up)" : "var(--color-down)"}
        stroke="var(--color-base)"
        strokeWidth="1"
      />
    </svg>
  );
}
