import React, { useState, useEffect, useRef, useCallback } from 'react';
import { createRoot } from 'react-dom/client';
import { createPortal } from 'react-dom';
import mermaid from 'mermaid';
import { PersonalDashboard } from './PersonalDashboard';
import { StockMarketPanel } from './StockMarketPanel';
import './index.css';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

type Role = 'user' | 'jarvis' | 'system';
type OrbState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'streaming';
type VoiceMode = 'Calm Male' | 'Energetic Male' | 'Friendly Female' | 'Professional Female';
type AgentMode = 'Default Assistant' | 'Code Debugger' | 'IoT Controller' | 'Autonomous Agent' | 'AR/VR Assistant';

interface Message {
  id: string;
  role: Role;
  content: string;
  timestamp: Date;
  streaming?: boolean;   // true while tokens are still arriving
  agent?: string;        // which agent handled this (for research/executor badge)
}

interface Reminder {
  id: number;
  text: string;
  fire_at: string;
}

interface ToastItem {
  id: string;
  text: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Browser APIs
// ─────────────────────────────────────────────────────────────────────────────

const SpeechRecognition: any =
  (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

// ─────────────────────────────────────────────────────────────────────────────
// Utilities
// ─────────────────────────────────────────────────────────────────────────────

let idCounter = 0;
function genId() { return `m-${++idCounter}`; }

function formatTime(date: Date) {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// Split text into alternating text/code-block/flashcard/mindmap/image/productivity parts
interface ContentPart { type: 'text' | 'code' | 'flashcard' | 'mindmap' | 'image' | 'productivity'; content: string; language?: string; front?: string; back?: string; url?: string; prodType?: string; }

function parseContent(text: string): ContentPart[] {
  const parts: ContentPart[] = [];
  const regex = /(```(\w*)\n?([\s\S]*?)```)|(\[FLASHCARD\]\s*Front:\s*([\s\S]*?)\s*\|\s*Back:\s*([\s\S]*?)\s*\[\/FLASHCARD\])|(\[MINDMAP\]([\s\S]*?)\[\/MINDMAP\])|(\[IMAGE\]([\s\S]*?)\[\/IMAGE\])|(\[(TASK_LIST|EMAIL_DRAFT|DOC_SUMMARY|MEETING_NOTES)\]\n?([\s\S]*?)\[\/\1\])/g;
  let last = 0, m: RegExpExecArray | null;
  while ((m = regex.exec(text)) !== null) {
    if (m.index > last) parts.push({ type: 'text', content: text.slice(last, m.index) });
    
    if (m[1]) {
      parts.push({ type: 'code', language: m[2] || 'code', content: m[3].trim() });
    } else if (m[4]) {
      parts.push({ type: 'flashcard', content: '', front: m[5].trim(), back: m[6].trim() });
    } else if (m[7]) {
      let rawMermaid = m[8].trim();
      rawMermaid = rawMermaid.replace(/^```mermaid\n?/i, '').replace(/```$/i, '').trim();
      parts.push({ type: 'mindmap', content: rawMermaid });
    } else if (m[9]) {
      parts.push({ type: 'image', content: '', url: m[10].trim() });
    } else if (m[11]) {
      parts.push({ type: 'productivity', content: m[13].trim(), prodType: m[12] });
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push({ type: 'text', content: text.slice(last) });
  return parts;
}

// Detect which agent handled a reply (for the badge)
function detectAgent(content: string): string | null {
  if (content.includes('Live web search results') || content.includes('web research')) return 'web';
  if (content.includes('execution report') || content.includes('Code executed')) return 'exec';
  if (content.includes("Home Assistant") || content.includes("thermostat") || content.includes("I've turned")) return 'home';
  if (content.includes("I've set a reminder") || content.includes("reminder")) return 'reminder';
  if (content.includes("[FLASHCARD]") || content.includes("study plan") || content.includes("TUTOR")) return 'tutor';
  if (content.includes("[IMAGE]")) return 'image';
  if (content.includes("[TASK_LIST]") || content.includes("[EMAIL_DRAFT]") || content.includes("[DOC_SUMMARY]") || content.includes("[MEETING_NOTES]")) return 'productivity';
  return null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Icons
// ─────────────────────────────────────────────────────────────────────────────

const Icon = ({ d, size = 18 }: { d: string; size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d={d} />
  </svg>
);

const MicIcon     = () => <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 1a4 4 0 0 1 4 4v7a4 4 0 0 1-8 0V5a4 4 0 0 1 4-4z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>;
const MicOffIcon  = () => <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="1" y1="1" x2="23" y2="23"/><path d="M9 9v3a3 3 0 0 0 5.12 2.12M15 9.34V5a3 3 0 0 0-5.94-.6"/><path d="M17 16.95A7 7 0 0 1 5 12v-2m14 0v2a7 7 0 0 1-.11 1.23"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>;
const VolumeIcon  = () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>;
const MuteIcon    = () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/></svg>;
const SendIcon    = () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>;
const AttachIcon  = () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>;
const BellIcon    = () => <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>;
const ChevronDownIcon = () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="6 9 12 15 18 9"/></svg>;
const CopyIcon    = () => <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>;
const DashboardIcon = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>;

// ─────────────────────────────────────────────────────────────────────────────
// Agent badge
// ─────────────────────────────────────────────────────────────────────────────

const AGENT_BADGES: Record<string, { label: string; color: string }> = {
  web:      { label: '🌐 Web Search', color: '#a855f7' },
  exec:     { label: '⚡ Executed',   color: '#ffc93c' },
  home:     { label: '🏠 Smart Home', color: '#00e5a0' },
  reminder: { label: '🔔 Reminder',   color: '#00c8ff' },
  tutor:    { label: '🎓 Study Tutor', color: '#ff4d4d' },
  image:    { label: '🎨 Image Gen',  color: '#ff66b2' },
  productivity: { label: '💼 Productivity', color: '#ffc93c' },
};

const AgentBadge = ({ type }: { type: string }) => {
  const b = AGENT_BADGES[type];
  if (!b) return null;
  return (
    <span style={{
      display: 'inline-block', padding: '1px 8px', borderRadius: '8px',
      fontSize: '10px', fontWeight: 600, letterSpacing: '0.5px',
      background: `${b.color}18`, border: `1px solid ${b.color}44`,
      color: b.color, marginBottom: '4px',
    }}>
      {b.label}
    </span>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// CodeBlock component
// ─────────────────────────────────────────────────────────────────────────────

const CodeBlock = ({ language, content }: { language: string; content: string }) => {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard?.writeText(content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <div className="code-block">
      <div className="code-header">
        <span className="code-lang">{language || 'code'}</span>
        <button className="code-copy-btn" onClick={copy}>{copied ? '✓ Copied' : 'Copy'}</button>
      </div>
      <pre><code>{content}</code></pre>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Flashcard component
// ─────────────────────────────────────────────────────────────────────────────

const Flashcard = ({ front, back }: { front: string; back: string }) => {
  const [flipped, setFlipped] = useState(false);
  return (
    <div className={`flashcard ${flipped ? 'flipped' : ''}`} onClick={() => setFlipped(!flipped)}>
      <div className="flashcard-inner">
        <div className="flashcard-front">
          <div className="flashcard-label">FRONT</div>
          <div className="flashcard-content">{front}</div>
          <div className="flashcard-hint">Click to flip</div>
        </div>
        <div className="flashcard-back">
          <div className="flashcard-label">BACK</div>
          <div className="flashcard-content">{back}</div>
        </div>
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// MindMap Component
// ─────────────────────────────────────────────────────────────────────────────

mermaid.initialize({ startOnLoad: false, theme: 'dark', suppressErrorRendering: true });

const MindMap = ({ content }: { content: string }) => {
  const [svgContent, setSvgContent] = useState<string>('');
  
  // Pan and Zoom state
  const [scale, setScale] = useState(1);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    if (content) {
      const renderDiagram = async () => {
        try {
          const { svg } = await mermaid.render(`mermaid-${genId()}`, content);
          setSvgContent(svg);
        } catch (e) {
          console.error("Mermaid error:", e);
          setSvgContent(`<div class="mic-error">Failed to render diagram</div><pre>${content}</pre>`);
        }
      };
      renderDiagram();
    }
  }, [content]);

  // Handle Zoom
  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const newScale = Math.min(Math.max(0.3, scale - e.deltaY * 0.002), 5);
    setScale(newScale);
  };

  // Handle Pan
  const handleMouseDown = (e: React.MouseEvent) => {
    setIsDragging(true);
    setDragStart({ x: e.clientX - position.x, y: e.clientY - position.y });
  };
  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging) return;
    setPosition({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y });
  };
  const handleMouseUp = () => setIsDragging(false);

  // Handle Export
  const handleExport = () => {
    if (!svgContent) return;
    const blob = new Blob([svgContent], {type: "image/svg+xml;charset=utf-8"});
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `diagram-${Date.now()}.svg`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const node = (
    <div className={`mindmap-container ${isFullscreen ? 'fullscreen' : ''}`}>
      <div className="mindmap-controls">
        <button className="icon-btn-small" onClick={() => { setScale(1); setPosition({x:0, y:0}); }} title="Reset View">🔄 Reset</button>
        <button className="icon-btn-small" onClick={handleExport} title="Export SVG">💾 Export</button>
        <button className="icon-btn-small" onClick={() => setIsFullscreen(!isFullscreen)} title="Fullscreen">
          {isFullscreen ? '↙ Exit' : '↗ Fullscreen'}
        </button>
      </div>
      <div 
        className="mindmap-viewport"
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        <div 
          className="mindmap-svg-wrapper"
          style={{ transform: `translate(${position.x}px, ${position.y}px) scale(${scale})` }}
          dangerouslySetInnerHTML={{ __html: svgContent }}
        ></div>
      </div>
    </div>
  );

  return isFullscreen ? createPortal(node, document.body) : node;
};

// ─────────────────────────────────────────────────────────────────────────────
// ImageCard Component
// ─────────────────────────────────────────────────────────────────────────────

const ImageCard = ({ url }: { url: string }) => {
  const [loading, setLoading] = useState(true);
  return (
    <div className="image-card-container">
      {loading && <div className="image-loading">Generating Canvas...</div>}
      <img 
        src={url} 
        alt="AI Generated" 
        className={`ai-image ${loading ? 'hidden' : ''}`}
        onLoad={() => setLoading(false)}
      />
      {!loading && (
        <a href={url} target="_blank" rel="noreferrer" className="image-download-btn">
          Full Resolution
        </a>
      )}
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// ProductivityBlock Component
// ─────────────────────────────────────────────────────────────────────────────

const ProductivityBlock = ({ content, prodType }: { content: string; prodType: string }) => {
  let title = 'PRODUCTIVITY';
  let className = 'productivity-block';

  if (prodType === 'TASK_LIST') { title = '📋 TASK MANAGER'; className += ' task-list'; }
  else if (prodType === 'EMAIL_DRAFT') { title = '✉️ EMAIL COMPOSER'; className += ' email-draft'; }
  else if (prodType === 'DOC_SUMMARY') { title = '📄 DOCUMENT ASSISTANT'; className += ' doc-summary'; }
  else if (prodType === 'MEETING_NOTES') { title = '📝 MEETING NOTES'; className += ' meeting-notes'; }

  return (
    <div className={className}>
      <div className="productivity-header">
        {title}
      </div>
      <div className="productivity-content" style={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit' }}>
        {content}
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Streaming cursor
// ─────────────────────────────────────────────────────────────────────────────

const StreamingCursor = () => (
  <span style={{
    display: 'inline-block', width: '2px', height: '1em',
    background: 'var(--accent, #00c8ff)', marginLeft: '2px',
    verticalAlign: 'text-bottom', animation: 'cursorBlink 0.75s step-end infinite',
  }} />
);

// ─────────────────────────────────────────────────────────────────────────────
// MessageBubble component
// ─────────────────────────────────────────────────────────────────────────────

const MessageBubble = ({ msg }: { msg: Message }) => {
  const [copied, setCopied] = useState(false);

  if (msg.role === 'system') {
    return <div className="message system">{msg.content}</div>;
  }

  const parts = msg.role === 'jarvis' ? parseContent(msg.content) : null;
  const agentType = msg.role === 'jarvis' ? detectAgent(msg.content) : null;

  const copyAll = () => {
    navigator.clipboard?.writeText(msg.content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className={`message-wrapper ${msg.role}`}>
      <span className="message-label">
        {msg.role === 'jarvis' ? '▸ ANTIGRAVITY' : '▸ YOU'}
        <span className="message-time">{formatTime(msg.timestamp)}</span>
      </span>
      <div className={`message ${msg.role}`}>
        {agentType && <div><AgentBadge type={agentType} /></div>}
        {parts ? (
          <>
            {parts.map((part, i) =>
              part.type === 'code' ? (
                <CodeBlock key={i} language={part.language!} content={part.content} />
              ) : part.type === 'flashcard' ? (
                <Flashcard key={i} front={part.front!} back={part.back!} />
              ) : part.type === 'mindmap' ? (
                <MindMap key={i} content={part.content} />
              ) : part.type === 'image' ? (
                <ImageCard key={i} url={part.url!} />
              ) : part.type === 'productivity' ? (
                <ProductivityBlock key={i} content={part.content} prodType={part.prodType!} />
              ) : (
                <span key={i} className="msg-text">{part.content.replace(/\[AWAITING_ANSWER\]/g, '')}</span>
              )
            )}
            {msg.streaming && <StreamingCursor />}
          </>
        ) : (
          <>
            <span className="msg-text">{msg.content.replace(/\[AWAITING_ANSWER\]/g, '')}</span>
            {msg.streaming && <StreamingCursor />}
          </>
        )}
        {msg.role === 'jarvis' && !msg.streaming && (
          <button className="copy-btn" onClick={copyAll} title="Copy reply">
            {copied ? '✓' : <CopyIcon />}
          </button>
        )}
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// RemindersPanel component
// ─────────────────────────────────────────────────────────────────────────────

const RemindersPanel = ({ reminders, onClose }: { reminders: Reminder[]; onClose: () => void }) => {
  const fmt = (fireAt: string) => {
    try {
      const d = new Date(fireAt.replace(' ', 'T'));
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch { return fireAt; }
  };
  return (
    <div className="reminders-panel">
      <div className="reminders-header">
        <span className="reminders-title"><BellIcon /> REMINDERS</span>
        <button className="reminders-close" onClick={onClose}>✕</button>
      </div>
      {reminders.length === 0 ? (
        <div className="reminders-empty">No upcoming reminders, Jay.</div>
      ) : (
        <ul className="reminders-list">
          {reminders.map(r => (
            <li key={r.id} className="reminder-item">
              <span className="reminder-time">{fmt(r.fire_at)}</span>
              <span className="reminder-text">{r.text}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Toast container
// ─────────────────────────────────────────────────────────────────────────────

const ToastContainer = ({ toasts }: { toasts: ToastItem[] }) => (
  <div className="toast-container">
    {toasts.map(t => (
      <div key={t.id} className="toast">
        <BellIcon /> <span>{t.text}</span>
      </div>
    ))}
  </div>
);

// ─────────────────────────────────────────────────────────────────────────────
// Voice Selector (Glassmorphic)
// ─────────────────────────────────────────────────────────────────────────────
let currentPreviewAudio: any = null;
let globalAudioCtx: AudioContext | null = null;

const VOICE_KEYS: Record<string, string> = {
  "Calm Male":          "calm_male",
  "Energetic Male":     "energetic_male",
  "Friendly Female":    "friendly_female",
  "Professional Female":"professional_female",
};

const VoiceSelector = ({ value, onChange }: { value: VoiceMode, onChange: (v: VoiceMode) => void }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const playVoicePreview = async (voiceDisplayName: string) => {
    const voiceKey = VOICE_KEYS[voiceDisplayName] || "calm_male";

    // Use Web Audio API and initialize synchronously to bypass autoplay and CSP restrictions
    if (!globalAudioCtx) {
      globalAudioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
    }
    if (globalAudioCtx.state === 'suspended') {
      globalAudioCtx.resume();
    }
    
    if (currentPreviewAudio) {
      if (currentPreviewAudio.stop) {
        try { currentPreviewAudio.stop(); } catch (e) {}
      } else if (currentPreviewAudio.pause) {
        currentPreviewAudio.pause();
      }
      currentPreviewAudio = null;
    }

    setIsPreviewing(true);

    try {
      let baseUrl = 'http://127.0.0.1:8000';
      if (window.location.protocol === 'http:' || window.location.protocol === 'https:') {
        baseUrl = `${window.location.protocol}//${window.location.host}`;
      }
      const response = await fetch(`${baseUrl}/api/voice/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ voice: voiceKey })
      });

      if (!response.ok) throw new Error(`Preview failed: ${response.status}`);

      const arrayBuffer = await response.arrayBuffer();
      
      const audioBuffer = await globalAudioCtx!.decodeAudioData(arrayBuffer);
      const source = globalAudioCtx!.createBufferSource();
      
      source.buffer = audioBuffer;
      source.connect(globalAudioCtx!.destination);
      
      source.onended = () => {
        setIsPreviewing(false);
      };
      
      // Store the source so it can be stopped if another voice is clicked
      (currentPreviewAudio as any) = source;
      source.start(0);

    } catch (err) {      setIsPreviewing(false);
      console.error("Voice preview error:", err);
    }
  };

  const handleSelect = (opt: VoiceMode) => {
    onChange(opt);
    setIsOpen(false);
    playVoicePreview(opt);
    localStorage.setItem("jarvis_voice", opt);
  };

  const options: VoiceMode[] = ['Calm Male', 'Energetic Male', 'Friendly Female', 'Professional Female'];

  return (
    <div ref={dropdownRef} className="voice-selector-container">
      <button 
        id="jay-voice-btn"
        className={`voice-selector-btn ${isOpen ? 'open' : ''}`}
        onClick={() => setIsOpen(!isOpen)}
        style={{ opacity: isPreviewing ? 0.7 : 1 }}
      >
        {isPreviewing ? `▶ ${value}...` : `🗣 ${value}`} <ChevronDownIcon />
      </button>

      {isOpen && (
        <div id="jay-voice-menu" className="voice-selector-menu">
          {options.map((opt) => (
            <div
              key={opt}
              role="button"
              className={`voice-selector-option ${value === opt ? 'selected' : ''}`}
              onClick={() => handleSelect(opt)}
            >
              {opt}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Agent Mode Selector (Glassmorphic)
// ─────────────────────────────────────────────────────────────────────────────

const AgentModeSelector = ({ value, onChange }: { value: AgentMode, onChange: (v: AgentMode) => void }) => {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const handleSelect = (opt: AgentMode) => {
    onChange(opt);
    setIsOpen(false);
    localStorage.setItem("jarvis_agent_mode", opt);
  };

  const options: AgentMode[] = ['Default Assistant', 'Code Debugger', 'IoT Controller', 'Autonomous Agent', 'AR/VR Assistant'];

  return (
    <div ref={dropdownRef} className="voice-selector-container" style={{ marginLeft: '10px' }}>
      <button 
        className={`voice-selector-btn ${isOpen ? 'open' : ''}`}
        onClick={() => setIsOpen(!isOpen)}
      >
        🧠 {value} <ChevronDownIcon />
      </button>

      {isOpen && (
        <div className="voice-selector-menu">
          {options.map((opt) => (
            <div
              key={opt}
              role="button"
              className={`voice-selector-option ${value === opt ? 'selected' : ''}`}
              onClick={() => handleSelect(opt)}
            >
              {opt}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Main App
// ─────────────────────────────────────────────────────────────────────────────

const App = () => {
  // ── State ────────────────────────────────────────────────────────────────
  const [messages, setMessages]           = useState<Message[]>([]);
  const [input, setInput]                 = useState('');
  const [connected, setConnected]         = useState(false);
  const [orbState, setOrbState]           = useState<OrbState>('idle');
  const [voiceMode, setVoiceMode]         = useState<VoiceMode>(() => (localStorage.getItem("jarvis_voice") as VoiceMode) || 'Calm Male');
  const [agentMode, setAgentMode]         = useState<AgentMode>(() => (localStorage.getItem("jarvis_agent_mode") as AgentMode) || 'Default Assistant');
  const [isThinking, setIsThinking]       = useState(false);
  const [isStreaming, setIsStreaming]      = useState(false);
  const [isListening, setIsListening]     = useState(false);
  const [alwaysOn, setAlwaysOn]           = useState(false);
  const [isMuted, setIsMuted]             = useState(false);
  const [transcript, setTranscript]       = useState('');
  const [micError, setMicError]           = useState('');
  const [attachedFile, setAttachedFile]   = useState<{ name: string; content: string } | null>(null);
  const [reminders, setReminders]         = useState<Reminder[]>([]);
  const [showReminders, setShowReminders] = useState(false);
  const [toasts, setToasts]               = useState<ToastItem[]>([]);
  const [showScrollBtn, setShowScrollBtn] = useState(false);
  const [autostart, setAutostart]         = useState(false);
  const [viewMode, setViewMode]           = useState<'chat' | 'personal'>('chat');

  // ── Refs ─────────────────────────────────────────────────────────────────
  const wsRef             = useRef<WebSocket | null>(null);
  const chatRef           = useRef<HTMLDivElement>(null);
  const chatEndRef        = useRef<HTMLDivElement>(null);
  const commandRecRef     = useRef<any>(null);
  const wakeRecRef        = useRef<any>(null);
  const fileInputRef      = useRef<HTMLInputElement>(null);
  const isMutedRef        = useRef(false);
  const alwaysOnRef       = useRef(false);
  const voiceModeRef      = useRef<VoiceMode>('Calm Male');
  const agentModeRef      = useRef<AgentMode>('Default Assistant');
  const streamingMsgIdRef = useRef<string | null>(null);
  isMutedRef.current      = isMuted;
  alwaysOnRef.current     = alwaysOn;
  voiceModeRef.current    = voiceMode;
  agentModeRef.current    = agentMode;

  // ── Toast helper ─────────────────────────────────────────────────────────
  const addToast = useCallback((text: string) => {
    const id = genId();
    setToasts(prev => [...prev, { id, text }]);
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 5000);
  }, []);

  // ── Auto scroll ──────────────────────────────────────────────────────────
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isThinking, isStreaming]);

  // ── Scroll-to-bottom button visibility ──────────────────────────────────
  useEffect(() => {
    const el = chatRef.current;
    if (!el) return;
    const onScroll = () => {
      setShowScrollBtn(el.scrollHeight - el.scrollTop - el.clientHeight > 120);
    };
    el.addEventListener('scroll', onScroll);
    return () => el.removeEventListener('scroll', onScroll);
  }, []);

  // ── Text to Speech ───────────────────────────────────────────────────────
  const speakText = useCallback(async (text: string) => {
    const clean = text
      .replace(/```[\s\S]*?```/g, ' [code block] ')
      .replace(/`[^`]+`/g, '').replace(/\*\*/g, '').replace(/\*/g, '')
      .replace(/#+\s/g, '').trim();
      
    if (!clean) return;

    if (currentPreviewAudio) {
      if (currentPreviewAudio.stop) {
        try { currentPreviewAudio.stop(); } catch (e) {}
      } else if (currentPreviewAudio.pause) {
        currentPreviewAudio.pause();
      }
      currentPreviewAudio = null;
    }

    if (!globalAudioCtx) {
      globalAudioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
    }
    if (globalAudioCtx.state === 'suspended') {
      globalAudioCtx.resume();
    }

    setOrbState('speaking');

    try {
      let baseUrl = 'http://127.0.0.1:8000';
      if (window.location.protocol === 'http:' || window.location.protocol === 'https:') {
        baseUrl = `${window.location.protocol}//${window.location.host}`;
      }
      
      const voiceKey = VOICE_KEYS[voiceModeRef.current] || "calm_male";
      
      const response = await fetch(`${baseUrl}/api/voice/speak`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ voice: voiceKey, text: clean })
      });

      if (!response.ok) throw new Error(`Speech failed: ${response.status}`);

      const arrayBuffer = await response.arrayBuffer();
      const audioBuffer = await globalAudioCtx!.decodeAudioData(arrayBuffer);
      const source = globalAudioCtx!.createBufferSource();
      
      source.buffer = audioBuffer;
      source.connect(globalAudioCtx!.destination);
      
      source.onended = () => {
        setOrbState('idle');
      };
      
      (currentPreviewAudio as any) = source;
      source.start(0);

    } catch (err) {
      setOrbState('idle');
      console.error("Speech error:", err);
      // Fallback to basic synth if backend fails
      const fallback = new SpeechSynthesisUtterance(clean);
      fallback.onend = () => setOrbState('idle');
      window.speechSynthesis?.speak(fallback);
    }
  }, []);

  // ── WebSocket ────────────────────────────────────────────────────────────
  useEffect(() => {
    const connect = () => {
      let wsUrl = 'ws://127.0.0.1:8000/ws';
      if (window.location.protocol === 'http:' || window.location.protocol === 'https:') {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        wsUrl = `${protocol}//${window.location.host}/ws`;
      }
      const ws = new WebSocket(wsUrl);
      ws.onopen = () => {
        setConnected(true);
        setOrbState('idle');
        ws.send(JSON.stringify({ type: 'get_history' }));
      };

      ws.onmessage = ({ data }) => {
        try {
          const msg = JSON.parse(data);

          // ── Thinking (pre-stream acknowledgement) ──────────────────────
          if (msg.type === 'thinking') {
            setIsThinking(true);
            setOrbState('thinking');

          // ── Token (streaming chunk) ────────────────────────────────────
          } else if (msg.type === 'token') {
            setIsThinking(false);
            setIsStreaming(true);
            setOrbState('streaming');

            setMessages(prev => {
              const sid = streamingMsgIdRef.current;
              if (sid) {
                // Append token to existing streaming bubble
                return prev.map(m =>
                  m.id === sid
                    ? { ...m, content: m.content + (msg.text || ''), streaming: true }
                    : m
                );
              } else {
                // Create new streaming bubble
                const newId = genId();
                streamingMsgIdRef.current = newId;
                return [...prev, {
                  id: newId,
                  role: 'jarvis',
                  content: msg.text || '',
                  timestamp: new Date(),
                  streaming: true,
                }];
              }
            });

          // ── Done (streaming complete) ──────────────────────────────────
          } else if (msg.type === 'done') {
            setIsStreaming(false);
            setOrbState('idle');

            const sid = streamingMsgIdRef.current;
            streamingMsgIdRef.current = null;

            if (sid) {
              // Finalise the streaming bubble
              setMessages(prev =>
                prev.map(m =>
                  m.id === sid
                    ? { ...m, content: msg.text || m.content, streaming: false }
                    : m
                )
              );
            } else {
              // Fallback: no tokens were received — show full reply
              if (msg.text) {
                setMessages(prev => [...prev, {
                  id: genId(), role: 'jarvis',
                  content: msg.text, timestamp: new Date(), streaming: false,
                }]);
              }
            }

            const fullText = msg.text || '';
            const shouldAutoListen = fullText.includes('[AWAITING_ANSWER]');
            const cleanText = fullText.replace(/\[AWAITING_ANSWER\]/g, '');
            
            if (!isMutedRef.current && cleanText) speakText(cleanText);
            else setOrbState('idle');
            
            if (shouldAutoListen) {
              setTimeout(() => {
                const btn = document.getElementById('jarvis-mic-btn');
                if (btn) btn.click();
              }, 1500); // Wait a moment for speech to begin or UI to settle
            } else if (alwaysOnRef.current) {
              setTimeout(() => startWakeWord(), 1500);
            }

          // ── System message ─────────────────────────────────────────────
          } else if (msg.type === 'system') {
            setIsThinking(false); setIsStreaming(false);
            setMessages(prev => [...prev, {
              id: genId(), role: 'system',
              content: msg.text, timestamp: new Date(),
            }]);
            setOrbState('idle');

          // ── Error ──────────────────────────────────────────────────────
          } else if (msg.type === 'error') {
            setIsThinking(false); setIsStreaming(false);
            streamingMsgIdRef.current = null;
            setOrbState('idle');

          // ── Reminder alert ─────────────────────────────────────────────
          } else if (msg.type === 'reminder') {
            addToast(msg.text);
            if (!isMutedRef.current) speakText(msg.text);
            wsRef.current?.send(JSON.stringify({ type: 'get_reminders' }));

          // ── Reminders list ─────────────────────────────────────────────
          } else if (msg.type === 'reminders_list') {
            setReminders(msg.reminders || []);
          // ── History list ───────────────────────────────────────────────
          } else if (msg.type === 'history_list') {
            const loaded = (msg.messages || []).map((m: any) => ({
              id: genId(),
              role: m.role,
              content: m.content,
              timestamp: new Date(m.timestamp),
            }));
            setMessages(loaded);
          }
        } catch { /* ignore parse errors */ }
      };

      ws.onclose = () => {
        setConnected(false); setOrbState('idle');
        setIsStreaming(false); setIsThinking(false);
        streamingMsgIdRef.current = null;
        setTimeout(connect, 3000);
      };
      ws.onerror = () => {};
      wsRef.current = ws;
    };
    connect();
    return () => wsRef.current?.close();
  }, [speakText, addToast]);

  // ── Send message ─────────────────────────────────────────────────────────
  const send = useCallback((overrideText?: string) => {
    const text = (overrideText ?? input).trim();
    if (!text || wsRef.current?.readyState !== WebSocket.OPEN) return;
    if (isStreaming) return; // don't allow send while streaming
    const file = attachedFile;
    const displayContent = file ? `${text}  [📎 ${file.name}]` : text;
    setMessages(prev => [...prev, {
      id: genId(), role: 'user',
      content: displayContent, timestamp: new Date(),
    }]);
    const payload: Record<string, string> = { 
      type: 'chat', 
      text,
      voice_mode: voiceModeRef.current.replace(' ', '_').toLowerCase(),
      agent_mode: agentModeRef.current
    };
    if (file) { payload.fileContent = file.content; payload.fileName = file.name; }
    wsRef.current!.send(JSON.stringify(payload));
    setInput('');
    setTranscript('');
    setAttachedFile(null);
    streamingMsgIdRef.current = null;
  }, [input, attachedFile, isStreaming]);

  // ── Clear history ────────────────────────────────────────────────────────
  const clearHistory = () => {
    setMessages([]);
    wsRef.current?.send(JSON.stringify({ type: 'clear_history' }));
    window.speechSynthesis?.cancel();
    setOrbState('idle');
    streamingMsgIdRef.current = null;
  };

  // ── Command microphone ───────────────────────────────────────────────────
  const startCommandRec = useCallback((autoSend = false) => {
    if (!SpeechRecognition) { setMicError('Voice not supported. Use Chrome or Edge.'); return; }
    try { commandRecRef.current?.stop(); } catch {}

    const rec = new SpeechRecognition();
    rec.continuous = false; rec.interimResults = true; rec.lang = 'en-US';
    rec.onstart = () => { setIsListening(true); setOrbState('listening'); };
    rec.onresult = (e: any) => {
      if (commandRecRef.current !== rec) return;
      let interim = '', final = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) {
          final += t;
        } else {
          interim += t;
        }
      }
      setTranscript(final || interim);
      if (final) {
        setInput(final);
        commandRecRef.current = null;
        try { rec.stop(); } catch {}
        if (autoSend) setTimeout(() => send(final), 300);
      }
    };
    rec.onerror = (e: any) => {
      if (commandRecRef.current === rec) {
        setMicError(`Mic error: ${e.error}`);
        setIsListening(false);
        setOrbState('idle');
      }
    };
    rec.onend = () => {
      if (commandRecRef.current === rec) {
        setIsListening(false);
        setOrbState('idle');
      }
    };
    commandRecRef.current = rec;
    try { rec.start(); } catch {}
  }, [send]);

  const toggleMic = useCallback(() => {
    setMicError('');
    if (isListening) {
      const activeRec = commandRecRef.current;
      commandRecRef.current = null;
      try { activeRec?.stop(); } catch {}
      setIsListening(false);
      setOrbState('idle');
      setTranscript('');
    } else {
      startCommandRec(false);
    }
  }, [isListening, startCommandRec]);

  // ── Wake word "Hey JARVIS" ───────────────────────────────────────────────
  const startWakeWord = useCallback(() => {
    if (!SpeechRecognition || !alwaysOnRef.current) return;
    try { wakeRecRef.current?.stop(); } catch {}

    const rec = new SpeechRecognition();
    rec.continuous = true; rec.interimResults = true; rec.lang = 'en-US';
    rec.onresult = (e: any) => {
      if (wakeRecRef.current !== rec) return;
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const text = e.results[i][0].transcript.toLowerCase().trim();
        const wakeWords = [
          'antigravity', 'anti gravity', 'anti-gravity', 'antugravity', 'auntie gravity', 'andy gravity',
          'assistant', 'jarvis', 'darvis', 'travis', 'garvis'
        ];
        if (wakeWords.some(w => text.includes(w))) {
          wakeRecRef.current = null;
          try { rec.stop(); } catch {}
          if (!isMutedRef.current) speakText("Yes, Jay?");
          setTimeout(() => startCommandRec(true), 1300);
          return;
        }
      }
    };
    rec.onerror = () => {
      if (wakeRecRef.current === rec && alwaysOnRef.current) {
        setTimeout(startWakeWord, 2000);
      }
    };
    rec.onend = () => {
      if (wakeRecRef.current === rec && alwaysOnRef.current) {
        setTimeout(startWakeWord, 500);
      }
    };
    wakeRecRef.current = rec;
    try { rec.start(); } catch {}
  }, [speakText, startCommandRec]);

  const toggleAlwaysOn = useCallback(() => {
    setAlwaysOn(prev => {
      const next = !prev;
      if (next) {
        setTimeout(startWakeWord, 200);
        addToast('Wake word enabled — say "Hey Antigravity"');
      } else {
        try { wakeRecRef.current?.stop(); } catch {}
        wakeRecRef.current = null;
        addToast('Wake word disabled');
      }
      return next;
    });
  }, [startWakeWord, addToast]);

  // ── File attach ──────────────────────────────────────────────────────────
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 50 * 1024) {
      setMicError(`File too large (max 50 KB). Yours: ${(file.size / 1024).toFixed(1)} KB`);
      e.target.value = ''; return;
    }
    const reader = new FileReader();
    reader.onload = ev => setAttachedFile({ name: file.name, content: ev.target?.result as string });
    reader.readAsText(file);
    e.target.value = '';
  };

  // ── Mute toggle ──────────────────────────────────────────────────────────
  const toggleMute = () => {
    if (!isMuted) {
      window.speechSynthesis?.cancel();
      if (currentPreviewAudio) {
        if (currentPreviewAudio.stop) {
          try { currentPreviewAudio.stop(); } catch (e) {}
        } else if (currentPreviewAudio.pause) {
          currentPreviewAudio.pause();
        }
        currentPreviewAudio = null;
      }
    }
    setIsMuted(m => !m);
    if (orbState === 'speaking') setOrbState('idle');
  };

  // ── Reminders panel ──────────────────────────────────────────────────────
  const toggleReminders = () => {
    const next = !showReminders;
    setShowReminders(next);
    if (next && wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'get_reminders' }));
    }
  };

  // ── Autostart toggle ──────────────────────────────────────────────────────
  useEffect(() => {
    const fetchAutostart = async () => {
      try {
        const res = await fetch('http://127.0.0.1:8000/api/autostart');
        const data = await res.json();
        setAutostart(data.enabled);
      } catch (e) {
        // ignore
      }
    };
    fetchAutostart();
  }, []);

  const toggleAutostart = async () => {
    try {
      const res = await fetch('http://127.0.0.1:8000/api/autostart', { method: 'POST' });
      const data = await res.json();
      setAutostart(data.enabled);
      addToast(data.enabled ? 'Run on startup enabled' : 'Run on startup disabled');
    } catch (e) {
      addToast('Failed to toggle autostart');
    }
  };

  // ── Orb label ─────────────────────────────────────────────────────────────
  const orbLabel = {
    idle:      connected ? (alwaysOn ? 'WAKE MODE' : 'STANDBY') : 'OFFLINE',
    listening: 'LISTENING',
    thinking:  'PROCESSING',
    speaking:  'SPEAKING',
    streaming: 'STREAMING',
  }[orbState];

  // ─────────────────────────────────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div className="app-container">

      {/* ── Header ── */}
      <header className="jarvis-header">
        <div className="header-brand">
          <div className="jarvis-title">A.N.T.I.G.R.A.V.I.T.Y</div>
          <div className="jarvis-subtitle">Jay's Personal AI Assistant</div>
        </div>
        <div className="header-controls">
          {/* Voice Mode Selector (Custom Glassmorphic) */}
          <VoiceSelector value={voiceMode} onChange={setVoiceMode} />
          {/* Agent Mode Selector */}
          <AgentModeSelector value={agentMode} onChange={setAgentMode} />
          {/* Dashboard link */}
          <a
            href={
              (window.location.protocol === 'http:' || window.location.protocol === 'https:')
                ? '/dashboard'
                : 'http://127.0.0.1:8000/dashboard'
            }
            target="_blank"
            rel="noopener noreferrer"
            className="wake-btn"
            title="Open live system dashboard"
            style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '5px' }}
          >
            <DashboardIcon /> SYSTEM
          </a>
          <button
            className={`wake-btn ${viewMode === 'personal' ? 'active' : ''}`}
            onClick={() => setViewMode(v => v === 'chat' ? 'personal' : 'chat')}
            title="Toggle Personal AI Capabilities"
            style={{ display: 'flex', alignItems: 'center', gap: '5px' }}
          >
            <DashboardIcon /> {viewMode === 'personal' ? 'CHAT' : 'PERSONAL AI'}
          </button>
          {/* Wake word toggle */}
          <button
            className={`wake-btn ${alwaysOn ? 'active' : ''}`}
            onClick={toggleAlwaysOn}
            title={alwaysOn ? 'Disable wake word' : 'Enable — say "Hey Antigravity"'}
          >
            {alwaysOn ? '🎙 WAKE ON' : '🔇 WAKE'}
          </button>
          {/* Autostart toggle */}
          <button
            className={`wake-btn ${autostart ? 'active' : ''}`}
            onClick={toggleAutostart}
            title={autostart ? 'Disable run on startup' : 'Enable run on startup'}
          >
            {autostart ? '🚀 AUTOSTART ON' : '🚀 AUTOSTART OFF'}
          </button>
          {/* Reminders bell */}
          <button className="bell-btn" onClick={toggleReminders} title="View reminders">
            <BellIcon />
            {reminders.length > 0 && <span className="bell-badge">{reminders.length}</span>}
          </button>
          {/* Status */}
          <div className="status-pill">
            <span className={`status-dot ${connected ? 'online' : 'offline'}`} />
            <span className="status-text">{connected ? 'ONLINE' : 'OFFLINE'}</span>
          </div>
          <button className="clear-btn" onClick={clearHistory}>CLEAR</button>
        </div>
      </header>

      {/* ── Reminders panel ── */}
      {showReminders && (
        <RemindersPanel reminders={reminders} onClose={() => setShowReminders(false)} />
      )}

      {viewMode === 'personal' ? (
        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <PersonalDashboard />
        </div>
      ) : (
        <div className="main-workspace-layout">
          <div className="center-workspace">
            {/* ── Arc Reactor Orb ── */}
            <div className="orb-container">
              <div className="orb-wrapper">
                <div className="orb-ring" />
                <div className="orb-ring orb-ring-mid" />
                <div className="orb-ring orb-ring-inner" />
                <div className={`orb ${orbState}`} />
                <div className={`orb-label ${orbState !== 'idle' ? orbState : ''}`}>{orbLabel}</div>
              </div>
            </div>

            {/* ── Chat ── */}
            <div className="chat-container" ref={chatRef}>
              {messages.length === 0 && !isThinking && !isStreaming && (
                <div className="empty-state">
                  <div className="empty-icon">⬡</div>
                  <p className="empty-greeting">Good day, Jay. How may I assist you?</p>
                  <p className="empty-hint">
                    Type · 🎙 Speak · Say "Hey Antigravity" · Attach 📎 a file<br/>
                    <span style={{ color: 'var(--accent, #00c8ff)', fontSize: '11px' }}>
                      🌐 Web Search · 🏠 Smart Home · ⚡ Execute Code · 🧠 Semantic Memory · 📈 Stock Market
                    </span>
                  </p>
                </div>
              )}

              {messages.map(m => <MessageBubble key={m.id} msg={m} />)}

              {isThinking && !isStreaming && (
                <div className="thinking-wrapper">
                  <span className="thinking-label">▸ ANTIGRAVITY · PROCESSING</span>
                  <div className="thinking-dots"><span /><span /><span /></div>
                </div>
              )}

              <div ref={chatEndRef} />
            </div>

            {/* ── Scroll to bottom ── */}
            {showScrollBtn && (
              <button
                className="scroll-btn"
                onClick={() => chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })}
                title="Scroll to bottom"
              >
                <ChevronDownIcon />
              </button>
            )}

            {/* ── Input area ── */}
            <div className="input-area">
              {attachedFile && (
                <div className="file-chip">
                  📎 <span>{attachedFile.name}</span>
                  <button onClick={() => setAttachedFile(null)} title="Remove file">✕</button>
                </div>
              )}
              {transcript && <div className="transcript-preview">🎙 {transcript}</div>}
              {micError && <div className="mic-error">{micError}</div>}

              <div className="input-container">
                {/* Mic */}
                <button
                  id="jarvis-mic-btn"
                  className={`btn btn-mic ${isListening ? 'listening' : ''}`}
                  onClick={toggleMic}
                  title={isListening ? 'Stop listening' : 'Voice input'}
                  disabled={isStreaming}
                >
                  {isListening ? <MicOffIcon /> : <MicIcon />}
                </button>

                {/* Attach */}
                <button
                  id="jarvis-attach-btn"
                  className="btn btn-attach"
                  onClick={() => fileInputRef.current?.click()}
                  title="Attach a file"
                  disabled={isStreaming}
                >
                  <AttachIcon />
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  style={{ display: 'none' }}
                  accept=".txt,.py,.js,.ts,.tsx,.md,.json,.csv,.html,.css,.xml,.yaml,.yml,.java,.cpp,.c,.go,.rs,.rb,.php,.sh"
                  onChange={handleFileChange}
                />

                {/* Text input */}
                <input
                  id="jarvis-text-input"
                  className="text-input"
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && !e.shiftKey && send()}
                  placeholder={
                    !connected    ? 'Connecting to backend…'  :
                    isStreaming   ? 'Antigravity is responding…'    :
                    isListening   ? 'Listening…'               :
                                    'Ask Antigravity anything…'
                  }
                  disabled={!connected || isListening || isStreaming}
                />

                {/* Mute */}
                <button
                  id="jarvis-mute-btn"
                  className={`btn btn-mute ${isMuted ? 'muted' : ''}`}
                  onClick={toggleMute}
                  title={isMuted ? 'Unmute Antigravity' : 'Mute Antigravity voice'}
                >
                  {isMuted ? <MuteIcon /> : <VolumeIcon />}
                </button>

                {/* Send */}
                <button
                  id="jarvis-send-btn"
                  className="btn btn-send"
                  onClick={() => send()}
                  disabled={!connected || !input.trim() || isThinking || isStreaming}
                >
                  <SendIcon /> <span className="send-label">SEND</span>
                </button>
              </div>
            </div>
          </div>

          {/* ── Stock Market Right Panel ── */}
          <StockMarketPanel onSelectQuery={(queryText) => {
            setInput(queryText);
          }} />
        </div>
      )}

      {/* ── Toasts ── */}
      <ToastContainer toasts={toasts} />
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Mount
// ─────────────────────────────────────────────────────────────────────────────

const rootElement = document.getElementById('root');
if (rootElement) createRoot(rootElement).render(<App />);