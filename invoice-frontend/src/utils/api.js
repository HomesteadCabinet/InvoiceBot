// Base URL for API requests

function formatApiError (errorData, status) {
  if (!errorData || typeof errorData !== 'object') {
    return `HTTP error! status: ${status}`
  }
  if (errorData.message) {
    return String(errorData.message)
  }
  if (errorData.detail) {
    return String(errorData.detail)
  }
  const parts = []
  for (const [key, value] of Object.entries(errorData)) {
    const messages = Array.isArray(value) ? value.map(String) : [String(value)]
    parts.push(`${key}: ${messages.join(', ')}`)
  }
  return parts.join(' · ') || `HTTP error! status: ${status}`
}

export async function fetchAPI(endpoint, options = {}) {
  // Ensure endpoint starts with a slash
  const url = endpoint.startsWith('/') ? `${endpoint}` : `/${endpoint}`

  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers
      }
    })

    if (response.status === 204) {
      return null
    }

    // Check if response is JSON
    const contentType = response.headers.get('content-type')
    if (!contentType || !contentType.includes('application/json')) {
      return null
    }

    if (!response.ok) {
      const errorData = await response.json()
      const err = new Error(formatApiError(errorData, response.status))
      err.data = errorData
      throw err
    }

    return response.json()
  } catch (error) {
    console.error('API Error:', error)
    throw error
  }
}

export async function postAPI(endpoint, data, options = {}) {
  return fetchAPI(endpoint, {
    method: 'POST',
    body: JSON.stringify(data),
    ...options
  })
}

export async function patchAPI(endpoint, data, options = {}) {
  return fetchAPI(endpoint, {
    method: 'PATCH',
    body: JSON.stringify(data),
    ...options
  })
}

export async function putAPI(endpoint, data, options = {}) {
  return fetchAPI(endpoint, {
    method: 'PUT',
    body: JSON.stringify(data),
    ...options
  })
}

export async function deleteAPI(endpoint, options = {}) {
  return fetchAPI(endpoint, {
    method: 'DELETE',
    ...options
  })
}

async function parseResponse (response) {
  if (response.status === 204) {
    return null
  }
  const contentType = response.headers.get('content-type')
  if (!contentType || !contentType.includes('application/json')) {
    return null
  }
  if (!response.ok) {
    const errorData = await response.json()
    throw new Error(errorData.message || errorData.detail || `HTTP error! status: ${response.status}`)
  }
  return response.json()
}

export async function submitFormAPI (endpoint, formData, method = 'POST', options = {}) {
  const url = endpoint.startsWith('/') ? `${endpoint}` : `/${endpoint}`
  const response = await fetch(url, {
    method,
    body: formData,
    ...options,
  })
  try {
    return await parseResponse(response)
  } catch (error) {
    console.error('API Error:', error)
    throw error
  }
}
