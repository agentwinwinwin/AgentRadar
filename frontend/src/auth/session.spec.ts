import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  authToken,
  authUser,
  clearAuthSession,
  getAuthToken,
  setAuthSession,
} from './session'

describe('authentication session expiry', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    clearAuthSession()
  })

  it('automatically clears the token at the server-provided expiry time', () => {
    const expiresAt = new Date(Date.now() + 3 * 60 * 60 * 1000).toISOString()
    setAuthSession('test-token', { id: 1, username: 'alice', is_staff: false }, expiresAt)

    vi.advanceTimersByTime(3 * 60 * 60 * 1000)

    expect(authToken.value).toBeNull()
    expect(authUser.value).toBeNull()
    expect(window.localStorage.getItem('agentradar_token')).toBeNull()
  })

  it('does not return an already expired stored token', () => {
    setAuthSession(
      'expired-token',
      { id: 2, username: 'bob', is_staff: false },
      new Date(Date.now() - 1).toISOString(),
    )

    expect(getAuthToken()).toBeNull()
  })
})
