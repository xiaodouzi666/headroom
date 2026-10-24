import type { ReactNode } from "react";
import {
  AlertCircle,
  ArrowUpRight,
  Activity,
  LoaderCircle,
} from "lucide-react";
import { human, text } from "./data";
export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}
export function Status({ value }: { value: unknown }) {
  const s = text(value, "unknown");
  const tone = ["completed", "done"].includes(s)
    ? "green"
    : ["failed", "rejected", "timeout"].includes(s)
      ? "red"
      : ["needs_human", "budget_exceeded"].includes(s)
        ? "amber"
        : "neutral";
  return (
    <Badge tone={tone}>
      <span className="status-dot" />
      {human(s)}
    </Badge>
  );
}
export function Empty({
  title,
  children,
}: {
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty">
      <Activity size={23} aria-hidden="true" />
      <strong>{title}</strong>
      {children && <p>{children}</p>}
    </div>
  );
}
export function Notice({
  children,
  tone = "amber",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return (
    <div
      className={`notice notice-${tone}`}
      role={tone === "red" ? "alert" : "status"}
    >
      <AlertCircle size={18} aria-hidden="true" />
      <div>{children}</div>
    </div>
  );
}
export function Loading({
  children = "Loading evidence…",
}: {
  children?: ReactNode;
}) {
  return (
    <div className="loading" role="status">
      <LoaderCircle size={18} className="spin" />
      {children}
    </div>
  );
}
export function Section({
  title,
  kicker,
  children,
  action,
  id,
}: {
  title: string;
  kicker?: string;
  children: ReactNode;
  action?: ReactNode;
  id?: string;
}) {
  return (
    <section className="panel" id={id}>
      <div className="section-heading">
        <div>
          {kicker && <p className="eyebrow">{kicker}</p>}
          <h2>{title}</h2>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
export function Metric({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note?: string;
}) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {note && <small>{note}</small>}
    </div>
  );
}
export function External({
  href,
  children,
}: {
  href: string;
  children: ReactNode;
}) {
  return (
    <a
      className="external"
      href={href}
      target="_blank"
      rel="noopener noreferrer"
    >
      {children}
      <ArrowUpRight size={14} />
    </a>
  );
}
