import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

import { AppSidebar } from "@/components/app-sidebar";
import { ScopeProvider } from "@/components/scope-provider";
import { ScopeSwitcher } from "@/components/scope-switcher";
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
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full">
        <ScopeProvider>
          <TooltipProvider delayDuration={200}>
            <SidebarProvider>
              <AppSidebar />
              <SidebarInset>
                <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-2 border-b bg-background/95 px-4 backdrop-blur">
                  <SidebarTrigger className="-ml-1" />
                  <Separator orientation="vertical" className="mr-2 h-4" />
                  <div className="flex-1" />
                  <ScopeSwitcher />
                </header>
                <main className="flex-1 p-4 md:p-6">{children}</main>
              </SidebarInset>
            </SidebarProvider>
            <Toaster position="bottom-right" richColors />
          </TooltipProvider>
        </ScopeProvider>
      </body>
    </html>
  );
}
