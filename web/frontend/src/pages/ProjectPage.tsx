import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { apiClient } from '../api/client'

interface Project {
  id: string
  name: string
  description: string
  embed_model_id: string
  llm_model_id: string
}

interface EmbedStatus {
  isEmbedding: boolean
  embedProgress: {
    embedded_chunks: number
    total_chunks: number
    elapsed_seconds: number
  } | null
  embedError: string | null
  embedSuccess: boolean
}

export default function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const [project, setProject] = useState<Project | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [isQuerying, setIsQuerying] = useState(false)
  const [queryResult, setQueryResult] = useState<any>(null)
  const [queryError, setQueryError] = useState<string | null>(null)
  const [uploadedFile, setUploadedFile] = useState<File | null>(null)
  const [embedStatus, setEmbedStatus] = useState<EmbedStatus>({
    isEmbedding: false,
    embedProgress: null,
    embedError: null,
    embedSuccess: false,
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
    } catch (error) {
      console.error('Failed to load project:', error)
      navigate('/dashboard')
    } finally {
      setIsLoading(false)
    }
  }

  const handleQuerySubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!query.trim() || !projectId) return

    setIsQuerying(true)
    setQueryError(null)
    try {
      const result = await apiClient.query(projectId, query)
      setQueryResult(result)
    } catch (error: any) {
      console.error('Query failed:', error)
      setQueryError(
        error.response?.data?.detail || 'Failed to execute query. Make sure you have embedded files.'
      )
      setQueryResult(null)
    } finally {
      setIsQuerying(false)
    }
  }

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !projectId) return

    setEmbedStatus({
      isEmbedding: false,
      embedProgress: null,
      embedError: null,
      embedSuccess: false,
    })

    try {
      // Upload file
      await apiClient.uploadFile(projectId, file)
      setUploadedFile(null)

      // Trigger embedding generation
      setEmbedStatus((prev) => ({
        ...prev,
        isEmbedding: true,
        embedError: null,
      }))

      const embedResult = await apiClient.embed(projectId)

      setEmbedStatus({
        isEmbedding: false,
        embedProgress: embedResult,
        embedError: null,
        embedSuccess: true,
      })

      // Auto-dismiss success message after 5 seconds
      setTimeout(() => {
        setEmbedStatus((prev) => ({
          ...prev,
          embedSuccess: false,
        }))
      }, 5000)
    } catch (error: any) {
      console.error('File upload or embedding failed:', error)
      setEmbedStatus((prev) => ({
        ...prev,
        isEmbedding: false,
        embedError:
          error.response?.data?.detail || 'Failed to upload and embed file',
      }))
    }
  }

  const handleEmbedClick = async () => {
    if (!projectId) return

    setEmbedStatus({
      isEmbedding: true,
      embedProgress: null,
      embedError: null,
      embedSuccess: false,
    })

    try {
      const embedResult = await apiClient.embed(projectId)
      setEmbedStatus({
        isEmbedding: false,
        embedProgress: embedResult,
        embedError: null,
        embedSuccess: true,
      })

      // Auto-dismiss success message after 5 seconds
      setTimeout(() => {
        setEmbedStatus((prev) => ({
          ...prev,
          embedSuccess: false,
        }))
      }, 5000)
    } catch (error: any) {
      console.error('Embedding failed:', error)
      setEmbedStatus((prev) => ({
        ...prev,
        isEmbedding: false,
        embedError: error.response?.data?.detail || 'Failed to embed files',
      }))
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
          <h1 className="text-2xl font-bold text-gray-800">{project.name}</h1>
          <button
            onClick={() => navigate('/dashboard')}
            className="bg-gray-600 text-white px-4 py-2 rounded hover:bg-gray-700"
          >
            Back to Projects
          </button>
        </div>
      </nav>

      <div className="max-w-7xl mx-auto px-4 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Main query section */}
          <div className="lg:col-span-2">
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-2xl font-bold mb-4">Query</h2>
              <form onSubmit={handleQuerySubmit} className="space-y-4">
                <div>
                  <textarea
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Ask a question..."
                    disabled={isQuerying}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500 disabled:bg-gray-100"
                    rows={4}
                  />
                </div>
                <button
                  type="submit"
                  disabled={!query.trim() || isQuerying}
                  className="w-full bg-blue-600 text-white font-bold py-2 px-4 rounded-lg hover:bg-blue-700 disabled:bg-gray-400 transition"
                >
                  {isQuerying ? 'Searching...' : 'Search'}
                </button>
              </form>

              {queryError && (
                <div className="mt-6 p-4 bg-red-50 rounded-lg border border-red-200">
                  <h3 className="font-bold text-red-700 mb-2">Error</h3>
                  <p className="text-red-600 text-sm">{queryError}</p>
                </div>
              )}

              {queryResult && (
                <div className="mt-6 p-4 bg-blue-50 rounded-lg border border-blue-200">
                  <div className="flex justify-between items-start mb-2">
                    <h3 className="font-bold">Answer:</h3>
                    <span className="text-xs text-gray-600">
                      {queryResult.elapsed_seconds?.toFixed(2)}s
                    </span>
                  </div>
                  <p className="text-gray-700 mb-4">{queryResult.answer}</p>
                  {queryResult.citations && queryResult.citations.length > 0 && (
                    <div>
                      <h4 className="font-bold text-sm mb-2">
                        Citations ({queryResult.num_retrieved} chunks):
                      </h4>
                      <ul className="text-sm space-y-1">
                        {queryResult.citations.map((citation: any, idx: number) => (
                          <li key={idx} className="text-gray-600">
                            - {citation.path} (chunk {citation.chunk_id})
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Upload section */}
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-xl font-bold mb-4">Upload & Embed</h2>
              <div className="space-y-3">
                <label className="block">
                  <div className="border-2 border-dashed border-gray-300 rounded-lg p-4 hover:border-blue-500 transition cursor-pointer text-center">
                    <input
                      type="file"
                      onChange={handleFileUpload}
                      disabled={embedStatus.isEmbedding}
                      className="hidden"
                    />
                    <p className="text-sm text-gray-600">
                      {embedStatus.isEmbedding
                        ? 'Embedding...'
                        : 'Click to upload file'}
                    </p>
                  </div>
                </label>

                {embedStatus.embedError && (
                  <div className="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
                    {embedStatus.embedError}
                  </div>
                )}

                {embedStatus.embedSuccess && embedStatus.embedProgress && (
                  <div className="p-3 bg-green-50 border border-green-200 rounded">
                    <p className="text-sm font-semibold text-green-700 mb-1">
                      ✓ Embedding complete!
                    </p>
                    <p className="text-xs text-green-600">
                      {embedStatus.embedProgress.embedded_chunks} chunks embedded
                      in {embedStatus.embedProgress.elapsed_seconds?.toFixed(2)}s
                    </p>
                  </div>
                )}

                {embedStatus.isEmbedding && (
                  <div className="p-3 bg-blue-50 border border-blue-200 rounded">
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-sm font-semibold text-blue-700">
                        Embedding files...
                      </p>
                      <div className="animate-spin rounded-full h-4 w-4 border-2 border-blue-600 border-t-transparent"></div>
                    </div>
                  </div>
                )}

                <button
                  onClick={handleEmbedClick}
                  disabled={embedStatus.isEmbedding}
                  className="w-full bg-green-600 text-white font-semibold py-2 px-4 rounded-lg hover:bg-green-700 disabled:bg-gray-400 transition"
                >
                  {embedStatus.isEmbedding ? 'Embedding...' : 'Re-embed Changed Files'}
                </button>
              </div>
            </div>

            {/* Settings section */}
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-xl font-bold mb-4">Configuration</h2>
              <div className="space-y-3 text-sm">
                <div>
                  <p className="text-gray-600">Embedding Model</p>
                  <p className="font-mono text-xs bg-gray-100 p-2 rounded mt-1 break-words">
                    {project.embed_model_id}
                  </p>
                </div>
                <div>
                  <p className="text-gray-600">LLM Model</p>
                  <p className="font-mono text-xs bg-gray-100 p-2 rounded mt-1 break-words">
                    {project.llm_model_id}
                  </p>
                </div>
              </div>
              <button
                onClick={() => navigate(`/projects/${projectId}/settings`)}
                className="w-full mt-4 bg-gray-600 text-white font-semibold py-2 px-4 rounded-lg hover:bg-gray-700 transition"
              >
                Admin Settings
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
