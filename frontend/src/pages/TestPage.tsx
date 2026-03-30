// TEST: Temporary test page to verify code updates
import React, { useEffect, useState } from 'react';

export default function TestPage() {
  const [apiData, setApiData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    console.log('🧪 TestPage loaded - code is updating!');

    fetch('/api/dashboard/instruments')
      .then(r => r.json())
      .then(data => {
        console.log('✅ API data received:', data);
        setApiData(data);
      })
      .catch(err => {
        console.error('❌ API error:', err);
        setError(err.message);
      });
  }, []);

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold">🧪 Test Page</h1>
      <p className="mt-4">If you can see this, React is updating!</p>

      {error && (
        <div className="mt-4 p-4 bg-red-100 border border-red-400 text-red-700 rounded">
          ❌ Error: {error}
        </div>
      )}

      {apiData && (
        <div className="mt-4 p-4 bg-green-100 border border-green-400 text-green-700 rounded">
          ✅ API Working: {apiData.data?.length || 0} instruments found
        </div>
      )}

      <div className="mt-4 p-4 bg-blue-100 border border-blue-400 text-blue-700 rounded">
        <p>Current timestamp: {new Date().toLocaleTimeString()}</p>
        <p>If this timestamp updates when you refresh, React is working!</p>
      </div>
    </div>
  );
}