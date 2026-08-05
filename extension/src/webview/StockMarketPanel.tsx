import React, { useState } from 'react';
import {
  TrendingUp,
  TrendingDown,
  Activity,
  ShieldAlert,
  BarChart3,
  Search,
  PieChart,
  ChevronRight,
  ChevronLeft,
  Zap,
  Target,
  Layers,
  Award
} from 'lucide-react';

interface StockMarketPanelProps {
  onSelectQuery?: (query: string) => void;
}

interface WatchlistItem {
  ticker: string;
  name: string;
  price: number;
  change: number;
  changePct: number;
  rsi: number;
  dmaSignal: 'above' | 'below';
  signalTag: string;
  volumeMultiplier: number;
}

interface RecommendationItem {
  ticker: string;
  cmp: number;
  entry: string;
  target: number;
  stopLoss: number;
  horizon: string;
  thesis: string;
  signals: {
    tech: string;
    fund: string;
    sent: string;
  };
}

export const StockMarketPanel: React.FC<StockMarketPanelProps> = ({ onSelectQuery }) => {
  const [collapsed, setCollapsed] = useState(false);
  const [activeTab, setActiveTab] = useState<'watchlist' | 'shadow' | 'signals'>('watchlist');
  const [searchQuery, setSearchQuery] = useState('');

  // Sample live market data for Indian primary equities (NSE/BSE)
  const watchlist: WatchlistItem[] = [
    { ticker: 'RELIANCE.NS', name: 'Reliance Industries', price: 3024.50, change: 42.10, changePct: 1.41, rsi: 58.4, dmaSignal: 'above', signalTag: '50/200 DMA Bullish', volumeMultiplier: 1.8 },
    { ticker: 'TCS.NS', name: 'Tata Consultancy', price: 4210.00, change: -25.40, changePct: -0.60, rsi: 44.2, dmaSignal: 'below', signalTag: 'Near 50 DMA Support', volumeMultiplier: 0.9 },
    { ticker: 'INFY.NS', name: 'Infosys Ltd', price: 1845.20, change: 38.60, changePct: 2.14, rsi: 63.1, dmaSignal: 'above', signalTag: 'MACD Bullish Cross', volumeMultiplier: 2.1 },
    { ticker: 'HDFCBANK.NS', name: 'HDFC Bank', price: 1610.80, change: 12.80, changePct: 0.80, rsi: 38.5, dmaSignal: 'above', signalTag: 'Oversold Rebound', volumeMultiplier: 1.4 },
    { ticker: 'SBIN.NS', name: 'State Bank of India', price: 845.00, change: 15.75, changePct: 1.90, rsi: 61.0, dmaSignal: 'above', signalTag: 'Volume Anomaly', volumeMultiplier: 2.4 },
  ];

  // 3-Layer Shortlist Recommendations
  const recommendations: RecommendationItem[] = [
    {
      ticker: 'RELIANCE.NS',
      cmp: 3024.50,
      entry: '₹2,980 – ₹3,010',
      target: 3250,
      stopLoss: 2890,
      horizon: 'Swing (3-6w)',
      thesis: 'Breakout above 50 DMA backed by 1.8x volume spike and strong Q1 retail margin expansion.',
      signals: {
        tech: 'RSI 58.4 | MACD Bullish Crossover | Above 50 & 200 DMA',
        fund: 'Forward P/E 24.1 vs Sector 28.5 | Debt-to-Equity 0.38',
        sent: 'Strong retail revenue growth (+14% YoY) & Green Energy CAPEX tailwinds'
      }
    },
    {
      ticker: 'INFY.NS',
      cmp: 1845.20,
      entry: '₹1,820 – ₹1,840',
      target: 1980,
      stopLoss: 1760,
      horizon: 'Short-term (1-3m)',
      thesis: 'Large deal wins momentum combined with oversold RSI bounce and promoter holding stability.',
      signals: {
        tech: 'RSI 63.1 | Volume 2.1x 20-day avg | 3M Resistance breakout',
        fund: 'YoY Profit Growth +8.7% | High FCF yield & stable 14.8% promoter %',
        sent: 'BFSI sector rebound & multi-year AI cloud deal announcements'
      }
    }
  ];

  const filteredWatchlist = watchlist.filter(w =>
    w.ticker.toLowerCase().includes(searchQuery.toLowerCase()) ||
    w.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleActionClick = (queryText: string) => {
    if (onSelectQuery) {
      onSelectQuery(queryText);
    }
  };

  if (collapsed) {
    return (
      <div className="stock-panel-collapsed">
        <button
          className="stock-panel-toggle-btn collapsed"
          onClick={() => setCollapsed(false)}
          title="Expand Stock Market Intelligence Panel"
        >
          <ChevronLeft size={16} />
          <span className="collapsed-vertical-text">STOCK MARKET INTEL</span>
        </button>
      </div>
    );
  }

  return (
    <aside className="stock-market-panel">
      <div className="stock-panel-header">
        <div 
          className="stock-panel-title-wrap"
          onClick={() => window.open('http://localhost:8765/', '_blank')}
          style={{ cursor: 'pointer' }}
          title="Open JARVIS Trading HUD"
        >
          <BarChart3 className="panel-hdr-icon" size={16} />
          <div>
            <div className="stock-panel-title" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              STOCK MARKET INTEL
              <span style={{ fontSize: '9px', opacity: 0.7, color: 'var(--accent)' }}>↗</span>
            </div>
            <div className="stock-panel-subtitle">NSE / BSE · LIVE 3-LAYER SIGNALS</div>
          </div>
        </div>
      <div className="stock-panel-hdr-right">
          <span className="live-indicator-pill">
            <span className="live-dot" />
            <span className="live-txt">LIVE</span>
          </span>
          <button
            className="stock-panel-toggle-btn"
            onClick={() => setCollapsed(true)}
            title="Collapse Panel"
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </div>

      {/* Shadow Portfolio Summary Banner */}
      <div className="shadow-portfolio-card">
        <div className="sp-card-hdr">
          <span className="sp-card-label">
            <PieChart size={12} style={{ display: 'inline', marginRight: '4px' }} />
            SHADOW PORTFOLIO (PAPER TRADING)
          </span>
          <span className="sp-badge-win">76.5% WIN RATE</span>
        </div>
        <div className="sp-stats-grid">
          <div className="sp-stat-item">
            <div className="sp-stat-val">₹50,000</div>
            <div className="sp-stat-lbl">CAPITAL</div>
          </div>
          <div className="sp-stat-item">
            <div className="sp-stat-val green">+₹3,450</div>
            <div className="sp-stat-lbl">DAY P&L (+6.9%)</div>
          </div>
          <div className="sp-stat-item">
            <div className="sp-stat-val">4</div>
            <div className="sp-stat-lbl">ACTIVE TRADES</div>
          </div>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="stock-panel-tabs">
        <button
          className={`stock-tab-btn ${activeTab === 'watchlist' ? 'active' : ''}`}
          onClick={() => setActiveTab('watchlist')}
        >
          <Activity size={12} />
          <span>WATCHLIST</span>
        </button>
        <button
          className={`stock-tab-btn ${activeTab === 'signals' ? 'active' : ''}`}
          onClick={() => setActiveTab('signals')}
        >
          <Zap size={12} />
          <span>3-LAYER SIGNALS</span>
        </button>
        <button
          className={`stock-tab-btn ${activeTab === 'shadow' ? 'active' : ''}`}
          onClick={() => setActiveTab('shadow')}
        >
          <Award size={12} />
          <span>PORTFOLIO</span>
        </button>
      </div>

      {/* Search Input for Watchlist */}
      {activeTab === 'watchlist' && (
        <div className="stock-search-wrap">
          <Search size={13} className="search-icon" />
          <input
            type="text"
            className="stock-search-input"
            placeholder="Search stocks (e.g. RELIANCE, TCS)..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
      )}

      {/* Main Tab Content */}
      <div className="stock-panel-content">
        {/* Watchlist View */}
        {activeTab === 'watchlist' && (
          <div className="watchlist-container">
            {filteredWatchlist.map((item) => {
              const isUp = item.change >= 0;
              return (
                <div
                  key={item.ticker}
                  className="watchlist-card"
                  onClick={() => handleActionClick(`Analyze ${item.ticker} stock signals and valuation`)}
                  title="Click to query Antigravity for live analysis"
                >
                  <div className="wl-row-top">
                    <div>
                      <span className="wl-ticker">{item.ticker}</span>
                      <span className="wl-name">{item.name}</span>
                    </div>
                    <div className="wl-price-box">
                      <div className="wl-price">₹{item.price.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
                      <div className={`wl-change ${isUp ? 'up' : 'down'}`}>
                        {isUp ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
                        <span>{isUp ? '+' : ''}{item.changePct}%</span>
                      </div>
                    </div>
                  </div>

                  <div className="wl-row-bottom">
                    <span className="wl-signal-badge">{item.signalTag}</span>
                    <span className="wl-rsi">RSI: {item.rsi}</span>
                    <span className="wl-vol">{item.volumeMultiplier}x Vol</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* 3-Layer Signals View */}
        {activeTab === 'signals' && (
          <div className="signals-container">
            <div className="signals-hdr-note">
              <Layers size={12} /> <span>TECH + FUNDAMENTAL + SENTIMENT SCORING</span>
            </div>
            {recommendations.map((rec) => (
              <div key={rec.ticker} className="recommendation-card">
                <div className="rec-card-top">
                  <span className="rec-ticker">{rec.ticker}</span>
                  <span className="rec-horizon">{rec.horizon}</span>
                </div>
                <div className="rec-metrics-grid">
                  <div className="rec-m-item">
                    <span className="rec-m-lbl">CMP</span>
                    <span className="rec-m-val">₹{rec.cmp}</span>
                  </div>
                  <div className="rec-m-item">
                    <span className="rec-m-lbl">ENTRY</span>
                    <span className="rec-m-val cyan">{rec.entry}</span>
                  </div>
                  <div className="rec-m-item">
                    <span className="rec-m-lbl">TARGET</span>
                    <span className="rec-m-val green">₹{rec.target}</span>
                  </div>
                  <div className="rec-m-item">
                    <span className="rec-m-lbl">STOP</span>
                    <span className="rec-m-val red">₹{rec.stopLoss}</span>
                  </div>
                </div>

                <div className="rec-thesis">
                  <strong>Thesis:</strong> {rec.thesis}
                </div>

                <div className="rec-layers-box">
                  <div className="layer-tag tech">
                    <span>TECH:</span> {rec.signals.tech}
                  </div>
                  <div className="layer-tag fund">
                    <span>FUND:</span> {rec.signals.fund}
                  </div>
                  <div className="layer-tag sent">
                    <span>SENT:</span> {rec.signals.sent}
                  </div>
                </div>

                <button
                  className="rec-action-btn"
                  onClick={() => handleActionClick(`When should I buy or sell ${rec.ticker}? Evaluate thesis invalidation.`)}
                >
                  <Target size={12} /> Evaluate Position & Signals
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Shadow Portfolio View */}
        {activeTab === 'shadow' && (
          <div className="shadow-tab-container">
            <div className="shadow-info-box">
              <ShieldAlert size={14} className="shadow-icon" />
              <div>
                <strong>SEBI Risk Compliance:</strong> Data-driven paper trading simulation. Not SEBI-registered financial advice.
              </div>
            </div>

            <div className="active-positions-title">ACTIVE POSITIONS</div>
            <div className="active-position-row">
              <div>
                <div className="ap-ticker">RELIANCE.NS</div>
                <div className="ap-sub">BUY @ ₹2,990.00</div>
              </div>
              <div className="ap-current green">₹3,024.50 (+1.15%)</div>
            </div>
            <div className="active-position-row">
              <div>
                <div className="ap-ticker">INFY.NS</div>
                <div className="ap-sub">BUY @ ₹1,810.00</div>
              </div>
              <div className="ap-current green">₹1,845.20 (+1.94%)</div>
            </div>
            <div className="active-position-row">
              <div>
                <div className="ap-ticker">SBIN.NS</div>
                <div className="ap-sub">BUY @ ₹830.00</div>
              </div>
              <div className="ap-current green">₹845.00 (+1.80%)</div>
            </div>
          </div>
        )}
      </div>

      {/* Quick Action Chips Bar */}
      <div className="stock-quick-actions">
        <div className="qa-title">QUICK INTEL ACTIONS</div>
        <div className="qa-buttons-grid">
          <button
            className="qa-stock-btn"
            onClick={() => handleActionClick('Suggest top 3 Indian stock ideas for ₹30,000 budget with 3-layer scoring')}
          >
            📊 Screen ₹30k Stocks
          </button>
          <button
            className="qa-stock-btn"
            onClick={() => handleActionClick('Show my Shadow Portfolio performance, win rate and hit rate review')}
          >
            📈 Shadow Portfolio Review
          </button>
          <button
            className="qa-stock-btn"
            onClick={() => handleActionClick('Check sector concentration risk and tax-lot implications')}
          >
            ⚠️ Risk & Tax Audit
          </button>
          <button
            className="qa-stock-btn"
            onClick={() => handleActionClick('What is the current NSE/BSE market sentiment and top sector tailwinds?')}
          >
            ⚡ Market Sentiment
          </button>
        </div>
      </div>
    </aside>
  );
};
