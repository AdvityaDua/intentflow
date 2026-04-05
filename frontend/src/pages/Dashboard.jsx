import { useState, useEffect } from 'react';
import { getOverview, getByIntent, getByPriority, getByMode, getSLAMetrics, getRecentTickets } from '../api';

export default function Dashboard() {
  const [overview, setOverview] = useState(null);
  const [byIntent, setByIntent] = useState([]);
  const [byPriority, setByPriority] = useState([]);
  const [byMode, setByMode] = useState([]);
  const [sla, setSla] = useState([]);
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [ov, bi, bp, bm, sl, tk] = await Promise.all([
        getOverview(),
        getByIntent(),
        getByPriority(),
        getByMode(),
        getSLAMetrics(),
        getRecentTickets(20),
      ]);
      setOverview(ov);
      setByIntent(bi);
      setByPriority(bp);
      setByMode(bm);
      setSla(sl);
      setTickets(tk);
    } catch (err) {
      console.error('Dashboard load error:', err);
    } finally {
      setLoading(false);
    }
  };

  const filterTickets = async (status) => {
    setFilter(status);
    try {
      const tk = await getRecentTickets(20, status);
      setTickets(tk);
    } catch (err) {
      console.error(err);
    }
  };

  if (loading) {
    return <div className="loading-center"><span className="spinner" /></div>;
  }

  const maxIntentCount = Math.max(...byIntent.map(x => x.count), 1);

  const priorityColors = { Critical: '#ef4444', High: '#f59e0b', Medium: '#3b82f6', Low: '#64748b' };
  const modeColors = { AUTO: '#10b981', ASSISTED: '#f59e0b', ESCALATED: '#ef4444', CLARIFICATION: '#8b5cf6' };

  const getBadgeClass = (val, type) => {
    const map = {
      status: { resolved: 'badge-resolved', escalated: 'badge-escalated', open: 'badge-open', in_progress: 'badge-open' },
      priority: { Critical: 'badge-critical', High: 'badge-high', Medium: 'badge-medium', Low: 'badge-low' },
      mode: { AUTO: 'badge-auto', ASSISTED: 'badge-assisted', ESCALATED: 'badge-escalated' },
    };
    return map[type]?.[val] || '';
  };

  return (
    <div className="slide-up">
      <div className="page-header">
        <h2>Dashboard</h2>
        <p>Real-time overview of IntentFlow performance</p>
      </div>

      {/* Metric Cards */}
      {overview && (
        <div className="metric-grid">
          <div className="metric-card">
            <div className="metric-icon">📋</div>
            <div className="metric-value">{overview.total_tickets}</div>
            <div className="metric-label">Total Tickets</div>
          </div>
          <div className="metric-card">
            <div className="metric-icon">✅</div>
            <div className="metric-value" style={{ color: '#34d399' }}>{overview.resolution_rate}%</div>
            <div className="metric-label">Resolution Rate</div>
          </div>
          <div className="metric-card">
            <div className="metric-icon">🎯</div>
            <div className="metric-value" style={{ color: '#a78bfa' }}>{overview.avg_confidence}%</div>
            <div className="metric-label">Avg Confidence</div>
          </div>
          <div className="metric-card">
            <div className="metric-icon">⚡</div>
            <div className="metric-value" style={{ color: '#60a5fa' }}>
              {overview.avg_resolution_ms < 1000
                ? `${overview.avg_resolution_ms}ms`
                : `${(overview.avg_resolution_ms / 1000).toFixed(1)}s`}
            </div>
            <div className="metric-label">Avg Resolution</div>
          </div>
          <div className="metric-card">
            <div className="metric-icon">📊</div>
            <div className="metric-value" style={{ color: '#10b981' }}>{overview.sla_compliance}%</div>
            <div className="metric-label">SLA Compliance</div>
          </div>
          <div className="metric-card">
            <div className="metric-icon">🚨</div>
            <div className="metric-value" style={{ color: overview.sla_breaches > 0 ? '#f87171' : '#34d399' }}>
              {overview.sla_breaches}
            </div>
            <div className="metric-label">SLA Breaches</div>
          </div>
        </div>
      )}

      {/* Charts Row */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 32 }}>
        {/* Intent Chart */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">Tickets by Intent</span>
          </div>
          {byIntent.length > 0 ? (
            <div className="chart-bars">
              {byIntent.slice(0, 8).map((item, i) => (
                <div key={i} className="chart-bar-col">
                  <span className="chart-bar-value">{item.count}</span>
                  <div
                    className="chart-bar"
                    style={{
                      height: `${(item.count / maxIntentCount) * 100}%`,
                      background: `hsl(${220 + i * 25}, 70%, 55%)`,
                    }}
                  />
                  <span className="chart-bar-label">{item.intent?.replace('_', ' ')}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state" style={{ padding: 20 }}><p>No data yet</p></div>
          )}
        </div>

        {/* Priority + Mode */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">Distribution</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
            <div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 12, textTransform: 'uppercase', letterSpacing: 1 }}>
                By Priority
              </div>
              {byPriority.map((item, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                  <div style={{ width: 10, height: 10, borderRadius: '50%', background: priorityColors[item.priority] || '#666' }} />
                  <span style={{ flex: 1, fontSize: '0.82rem' }}>{item.priority}</span>
                  <span style={{ fontWeight: 700, fontSize: '0.85rem' }}>{item.count}</span>
                </div>
              ))}
              {byPriority.length === 0 && <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>No data</p>}
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 12, textTransform: 'uppercase', letterSpacing: 1 }}>
                By Mode
              </div>
              {byMode.map((item, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                  <div style={{ width: 10, height: 10, borderRadius: '50%', background: modeColors[item.mode] || '#666' }} />
                  <span style={{ flex: 1, fontSize: '0.82rem' }}>{item.mode}</span>
                  <span style={{ fontWeight: 700, fontSize: '0.85rem' }}>{item.count}</span>
                </div>
              ))}
              {byMode.length === 0 && <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>No data</p>}
            </div>
          </div>
        </div>
      </div>

      {/* SLA Cards */}
      {sla.length > 0 && (
        <div className="card" style={{ marginBottom: 32 }}>
          <div className="card-header">
            <span className="card-title">SLA Compliance by Priority</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
            {sla.map((s, i) => (
              <div key={i} style={{ textAlign: 'center', padding: 16, background: 'var(--bg-glass)', borderRadius: 12 }}>
                <div style={{ fontSize: '1.6rem', fontWeight: 800, color: s.compliance >= 90 ? '#34d399' : s.compliance >= 70 ? '#fbbf24' : '#f87171' }}>
                  {s.compliance}%
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 4 }}>{s.priority}</div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{s.total} tickets, {s.breached} breached</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent Tickets */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">Recent Tickets</span>
          <button className="btn btn-sm btn-outline" onClick={loadData}>Refresh</button>
        </div>

        <div className="filter-tabs">
          {[null, 'open', 'in_progress', 'resolved', 'escalated'].map(s => (
            <button
              key={s || 'all'}
              className={`filter-tab ${filter === s ? 'active' : ''}`}
              onClick={() => filterTickets(s)}
            >
              {s ? s.replace('_', ' ') : 'All'}
            </button>
          ))}
        </div>

        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Query</th>
                <th>Intent</th>
                <th>Priority</th>
                <th>Mode</th>
                <th>Confidence</th>
                <th>Status</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {tickets.map(t => (
                <tr key={t.id}>
                  <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {t.from_voice && '🎤 '}{t.query}
                  </td>
                  <td>{t.intent?.replace('_', ' ')}</td>
                  <td><span className={`badge ${getBadgeClass(t.priority, 'priority')}`}>{t.priority}</span></td>
                  <td><span className={`badge ${getBadgeClass(t.mode, 'mode')}`}>{t.mode}</span></td>
                  <td>
                    {t.confidence != null && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <div className="confidence-bar">
                          <div className="confidence-fill" style={{
                            width: `${t.confidence}%`,
                            background: t.confidence >= 75 ? '#10b981' : t.confidence >= 45 ? '#f59e0b' : '#ef4444',
                          }} />
                        </div>
                        <span style={{ fontSize: '0.78rem' }}>{t.confidence}%</span>
                      </div>
                    )}
                  </td>
                  <td><span className={`badge ${getBadgeClass(t.status, 'status')}`}>{t.status}</span></td>
                  <td style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                    {new Date(t.created_at).toLocaleString()}
                  </td>
                </tr>
              ))}
              {tickets.length === 0 && (
                <tr><td colSpan={7} style={{ textAlign: 'center', padding: 40 }}>No tickets found</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
