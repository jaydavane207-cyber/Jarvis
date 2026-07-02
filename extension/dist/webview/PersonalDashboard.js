"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.PersonalDashboard = void 0;
const jsx_runtime_1 = require("react/jsx-runtime");
const react_1 = require("react");
const lucide_react_1 = require("lucide-react");
const PersonalDashboard = () => {
    const [data, setData] = (0, react_1.useState)(null);
    const [loading, setLoading] = (0, react_1.useState)(true);
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
        }
        catch (err) {
            console.error('Failed to fetch personal data:', err);
        }
        finally {
            setLoading(false);
        }
    };
    (0, react_1.useEffect)(() => {
        fetchData();
    }, []);
    if (loading && !data) {
        return ((0, jsx_runtime_1.jsxs)("div", { className: "personal-dashboard loading-state", children: [(0, jsx_runtime_1.jsxs)("div", { className: "thinking-dots", children: [(0, jsx_runtime_1.jsx)("span", {}), (0, jsx_runtime_1.jsx)("span", {}), (0, jsx_runtime_1.jsx)("span", {})] }), (0, jsx_runtime_1.jsx)("p", { children: "Loading Personal AI Profile..." })] }));
    }
    const { goals = [], health = [], finance = [], memory = {} } = data || {};
    // Calculate some basic finance metrics
    const totalExpenses = finance
        .filter((f) => f.log_type === 'expense')
        .reduce((acc, curr) => acc + curr.amount, 0);
    const totalIncome = finance
        .filter((f) => f.log_type === 'income')
        .reduce((acc, curr) => acc + curr.amount, 0);
    return ((0, jsx_runtime_1.jsxs)("div", { className: "personal-dashboard fade-in", children: [(0, jsx_runtime_1.jsxs)("div", { className: "dashboard-header", children: [(0, jsx_runtime_1.jsx)("h2", { children: "Your Personal AI Profile" }), (0, jsx_runtime_1.jsx)("button", { onClick: fetchData, className: "refresh-btn", title: "Refresh Data", children: (0, jsx_runtime_1.jsx)(lucide_react_1.RefreshCw, { size: 16 }) })] }), (0, jsx_runtime_1.jsxs)("div", { className: "dashboard-grid", children: [(0, jsx_runtime_1.jsxs)("div", { className: "dash-card span-full", children: [(0, jsx_runtime_1.jsxs)("div", { className: "dash-card-header", children: [(0, jsx_runtime_1.jsx)(lucide_react_1.Brain, { size: 18, className: "icon-purple" }), (0, jsx_runtime_1.jsx)("h3", { children: "Memory & Context" })] }), (0, jsx_runtime_1.jsx)("div", { className: "memory-chips", children: Object.keys(memory).length === 0 ? ((0, jsx_runtime_1.jsx)("span", { className: "empty-text", children: "No preferences learned yet." })) : (Object.entries(memory).map(([k, v]) => ((0, jsx_runtime_1.jsxs)("div", { className: "memory-chip", children: [(0, jsx_runtime_1.jsx)("span", { className: "memory-key", children: k }), (0, jsx_runtime_1.jsx)("span", { className: "memory-val", children: v })] }, k)))) })] }), (0, jsx_runtime_1.jsxs)("div", { className: "dash-card", children: [(0, jsx_runtime_1.jsxs)("div", { className: "dash-card-header", children: [(0, jsx_runtime_1.jsx)(lucide_react_1.Target, { size: 18, className: "icon-blue" }), (0, jsx_runtime_1.jsx)("h3", { children: "Goal Tracker" })] }), (0, jsx_runtime_1.jsx)("div", { className: "goals-list", children: goals.length === 0 ? ((0, jsx_runtime_1.jsx)("span", { className: "empty-text", children: "No active goals. Ask JARVIS to set one!" })) : (goals.map((g, i) => ((0, jsx_runtime_1.jsxs)("div", { className: "goal-item", children: [(0, jsx_runtime_1.jsxs)("div", { className: "goal-title-row", children: [(0, jsx_runtime_1.jsx)("span", { className: "goal-title", children: g.title }), (0, jsx_runtime_1.jsxs)("span", { className: "goal-status", children: [g.progress, "%"] })] }), (0, jsx_runtime_1.jsx)("div", { className: "progress-bar-bg", children: (0, jsx_runtime_1.jsx)("div", { className: "progress-bar-fill", style: { width: `${g.progress}%` } }) })] }, i)))) })] }), (0, jsx_runtime_1.jsxs)("div", { className: "dash-card", children: [(0, jsx_runtime_1.jsxs)("div", { className: "dash-card-header", children: [(0, jsx_runtime_1.jsx)(lucide_react_1.HeartPulse, { size: 18, className: "icon-green" }), (0, jsx_runtime_1.jsx)("h3", { children: "Health & Wellness" })] }), (0, jsx_runtime_1.jsx)("div", { className: "health-logs", children: health.length === 0 ? ((0, jsx_runtime_1.jsx)("span", { className: "empty-text", children: "No health data. Log your sleep or exercise!" })) : (health.slice(0, 4).map((h, i) => ((0, jsx_runtime_1.jsxs)("div", { className: "health-item", children: [(0, jsx_runtime_1.jsx)("span", { className: `health-type badge-${h.log_type.toLowerCase()}`, children: h.log_type.toUpperCase() }), (0, jsx_runtime_1.jsx)("span", { className: "health-val", children: h.value })] }, i)))) })] }), (0, jsx_runtime_1.jsxs)("div", { className: "dash-card", children: [(0, jsx_runtime_1.jsxs)("div", { className: "dash-card-header", children: [(0, jsx_runtime_1.jsx)(lucide_react_1.DollarSign, { size: 18, className: "icon-yellow" }), (0, jsx_runtime_1.jsx)("h3", { children: "Financial Advisor" })] }), (0, jsx_runtime_1.jsxs)("div", { className: "finance-summary", children: [(0, jsx_runtime_1.jsxs)("div", { className: "finance-stat", children: [(0, jsx_runtime_1.jsx)("span", { className: "finance-label", children: "Income" }), (0, jsx_runtime_1.jsxs)("span", { className: "finance-val income", children: ["$", totalIncome.toFixed(2)] })] }), (0, jsx_runtime_1.jsxs)("div", { className: "finance-stat", children: [(0, jsx_runtime_1.jsx)("span", { className: "finance-label", children: "Expenses" }), (0, jsx_runtime_1.jsxs)("span", { className: "finance-val expense", children: ["$", totalExpenses.toFixed(2)] })] })] }), (0, jsx_runtime_1.jsx)("div", { className: "finance-logs", children: finance.slice(0, 3).map((f, i) => ((0, jsx_runtime_1.jsxs)("div", { className: "finance-item", children: [(0, jsx_runtime_1.jsx)("span", { children: f.category }), (0, jsx_runtime_1.jsxs)("span", { className: f.log_type === 'expense' ? 'text-expense' : 'text-income', children: [f.log_type === 'expense' ? '-' : '+', "$", f.amount.toFixed(2)] })] }, i))) })] }), (0, jsx_runtime_1.jsxs)("div", { className: "dash-card", children: [(0, jsx_runtime_1.jsxs)("div", { className: "dash-card-header", children: [(0, jsx_runtime_1.jsx)(lucide_react_1.Lightbulb, { size: 18, className: "icon-orange" }), (0, jsx_runtime_1.jsx)("h3", { children: "Creative Partner" })] }), (0, jsx_runtime_1.jsxs)("div", { className: "creative-canvas", children: [(0, jsx_runtime_1.jsx)("p", { className: "creative-prompt", children: "\"Hey JARVIS, let's brainstorm ideas for my new project.\"" }), (0, jsx_runtime_1.jsxs)("div", { className: "creative-decoration", children: [(0, jsx_runtime_1.jsx)("div", { className: "creative-orb" }), (0, jsx_runtime_1.jsx)("div", { className: "creative-orb-2" })] })] })] })] })] }));
};
exports.PersonalDashboard = PersonalDashboard;
//# sourceMappingURL=PersonalDashboard.js.map