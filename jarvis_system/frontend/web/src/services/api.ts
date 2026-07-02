import axios from 'axios';

// The FastAPI backend is running on port 8000
const API_BASE_URL = 'http://localhost:8000/api/v1';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Example API calls tying into our Phase 1-4 Backend Modules
export const JARVIS_API = {
  // Study Module
  getNotes: () => apiClient.get('/study/notes'),
  createNote: (data: { title: string; content: string; subject: string }) => 
    apiClient.post('/study/notes', data),
    
  // Productivity Module
  getTasks: () => apiClient.get('/productivity/tasks'),
  
  // Cognitive Engine
  synthesizeIdeas: (concepts: string[]) => 
    apiClient.post('/cognitive/synthesize', { concepts, context_depth: 'deep' }),
    
  // India Ops (UPI Fraud Check)
  checkUPI: (vpa: string, amount: number) => 
    apiClient.post('/india/upi/fraud-check', { vpa, amount }),
};
