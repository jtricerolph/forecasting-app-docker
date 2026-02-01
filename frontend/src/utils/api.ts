import axios from 'axios'

const API_BASE = '/api'

const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export interface User {
  id: number
  username: string
  display_name: string
  is_active: boolean
}

export interface LoginResponse {
  access_token: string
  token_type: string
}

export interface UserWithDate extends User {
  created_at: string | null
}

export interface CreateUserRequest {
  username: string
  password: string
  display_name?: string
}

export const authApi = {
  login: async (username: string, password: string): Promise<LoginResponse> => {
    const response = await api.post<LoginResponse>('/auth/login', { username, password })
    return response.data
  },

  getMe: async (): Promise<User> => {
    const response = await api.get<User>('/auth/me')
    return response.data
  },

  getUsers: async (): Promise<UserWithDate[]> => {
    const response = await api.get<UserWithDate[]>('/auth/users')
    return response.data
  },

  createUser: async (data: CreateUserRequest): Promise<UserWithDate> => {
    const response = await api.post<UserWithDate>('/auth/users', data)
    return response.data
  },

  deleteUser: async (userId: number): Promise<void> => {
    await api.delete(`/auth/users/${userId}`)
  },
}

export default api
