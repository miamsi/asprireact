'use client';

import { useState, useEffect } from 'react';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface Task {
  id: string;
  task: string;
  is_done: boolean;
  category: string;
  priority: string;
}

export default function ChatDashboard() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [tasks, setTasks] = useState<Task[]>([]);
  const [filter, setFilter] = useState('open');
  const [isLoading, setIsLoading] = useState(false);
  
  const USER_ID = "michael_sidabutar"; 
  const API_BASE = "http://localhost:8000"; // Point this to your backend server URL

  const fetchTasks = async (currentFilter: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/tasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: USER_ID, filter_type: currentFilter }),
      });
      const data = await res.json();
      setTasks(data.tasks || []);
    } catch (err) {
      console.error("Failed fetching task tracking records:", err);
    }
  };

  useEffect(() => {
    fetchTasks(filter);
  }, [filter]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage: Message = { role: 'user', content: input };
    const updatedHistory = [...messages, userMessage];
    setMessages(updatedHistory);
    setInput('');
    setIsLoading(true);

    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: USER_ID,
          prompt: input,
          history: messages.map(m => ({ role: m.role, content: m.content }))
        }),
      });
      const data = await res.json();
      setMessages([...updatedHistory, { role: 'assistant', content: data.reply }]);
      
      if (data.changed) {
        fetchTasks(filter);
      }
    } catch (err) {
      setMessages([...updatedHistory, { role: 'assistant', content: "Error: Could not reach the engine." }]);
    } finally {
      setIsLoading(false);
    }
  };

  const toggleTask = async (id: string) => {
    try {
      await fetch(`${API_BASE}/api/tasks/complete/${id}`, { method: 'POST' });
      fetchTasks(filter);
    } catch (err) {
      console.error("Failed updating task state:", err);
    }
  };

  return (
    <div className="flex h-screen bg-gray-950 text-gray-100 antialiased">
      {/* SIDEBAR */}
      <aside className="w-80 bg-gray-900 border-r border-gray-800 flex flex-col p-4">
        <h2 className="text-lg font-bold mb-4 text-indigo-400 tracking-tight">📋 Aspri Workspace</h2>
        <div className="flex flex-wrap gap-1.5 mb-4">
          {['open', 'today', 'upcoming', 'overdue', 'done'].map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-2.5 py-1 rounded-md text-xs font-medium capitalize transition ${
                filter === f ? 'bg-indigo-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
              }`}
            >
              {f}
            </button>
          ))}
        </div>
        <div className="flex-1 overflow-y-auto space-y-2 pr-1">
          {tasks.map((task) => (
            <div key={task.id} className="p-3 bg-gray-950 border border-gray-800 rounded-lg flex items-start gap-3">
              <input
                type="checkbox"
                checked={task.is_done}
                onChange={() => toggleTask(task.id)}
                className="mt-1 h-4 w-4 rounded accent-indigo-600 border-gray-700 bg-gray-800 cursor-pointer"
              />
              <div className="flex-1 min-w-0">
                <p className={`text-sm font-medium ${task.is_done ? 'line-through text-gray-500' : 'text-gray-200'}`}>
                  {task.task}
                </p>
                <div className="flex gap-2 mt-1.5 text-[10px] font-mono capitalize">
                  <span className="px-1.5 py-0.5 bg-gray-800 rounded text-gray-400">{task.priority}</span>
                  <span className="px-1.5 py-0.5 bg-indigo-950 text-indigo-400 rounded">{task.category}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </aside>

      {/* CHAT WINDOW */}
      <main className="flex-1 flex flex-col bg-gray-950">
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {messages.map((msg, idx) => (
            <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-xl p-4 rounded-xl text-sm leading-relaxed shadow-sm ${
                msg.role === 'user' ? 'bg-indigo-600 text-white rounded-br-none' : 'bg-gray-900 text-gray-200 border border-gray-800 rounded-bl-none'
              }`}>
                {msg.content}
              </div>
            </div>
          ))}
          {isLoading && (
            <div className="flex justify-start">
              <div className="bg-gray-900 border border-gray-800 text-gray-400 text-xs px-4 py-2.5 rounded-lg animate-pulse">
                Processing tool actions...
              </div>
            </div>
          )}
        </div>
        <form onSubmit={handleSend} className="p-4 bg-gray-900 border-t border-gray-800 flex gap-3">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type your message..."
            className="flex-1 bg-gray-950 border border-gray-800 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-indigo-500 transition text-gray-100"
          />
          <button
            type="submit"
            disabled={isLoading}
            className="bg-indigo-600 hover:bg-indigo-500 disabled:bg-gray-800 text-white font-medium px-5 py-3 rounded-xl text-sm transition"
          >
            Send
          </button>
        </form>
      </main>
    </div>
  );
}
