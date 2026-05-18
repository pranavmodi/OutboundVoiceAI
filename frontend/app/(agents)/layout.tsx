import { AgentShell } from "@/components/agents/AgentShell";

export default function AgentsLayout({ children }: { children: React.ReactNode }) {
  return <AgentShell>{children}</AgentShell>;
}
