import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Yupoo Downloader',
  description: 'Baixe álbuns completos da Yupoo direto para o Google Drive',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  )
}
