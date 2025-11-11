import axios, { AxiosInstance } from 'axios'

const API_BASE_URL = '/api'

class APIClient {
  private client: AxiosInstance
  private token: string | null = null

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      headers: {
        'Content-Type': 'application/json',
      },
    })

    // Add request interceptor to include token
    this.client.interceptors.request.use((config) => {
      const token = localStorage.getItem('token')
      if (token) {
        config.headers.Authorization = `Bearer ${token}`
      }
      return config
    })

    // Add response interceptor to handle auth errors
    this.client.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response?.status === 401) {
          localStorage.removeItem('token')
          window.location.href = '/login'
        }
        return Promise.reject(error)
      }
    )

    // Load token from localStorage
    const savedToken = localStorage.getItem('token')
    if (savedToken) {
      this.token = savedToken
    }
  }

  setToken(token: string): void {
    this.token = token
    localStorage.setItem('token', token)
  }

  clearToken(): void {
    this.token = null
    localStorage.removeItem('token')
  }

  // Auth endpoints
  async register(username: string, email: string, password: string) {
    const response = await this.client.post('/auth/register', {
      username,
      email,
      password,
    })
    if (response.data.access_token) {
      this.setToken(response.data.access_token)
    }
    return response.data
  }

  async login(username: string, password: string) {
    const response = await this.client.post('/auth/login', {
      username,
      password,
    })
    if (response.data.access_token) {
      this.setToken(response.data.access_token)
    }
    return response.data
  }

  async logout() {
    this.clearToken()
  }

  // User endpoints
  async getCurrentUser() {
    const response = await this.client.get('/users/me')
    return response.data
  }

  // Project endpoints
  async createProject(name: string, description?: string, embedModel?: string, llmModel?: string) {
    const response = await this.client.post('/projects', {
      name,
      description,
      embed_model_id: embedModel,
      llm_model_id: llmModel,
    })
    return response.data
  }

  async listProjects() {
    const response = await this.client.get('/projects')
    return response.data
  }

  async getProject(projectId: string) {
    const response = await this.client.get(`/projects/${projectId}`)
    return response.data
  }

  async updateProject(projectId: string, updates: Record<string, any>) {
    const response = await this.client.put(`/projects/${projectId}`, updates)
    return response.data
  }

  async deleteProject(projectId: string) {
    await this.client.delete(`/projects/${projectId}`)
  }

  // File endpoints
  async uploadFile(projectId: string, file: File) {
    const formData = new FormData()
    formData.append('file', file)
    const response = await this.client.post(
      `/projects/${projectId}/files/upload`,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    )
    return response.data
  }

  async listFiles(projectId: string) {
    const response = await this.client.get(`/projects/${projectId}/files`)
    return response.data
  }

  async deleteFile(projectId: string, filePath: string) {
    await this.client.delete(`/projects/${projectId}/files/${filePath}`)
  }

  // Query endpoints
  async query(projectId: string, query: string, k?: number) {
    const response = await this.client.post(`/projects/${projectId}/query`, {
      query,
      k,
    })
    return response.data
  }

  async embed(projectId: string, batchSize?: number) {
    const response = await this.client.post(`/projects/${projectId}/embed`, {
      batch_size: batchSize,
    })
    return response.data
  }

  // Health endpoints
  async health() {
    const response = await this.client.get('/health')
    return response.data
  }
}

export const apiClient = new APIClient()
