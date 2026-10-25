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

const SITE_URL = "https://medschedule-ai.vercel.app";
const SITE_TITLE = "MedSchedule AI | Integrated MBBS & BDS Timetable Engine";
const SITE_DESCRIPTION =
  "Turn MBBS & BDS module syllabi into conflict-free, integrated weekly timetables. AI curriculum ingestion, horizontal & vertical integration review, OR-Tools solving, drag-and-drop editing with an AI copilot, and 1-page Word export.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: SITE_TITLE,
    template: "%s | MedSchedule AI",
  },
  description: SITE_DESCRIPTION,
  applicationName: "MedSchedule AI",
  authors: [{ name: "Muhammad Dawood", url: "https://github.com/dawoodcs195-spec" }],
  creator: "Muhammad Dawood",
  keywords: [
    "medical timetable",
    "MBBS timetable",
    "BDS timetable",
    "curriculum integration",
    "constraint programming",
    "OR-Tools",
    "CP-SAT",
    "Gemini",
    "pgvector",
    "Next.js",
    "FastAPI",
  ],
  alternates: { canonical: "/" },
  openGraph: {
    type: "website",
    url: SITE_URL,
    siteName: "MedSchedule AI",
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    locale: "en_US",
    images: [
      {
        url: "/og.png",
        width: 1200,
        height: 630,
        alt: "MedSchedule AI: integrated timetables, solved in minutes",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    images: ["/og.png"],
  },
  robots: { index: true, follow: true },
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
