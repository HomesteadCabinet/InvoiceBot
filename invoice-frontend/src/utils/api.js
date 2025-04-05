// Base URL for API requests

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

    // Check if response is JSON
    const contentType = response.headers.get('content-type')
    if (!contentType || !contentType.includes('application/json')) {
      throw new Error('Response was not JSON')
    }

    if (!response.ok) {
      const errorData = await response.json()
      throw new Error(errorData.message || `HTTP error! status: ${response.status}`)
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
