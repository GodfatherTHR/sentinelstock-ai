import { SentinelShell } from "@/components/sentinel-shell";

export default async function SectionPage({ params }: { params: Promise<{ section: string }> }) {
  const { section } = await params;
  return <SentinelShell initialSection={section} />;
}
