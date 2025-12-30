import React from 'react';
import './App.css';

function App() {
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm">
        {/* header with app title */}
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <h1 className="text-3xl font-bold text-gray-900">
            SafeStep
          </h1>
          <p className="text-gray-600 mt-1">
            AI Safety Route Navigator
          </p>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* placeholder for map component */}
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold text-gray-800 mb-4">
            Find the Safest Route
          </h2>
          <p className="text-gray-600">
            map and route calculation will be implemented in the next commits
          </p>
        </div>
      </main>
    </div>
  );
}

export default App;

