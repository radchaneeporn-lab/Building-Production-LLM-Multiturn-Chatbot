import "./globals.css";

export const metadata = {
  title: "Chatbot",
  description: "Frontend for the agentic multiturn chatbot backend",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
