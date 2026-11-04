import { EventDetailScreen } from "@/components/push/EventDetail";

export const metadata = { title: "Event, FINN" };

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <EventDetailScreen id={decodeURIComponent(id)} />;
}
