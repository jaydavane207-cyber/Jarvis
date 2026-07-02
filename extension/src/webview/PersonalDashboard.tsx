import React, { useEffect, useState } from 'react';
import { Brain, Target, HeartPulse, DollarSign, Lightbulb, RefreshCw } from 'lucide-react';

interface PersonalData {
  goals: any[];
  health: any[];
  finance: any[];
  memory: Record<string, string>;
}

export const PersonalDashboard = () => {
  const [data, setData] = useState<PersonalData | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    setLoading(true);
    try {
      let baseUrl = 'http://127.0.0.1:8000';
      if (window.location.protocol === 'http:' || window.location.protocol === 'https:') {
        baseUrl = `${window.location.protocol}//${window.location.host}`;
      }
      const res = await fetch(`${baseUrl}/api/personal/stats`);
      if (res.ok) {
        const json = await res.json();
        setData(json);
      }
    } catch (err) {
      console.error('Failed to fetch personal data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  if (loading && !data) {
    return (
      <div className="personal-dashboard loading-state">
        <div className="thinking-dots"><span /><span /><span /></div>
        <p>Loading Personal AI Profile...</p>
      </div>
    );
  }

  const { goals = [], health = [], finance = [], memory = {} } = data || {};

  // Calculate some basic finance metrics
  const totalExpenses = finance
    .filter((f) => f.log_type === 'expense')
    .reduce((acc, curr) => acc + curr.amount, 0);
  const totalIncome = finance
    .filter((f) => f.log_type === 'income')
    .reduce((acc, curr) => acc + curr.amount, 0);

  return (
    <div className="personal-dashboard fade-in">
      <div className="dashboard-header">
        <h2>Your Personal AI Profile</h2>
        <button onClick={fetchData} className="refresh-btn" title="Refresh Data">
          <RefreshCw size={16} />
        </button>
      </div>

      <div className="dashboard-grid">
        
        {/* ── Memory & Context ── */}
        <div className="dash-card span-full">
          <div className="dash-card-header">
            <Brain size={18} className="icon-purple" />
            <h3>Memory & Context</h3>
          </div>
          <div className="memory-chips">
            {Object.keys(memory).length === 0 ? (
              <span className="empty-text">No preferences learned yet.</span>
            ) : (
              Object.entries(memory).map(([k, v]) => (
                <div key={k} className="memory-chip">
                  <span className="memory-key">{k}</span>
                  <span className="memory-val">{v}</span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* ── Goal Tracker ── */}
        <div className="dash-card">
          <div className="dash-card-header">
            <Target size={18} className="icon-blue" />
            <h3>Goal Tracker</h3>
          </div>
          <div className="goals-list">
            {goals.length === 0 ? (
              <span className="empty-text">No active goals. Ask JARVIS to set one!</span>
            ) : (
              goals.map((g, i) => (
                <div key={i} className="goal-item">
                  <div className="goal-title-row">
                    <span className="goal-title">{g.title}</span>
                    <span className="goal-status">{g.progress}%</span>
                  </div>
                  <div className="progress-bar-bg">
                    <div className="progress-bar-fill" style={{ width: `${g.progress}%` }} />
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* ── Health & Wellness ── */}
        <div className="dash-card">
          <div className="dash-card-header">
            <HeartPulse size={18} className="icon-green" />
            <h3>Health & Wellness</h3>
          </div>
          <div className="health-logs">
            {health.length === 0 ? (
              <span className="empty-text">No health data. Log your sleep or exercise!</span>
            ) : (
              health.slice(0, 4).map((h, i) => (
                <div key={i} className="health-item">
                  <span className={`health-type badge-${h.log_type.toLowerCase()}`}>
                    {h.log_type.toUpperCase()}
                  </span>
                  <span className="health-val">{h.value}</span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* ── Financial Advisor ── */}
        <div className="dash-card">
          <div className="dash-card-header">
            <DollarSign size={18} className="icon-yellow" />
            <h3>Financial Advisor</h3>
          </div>
          <div className="finance-summary">
            <div className="finance-stat">
              <span className="finance-label">Income</span>
              <span className="finance-val income">${totalIncome.toFixed(2)}</span>
            </div>
            <div className="finance-stat">
              <span className="finance-label">Expenses</span>
              <span className="finance-val expense">${totalExpenses.toFixed(2)}</span>
            </div>
          </div>
          <div className="finance-logs">
            {finance.slice(0, 3).map((f, i) => (
              <div key={i} className="finance-item">
                <span>{f.category}</span>
                <span className={f.log_type === 'expense' ? 'text-expense' : 'text-income'}>
                  {f.log_type === 'expense' ? '-' : '+'}${f.amount.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* ── Creative Partner ── */}
        <div className="dash-card">
          <div className="dash-card-header">
            <Lightbulb size={18} className="icon-orange" />
            <h3>Creative Partner</h3>
          </div>
          <div className="creative-canvas">
            <p className="creative-prompt">
              "Hey JARVIS, let's brainstorm ideas for my new project."
            </p>
            <div className="creative-decoration">
              <div className="creative-orb" />
              <div className="creative-orb-2" />
            </div>
          </div>
        </div>

      </div>
    </div>
  );
};
