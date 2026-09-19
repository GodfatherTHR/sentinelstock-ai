import { redirect } from "next/navigation";
import { SentinelShell } from "@/components/sentinel-shell";
import { getServerUser } from "@/lib/supabase-server";

export default async function SectionPage({ params }: { params: Promise<{ section: string }> }) {
  const user = await getServerUser();
  if (!user) redirect("/login");

  const { section } = await params;
  return <SentinelShell initialSection={section} />;
}
