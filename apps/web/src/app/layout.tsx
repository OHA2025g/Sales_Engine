import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { connection } from "next/server";
import { RevenueDesign } from "@/components/revenue-design";
import "./globals.css";
import "./design.css";

const sans = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
});

export const metadata: Metadata = {
  title: "Sales Engine",
  description: "Revenue workspace for AGRAYIAN AI Labs",
  icons: {
    icon: [{ url: "/icon.svg", type: "image/svg+xml" }],
  },
};

export const dynamic = "force-dynamic";

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  await connection();
  void children;
  return (
    <html lang="en">
      <body className={`${sans.variable} font-sans antialiased`}>
        <RevenueDesign />
      </body>
    </html>
  );
}
