import type {Metadata} from "next";
import type {ReactNode} from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Devita AI Reporting",
  description: "Natural language reporting over the Devita project database"
};

export default function RootLayout({children}: {children: ReactNode}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
