import { redirect } from "next/navigation";
import { SentinelShell } from "@/components/sentinel-shell";
import { getServerUser } from "@/lib/supabase-server";

export default async function DashboardPage() {
  const user = await getServerUser();
  if (!user) redirect("/login");
  return <SentinelShell />;
}
