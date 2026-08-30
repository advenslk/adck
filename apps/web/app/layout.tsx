import './globals.css';
import React from 'react';

export const metadata = { title: 'ArveX Control Center', description: 'Hosting automation SaaS admin dashboard' };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
