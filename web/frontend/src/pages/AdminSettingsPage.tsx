import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { apiClient } from '../api/client'

interface Project {
  id: string
  name: string
  description: string
  embed_model_id: string
  llm_model_id: string
  hf_endpoint_url: string | null
  hf_api_token_set: boolean
  llm_endpoint_url: string | null
  llm_api_token_set: boolean
  chunk_target_tokens: number
  chunk_overlap_tokens: number
}

interface FormData {
  embed_model_id: string
  hf_endpoint_url: string
  hf_api_token: string
  llm_model_id: string
  llm_endpoint_url: string
  llm_api_token: string
  chunk_target_tokens: number
  chunk_overlap_tokens: number
}

export default function AdminSettingsPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const [project, setProject] = useState<Project | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [saveSuccess, setSaveSuccess] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const [formData, setFormData] = useState<FormData>({
    embed_model_id: 'BAAI/bge-m3',
    hf_endpoint_url: '',
    hf_api_token: '',
    llm_model_id: 'gpt-4o',
    llm_endpoint_url: '',
    llm_api_token: '',
    chunk_target_tokens: 512,
    chunk_overlap_tokens: 50,
  })

  useEffect(() => {
    if (projectId) {
      fetchProject()
    }
  }, [projectId])

  const fetchProject = async () => {
    setIsLoading(true)
    try {
      const response = await apiClient.getProject(projectId!)
      setProject(response)

      // Initialize form with current values
      setFormData({
        embed_model_id: response.embed_model_id || 'BAAI/bge-m3',
        hf_endpoint_url: response.hf_endpoint_url || '',
        hf_api_token: '', // Never pre-fill tokens
        llm_model_id: response.llm_model_id || 'gpt-4o',
        llm_endpoint_url: response.llm_endpoint_url || '',
        llm_api_token: '', // Never pre-fill tokens
        chunk_target_tokens: response.chunk_target_tokens || 512,
        chunk_overlap_tokens: response.chunk_overlap_tokens || 50,
      })
    } catch (error) {
      console.error('Failed to load project:', error)
      navigate('/dashboard')
    } finally {
      setIsLoading(false)
    }
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target
    setFormData((prev) => ({
      ...prev,
      [name]: name.includes('tokens') ? parseInt(value) || 0 : value,
    }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!projectId) return

    setIsSaving(true)
    setSaveSuccess(false)
    setSaveError(null)

    try {
      // Only send fields that have values
      const updates: Record<string, any> = {
        embed_model_id: formData.embed_model_id,
        llm_model_id: formData.llm_model_id,
        chunk_target_tokens: formData.chunk_target_tokens,
        chunk_overlap_tokens: formData.chunk_overlap_tokens,
      }

      if (formData.hf_endpoint_url) {
        updates.hf_endpoint_url = formData.hf_endpoint_url
      }
      if (formData.hf_api_token) {
        updates.hf_api_token = formData.hf_api_token
      }
      if (formData.llm_endpoint_url) {
        updates.llm_endpoint_url = formData.llm_endpoint_url
      }
      if (formData.llm_api_token) {
        updates.llm_api_token = formData.llm_api_token
      }

      await apiClient.updateProject(projectId, updates)
      setSaveSuccess(true)

      // Clear token fields after successful save
      setFormData((prev) => ({
        ...prev,
        hf_api_token: '',
        llm_api_token: '',
      }))

      // Refresh project data
      await fetchProject()

      // Auto-dismiss success message after 5 seconds
      setTimeout(() => {
        setSaveSuccess(false)
      }, 5000)
    } catch (error: any) {
      console.error('Failed to save settings:', error)
      setSaveError(
        error.response?.data?.detail || 'Failed to save settings. Please try again.'
      )
    } finally {
      setIsSaving(false)
    }
  }

  if (isLoading) {
    return (
      <div className="flex justify-center items-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    )
  }

  if (!project) {
    return <div className="p-8">Project not found</div>
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white shadow">
        <div className="max-w-7xl mx-auto px-4 py-4 flex justify-between items-center">
          <h1 className="text-2xl font-bold text-gray-800">
            Admin Settings - {project.name}
          </h1>
          <button
            onClick={() => navigate(`/projects/${projectId}`)}
            className="bg-gray-600 text-white px-4 py-2 rounded hover:bg-gray-700"
          >
            Back to Project
          </button>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-2xl font-bold mb-6">Project Configuration</h2>

          {saveSuccess && (
            <div className="mb-6 p-4 bg-green-50 border border-green-200 rounded">
              <p className="text-green-700 font-semibold">Settings saved successfully!</p>
            </div>
          )}

          {saveError && (
            <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded">
              <p className="text-red-700 font-semibold">Error: {saveError}</p>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-8">
            {/* Embedding Configuration */}
            <div className="border-b pb-6">
              <h3 className="text-xl font-semibold mb-4 text-gray-700">Embedding Configuration</h3>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Embedding Model ID
                  </label>
                  <input
                    type="text"
                    name="embed_model_id"
                    value={formData.embed_model_id}
                    onChange={handleInputChange}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500"
                    placeholder="BAAI/bge-m3"
                  />
                  <p className="mt-1 text-xs text-gray-500">
                    e.g., BAAI/bge-m3, intfloat/e5-large-v2, sentence-transformers/all-MiniLM-L6-v2
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Hugging Face Endpoint URL (Optional)
                  </label>
                  <input
                    type="text"
                    name="hf_endpoint_url"
                    value={formData.hf_endpoint_url}
                    onChange={handleInputChange}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500"
                    placeholder="https://api-inference.huggingface.co/models/..."
                  />
                  <p className="mt-1 text-xs text-gray-500">
                    Leave empty to use Hugging Face Inference API
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Hugging Face API Token {project.hf_api_token_set && <span className="text-green-600">(Currently set)</span>}
                  </label>
                  <input
                    type="password"
                    name="hf_api_token"
                    value={formData.hf_api_token}
                    onChange={handleInputChange}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500"
                    placeholder={project.hf_api_token_set ? "Leave empty to keep current token" : "Enter API token"}
                  />
                  <p className="mt-1 text-xs text-gray-500">
                    {project.hf_api_token_set
                      ? "Enter a new token to replace the existing one, or leave empty to keep current"
                      : "Required for private models or higher rate limits"}
                  </p>
                </div>
              </div>
            </div>

            {/* LLM Configuration */}
            <div className="border-b pb-6">
              <h3 className="text-xl font-semibold mb-4 text-gray-700">LLM Configuration</h3>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    LLM Model ID
                  </label>
                  <input
                    type="text"
                    name="llm_model_id"
                    value={formData.llm_model_id}
                    onChange={handleInputChange}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500"
                    placeholder="gpt-4o"
                  />
                  <p className="mt-1 text-xs text-gray-500">
                    e.g., gpt-4o, gpt-3.5-turbo, meta-llama/Llama-3.1-8B-Instruct
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    LLM Endpoint URL (Optional)
                  </label>
                  <input
                    type="text"
                    name="llm_endpoint_url"
                    value={formData.llm_endpoint_url}
                    onChange={handleInputChange}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500"
                    placeholder="https://api.openai.com/v1"
                  />
                  <p className="mt-1 text-xs text-gray-500">
                    Leave empty for OpenAI, or provide custom endpoint for HuggingFace/other providers
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    LLM API Token {project.llm_api_token_set && <span className="text-green-600">(Currently set)</span>}
                  </label>
                  <input
                    type="password"
                    name="llm_api_token"
                    value={formData.llm_api_token}
                    onChange={handleInputChange}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500"
                    placeholder={project.llm_api_token_set ? "Leave empty to keep current token" : "Enter API token"}
                  />
                  <p className="mt-1 text-xs text-gray-500">
                    {project.llm_api_token_set
                      ? "Enter a new token to replace the existing one, or leave empty to keep current"
                      : "OpenAI API key or HuggingFace token"}
                  </p>
                </div>
              </div>
            </div>

            {/* Chunking Configuration */}
            <div className="pb-6">
              <h3 className="text-xl font-semibold mb-4 text-gray-700">Chunking Configuration</h3>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Target Tokens per Chunk
                  </label>
                  <input
                    type="number"
                    name="chunk_target_tokens"
                    value={formData.chunk_target_tokens}
                    onChange={handleInputChange}
                    min="128"
                    max="2048"
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500"
                  />
                  <p className="mt-1 text-xs text-gray-500">
                    Default: 512. Range: 128-2048
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Overlap Tokens
                  </label>
                  <input
                    type="number"
                    name="chunk_overlap_tokens"
                    value={formData.chunk_overlap_tokens}
                    onChange={handleInputChange}
                    min="0"
                    max="512"
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500"
                  />
                  <p className="mt-1 text-xs text-gray-500">
                    Default: 50. Range: 0-512
                  </p>
                </div>
              </div>
            </div>

            {/* Submit Button */}
            <div className="pt-4">
              <button
                type="submit"
                disabled={isSaving}
                className="w-full bg-blue-600 text-white font-bold py-3 px-6 rounded-lg hover:bg-blue-700 disabled:bg-gray-400 transition"
              >
                {isSaving ? 'Saving...' : 'Save Configuration'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}
