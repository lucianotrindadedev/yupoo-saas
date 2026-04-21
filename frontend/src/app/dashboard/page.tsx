'use client'
import { Suspense } from 'react'
import DashboardInner from './Dashboard'

export default function DashboardPage() {
  return (
    <Suspense fallback={
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ color: '#666', fontSize: 14 }}>Carregando...</div>
      </div>
    }>
      <DashboardInner />
    </Suspense>
  )
}
