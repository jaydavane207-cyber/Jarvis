import { useState } from 'react';

function App() {
  const [activeTab, setActiveTab] = useState('study');

  return (
    <div className="flex h-screen bg-gray-900 text-white font-sans overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 bg-gray-800 border-r border-gray-700 flex flex-col">
        <div className="p-6">
          <h1 className="text-2xl font-bold tracking-widest text-blue-400">JARVIS</h1>
          <p className="text-xs text-gray-400 mt-1">QUANTUM v2.0</p>
        </div>
        
        <nav className="flex-1 px-4 space-y-2">
          <button 
            onClick={() => setActiveTab('study')}
            className={`w-full text-left px-4 py-2 rounded-md transition-colors ${activeTab === 'study' ? 'bg-blue-600 text-white' : 'text-gray-300 hover:bg-gray-700'}`}
          >
            Study Module
          </button>
          <button 
            onClick={() => setActiveTab('work')}
            className={`w-full text-left px-4 py-2 rounded-md transition-colors ${activeTab === 'work' ? 'bg-blue-600 text-white' : 'text-gray-300 hover:bg-gray-700'}`}
          >
            Work Module
          </button>
        </nav>

        {/* Security Widget */}
        <div className="p-4 m-4 bg-gray-900 rounded-lg border border-red-900/30">
          <h3 className="text-sm font-semibold text-red-400 mb-2">Digital Twin Status</h3>
          <div className="flex items-center space-x-2 text-xs">
            <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
            <span>Layer: PARTIAL_TWIN</span>
          </div>
          <div className="mt-2 text-[10px] text-gray-500 font-mono break-all">
            Key: q-rand-2f9a...
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 p-8 overflow-y-auto">
        <header className="mb-8 flex justify-between items-center">
          <h2 className="text-3xl font-light">
            {activeTab === 'study' ? 'Cognitive Study Assistant' : 'Task & Workflow Optimizer'}
          </h2>
          <div className="px-3 py-1 bg-green-900/30 text-green-400 text-xs rounded-full border border-green-800">
            PQC Secured
          </div>
        </header>

        {/* Dynamic Content Area */}
        {activeTab === 'study' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="bg-gray-800 p-6 rounded-xl border border-gray-700">
              <h3 className="text-xl font-medium mb-4">Jarvis Tutor</h3>
              <div className="bg-gray-900 p-4 rounded-lg h-48 overflow-y-auto font-mono text-sm text-gray-300 mb-4">
                [Jarvis]: Awaiting your questions.
              </div>
              <div className="flex space-x-2">
                <input type="text" placeholder="Ask a question..." className="flex-1 bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 focus:outline-none focus:border-blue-500" />
                <button className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg transition-colors">Ask</button>
              </div>
            </div>

            <div className="bg-gray-800 p-6 rounded-xl border border-gray-700">
              <h3 className="text-xl font-medium mb-4">Skill Accelerator</h3>
              <button className="w-full bg-gray-700 hover:bg-gray-600 text-left px-4 py-3 rounded-lg transition-colors border border-gray-600 mb-2">
                <span className="text-blue-400 block font-semibold text-sm">Target Skill: Machine Learning</span>
                <span className="text-xs text-gray-400 mt-1 block">Generate adaptive path...</span>
              </button>
            </div>
          </div>
        )}

        {activeTab === 'work' && (
          <div className="bg-gray-800 p-6 rounded-xl border border-gray-700">
            <h3 className="text-xl font-medium mb-4">Active Tasks</h3>
            <div className="space-y-3">
               <div className="bg-gray-700 p-3 rounded-lg flex justify-between items-center border border-gray-600">
                  <span>Prepare Q3 Report</span>
                  <span className="px-2 py-1 bg-red-900/50 text-red-400 text-xs rounded border border-red-800">High Priority</span>
               </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
