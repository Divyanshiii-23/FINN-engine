import type { Metadata, Viewport } from "next";
import "@fontsource-variable/ibm-plex-sans";
import "@fontsource-variable/source-serif-4";
import "@fontsource-variable/source-serif-4/opsz-italic.css";
import "./globals.css";
import { StoreProvider } from "@/lib/store";
import { AppShell } from "@/components/shell/AppShell";

export const metadata: Metadata = {
  title: "FINN",
  description: "What changed in your portfolio, why it matters, and whether management kept its word.",
  applicationName: "FINN",
};

export const viewport: Viewport = {
  themeColor: "#0d1218",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-IN">
      <body>
        <StoreProvider>
          <AppShell>{children}</AppShell>
        </StoreProvider>
      </body>
    </html>
  );
}
