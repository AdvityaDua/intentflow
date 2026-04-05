import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, NavLink, useNavigate } from 'react-router-dom';
import { getToken, getUser, clearAuth } from './api';
import Login from './pages/Login';
import Chat from './pages/Chat';
import Dashboard from './pages/Dashboard';
import Audit from './pages/Audit';

function ProtectedRoute({ children }) {
  const token = getToken();
  if (!token) return <Navigate to="/login" replace />;
  return children;
}

function AppLayout() {
  const user = getUser();
  const navigate = useNavigate();
  const isAdmin = user?.role === 'admin' || user?.role === 'agent';

  const handleLogout = () => {
    clearAuth();
    navigate('/login');
  };

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <h1>IntentFlow</h1>
          <span>AI Resolution Engine</span>
        </div>
        <nav className="sidebar-nav">
          <NavLink to="/chat" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
            <span className="icon">💬</span>
            Chat
          </NavLink>
          {isAdmin && (
            <>
              <NavLink to="/dashboard" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
                <span className="icon">📊</span>
                Dashboard
              </NavLink>
              <NavLink to="/audit" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
                <span className="icon">🔍</span>
                Audit Trail
              </NavLink>
            </>
          )}
        </nav>
        <div className="sidebar-user">
          <div className="sidebar-avatar">
            {user?.name?.charAt(0)?.toUpperCase() || '?'}
          </div>
          <div className="sidebar-user-info">
            <div className="sidebar-user-name">{user?.name || 'User'}</div>
            <div className="sidebar-user-role">{user?.role || 'user'}</div>
          </div>
          <button className="btn btn-sm btn-outline" onClick={handleLogout} title="Logout">
            ⏻
          </button>
        </div>
      </aside>
      <main className="main-content">
        <Routes>
          <Route path="/chat" element={<Chat />} />
          {isAdmin && <Route path="/dashboard" element={<Dashboard />} />}
          {isAdmin && <Route path="/audit" element={<Audit />} />}
          <Route path="*" element={<Navigate to="/chat" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/*" element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        } />
      </Routes>
    </BrowserRouter>
  );
}
