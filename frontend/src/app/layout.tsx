import type { Metadata, Viewport } from "next";
import { Figtree, Noto_Sans, Geist_Mono } from "next/font/google";
import { Providers } from "@/components/providers";
import { themeInitScript } from "@/lib/theme-script";
import "./globals.css";

const heading = Figtree({
  variable: "--font-heading-face",
  subsets: ["latin"],
  display: "swap",
});

const body = Noto_Sans({
  variable: "--font-body",
  subsets: ["latin"],
  display: "swap",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "MedSchedule AI | Integrated MBBS & BDS Timetable Engine",
  description:
    "Turn MBBS & BDS module syllabi into conflict-free, integrated weekly timetables. AI curriculum ingestion, horizontal & vertical integration review, OR-Tools solving, drag-and-drop editing with an AI copilot, and 1-page Word export.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f7fbfc" },
    { media: "(prefers-color-scheme: dark)", color: "#0d1620" },
  ],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${heading.variable} ${body.variable} ${geistMono.variable} h-full antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body suppressHydrationWarning className="min-h-full flex flex-col">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
