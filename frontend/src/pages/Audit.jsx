import { useState, useEffect } from 'react';
import { getRecentTickets, getTicket } from '../api';

export default function Audit() {
  const [tickets, setTickets] = useState([]);
  const [selectedTicket, setSelectedTicket] = useState(null);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [filter, setFilter] = useState(null);
  const [search, setSearch] = useState('');

  useEffect(() => {
    loadTickets();
  }, []);

  const loadTickets = async (status = null) => {
    setLoading(true);
    try {
      const tk = await getRecentTickets(50, status);
      setTickets(tk);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const loadDetail = async (ticketId) => {
    if (selectedTicket === ticketId) {
      setSelectedTicket(null);
      setDetail(null);
      return;
    }
    setSelectedTicket(ticketId);
    setDetailLoading(true);
    try {
      const d = await getTicket(ticketId);
      setDetail(d);
    } catch (err) {
      console.error(err);
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const handleFilter = (status) => {
    setFilter(status);
    loadTickets(status);
  };

  const filteredTickets = search
    ? tickets.filter(t =>
        t.query?.toLowerCase().includes(search.toLowerCase()) ||
        t.intent?.toLowerCase().includes(search.toLowerCase()) ||
        t.id?.toLowerCase().includes(search.toLowerCase())
      )
    : tickets;

  const getConfidenceColor = (conf) => {
    if (conf >= 75) return '#10b981';
    if (conf >= 45) return '#f59e0b';
    return '#ef4444';
  };

  return (
    <div className="slide-up">
      <div className="page-header">
        <h2>Audit Trail</h2>
        <p>Inspect every decision, confidence score, and agent action</p>
      </div>

      {/* Search + Filters */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 24, alignItems: 'center' }}>
        <input
          className="form-input"
          placeholder="Search by ticket ID, query, or intent..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ maxWidth: 400 }}
        />
        <div className="filter-tabs" style={{ marginBottom: 0 }}>
          {[null, 'resolved', 'escalated', 'open'].map(s => (
            <button
              key={s || 'all'}
              className={`filter-tab ${filter === s ? 'active' : ''}`}
              onClick={() => handleFilter(s)}
            >
              {s || 'All'}
            </button>
          ))}
        </div>
        <button className="btn btn-sm btn-outline" onClick={() => loadTickets(filter)} style={{ marginLeft: 'auto' }}>
          🔄 Refresh
        </button>
      </div>

      {loading ? (
        <div className="loading-center"><span className="spinner" /></div>
      ) : filteredTickets.length === 0 ? (
        <div className="empty-state">
          <div className="icon">🔍</div>
          <h3>No tickets found</h3>
          <p>Submit some complaints from the Chat page to see audit trails here.</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {filteredTickets.map(t => (
            <div key={t.id}>
              {/* Ticket Row */}
              <div
                className="card"
                style={{
                  padding: '14px 20px',
                  cursor: 'pointer',
                  borderColor: selectedTicket === t.id ? 'var(--accent-blue)' : undefined,
                }}
                onClick={() => loadDetail(t.id)}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'monospace' }}>
                        {t.id}
                      </span>
                      {t.from_voice && <span style={{ fontSize: '0.7rem' }}>🎤</span>}
                    </div>
                    <div style={{ fontSize: '0.88rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {t.query}
                    </div>
                  </div>
                  <span className={`badge badge-${t.priority?.toLowerCase()}`}>{t.priority}</span>
                  <span className={`badge badge-${t.mode?.toLowerCase()}`}>{t.mode}</span>
                  <span className={`badge badge-${t.status}`}>{t.status}</span>
                  {t.confidence != null && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4, minWidth: 60 }}>
                      <div className="confidence-bar" style={{ width: 40 }}>
                        <div className="confidence-fill" style={{
                          width: `${t.confidence}%`,
                          background: getConfidenceColor(t.confidence),
                        }} />
                      </div>
                      <span style={{ fontSize: '0.75rem', fontWeight: 700 }}>{t.confidence}%</span>
                    </div>
                  )}
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', minWidth: 80, textAlign: 'right' }}>
                    {new Date(t.created_at).toLocaleDateString()}
                  </span>
                  <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                    {selectedTicket === t.id ? '▲' : '▼'}
                  </span>
                </div>
              </div>

              {/* Expanded Audit Trail */}
              {selectedTicket === t.id && (
                <div className="card fade-in" style={{ marginTop: 2, padding: '20px 24px', borderColor: 'var(--accent-blue)' }}>
                  {detailLoading ? (
                    <div className="loading-center" style={{ minHeight: 100 }}><span className="spinner" /></div>
                  ) : detail ? (
                    <>
                      <h4 style={{ marginBottom: 16, fontSize: '0.95rem' }}>
                        Decision Trail — {detail.audit_trail?.length || 0} steps
                      </h4>

                      {detail.audit_trail && detail.audit_trail.length > 0 ? (
                        <div className="audit-timeline">
                          {detail.audit_trail.map((entry, i) => (
                            <div key={i} className="audit-entry">
                              <div className="audit-entry-header">
                                <div>
                                  <span className="audit-agent">{entry.agent}</span>
                                  <span className="audit-step" style={{ marginLeft: 8 }}>{entry.step}</span>
                                </div>
                                <span className="audit-latency">
                                  {entry.latency_ms ? `${entry.latency_ms}ms` : ''}
                                </span>
                              </div>

                              {entry.reasoning && (
                                <div className="audit-reasoning">{entry.reasoning}</div>
                              )}

                              {entry.confidence != null && (
                                <div className="audit-confidence">
                                  <div className="confidence-bar" style={{ width: 80 }}>
                                    <div className="confidence-fill" style={{
                                      width: `${entry.confidence * 100}%`,
                                      background: getConfidenceColor(entry.confidence * 100),
                                    }} />
                                  </div>
                                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                                    {(entry.confidence * 100).toFixed(0)}%
                                  </span>
                                </div>
                              )}

                              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: 4 }}>
                                {new Date(entry.timestamp).toLocaleString()}
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No audit trail available for this ticket.</p>
                      )}
                    </>
                  ) : (
                    <p style={{ color: 'var(--text-muted)' }}>Failed to load details</p>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
