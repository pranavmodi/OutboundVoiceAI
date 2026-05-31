"use client";

import { useBackfillApi } from "@/hooks/useBackfillApi";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Phone, CalendarX } from "lucide-react";

type AgentTab = {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  match: (pathname: string) => boolean;
};

const AGENTS: AgentTab[] = [
  {
    href: "/",
    label: "Outbound Caller",
    icon: Phone,
    match: (p) => p === "/" || p.startsWith("/admin") || p.startsWith("/analytics"),
  },
  {
    href: "/backfill",
    label: "Cancellation Backfill",
    icon: CalendarX,
    match: (p) => p === "/backfill",
  },
];

export function AgentShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { getAgentStatus } = useBackfillApi();
  const [backfillEnabled, setBackfillEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    if (pathname !== "/backfill") {
      setBackfillEnabled(null);
      return;
    }
    let cancelled = false;
    getAgentStatus().then((res) => {
      if (!cancelled && res) setBackfillEnabled(res.enabled);
    });
    return () => {
      cancelled = true;
    };
  }, [pathname, getAgentStatus]);

  return (
    <div className="min-h-screen bg-background">
      <nav className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 sticky top-0 z-50">
        <div className="flex items-center gap-1 px-4 h-12">
          <span className="font-semibold text-sm mr-4">AI Outreach Platform</span>
          {AGENTS.map(({ href, label, icon: Icon, match }) => {
            const active = match(pathname);
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-2 px-3 py-1.5 text-sm rounded-md transition-colors ${
                  active
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                }`}
              >
                <Icon className="h-4 w-4" />
                {label}
                {href === "/backfill" && backfillEnabled !== null && (
                  <span
                    className={`ml-1 text-xs px-1.5 py-0.5 rounded ${
                      active
                        ? "bg-primary-foreground/20 text-primary-foreground"
                        : backfillEnabled
                          ? "bg-green-600/15 text-green-700 dark:text-green-400"
                          : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {backfillEnabled ? "On" : "Off"}
                  </span>
                )}
              </Link>
            );
          })}
        </div>
      </nav>
      {children}
    </div>
  );
}
