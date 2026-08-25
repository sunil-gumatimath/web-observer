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
  title: "Web Observer",
  description: "Detect web page changes and get high-signal alerts with diffs.",
  icons: {
    icon: [{ url: "/icon.svg", type: "image/svg+xml" }],
    apple: [{ url: "/apple-icon.svg", type: "image/svg+xml" }],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
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
