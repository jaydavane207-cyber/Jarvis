
        // Setup Marked.js
        marked.setOptions({
            highlight: function(code, lang) {
                if (lang && hljs.getLanguage(lang)) return hljs.highlight(code, { language: lang }).value;
                return hljs.highlightAuto(code).value;
            },
            breaks: true
        });

        // State
        let allFiles = [];
        let sessions = []; // Array of {id, title, count, date, files}
        let primarySessionId = null;
        let compareSessionId = null;
        let isCompareMode = false;
        
        let primaryData = [];
        let compareData = [];

        // Local Storage State
        let userState = JSON.parse(localStorage.getItem('jarvisViewerState')) || { pins: [], tags: {}, archives: [] };
        function saveState() { localStorage.setItem('jarvisViewerState', JSON.stringify(userState)); }

        // DOM Elements
        const dirPicker = document.getElementById('dirPicker');
        const activeCard = document.getElementById('activeSessionCard');
        const sessionActions = document.getElementById('sessionActions');
        const exportRow = document.getElementById('exportRow');
        const statsWrapper = document.getElementById('statsWrapper');
        const logsWrapper = document.getElementById('logsWrapper');
        const log1 = document.getElementById('log-container-1');
        const log2 = document.getElementById('log-container-2');
        const compareCol = document.getElementById('compareCol');
        const initialState = document.getElementById('initial-state');

        // Theme Toggle
        document.getElementById('themeToggleBtn').addEventListener('click', () => {
            document.body.classList.toggle('calm-mode');
        });

        // Refresh
        document.getElementById('refreshBtn').addEventListener('click', (e) => {
            e.currentTarget.classList.add('spinning');
            setTimeout(() => { e.currentTarget.classList.remove('spinning'); if(primarySessionId) loadSession(primarySessionId, true); }, 1000);
        });

        // Shortcuts
        document.getElementById('shortcutsBtn').addEventListener('click', () => { document.getElementById('shortcutsModalOverlay').style.display = 'flex'; });
        document.addEventListener('keydown', (e) => {
            if(e.ctrlKey && e.key === 'o') { e.preventDefault(); dirPicker.click(); }
            if(e.ctrlKey && e.key === 'k') { e.preventDefault(); openSessionBrowser(); }
            if(e.ctrlKey && e.key === 'f') { e.preventDefault(); document.getElementById('searchInput').focus(); }
            if(e.ctrlKey && e.key === 'p') { e.preventDefault(); window.print(); }
            if(e.key === 'Escape') { 
                document.getElementById('sessionModal').style.display = 'none'; 
                document.getElementById('shortcutsModalOverlay').style.display = 'none'; 
            }
        });

        // Copy delegation
        document.addEventListener('click', function(e) {
            const btn = e.target.closest('.copy-btn');
            if(btn) {
                const codeBlock = btn.nextElementSibling;
                navigator.clipboard.writeText(codeBlock.innerText).then(() => {
                    const originalText = btn.innerHTML;
                    btn.innerHTML = '<i class="fa-solid fa-check"></i> COPIED!';
                    setTimeout(() => btn.innerHTML = originalText, 2000);
                });
            }
        });

        // Directory Parsing
        function extractTitle(lines) {
            for (let line of lines) {
                try {
                    const parsed = JSON.parse(line);
                    if ((parsed.source === 'USER_EXPLICIT' || parsed.type === 'USER_INPUT') && parsed.content) {
                        let text = parsed.content.trim();
                        if (text.startsWith('<USER_REQUEST>')) {
                            const match = text.match(/<USER_REQUEST>([\s\S]*?)<\/USER_REQUEST>/);
                            if (match) text = match[1].trim();
                        }
                        return text.length > 50 ? text.substring(0, 50) + '...' : text;
                    }
                } catch (e) {}
            }
            return "UNTITLED CONVERSATION";
        }

        function extractDate(lines) {
            for (let line of lines) {
                try { const p = JSON.parse(line); if(p.timestamp) return new Date(p.timestamp); } catch(e){}
            }
            return new Date();
        }

        dirPicker.addEventListener('change', async (event) => {
            allFiles = Array.from(event.target.files).filter(f => f.name === 'transcript.jsonl' || f.name === 'transcript_full.jsonl');
            const convoMap = new Map();
            
            log1.innerHTML = '<div class="hud-loading"><div class="arc-reactor"></div><p>ANALYZING DATA STREAMS...</p></div>';

            for (const f of allFiles) {
                const parts = f.webkitRelativePath.split('/');
                if (parts.length > 1) {
                    const id = parts[1];
                    if (!convoMap.has(id)) convoMap.set(id, { id: id, files: [] });
                    convoMap.get(id).files.push(f);
                }
            }

            sessions = [];
            for (const [id, data] of convoMap.entries()) {
                const f = data.files.find(x => x.name === 'transcript.jsonl') || data.files[0];
                const text = await f.text();
                const lines = text.split('\n').filter(l => l.trim() !== '');
                data.title = extractTitle(lines);
                data.count = lines.length;
                data.date = extractDate(lines);
                sessions.push(data);
            }

            log1.innerHTML = '<p style="text-align:center; color: var(--primary); font-family: \'Rajdhani\'; letter-spacing: 2px; margin-top:50px;">SYSTEM READY. OPEN SESSION BROWSER TO BEGIN.</p>';
            
            document.getElementById('activeSessionTitle').innerText = `[${sessions.length} SESSIONS LOADED]`;
            openSessionBrowser();
        });

        // Modal Logic
        function openSessionBrowser() {
            renderModalList();
        }
        function closeSessionBrowser() { document.getElementById('sessionModal').style.display = 'none'; }

        document.getElementById('modalSearch').addEventListener('input', renderModalList);
        document.getElementById('modalSort').addEventListener('change', renderModalList);

        function renderModalList() {
            const list = document.getElementById('modalSessionList');
            const query = document.getElementById('modalSearch').value.toLowerCase();
            const sort = document.getElementById('modalSort').value;

            let filtered = sessions.filter(s => 
                s.title.toLowerCase().includes(query) || s.id.toLowerCase().includes(query)
            );

            filtered.sort((a, b) => {
                // Always pin to top first
                const aPin = userState.pins.includes(a.id);
                const bPin = userState.pins.includes(b.id);
                if(aPin && !bPin) return -1;
                if(!aPin && bPin) return 1;

                if (sort === 'recent') return b.date - a.date;
                if (sort === 'length') return b.count - a.count;
                if (sort === 'alpha') return a.title.localeCompare(b.title);
                return 0;
            });

            list.innerHTML = '';
            filtered.forEach(s => {
                const isPinned = userState.pins.includes(s.id);
                const isArchived = userState.archives.includes(s.id);
                const tag = userState.tags[s.id];

                const div = document.createElement('div');
                div.className = `session-item ${isPinned ? 'pinned' : ''} ${isArchived ? 'archived' : ''}`;
                div.onclick = () => {
                    
                    if(isCompareMode) loadSession(s.id, false);
                    else loadSession(s.id, true);
                };

                let badgesHtml = '';
                if(isPinned) badgesHtml += '<span class="s-badge pin"><i class="fa-solid fa-star"></i> PINNED</span>';
                if(tag) badgesHtml += `<span class="s-badge tag"><i class="fa-solid fa-tag"></i> ${tag}</span>`;
                if(isArchived) badgesHtml += '<span class="s-badge" style="border:1px solid #666;"><i class="fa-solid fa-box-archive"></i> ARCHIVED</span>';

                div.innerHTML = `
                    <div class="s-info">
                        <div class="s-title">${escapeHtml(s.title)}</div>
                        <div class="s-meta">
                            <span><i class="fa-solid fa-hashtag"></i> ${s.count}</span>
                            <span><i class="fa-regular fa-clock"></i> ${s.date.toLocaleDateString()}</span>
                            <span><i class="fa-solid fa-fingerprint"></i> ${s.id.substring(0,8)}...</span>
                        </div>
                    </div>
                    <div class="s-badges">${badgesHtml}</div>
                `;
                list.appendChild(div);
            });
        }

        // Load Session
        async function loadSession(id, isPrimary) {
            const container = isPrimary ? log1 : log2;
            if(isPrimary) {
                primarySessionId = id;
                updateActiveCard(id);
                sessionActions.style.display = 'flex';
                document.getElementById('commandBar').style.display = 'flex'; document.getElementById('rightSidebar').style.display = 'flex';
                
                document.getElementById('floatingBtns').style.display = 'flex';
            } else {
                compareSessionId = id;
            }

            container.innerHTML = '<div class="hud-loading"><div class="arc-reactor"></div><p>DECRYPTING LOG FILES...</p></div>';
            
            const sessionMeta = sessions.find(s => s.id === id);
            let text = "";
            if (sessionMeta.files && sessionMeta.files.length > 0) {
                const file = sessionMeta.files.find(f => f.name === 'transcript_full.jsonl') || sessionMeta.files.find(f => f.name === 'transcript.jsonl') || sessionMeta.files[0];
                if (file) text = await file.text();
            } else {
                try {
                    const res = await fetch('/api/conversations/' + id);
                    if (res.ok) text = await res.text();
                } catch(e) { console.error(e); }
            }

            if (text) {
                try {
                    const lines = text.split('\n').filter(l => l.trim() !== '');
                    
                    const dataArr = [];
                    lines.forEach(line => { try { dataArr.push(JSON.parse(line)); } catch(e) {} });

                    if(isPrimary) primaryData = dataArr;
                    else compareData = dataArr;

                    if(isPrimary) calculateStats(dataArr);
                    renderLogs(dataArr, container, isPrimary);
                } catch(err) {
                    container.innerHTML = `<div class="hud-error"><i class="fa-solid fa-triangle-exclamation"></i><h2>DATA CORRUPTION DETECTED</h2><p>${escapeHtml(err.message)}</p></div>`;
                }
            }
        }

        function updateActiveCard(id) {
            const s = sessions.find(x => x.id === id);
            document.getElementById('activeSessionTitle').innerText = s.title;
            document.getElementById('activeSessionCount').innerHTML = `<i class="fa-solid fa-hashtag"></i> ${s.count} MSGS`;
            document.getElementById('activeSessionDate').innerHTML = `<i class="fa-regular fa-clock"></i> ${s.date.toLocaleString()}`;
            
            const isPinned = userState.pins.includes(id);
            const tag = userState.tags[id];
            let badgesHtml = '';
            if(isPinned) badgesHtml += '<span class="s-badge pin"><i class="fa-solid fa-star"></i> PINNED</span>';
            if(tag) badgesHtml += `<span class="s-badge tag"><i class="fa-solid fa-tag"></i> ${tag}</span>`;
            document.getElementById('activeSessionBadges').innerHTML = badgesHtml;

            // Update button states
            document.getElementById('pinBtn').classList.toggle('active', isPinned);
            document.getElementById('archiveBtn').classList.toggle('active', userState.archives.includes(id));
        }

        // Stats & Timeline
        
        // Drawer toggles
        document.getElementById('leftDrawerToggle').addEventListener('click', () => {
            document.getElementById('leftSidebar').classList.toggle('open');
        });
        document.getElementById('rightDrawerToggle').addEventListener('click', () => {
            document.getElementById('rightSidebar').classList.toggle('open');
        });
        
        // Custom calculateStats for command center
        function calculateStats(data) {
            let tools = 0, jay = 0, anti = 0, sys = 0;
            const timeline = document.getElementById('timelineScrubber');
            if (timeline) timeline.innerHTML = '';
            
            const total = data.length;
            const toolCounts = {};
            const keyMoments = [];
            
            const chunks = 20; // For sparkline
            const chunkCounts = new Array(chunks).fill(0);
            
            const d1 = (data.length > 0 && data[0].timestamp) ? new Date(data[0].timestamp).getTime() : 0;
            const d2 = (data.length > 0 && data[total-1].timestamp) ? new Date(data[total-1].timestamp).getTime() : 0;
            const durationMs = d2 - d1;

            data.forEach((p, index) => {
                let role = 'sys'; let color = 'var(--system-color)';
                if (p.source === 'USER_EXPLICIT' || p.type === 'USER_INPUT') { jay++; role = 'jay'; color = 'var(--jay-color)'; }
                else if (p.source === 'MODEL' || p.type === 'PLANNER_RESPONSE') { anti++; role = 'anti'; color = 'var(--antigravity-color)'; }
                else sys++;

                if (p.tool_calls && p.tool_calls.length > 0) {
                    tools += p.tool_calls.length;
                    p.tool_calls.forEach(tc => {
                        const tName = tc.name || (tc.function && tc.function.name) || 'UNKNOWN_TOOL';
                        toolCounts[tName] = (toolCounts[tName] || 0) + 1;
                    });
                    if (p.tool_calls.length >= 3) {
                        keyMoments.push({index: index, type: 'tool', desc: `Chain of ${p.tool_calls.length} tools`});
                    }
                }
                
                if (p.status === 'ERROR') {
                    keyMoments.push({index: index, type: 'error', desc: `System Error Detected`});
                }
                if (p.content && p.content.length > 2000) {
                    keyMoments.push({index: index, type: 'long', desc: `Long output (>2k chars)`});
                }

                // Timeline Tick
                if (timeline) {
                    const tick = document.createElement('div');
                    tick.className = 'timeline-tick';
                    tick.style.left = `${(index / total) * 100}%`;
                    tick.style.backgroundColor = color;
                    tick.title = `Msg ${index+1}: ${role.toUpperCase()}`;
                    tick.onclick = () => {
                        const el = document.getElementById(isCompareMode ? `msg-compare-${index}` : `msg-primary-${index}`);
                        if(el) el.scrollIntoView({behavior: 'smooth', block: 'center'});
                    };
                    timeline.appendChild(tick);
                }
                
                // Sparkline
                if (durationMs > 0 && p.timestamp) {
                    const t = new Date(p.timestamp).getTime();
                    const percent = (t - d1) / durationMs;
                    let chunkIdx = Math.floor(percent * chunks);
                    if (chunkIdx >= chunks) chunkIdx = chunks - 1;
                    chunkCounts[chunkIdx]++;
                }
            });

            document.getElementById('statTotal').innerText = total;
            document.getElementById('statTools').innerText = tools;
            document.getElementById('statJay').innerText = jay;
            document.getElementById('statAnti').innerText = anti;
            document.getElementById('statSys').innerText = sys;

            // Update Donut Chart
            let jayPct = total > 0 ? (jay/total)*100 : 0;
            let antiPct = total > 0 ? (anti/total)*100 : 0;
            let sysPct = total > 0 ? (sys/total)*100 : 0;
            
            // Format conic gradient: jay (0 to jayPct), anti (jayPct to jayPct+antiPct), sys (rest)
            const p1 = jayPct;
            const p2 = jayPct + antiPct;
            document.getElementById('roleDonut').style.background = `conic-gradient(
                var(--jay-color) 0% ${p1}%, 
                var(--antigravity-color) ${p1}% ${p2}%, 
                var(--system-color) ${p2}% 100%
            )`;

            // Duration
            if(durationMs > 0) {
                const diffMin = Math.round(durationMs / 60000);
                document.getElementById('statDuration').innerText = diffMin > 60 ? `${(diffMin/60).toFixed(1)}h` : `${diffMin}m`;
            } else {
                document.getElementById('statDuration').innerText = '--';
            }
            
            // Render Sparkline
            const sparkContainer = document.getElementById('sparklineContainer');
            sparkContainer.innerHTML = '';
            const maxChunk = Math.max(...chunkCounts, 1);
            chunkCounts.forEach(c => {
                const bar = document.createElement('div');
                bar.className = 'spark-bar';
                bar.style.height = `${(c / maxChunk) * 100}%`;
                bar.title = `${c} messages`;
                sparkContainer.appendChild(bar);
            });
            
            // Render Tools
            const toolList = document.getElementById('toolFreqList');
            toolList.innerHTML = '';
            const sortedTools = Object.entries(toolCounts).sort((a,b) => b[1] - a[1]).slice(0, 5);
            if (sortedTools.length === 0) {
                toolList.innerHTML = '<div style="color:#666; font-size:0.8rem; text-align:center;">NO TOOLS USED</div>';
            } else {
                sortedTools.forEach(([name, count]) => {
                    toolList.innerHTML += `<div class="tool-freq-item"><span><i class="fa-solid fa-terminal"></i> ${name}</span> <span>${count}</span></div>`;
                });
            }
            
            // Render Key Moments
            const momentsList = document.getElementById('keyMomentsList');
            momentsList.innerHTML = '';
            if (keyMoments.length === 0) {
                momentsList.innerHTML = '<div style="color:#666; font-size:0.8rem; text-align:center;">NO FLAGS DETECTED</div>';
            } else {
                // limit to top 8
                keyMoments.slice(0, 8).forEach(m => {
                    const icon = m.type === 'error' ? '<i class="fa-solid fa-triangle-exclamation" style="color:red"></i>' : 
                                 m.type === 'tool' ? '<i class="fa-solid fa-link" style="color:var(--tool-color)"></i>' : 
                                 '<i class="fa-solid fa-align-left" style="color:var(--antigravity-color)"></i>';
                    
                    const div = document.createElement('div');
                    div.className = 'key-moment-item';
                    div.innerHTML = `${icon} Msg ${m.index}: ${m.desc}`;
                    div.onclick = () => {
                        const el = document.getElementById(`msg-primary-${m.index}`);
                        if(el) el.scrollIntoView({behavior: 'smooth', block: 'center'});
                    };
                    momentsList.appendChild(div);
                });
            }
        }
    
        function oldCalculateStats(data) {
            let tools = 0, jay = 0, anti = 0, sys = 0;
            const timeline = document.getElementById('timelineScrubber');
            timeline.innerHTML = '';
            
            const total = data.length;

            data.forEach((p, index) => {
                let role = 'sys'; let color = 'var(--system-color)';
                if (p.source === 'USER_EXPLICIT' || p.type === 'USER_INPUT') { jay++; role = 'jay'; color = 'var(--jay-color)'; }
                else if (p.source === 'MODEL' || p.type === 'PLANNER_RESPONSE') { anti++; role = 'anti'; color = 'var(--antigravity-color)'; }
                else sys++;

                if (p.tool_calls && p.tool_calls.length > 0) tools += p.tool_calls.length;

                // Timeline Tick
                const tick = document.createElement('div');
                tick.className = 'timeline-tick';
                tick.style.left = `${(index / total) * 100}%`;
                tick.style.backgroundColor = color;
                tick.title = `Msg ${index+1} (${role})`;
                tick.onclick = () => {
                    const msgEl = document.getElementById(`msg-primary-${index}`);
                    if(msgEl) window.scrollTo({top: msgEl.offsetTop - 100, behavior: 'smooth'});
                };
                timeline.appendChild(tick);
            });

            document.getElementById('statTotal').innerText = total;
            document.getElementById('statTools').innerText = tools;
            document.getElementById('statJay').innerText = jay;
            document.getElementById('statAnti').innerText = anti;

            // Progress Bar
            const bar = document.getElementById('roleProgressBar');
            bar.innerHTML = `
                <div class="role-segment role-jay" style="width: ${(jay/total)*100}%" title="User"></div>
                <div class="role-segment role-anti" style="width: ${(anti/total)*100}%" title="Model"></div>
                <div class="role-segment role-sys" style="width: ${(sys/total)*100}%" title="System"></div>
            `;

            // Duration
            if(total > 1 && data[0].timestamp && data[total-1].timestamp) {
                const d1 = new Date(data[0].timestamp);
                const d2 = new Date(data[total-1].timestamp);
                const diffMin = Math.round((d2 - d1) / 60000);
                document.getElementById('statDuration').innerText = diffMin > 60 ? `${(diffMin/60).toFixed(1)}h` : `${diffMin}m`;
            } else {
                document.getElementById('statDuration').innerText = '--';
            }
        }

        // Render Logs
        function renderLogs(data, container, isPrimary) {
            container.innerHTML = '';
            const query = document.getElementById('searchInput').value.toLowerCase();
            const showUser = document.querySelector('.msg-filter[value="user"]').checked;
            const showModel = document.querySelector('.msg-filter[value="model"]').checked;
            const showSystem = document.querySelector('.msg-filter[value="system"]').checked;
            const showTools = document.getElementById('toolFilter').checked;

            let visibleCount = 0;

            data.forEach((parsed, index) => {
                let sourceClass = 'msg-role-system'; let sourceName = 'SYSTEM'; let icon = 'fa-microchip';
                
                if (parsed.source === 'USER_EXPLICIT' || parsed.type === 'USER_INPUT') {
                    sourceClass = 'msg-role-user'; sourceName = 'JAY'; icon = 'fa-user';
                }
                else if (parsed.source === 'MODEL' || p.type === 'PLANNER_RESPONSE') {
                    sourceClass = 'msg-role-model'; sourceName = 'ANTIGRAVITY'; icon = 'fa-bolt';
                }

                if (!showUser && sourceClass === 'msg-role-user') return;
                if (!showModel && sourceClass === 'msg-role-model') return;
                if (!showSystem && sourceClass === 'msg-role-system') return;

                const hasContent = parsed.content && parsed.content.trim() !== '';
                const hasTools = parsed.tool_calls && parsed.tool_calls.length > 0;
                if (!hasContent && (!hasTools || !showTools)) return;

                const contentStr = parsed.content || '';
                const toolStr = hasTools ? JSON.stringify(parsed.tool_calls) : '';
                if (query && !contentStr.toLowerCase().includes(query) && !toolStr.toLowerCase().includes(query)) return;

                visibleCount++;
                const div = document.createElement('div');
                div.className = `message ${sourceClass}`;
                div.id = isPrimary ? `msg-primary-${index}` : `msg-compare-${index}`;
                
                const ts = parsed.timestamp ? new Date(parsed.timestamp).toLocaleString() : 'UNKNOWN';
                let html = `<div class="message-header"><span><i class="fa-solid ${icon}"></i> ${sourceName}</span><span class="timestamp">[${ts}]</span></div>`;
                
                if (hasContent) {
                    let text = parsed.content;
                    text = text.replace(/<USER_REQUEST>([\s\S]*?)<\/USER_REQUEST>/g, '> **USER REQUEST:**\n> $1');
                    text = text.replace(/<ADDITIONAL_METADATA>([\s\S]*?)<\/ADDITIONAL_METADATA>/g, '');
                    text = text.replace(/<EPHEMERAL_MESSAGE>([\s\S]*?)<\/EPHEMERAL_MESSAGE>/g, '');
                    let rendered = marked.parse(text);
                    rendered = rendered.replace(/<pre><code/g, '<pre><button class="copy-btn"><i class="fa-solid fa-copy"></i> COPY</button><code');
                    html += `<div class="markdown-body">${rendered}</div>`;
                }

                if (hasTools && showTools) {
                    parsed.tool_calls.forEach(tc => {
                        const tName = tc.name || (tc.function && tc.function.name) || 'UNKNOWN_TOOL';
                        const args = tc.arguments || (tc.function && tc.function.arguments) || tc;
                        let argsStr = typeof args === 'string' ? args : JSON.stringify(args, null, 2);
                        try { if(typeof args === 'string') argsStr = JSON.stringify(JSON.parse(args), null, 2); } catch(e){}
                        html += `
                            <div class="tool-call-container">
                                <div class="tool-call-header" onclick="this.nextElementSibling.classList.toggle('expanded'); this.querySelector('i').classList.toggle('fa-chevron-right'); this.querySelector('i').classList.toggle('fa-chevron-down');">
                                    <i class="fa-solid fa-chevron-right"></i>
                                    <span><i class="fa-solid fa-terminal"></i> ${tName}</span>
                                </div>
                                <div class="tool-call-body">${escapeHtml(argsStr)}</div>
                            </div>`;
                    });
                }
                div.innerHTML = html;
                container.appendChild(div);
            });

            if (visibleCount === 0) {
                container.innerHTML = `<div class="hud-error" style="animation:none;"><i class="fa-solid fa-triangle-exclamation"></i><h2>NO RECORDS FOUND</h2><p>Adjust parameters.</p></div>`;
            }
        }

        // Global Event Listeners for Filters
        document.getElementById('searchInput').addEventListener('input', () => { if(primaryData.length) renderLogs(primaryData, log1, true); if(compareData.length) renderLogs(compareData, log2, false); });
        document.querySelectorAll('.msg-filter').forEach(cb => cb.addEventListener('change', () => { if(primaryData.length) renderLogs(primaryData, log1, true); if(compareData.length) renderLogs(compareData, log2, false); }));
        document.getElementById('toolFilter').addEventListener('change', () => { if(primaryData.length) renderLogs(primaryData, log1, true); if(compareData.length) renderLogs(compareData, log2, false); });

        // Action Buttons
        document.getElementById('pinBtn').addEventListener('click', function() {
            if(!primarySessionId) return;
            const idx = userState.pins.indexOf(primarySessionId);
            if(idx > -1) userState.pins.splice(idx, 1);
            else userState.pins.push(primarySessionId);
            saveState(); updateActiveCard(primarySessionId);
        });

        document.getElementById('tagBtn').addEventListener('click', function() {
            if(!primarySessionId) return;
            const current = userState.tags[primarySessionId] || '';
            const tag = prompt("Enter tag name (e.g. TRADING, BUG):", current);
            if(tag !== null) {
                if(tag.trim() === '') delete userState.tags[primarySessionId];
                else userState.tags[primarySessionId] = tag.trim().toUpperCase();
                saveState(); updateActiveCard(primarySessionId);
            }
        });

        document.getElementById('archiveBtn').addEventListener('click', function() {
            if(!primarySessionId) return;
            const idx = userState.archives.indexOf(primarySessionId);
            if(idx > -1) userState.archives.splice(idx, 1);
            else userState.archives.push(primarySessionId);
            saveState(); updateActiveCard(primarySessionId);
        });

        // Compare Mode
        function toggleCompareMode() {
            isCompareMode = !isCompareMode;
            document.getElementById('compareBtn').classList.toggle('active', isCompareMode);
            if(isCompareMode) {
                logsWrapper.classList.add('compare-active');
                compareCol.style.display = 'flex';
                if(!compareSessionId) openSessionBrowser();
            } else {
                logsWrapper.classList.remove('compare-active');
                compareCol.style.display = 'none';
                compareSessionId = null;
                compareData = [];
                log2.innerHTML = '<div class="hud-loading"><div class="arc-reactor" style="width:30px;height:30px;"></div><p>SELECT SESSION TO COMPARE</p></div>';
            }
        }
        document.getElementById('compareBtn').addEventListener('click', toggleCompareMode);

        // Export Functions
        function downloadFile(filename, text) {
            const el = document.createElement('a');
            el.setAttribute('href', 'data:text/plain;charset=utf-8,' + encodeURIComponent(text));
            el.setAttribute('download', filename);
            el.style.display = 'none'; document.body.appendChild(el); el.click(); document.body.removeChild(el);
        }

        document.getElementById('exportMdBtn').addEventListener('click', () => {
            if (!primaryData.length) return;
            let md = `# SYSTEM LOG EXPORT - ${primarySessionId}\n\n`;
            primaryData.forEach(p => {
                if (p.content) {
                    const author = (p.source === 'USER_EXPLICIT' || p.type === 'USER_INPUT') ? 'JAY' : 'ANTIGRAVITY';
                    md += `### [ ${author} ]\n\n${p.content}\n\n---\n\n`;
                }
            });
            downloadFile(`session_${primarySessionId}.md`, md);
        });

        document.getElementById('exportHtmlBtn').addEventListener('click', () => {
            const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>Export</title><style>body{font-family:monospace;background:#03050A;color:#E6F7FF;padding:20px;} .message{padding:15px;border:1px solid rgba(0,240,255,0.3);margin-bottom:20px;} pre{background:#000;padding:10px;color:#E6F7FF;overflow-x:auto;}</style></head><body>${log1.innerHTML}</body></html>`;
            downloadFile(`session_${primarySessionId}.html`, html);
        });

        document.getElementById('exportJsonBtn').addEventListener('click', () => {
            if (!primaryData.length) return;
            downloadFile(`session_${primarySessionId}.json`, JSON.stringify(primaryData, null, 2));
        });

        document.getElementById('exportPdfBtn').addEventListener('click', () => {
            window.print();
        });

        document.getElementById('copyLinkBtn').addEventListener('click', (e) => {
            navigator.clipboard.writeText(window.location.href).then(() => {
                const icon = e.currentTarget.querySelector('i');
                icon.className = 'fa-solid fa-check'; setTimeout(()=> icon.className = 'fa-solid fa-link', 2000);
            });
        });

        document.getElementById('copyIdBtn').addEventListener('click', (e) => {
            if(primarySessionId) {
                navigator.clipboard.writeText(primarySessionId).then(() => {
                    const icon = e.currentTarget.querySelector('i');
                    icon.className = 'fa-solid fa-check'; setTimeout(()=> icon.className = 'fa-solid fa-fingerprint', 2000);
                });
            }
        });

        function escapeHtml(unsafe) {
            return (unsafe || '').replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
        }
    
        // Auto-fetch data from backend API if available
        (async function initData() {
            try {
                const res = await fetch('/api/conversations');
                if (res.ok) {
                    const data = await res.json();
                    if (data && data.length > 0) {
                        sessions = data.map(d => ({
                            id: d.id,
                            title: d.title,
                            count: d.count,
                            date: new Date(),
                            files: []
                        }));
                        log1.innerHTML = '<p style="text-align:center; color: var(--primary); font-family: \'Rajdhani\'; letter-spacing: 2px; margin-top:50px;">DATABANKS SYNCHRONIZED.</p>';
                        openSessionBrowser();
                        // Auto load first session
                        if (sessions.length > 0) {
                            loadSession(sessions[0].id, true);
                        }
                    }
                }
            } catch (err) {
                console.log("No backend API detected. Running in offline/local mode.");
            }
        })();
    