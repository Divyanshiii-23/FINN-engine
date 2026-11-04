import { CompanyScreen } from "@/components/research/CompanyScreen";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  return { title: `${decodeURIComponent(symbol).toUpperCase()}, FINN research` };
}

export default async function Page({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  return <CompanyScreen symbol={decodeURIComponent(symbol).trim().toUpperCase().replace(/\.NS$/, "")} />;
}
