import { MoveDetailScreen } from "@/components/push/MoveDetail";

export const metadata = { title: "Market move, FINN" };

export default async function Page({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  return <MoveDetailScreen symbol={decodeURIComponent(symbol).toUpperCase()} />;
}
