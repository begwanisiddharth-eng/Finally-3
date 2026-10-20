import type { ReactNode } from "react";

interface PanelProps {
  title: string;
  children: ReactNode;
  className?: string;
  action?: ReactNode;
}

/** Terminal-style card with a header strip. */
export default function Panel({ title, children, className = "", action }: PanelProps) {
  return (
    <section
      className={`flex flex-col rounded-md border border-border bg-panel overflow-hidden ${className}`}
    >
      <header className="flex items-center justify-between border-b border-border-soft px-3 py-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-fg-muted">{title}</h2>
        {action}
      </header>
      <div className="flex-1 min-h-0 overflow-auto">{children}</div>
    </section>
  );
}
