import type { Metadata } from "next";
import { Manrope } from "next/font/google";
import { connection } from "next/server";
import { getApiBase } from "@agrayian/sdk";
import { Providers } from "@/components/providers";
import "./globals.css";

const sans = Manrope({
  subsets: ["latin"],
  variable: "--font-sans",
});

export const metadata: Metadata = {
  title: "AGRAYIAN · Revenue OS",
  description: "Revenue operating system for AGRAYIAN AI Labs",
  icons: {
    icon: [{ url: "/icon.svg", type: "image/svg+xml" }],
  },
};

export const dynamic = "force-dynamic";

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  await connection();
  const apiUrl = getApiBase();
  return (
    <html lang="en">
      <body className={`${sans.variable} font-sans antialiased text-ink bg-canvas`}>
        <script
          dangerouslySetInnerHTML={{
            __html: `window.__AGRAYIAN_API_URL=${JSON.stringify(apiUrl)};`,
          }}
        />
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
