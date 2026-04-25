import "../../styles/panel.css";
import type { ReactNode } from "react";

interface PanelProps {
  title: string;
  children: ReactNode;
  className?: string;
}

function Panel({ title, children, className = "" }: PanelProps) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel__header">
        <h3 className="panel__title">{title}</h3>
      </div>

      <div className="panel__body">{children}</div>
    </section>
  );
}

export default Panel;