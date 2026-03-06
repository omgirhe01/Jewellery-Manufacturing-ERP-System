'use client'
import './globals.css'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'
import { useState } from 'react'

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient({
    defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } }
  }))

  return (
    <html lang="en">
      <head>
        <title>Sona Jewellery ERP</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=Cormorant+Garamond:wght@300;400;600;700&display=swap" rel="stylesheet" />
      </head>
      <body>
        <QueryClientProvider client={queryClient}>
          {children}
          <Toaster position="bottom-right" toastOptions={{
            style: { background: '#13110e', border: '1px solid #2a2318', color: '#e8e0d0', fontFamily: 'DM Mono, monospace', fontSize: '12px' },
            success: { iconTheme: { primary: '#4cc96f', secondary: '#13110e' } },
            error: { iconTheme: { primary: '#e04c4c', secondary: '#13110e' } },
          }} />
        </QueryClientProvider>
      </body>
    </html>
  )
}
