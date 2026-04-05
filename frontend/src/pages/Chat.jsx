import { useState, useRef, useEffect } from 'react';
import { createTicket, transcribeAudio, getUser } from '../api';

export default function Chat() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [recording, setRecording] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [expandedTicket, setExpandedTicket] = useState(null);
  const messagesEndRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const user = getUser();

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const addMessage = (role, content, data = null) => {
    setMessages(prev => [...prev, { role, content, data, ts: Date.now() }]);
  };

  const handleSend = async () => {
    const query = input.trim();
    if (!query || loading) return;

    setInput('');
    addMessage('user', query);
    setLoading(true);

    try {
      const result = await createTicket(query, sessionId);
      if (!sessionId) setSessionId(result.session_id);
      addMessage('assistant', result.empathy_response || result.resolution_summary || result.clarification_prompt || 'Processing your request...', result);
    } catch (err) {
      addMessage('assistant', `❌ Error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // ── Voice Recording ──────────────────────────────────────────────────────

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      chunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });

        if (blob.size < 100) return;

        addMessage('user', '🎤 [Voice message — transcribing...]');
        setLoading(true);

        try {
          const transcription = await transcribeAudio(blob);
          const text = transcription.transcription;

          // Update the voice message with the transcription
          setMessages(prev => {
            const copy = [...prev];
            const lastUserIdx = copy.findLastIndex(m => m.role === 'user');
            if (lastUserIdx >= 0) {
              copy[lastUserIdx].content = `🎤 "${text}"`;
            }
            return copy;
          });

          // Submit as ticket
          const result = await createTicket(text, sessionId, true);
          if (!sessionId) setSessionId(result.session_id);
          addMessage('assistant', result.empathy_response || result.resolution_summary || 'Processing your request...', result);
        } catch (err) {
          addMessage('assistant', `❌ Voice error: ${err.message}`);
        } finally {
          setLoading(false);
        }
      };

      mediaRecorderRef.current = mediaRecorder;
      mediaRecorder.start();
      setRecording(true);
    } catch (err) {
      alert('Microphone access denied. Please enable microphone permissions.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && recording) {
      mediaRecorderRef.current.stop();
      setRecording(false);
    }
  };

  const toggleRecording = () => {
    if (recording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  // ── Render Helpers ─────────────────────────────────────────────────────────

  const getBadgeClass = (value, type) => {
    if (!value) return '';
    const map = {
      status: { resolved: 'badge-resolved', escalated: 'badge-escalated', open: 'badge-open', in_progress: 'badge-open' },
      mode: { AUTO: 'badge-auto', ASSISTED: 'badge-assisted', ESCALATED: 'badge-escalated' },
      priority: { Critical: 'badge-critical', High: 'badge-high', Medium: 'badge-medium', Low: 'badge-low' },
    };
    return map[type]?.[value] || '';
  };

  return (
    <div className="chat-container">
      {/* Messages */}
      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="empty-state">
            <div className="icon">💬</div>
            <h3>Welcome to IntentFlow</h3>
            <p>Describe your issue below, or use the microphone for voice input.</p>
            <p style={{ marginTop: 12, fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Try: "I can't log in to my account" or "I need a refund for order #12345"
            </p>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`chat-msg ${msg.role} fade-in`}>
            <div className="chat-msg-avatar">
              {msg.role === 'user' ? user?.name?.charAt(0)?.toUpperCase() || 'U' : '🤖'}
            </div>
            <div>
              <div className="chat-msg-body">
                <div className="chat-msg-text" style={{ whiteSpace: 'pre-wrap' }}>
                  {msg.content}
                </div>
              </div>

              {msg.data && (
                <div className="chat-msg-meta">
                  {msg.data.mode && (
                    <span className={`badge ${getBadgeClass(msg.data.mode, 'mode')}`}>
                      {msg.data.mode}
                    </span>
                  )}
                  {msg.data.priority && (
                    <span className={`badge ${getBadgeClass(msg.data.priority, 'priority')}`}>
                      {msg.data.priority}
                    </span>
                  )}
                  {msg.data.status && (
                    <span className={`badge ${getBadgeClass(msg.data.status, 'status')}`}>
                      {msg.data.status}
                    </span>
                  )}
                  {msg.data.confidence != null && (
                    <span className="badge" style={{ background: 'rgba(139,92,246,0.15)', color: '#a78bfa' }}>
                      {msg.data.confidence}% confidence
                    </span>
                  )}
                  {msg.data.stress_level != null && msg.data.stress_level > 0.3 && (
                    <span className="badge" style={{ background: 'rgba(239,68,68,0.15)', color: '#f87171' }}>
                      Stress: {(msg.data.stress_level * 100).toFixed(0)}%
                    </span>
                  )}
                </div>
              )}

              {/* Expandable ticket detail */}
              {msg.data && (
                <div style={{ marginTop: 8 }}>
                  <button
                    className="btn btn-sm btn-outline"
                    onClick={() => setExpandedTicket(expandedTicket === i ? null : i)}
                  >
                    {expandedTicket === i ? '▲ Hide details' : '▼ View details'}
                  </button>

                  {expandedTicket === i && (
                    <div className="ticket-detail fade-in">
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, fontSize: '0.82rem' }}>
                        <div><strong style={{ color: 'var(--text-muted)' }}>Ticket ID:</strong> {msg.data.ticket_id}</div>
                        <div><strong style={{ color: 'var(--text-muted)' }}>Intent:</strong> {msg.data.intent}</div>
                        {msg.data.sla_deadline && (
                          <div><strong style={{ color: 'var(--text-muted)' }}>SLA Deadline:</strong> {new Date(msg.data.sla_deadline).toLocaleString()}</div>
                        )}
                      </div>

                      {msg.data.resolution_plan && msg.data.resolution_plan.length > 0 && (
                        <div className="ticket-plan">
                          <strong style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>Resolution Plan:</strong>
                          {msg.data.resolution_plan.map((step, si) => (
                            <div key={si} className="ticket-plan-step">
                              <span className="step-num">{si + 1}</span>
                              <span>{step}</span>
                            </div>
                          ))}
                        </div>
                      )}

                      {msg.data.violations && msg.data.violations.length > 0 && (
                        <div style={{ marginTop: 12 }}>
                          <strong style={{ color: '#f87171', fontSize: '0.8rem' }}>⚠ Violations:</strong>
                          {msg.data.violations.map((v, vi) => (
                            <div key={vi} style={{ fontSize: '0.82rem', color: '#f87171', marginTop: 4 }}>• {v}</div>
                          ))}
                        </div>
                      )}

                      {msg.data.escalation_reason && (
                        <div style={{ marginTop: 12, padding: 12, background: 'rgba(245,158,11,0.08)', borderRadius: 8 }}>
                          <strong style={{ color: '#fbbf24', fontSize: '0.8rem' }}>Escalation Reason:</strong>
                          <p style={{ fontSize: '0.85rem', marginTop: 4 }}>{msg.data.escalation_reason}</p>
                        </div>
                      )}

                      {msg.data.resolution_summary && (
                        <div style={{ marginTop: 12, padding: 12, background: 'rgba(16,185,129,0.08)', borderRadius: 8 }}>
                          <strong style={{ color: '#34d399', fontSize: '0.8rem' }}>Resolution:</strong>
                          <p style={{ fontSize: '0.85rem', marginTop: 4, whiteSpace: 'pre-wrap' }}>{msg.data.resolution_summary}</p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="chat-msg assistant fade-in">
            <div className="chat-msg-avatar">🤖</div>
            <div className="chat-msg-body">
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span className="spinner" />
                <span style={{ color: 'var(--text-muted)', fontSize: '0.88rem' }}>
                  Analyzing your request...
                </span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="chat-input-area">
        <div className="chat-input-wrapper">
          <input
            className="chat-input"
            placeholder="Describe your issue..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
          />
        </div>

        <button
          className={`voice-btn ${recording ? 'recording' : ''}`}
          onClick={toggleRecording}
          disabled={loading && !recording}
          title={recording ? 'Stop recording' : 'Start voice input'}
        >
          {recording ? '⏹' : '🎤'}
        </button>

        <button
          className="btn btn-primary btn-icon"
          onClick={handleSend}
          disabled={loading || !input.trim()}
          title="Send"
        >
          ➤
        </button>
      </div>
    </div>
  );
}
