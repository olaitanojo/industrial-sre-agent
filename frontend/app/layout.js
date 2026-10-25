import "./globals.css";

export const metadata = {
  title: "Industrial SRE Agent",
  description: "Autonomous industrial site reliability control plane"
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
