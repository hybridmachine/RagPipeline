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

export default function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const [project, setProject] = useState<Project | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [queryResult, setQueryResult] = useState<any>(null)
  const [uploadedFile, setUploadedFile] = useState<File | null>(null)

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

    try {
      const result = await apiClient.query(projectId, query)
      setQueryResult(result)
    } catch (error) {
      console.error('Query failed:', error)
    }
  }

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !projectId) return

    try {
      await apiClient.uploadFile(projectId, file)
      setUploadedFile(null)
      // Trigger embedding generation
      await apiClient.embed(projectId)
    } catch (error) {
      console.error('File upload failed:', error)
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
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500"
                    rows={4}
                  />
                </div>
                <button
                  type="submit"
                  disabled={!query.trim()}
                  className="w-full bg-blue-600 text-white font-bold py-2 px-4 rounded-lg hover:bg-blue-700 disabled:bg-gray-400 transition"
                >
                  Search
                </button>
              </form>

              {queryResult && (
                <div className="mt-6 p-4 bg-blue-50 rounded-lg border border-blue-200">
                  <h3 className="font-bold mb-2">Answer:</h3>
                  <p className="text-gray-700 mb-4">{queryResult.answer}</p>
                  {queryResult.citations && queryResult.citations.length > 0 && (
                    <div>
                      <h4 className="font-bold text-sm mb-2">Citations:</h4>
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
              <h2 className="text-xl font-bold mb-4">Upload Files</h2>
              <label className="block">
                <input
                  type="file"
                  onChange={handleFileUpload}
                  className="block w-full text-sm text-gray-600"
                />
              </label>
            </div>

            {/* Settings section */}
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-xl font-bold mb-4">Configuration</h2>
              <div className="space-y-3 text-sm">
                <div>
                  <p className="text-gray-600">Embedding Model</p>
                  <p className="font-semibold">{project.embed_model_id}</p>
                </div>
                <div>
                  <p className="text-gray-600">LLM Model</p>
                  <p className="font-semibold">{project.llm_model_id}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
