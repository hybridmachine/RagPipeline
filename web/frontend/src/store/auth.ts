import { create } from 'zustand'
import { apiClient } from '../api/client'

interface User {
  id: string
  username: string
  email: string
}

interface AuthStore {
  user: User | null
  isLoading: boolean
  error: string | null
  login: (username: string, password: string) => Promise<void>
  register: (username: string, email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  fetchUser: () => Promise<void>
  clearError: () => void
}

export const useAuth = create<AuthStore>((set) => ({
  user: null,
  isLoading: false,
  error: null,

  login: async (username: string, password: string) => {
    set({ isLoading: true, error: null })
    try {
      const response = await apiClient.login(username, password)
      // Fetch user after login
      const user = await apiClient.getCurrentUser()
      set({ user, isLoading: false })
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Login failed',
        isLoading: false,
      })
      throw error
    }
  },

  register: async (username: string, email: string, password: string) => {
    set({ isLoading: true, error: null })
    try {
      const response = await apiClient.register(username, email, password)
      // Fetch user after registration
      const user = await apiClient.getCurrentUser()
      set({ user, isLoading: false })
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Registration failed',
        isLoading: false,
      })
      throw error
    }
  },

  logout: async () => {
    set({ isLoading: true })
    try {
      await apiClient.logout()
      set({ user: null, isLoading: false })
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Logout failed',
        isLoading: false,
      })
    }
  },

  fetchUser: async () => {
    set({ isLoading: true })
    try {
      const user = await apiClient.getCurrentUser()
      set({ user, isLoading: false })
    } catch (error) {
      set({ isLoading: false })
      // User might not be authenticated
    }
  },

  clearError: () => set({ error: null }),
}))
