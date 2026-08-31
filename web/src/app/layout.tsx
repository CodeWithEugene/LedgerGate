import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

import { AppSidebar } from "@/components/app-sidebar";
import { ScopeProvider } from "@/components/scope-provider";
import { ScopeSwitcher } from "@/components/scope-switcher";
import { ThemeProvider } from "@/components/theme-provider";
import { Separator } from "@/components/ui/separator";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "LedgerGate — cash application",
  description:
    "Apply incoming bank receipts to supplier invoices, with an agent that proposes and a safety gate that can only refuse.",
  manifest: "/site.webmanifest",
  icons: {
    // The mark is navy on a transparent surround, which disappears against a
    // dark tab strip. Browsers honour `media` on an icon link, so the white
    // version is served to dark mode rather than shipping one icon that is
    // only legible half the time.
    icon: [
      {
        url: "/icon-32.png",
        type: "image/png",
        sizes: "32x32",
        media: "(prefers-color-scheme: light)",
      },
      {
        url: "/icon-32-light.png",
        type: "image/png",
        sizes: "32x32",
        media: "(prefers-color-scheme: dark)",
      },
      { url: "/icon-192.png", type: "image/png", sizes: "192x192" },
      { url: "/icon-512.png", type: "image/png", sizes: "512x512" },
    ],
    shortcut: "/favicon.ico",
    // iOS composites a transparent icon onto black, so the home-screen icon
    // is the white mark. The navy one would be an invisible app.
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180" }],
  },
};

export const viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0f172a" },
  ],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full">
        <ThemeProvider>
          <ScopeProvider>
            <TooltipProvider delayDuration={200}>
              <SidebarProvider>
                <AppSidebar />
                <SidebarInset>
                  <header className="sticky top-0 z-20 flex min-h-14 shrink-0 flex-wrap items-center gap-2 border-b bg-background/95 px-4 py-2 backdrop-blur">
                    <SidebarTrigger className="-ml-1" />
                    <Separator
                      orientation="vertical"
                      className="mr-2 hidden h-4 sm:block"
                    />
                    <div className="ml-auto">
                      <ScopeSwitcher />
                    </div>
                  </header>
                  <div className="flex-1 p-4 md:p-6">{children}</div>
                </SidebarInset>
              </SidebarProvider>
              <Toaster position="bottom-right" richColors />
            </TooltipProvider>
          </ScopeProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
