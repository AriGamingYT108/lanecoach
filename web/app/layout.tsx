import type {Metadata} from "next";
import "./globals.css";
export const metadata: Metadata = {title: "LaneCoach — Your League of Legends coach", description: "A conversational coach and personalized game plans for every League of Legends role."};
export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang="en"><body>{children}</body></html>;
}
