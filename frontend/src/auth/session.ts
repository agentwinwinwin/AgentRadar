import { computed, ref } from 'vue'

export interface AuthUser {
  id: number
  username: string
  is_staff: boolean
}

const TOKEN_KEY = 'agentradar_token'
const USER_KEY = 'agentradar_user'
const EXPIRES_AT_KEY = 'agentradar_token_expires_at'
let expiryTimer: number | undefined

function readExpiry(): number | null {
  const raw = window.localStorage.getItem(EXPIRES_AT_KEY)
  if (!raw) return null
  const value = Date.parse(raw)
  return Number.isFinite(value) ? value : null
}

function storedSessionIsValid(): boolean {
  const expiresAt = readExpiry()
  return expiresAt !== null && expiresAt > Date.now()
}

function readStoredUser(): AuthUser | null {
  try {
    const raw = window.localStorage.getItem(USER_KEY)
    if (!raw) return null
    const value = JSON.parse(raw) as Partial<AuthUser>
    return typeof value.id === 'number' && typeof value.username === 'string'
      ? { id: value.id, username: value.username, is_staff: value.is_staff === true }
      : null
  } catch {
    window.localStorage.removeItem(USER_KEY)
    return null
  }
}

if (!storedSessionIsValid()) {
  window.localStorage.removeItem(TOKEN_KEY)
  window.localStorage.removeItem(USER_KEY)
  window.localStorage.removeItem(EXPIRES_AT_KEY)
}

export const authToken = ref(window.localStorage.getItem(TOKEN_KEY))
export const authUser = ref<AuthUser | null>(readStoredUser())
export const isAuthenticated = computed(() => Boolean(authToken.value && authUser.value))

function scheduleExpiry(expiresAt: string) {
  if (expiryTimer !== undefined) window.clearTimeout(expiryTimer)
  const remaining = Date.parse(expiresAt) - Date.now()
  if (remaining <= 0) {
    expireAuthSession()
    return
  }
  expiryTimer = window.setTimeout(expireAuthSession, remaining)
}

function expireAuthSession() {
  clearAuthSession()
  window.dispatchEvent(new Event('agentradar:session-expired'))
}

export function setAuthSession(token: string, user: AuthUser, expiresAt: string) {
  window.localStorage.setItem(TOKEN_KEY, token)
  window.localStorage.setItem(USER_KEY, JSON.stringify(user))
  window.localStorage.setItem(EXPIRES_AT_KEY, expiresAt)
  authToken.value = token
  authUser.value = user
  scheduleExpiry(expiresAt)
}

export function updateAuthUser(user: AuthUser) {
  window.localStorage.setItem(USER_KEY, JSON.stringify(user))
  authUser.value = user
}

export function clearAuthSession() {
  if (expiryTimer !== undefined) window.clearTimeout(expiryTimer)
  expiryTimer = undefined
  window.localStorage.removeItem(TOKEN_KEY)
  window.localStorage.removeItem(USER_KEY)
  window.localStorage.removeItem(EXPIRES_AT_KEY)
  authToken.value = null
  authUser.value = null
}

export function getAuthToken(): string | null {
  if (!storedSessionIsValid()) {
    expireAuthSession()
    return null
  }
  return authToken.value
}

const storedExpiry = window.localStorage.getItem(EXPIRES_AT_KEY)
if (authToken.value && storedExpiry) scheduleExpiry(storedExpiry)
