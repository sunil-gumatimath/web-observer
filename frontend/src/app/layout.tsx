import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { ThemedClerkProvider } from "@/components/clerk-theme-provider";
import { Providers } from "@/components/providers";
import { ThemeProvider } from "@/components/theme-provider";
import { config } from "@/lib/config";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "Web Observer",
    template: "%s | Web Observer",
  },
  description:
    "Web Observer — know the moment pages you care about change. Content, price, and link monitoring with clear diffs and high-signal alerts.",
  applicationName: "Web Observer",
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
      { url: "/web-observer-icon.svg", type: "image/svg+xml" },
    ],
    apple: [{ url: "/apple-icon.svg", type: "image/svg+xml" }],
    shortcut: "/icon.svg",
  },
  openGraph: {
    title: "Web Observer",
    description:
      "Web change detection and alerting — precise diffs, AI summaries, and alerts where you work.",
    type: "website",
    images: [{ url: "/opengraph-image.svg", width: 1200, height: 630, alt: "Web Observer" }],
  },
  twitter: {
    card: "summary",
    title: "Web Observer",
    description:
      "Track content, price, and link changes with clear diffs and high-signal alerts.",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Strip attributes injected by browser extensions (e.g. Retriever `rtrvr-ls`) before React hydrates */}
        {/* eslint-disable-next-line @next/next/no-page-custom-font */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){function s(n){if(n.nodeType!==1)return;for(var i=n.attributes.length-1;i>=0;i--){var a=n.attributes[i].name;if(a.startsWith('rtrvr'))n.removeAttribute(a)}for(var c=n.firstChild;c;c=c.nextSibling)s(c)}s(document.documentElement);new MutationObserver(function(m){m.forEach(function(x){if(x.type==='attributes'&&x.attributeName&&x.attributeName.startsWith('rtrvr'))x.target.removeAttribute(x.attributeName);x.addedNodes&&x.addedNodes.forEach(function(n){s(n)})})}).observe(document.documentElement,{attributes:true,childList:true,subtree:true})})();`,
          }}
        />
      </head>
      <body
        className={`${geistSans.variable} ${geistMono.variable} font-sans antialiased`}
        suppressHydrationWarning
      >
        <ThemeProvider>
          {config.clerkEnabled ? (
            <ThemedClerkProvider>
              <Providers>{children}</Providers>
            </ThemedClerkProvider>
          ) : (
            <Providers>{children}</Providers>
          )}
        </ThemeProvider>
      </body>
    </html>
  );
}
