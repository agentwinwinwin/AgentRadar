import type { DashboardData } from '@/types/api'

const CACHE_KEY = 'agentradar-dashboard-v2'

export interface DashboardCache {
  data: DashboardData
  cachedAt: string
}

export function readDashboardCache(): DashboardCache | null {
  try {
    const raw = window.localStorage.getItem(CACHE_KEY)
    if (!raw) return null
    const cached = JSON.parse(raw) as Partial<DashboardCache>
    if (!cached.data || typeof cached.cachedAt !== 'string') return null
    return cached as DashboardCache
  } catch {
    window.localStorage.removeItem(CACHE_KEY)
    return null
  }
}

export function writeDashboardCache(data: DashboardData): DashboardCache {
  const cached = { data, cachedAt: new Date().toISOString() }
  window.localStorage.setItem(CACHE_KEY, JSON.stringify(cached))
  return cached
}
