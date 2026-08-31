"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BookText,
  FlaskConical,
  Inbox,
  ReceiptText,
  ShieldCheck,
  Stamp,
} from "lucide-react";

import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { api } from "@/lib/api";
import { useEngine } from "@/hooks/use-engine";
import { useScope } from "@/components/scope-provider";

const WORK = [
  { href: "/", label: "Inbox", icon: Inbox, badge: null },
  { href: "/review", label: "Needs review", icon: ShieldCheck, badge: "ESCALATED" },
  { href: "/approvals", label: "Approvals", icon: Stamp, badge: "AWAITING_APPROVAL" },
] as const;

const REFERENCE = [
  { href: "/invoices", label: "Invoice register", icon: ReceiptText },
  { href: "/procedure", label: "Procedure AP-07", icon: BookText },
] as const;

export function AppSidebar() {
  const pathname = usePathname();
  const scope = useScope();
  const { data } = useEngine(() => api.overview(scope));

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="border-b">
        <div className="flex items-center gap-2 px-2 py-1.5">
          {/* Two files rather than one tinted image: the mark is a knockout,
              so its ledger rules are transparent-safe white and cannot be
              recoloured with a CSS filter without losing them. */}
          <div className="relative size-8 shrink-0">
            <Image
              src="/logo-mark.png"
              alt=""
              width={64}
              height={64}
              priority
              className="size-8 dark:hidden"
            />
            <Image
              src="/logo-mark-light.png"
              alt=""
              width={64}
              height={64}
              priority
              className="hidden size-8 dark:block"
            />
          </div>
          <div className="grid text-sm leading-tight group-data-[collapsible=icon]:hidden">
            <span className="font-semibold">LedgerGate</span>
            <span className="text-xs text-muted-foreground">Cash application</span>
          </div>
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Work</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {WORK.map((item) => {
                const count = item.badge
                  ? data?.counts?.[item.badge as keyof typeof data.counts]
                  : undefined;
                return (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton
                      asChild
                      isActive={isActive(item.href)}
                      tooltip={item.label}
                    >
                      <Link href={item.href}>
                        <item.icon />
                        <span>{item.label}</span>
                      </Link>
                    </SidebarMenuButton>
                    {count ? <SidebarMenuBadge>{count}</SidebarMenuBadge> : null}
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel>Reference</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {REFERENCE.map((item) => (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton
                    asChild
                    isActive={isActive(item.href)}
                    tooltip={item.label}
                  >
                    <Link href={item.href}>
                      <item.icon />
                      <span>{item.label}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel>Reviewer</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  asChild
                  isActive={isActive("/evaluation")}
                  tooltip="Evaluation (uses ground truth)"
                >
                  <Link href="/evaluation">
                    <FlaskConical />
                    <span>Evaluation</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  );
}
