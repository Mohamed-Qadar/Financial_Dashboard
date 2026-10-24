/** Loading indicator. Decorative unless `label` is given (then announced politely). */
export function Spinner({ label }: { label?: string }) {
  const svg = (
    <svg className="ui-spinner" width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="3" opacity="0.25" />
      <path d="M21 12a9 9 0 0 0-9-9" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
  if (!label) return svg;
  return (
    <span className="ui-loading" role="status">
      {svg}
      <span>{label}</span>
    </span>
  );
}
