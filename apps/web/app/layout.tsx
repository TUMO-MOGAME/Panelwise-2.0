import type { Metadata } from "next";
import { Atkinson_Hyperlegible_Next, Courier_Prime } from "next/font/google";
import localFont from "next/font/local";

import "./globals.css";

// The three faces of web.md §2: display (headings and shot numbers only), body, and the script
// face for anything quoted from the screenplay.
// Big Shoulders Display (OFL, app/fonts/OFL.txt) is self-hosted: next/font/google lists only the
// merged Big Shoulders family, whose widest optical size still sets wider than the Display cut
// the references were drawn in.
const display = localFont({
  src: "./fonts/BigShouldersDisplay-latin.woff2",
  weight: "100 900",
  variable: "--font-big-shoulders",
});
const body = Atkinson_Hyperlegible_Next({
  subsets: ["latin"],
  weight: ["400", "500", "700"],
  variable: "--font-atkinson",
});
const script = Courier_Prime({
  subsets: ["latin"],
  weight: ["400", "700"],
  style: ["normal", "italic"],
  variable: "--font-courier-prime",
});

export const metadata: Metadata = {
  title: "Panelwise",
  description: "A screenplay, boarded: one frame per shot, each beside the lines it came from.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable} ${script.variable}`}>
      <body>{children}</body>
    </html>
  );
}
