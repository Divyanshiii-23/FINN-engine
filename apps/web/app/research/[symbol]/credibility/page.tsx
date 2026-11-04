import { CredibilityScreen } from "@/components/research/Credibility";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  return { title: `${decodeURIComponent(symbol).toUpperCase()} management credibility, FINN` };
}

export default async function Page({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  return <CredibilityScreen symbol={decodeURIComponent(symbol).trim().toUpperCase()} />;
}
