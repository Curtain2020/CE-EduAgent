// 全局变量
let isInitialized = false;
let isLoading = false;
let activeStudents = [];
let vrControlEnabled = true;
const allowedStudents = [
    { name: '崔展豪', enableLongTermMemory: true, enableKnowledgeBase: false, positivity: 0.5 },
    { name: '李昌龙', enableLongTermMemory: true, enableKnowledgeBase: false, positivity: 0.5 },
    { name: '包梓群', enableLongTermMemory: true, enableKnowledgeBase: false, positivity: 0.5 },
    { name: '丽娃', enableLongTermMemory: true, enableKnowledgeBase: false, positivity: 0.5 },
    { name: '张晓丹', enableLongTermMemory: true, enableKnowledgeBase: false, positivity: 0.5 },
    { name: '萧华诗', enableLongTermMemory: true, enableKnowledgeBase: false, positivity: 0.5 }
];

const ACTION_EMOJIS = {
    raiseHand: '🙋',
    sitProperly: '🧒',
    standUp: '🧍',
    sitDown: '🪑'
};

const ACTION_LABELS = {
    raiseHand: '举手',
    sitProperly: '端坐',
    standUp: '起立',
    sitDown: '坐下'
};

const EXPRESSION_EMOJIS = {
    calm: '😐',
    dazed: '😵',
    smile: '😊'
};

const EXPRESSION_LABELS = {
    calm: '平静',
    dazed: '呆滞',
    smile: '微笑'
};

let studentConfigs = {};
let activeStudentConfigs = {};
let studentPanelCollapsed = false;

function initializeStudentSelector() {
    const listEl = document.getElementById('studentList');
    if (!listEl) {
        return;
    }

    studentConfigs = {};
    listEl.innerHTML = '';

    allowedStudents.forEach((student) => {
        studentConfigs[student.name] = {
            selected: false,
            enableLongTermMemory: student.enableLongTermMemory,
            enableKnowledgeBase: student.enableKnowledgeBase,
            positivity: typeof student.positivity === 'number' ? student.positivity : 0.5
        };

        const itemEl = document.createElement('div');
        itemEl.className = 'student-item';
        itemEl.dataset.student = student.name;

        const nameLabel = document.createElement('label');
        const nameCheckbox = document.createElement('input');
        nameCheckbox.type = 'checkbox';
        nameCheckbox.className = 'student-checkbox';
        nameCheckbox.value = student.name;
        nameCheckbox.addEventListener('change', (event) => {
            studentConfigs[student.name].selected = event.target.checked;
            itemEl.classList.toggle('selected', event.target.checked);
            updateApplyGlobalBtnState();
        });

        nameLabel.appendChild(nameCheckbox);
        nameLabel.appendChild(document.createTextNode(student.name));

        const longTermLabel = document.createElement('label');
        const longTermCheckbox = document.createElement('input');
        longTermCheckbox.type = 'checkbox';
        longTermCheckbox.className = 'student-long-term';
        longTermCheckbox.checked = student.enableLongTermMemory;
        longTermCheckbox.addEventListener('change', (event) => {
            studentConfigs[student.name].enableLongTermMemory = event.target.checked;
        });
        longTermLabel.appendChild(longTermCheckbox);
        longTermLabel.appendChild(document.createTextNode('长期记忆'));

        const knowledgeLabel = document.createElement('label');
        const knowledgeCheckbox = document.createElement('input');
        knowledgeCheckbox.type = 'checkbox';
        knowledgeCheckbox.className = 'student-knowledge';
        knowledgeCheckbox.checked = student.enableKnowledgeBase;
        knowledgeCheckbox.addEventListener('change', (event) => {
            studentConfigs[student.name].enableKnowledgeBase = event.target.checked;
        });
        knowledgeLabel.appendChild(knowledgeCheckbox);
        knowledgeLabel.appendChild(document.createTextNode('认知增强'));

        const positivityWrapper = document.createElement('div');
        positivityWrapper.className = 'student-positivity-control';
        const positivityLabel = document.createElement('span');
        positivityLabel.className = 'student-positivity-text';
        const initialPositivity = studentConfigs[student.name].positivity ?? 0.5;
        positivityLabel.textContent = `积极性：${initialPositivity.toFixed(2)}`;
        const positivitySlider = document.createElement('input');
        positivitySlider.type = 'range';
        positivitySlider.min = '0';
        positivitySlider.max = '1';
        positivitySlider.step = '0.01';
        positivitySlider.value = initialPositivity;
        positivitySlider.className = 'student-positivity-slider';
        positivitySlider.addEventListener('input', (event) => {
            const val = Number(event.target.value);
            positivityLabel.textContent = `积极性：${val.toFixed(2)}`;
            studentConfigs[student.name].positivity = val;
        });
        positivityWrapper.appendChild(positivityLabel);
        positivityWrapper.appendChild(positivitySlider);

        // per-student import/export buttons and status
        const graphOps = document.createElement('div');
        graphOps.className = 'student-graph-ops';
        const btnImport = document.createElement('button');
        btnImport.textContent = '导入最新图谱';
        btnImport.className = 'btn-import';
        btnImport.addEventListener('click', async () => {
            await importLatestGraphsForStudents([student.name]);
        });
        const btnExport = document.createElement('button');
        btnExport.textContent = '导出图谱';
        btnExport.className = 'btn-export';
        btnExport.addEventListener('click', async () => {
            await exportGraphsForStudents([student.name]);
        });
        const status = document.createElement('span');
        status.className = 'student-graph-status';
        status.textContent = '';
        graphOps.appendChild(btnImport);
        graphOps.appendChild(btnExport);
        graphOps.appendChild(status);

        itemEl.appendChild(nameLabel);
        itemEl.appendChild(longTermLabel);
        itemEl.appendChild(knowledgeLabel);
        itemEl.appendChild(positivityWrapper);
        itemEl.appendChild(graphOps);
        listEl.appendChild(itemEl);
    });

    updateApplyGlobalBtnState();
    updateStudentPanelVisualState();
}

function updateApplyGlobalBtnState() {
    const btn = document.getElementById('applyGlobalBtn');
    if (!btn) return;
    if (btn.dataset.locked === 'true') {
        btn.disabled = true;
        return;
    }
    const hasSelected = Object.values(studentConfigs).some((cfg) => cfg.selected);
    btn.disabled = !hasSelected;
}

function getGlobalConfig() {
    const globalLongTerm = document.getElementById('globalEnableLongTermMemory');
    const globalKnowledge = document.getElementById('globalEnableKnowledgeBase');
    return {
        enableLongTermMemory: globalLongTerm ? globalLongTerm.checked : true,
        enableKnowledgeBase: globalKnowledge ? globalKnowledge.checked : false
    };
}

function applyGlobalConfig() {
    const { enableLongTermMemory, enableKnowledgeBase } = getGlobalConfig();
    const listEl = document.getElementById('studentList');
    if (!listEl) return;

    let appliedCount = 0;

    Object.entries(studentConfigs).forEach(([name, cfg]) => {
        if (!cfg.selected) return;
        cfg.enableLongTermMemory = enableLongTermMemory;
        cfg.enableKnowledgeBase = enableKnowledgeBase;
        appliedCount += 1;
        const itemEl = listEl.querySelector(`.student-item[data-student="${name}"]`);
        if (itemEl) {
            const longTermCheckbox = itemEl.querySelector('.student-long-term');
            const knowledgeCheckbox = itemEl.querySelector('.student-knowledge');
            if (longTermCheckbox) {
                longTermCheckbox.checked = enableLongTermMemory;
            }
            if (knowledgeCheckbox) {
                knowledgeCheckbox.checked = enableKnowledgeBase;
            }
        }
    });
    if (appliedCount > 0) {
        updateStatus('已将统一配置应用至选中学生', 'success');
    } else {
        updateStatus('请先勾选需要应用的学生', 'error');
    }
}

function setStudentSelectorEnabled(enabled) {
    const listEl = document.getElementById('studentList');
    const globalLongTerm = document.getElementById('globalEnableLongTermMemory');
    const globalKnowledge = document.getElementById('globalEnableKnowledgeBase');
    const applyBtn = document.getElementById('applyGlobalBtn');
    const toggleBtn = document.getElementById('studentSelectorToggle');
    const vrToggle = document.getElementById('vrControlToggle');

    if (globalLongTerm) globalLongTerm.disabled = !enabled;
    if (globalKnowledge) globalKnowledge.disabled = !enabled;
    if (vrToggle) vrToggle.disabled = false;
    if (applyBtn) {
        applyBtn.dataset.locked = (!enabled).toString();
        applyBtn.disabled = !enabled;
    }
    if (toggleBtn) {
        toggleBtn.disabled = false;
    }

    if (!listEl) return;

    listEl.querySelectorAll('input[type="checkbox"]').forEach((input) => {
        input.disabled = !enabled;
    });
    listEl.querySelectorAll('input[type="range"]').forEach((input) => {
        input.disabled = !enabled;
    });

    listEl.querySelectorAll('.student-item').forEach((item) => {
        item.classList.toggle('disabled', !enabled);
    });

    if (enabled) {
        updateApplyGlobalBtnState();
    }
    updateStudentPanelVisualState();
}

async function fetchVrControlState() {
    try {
        const response = await fetch('/api/settings/vr');
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || '获取失败');
        }
        vrControlEnabled = !!data.enabled;
        const toggle = document.getElementById('vrControlToggle');
        if (toggle) {
            toggle.checked = vrControlEnabled;
        }
    } catch (error) {
        console.error('获取数字人控制状态失败:', error);
        updateStatus('获取数字人控制状态失败: ' + error.message, 'error');
    }
}

async function handleVrToggleChange(event) {
    const enabled = event.target.checked;
    try {
        const response = await fetch('/api/settings/vr', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ enabled })
        });
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || '更新失败');
        }
        vrControlEnabled = !!data.enabled;
        updateStatus(`数字人控制${vrControlEnabled ? '已开启' : '已关闭'}`, 'success');
    } catch (error) {
        console.error('设置数字人控制失败:', error);
        event.target.checked = vrControlEnabled;
        updateStatus('数字人控制切换失败: ' + error.message, 'error');
    }
}

function initializeVrToggle() {
    const toggle = document.getElementById('vrControlToggle');
    if (!toggle) return;
    toggle.addEventListener('change', handleVrToggleChange);
    fetchVrControlState();
}

function toggleStudentPanel() {
    studentPanelCollapsed = !studentPanelCollapsed;
    updateStudentPanelVisualState();
}

function updateStudentPanelVisualState() {
    const panel = document.getElementById('studentSelectorPanel');
    const toggleBtn = document.getElementById('studentSelectorToggle');
    if (!panel || !toggleBtn) return;
    panel.classList.toggle('collapsed', studentPanelCollapsed);
    toggleBtn.textContent = studentPanelCollapsed ? '展开' : '收起';
    toggleBtn.setAttribute('aria-expanded', (!studentPanelCollapsed).toString());
}

function getSelectedStudentConfigs() {
    return Object.entries(studentConfigs)
        .filter(([, cfg]) => cfg.selected)
        .map(([name, cfg]) => ({
            student_name: name,
            enable_long_term_memory: cfg.enableLongTermMemory,
            enable_knowledge_base: cfg.enableKnowledgeBase,
            positivity: typeof cfg.positivity === 'number' ? cfg.positivity : 0.5
        }));
}

// 初始化学生
async function initStudent() {
    if (isLoading) return;

    const selectedConfigs = getSelectedStudentConfigs();
    if (selectedConfigs.length === 0) {
        updateStatus('请至少选择一名学生', 'error');
        return;
    }

    isLoading = true;
    updateStatus('正在初始化虚拟学生...', 'success');
    setStudentSelectorEnabled(false);

    try {
        const response = await fetch('/api/init', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                student_configs: selectedConfigs
            })
        });

        const data = await response.json();

        if (data.success) {
            isInitialized = true;
            activeStudents = Array.isArray(data.student_names) && data.student_names.length > 0
                ? data.student_names
                : selectedConfigs.map((cfg) => cfg.student_name);

            const configsFromServer = Array.isArray(data.student_configs) ? data.student_configs : selectedConfigs;
            activeStudentConfigs = {};
            configsFromServer.forEach((cfg) => {
                activeStudentConfigs[cfg.student_name] = {
                    enable_long_term_memory: cfg.enable_long_term_memory,
                    enable_knowledge_base: cfg.enable_knowledge_base,
                    positivity: typeof cfg.positivity === 'number' ? cfg.positivity : 0.5
                };
            });

            updateStatus(`已初始化学生：${activeStudents.join('、')}`, 'success');
            updateSpeechButtons();

            // 更新UI
            document.getElementById('initBtn').style.display = 'none';
            document.getElementById('resetBtn').style.display = 'inline-block';
            document.getElementById('messageInput').disabled = false;
            document.getElementById('sendBtn').disabled = false;
            setStudentSelectorEnabled(false);
            
            // 清空聊天记录
            document.getElementById('chatMessages').innerHTML = '';

            // 添加欢迎消息
            activeStudents.forEach((name) => {
                const cfg = activeStudentConfigs[name] || {
                    enable_long_term_memory: true,
                    enable_knowledge_base: false
                };
                const modeText = cfg.enable_knowledge_base ? '已启用认知增强模式' : '已启用基础模式';
                addMessage('assistant', `你好，老师！我是${name}，${modeText}，准备开始学习！`, {
                    senderName: name
                });
            });

            // 更新上下文
            updateContext();

            studentPanelCollapsed = true;
            updateStudentPanelVisualState();
        } else {
            updateStatus('初始化失败: ' + data.error, 'error');
            setStudentSelectorEnabled(true);
        }
    } catch (error) {
        updateStatus('初始化失败: ' + error.message, 'error');
        console.error('初始化错误:', error);
        setStudentSelectorEnabled(true);
    } finally {
        isLoading = false;
    }
}

// 重置学生
async function resetStudent() {
    if (!confirm('确定要重置虚拟学生吗？如果开启了长期记忆，当前的短期记忆将自动存入长期记忆。')) {
        return;
    }
    
    try {
        updateStatus('正在保存短期记忆到长期记忆...', 'success');
        
        const response = await fetch('/api/reset', {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            isInitialized = false;
            activeStudents = [];
            activeStudentConfigs = {};
            updateStatus('已重置，短期记忆已存入长期记忆', 'success');
        } else {
            updateStatus('重置失败: ' + (data.error || '未知错误'), 'error');
        }
        
        stopSpeechRecording(true);
        updateSpeechButtons();
        updateSpeechStatus('语音识别未启动');
        
        // 重置UI
        document.getElementById('initBtn').style.display = 'inline-block';
        document.getElementById('resetBtn').style.display = 'none';
        document.getElementById('messageInput').disabled = true;
        document.getElementById('sendBtn').disabled = true;
        initializeStudentSelector();
        setStudentSelectorEnabled(true);
        studentPanelCollapsed = false;
        updateStudentPanelVisualState();
        
        document.getElementById('chatMessages').innerHTML = '';
        document.getElementById('contextInfo').innerHTML = '<p class="context-placeholder">请先初始化虚拟学生</p>';
    } catch (error) {
        updateStatus('重置失败: ' + error.message, 'error');
        console.error('重置错误:', error);
    }
}

// 发送消息
async function sendMessage() {
    if (!isInitialized || isLoading) return;
    
    const input = document.getElementById('messageInput');
    const message = input.value.trim();
    
    if (!message) return;
    
    // 添加用户消息到界面
    addMessage('user', message, { senderName: '老师' });
    input.value = '';
    
    // 显示加载状态
    const loadingId = addMessage('assistant', '正在思考...', {
        isLoading: true,
        senderName: activeStudents.length > 1 ? '学生（全部）' : (activeStudents[0] || '学生')
    });
    isLoading = true;
    document.getElementById('sendBtn').disabled = true;
    
    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                message: message
            })
        });
        
        const data = await response.json();
        
        // 移除加载消息
        const loadingElement = document.getElementById(loadingId);
        if (loadingElement) {
            loadingElement.remove();
        }
        if (!data.success && !Array.isArray(data.responses)) {
            throw new Error(data.error || '处理消息时出错');
        }

        const responses = Array.isArray(data.responses) ? data.responses : [];
        const systemText = data.message || data.response;
        if (responses.length === 0 && systemText) {
            // 无学生发言时，仅展示课堂助手（避免与下面 data.message 再次渲染重复）
            addMessage('system', systemText, {
                senderName: '课堂助手',
                studentsState: Array.isArray(data.students_state) ? data.students_state : []
            });
        } else {
            responses.forEach((item) => {
                if (!item.success) {
                    addMessage('assistant', `抱歉，处理消息时出错: ${item.error}`, {
                        senderName: item.student_name || '学生'
                    });
                    return;
                }
                addMessage('assistant', item.response, {
                    senderName: item.student_name || '学生',
                    toolCalls: item.tool_calls,
                    intermediateSteps: item.intermediate_steps,
                    actionState: item.action_state,
                    expressionState: item.expression_state
                });
            });
        }

        // 仅在已有学生响应时，再追加课堂助手的课堂状态信息，避免重复渲染
        if (data.message && responses.length > 0) {
            addMessage('system', data.message, {
                senderName: '课堂助手',
                studentsState: Array.isArray(data.students_state) ? data.students_state : []
            });
        }

        if (data.intent || data.action) {
            updateStatus(`意图：${data.intent || '未知'}，动作：${data.action || '无'}`, 'success');
        }

        // 更新上下文
        updateContext();
    } catch (error) {
        // 移除加载消息
        const loadingElement = document.getElementById(loadingId);
        if (loadingElement) {
            loadingElement.remove();
        }
        
        addMessage('assistant', '抱歉，发送消息时出错: ' + error.message, {
            senderName: '系统'
        });
        console.error('发送消息错误:', error);
    } finally {
        isLoading = false;
        document.getElementById('sendBtn').disabled = false;
        input.focus();
    }
}

// 添加消息到聊天界面
function addMessage(type, content, options = {}) {
    const {
        isLoading = false,
        toolCalls = [],
        intermediateSteps = [],
        senderName,
        actionState,
        expressionState,
        studentsState = []
    } = options;

    const messagesContainer = document.getElementById('chatMessages');
    const messageId = 'msg-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;
    messageDiv.id = messageId;
    
    const messageContent = document.createElement('div');
    messageContent.className = 'message-content';
    
    const headerTitle = senderName || (type === 'user' ? '老师' : (type === 'system' ? '课堂助手' : '学生'));

    if (type === 'user') {
        messageContent.innerHTML = `
            <div class="message-header">${escapeHtml(headerTitle)}</div>
            <div>${escapeHtml(content)}</div>
        `;
    } else {
        let html = `
            <div class="message-header">${escapeHtml(headerTitle)}</div>
        `;
        if (actionState || expressionState) {
            const badges = [];
            if (actionState) {
                const emoji = ACTION_EMOJIS[actionState] || '🎯';
                const label = ACTION_LABELS[actionState] || actionState;
                badges.push(`<span class="state-badge">${emoji} ${escapeHtml(label)}</span>`);
            }
            if (expressionState) {
                const emoji = EXPRESSION_EMOJIS[expressionState] || '🙂';
                const label = EXPRESSION_LABELS[expressionState] || expressionState;
                badges.push(`<span class="state-badge">${emoji} ${escapeHtml(label)}</span>`);
            }
            html += `<div class="state-badges">${badges.join('')}</div>`;
        }
        html += `<div>${escapeHtml(content)}</div>`;
        if (type === 'system' && studentsState && studentsState.length > 0) {
            html += '<div class="classroom-state">';
            studentsState.forEach((state) => {
                const actionEmoji = ACTION_EMOJIS[state.action_state] || '🎯';
                const actionLabel = ACTION_LABELS[state.action_state] || state.action_state;
                const expressionEmoji = EXPRESSION_EMOJIS[state.expression_state] || '🙂';
                const expressionLabel = EXPRESSION_LABELS[state.expression_state] || state.expression_state;
                html += `
                    <div class="classroom-state-item">
                        <div class="classroom-state-name">${escapeHtml(state.student_name || '学生')}</div>
                        <div class="classroom-state-badges">
                            <span class="state-badge">${actionEmoji} ${escapeHtml(actionLabel)}</span>
                            <span class="state-badge">${expressionEmoji} ${escapeHtml(expressionLabel)}</span>
                        </div>
                    </div>
                `;
            });
            html += '</div>';
        }
        
        // 添加工具调用信息
        if (toolCalls && toolCalls.length > 0) {
            html += '<div class="tool-call">';
            html += '<div class="tool-call-header">🔧 工具调用</div>';
            
            toolCalls.forEach((toolCall, index) => {
                html += `<div style="margin-top: 8px;">`;
                html += `<span class="tool-call-name">${escapeHtml(toolCall.name)}</span>`;
                html += `<div class="tool-arguments">参数: ${escapeHtml(JSON.stringify(toolCall.arguments, null, 2))}</div>`;
                
                // 添加工具执行结果
                if (intermediateSteps && intermediateSteps[index]) {
                    const step = intermediateSteps[index];
                    html += `<div class="tool-result">结果: ${escapeHtml(step.result)}</div>`;
                }
                
                html += `</div>`;
            });
            
            html += '</div>';
        }
        
        if (isLoading) {
            html += '<span class="loading"></span>';
        }
        
        messageContent.innerHTML = html;
    }
    
    messageDiv.appendChild(messageContent);
    messagesContainer.appendChild(messageDiv);
    
    // 滚动到底部
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
    
    return messageId;
}

// 更新上下文信息
async function updateContext() {
    if (!isInitialized || activeStudents.length === 0) {
        return;
    }

    try {
        const response = await fetch('/api/context');
        const data = await response.json();

        if (!data.success || !Array.isArray(data.students)) {
            return;
        }

        const contextInfo = document.getElementById('contextInfo');
        const html = data.students.map((student) => {
            const shortTerm = Array.isArray(student.short_term_memory) ? student.short_term_memory : [];
            const longTermText = student.long_term_context || '暂无长期记忆';
            const longTermDisplay = longTermText.length > 500
                ? `${longTermText.substring(0, 500)}...`
                : longTermText;
            const positivity = typeof student.positivity === 'number'
                ? Math.min(1, Math.max(0, student.positivity))
                : 0.5;
            const positivityDisplay = positivity.toFixed(2);

            const memories = shortTerm.length === 0
                ? `<p style="color: #999;">暂无短期记忆</p>`
                : shortTerm.map((conv) => {
                    const studentResponse = (conv.student_response || '').toString();
                    const trimmedResponse = studentResponse.length > 100
                        ? `${studentResponse.substring(0, 100)}...`
                        : studentResponse;
                    const teacherMessage = (conv.user_message || '').toString();
                    const speakerName = conv.student_name || student.student_name || '学生';
                    return `
                    <div class="memory-item">
                        <div class="timestamp">${new Date(conv.timestamp).toLocaleString()}</div>
                        <div class="user-message">老师：${escapeHtml(teacherMessage)}</div>
                        <div class="assistant-message">学生（${escapeHtml(speakerName)}）：${escapeHtml(trimmedResponse)}</div>
                    </div>
                `;
                }).join('');

            return `
                <div class="context-section">
                    <h3>${escapeHtml(student.student_name || '学生')}</h3>
                    <p><span class="label">长期记忆:</span> ${student.enable_long_term_memory ? '✅ 启用' : '❌ 禁用'}</p>
                    <p><span class="label">认知增强:</span> ${student.enable_knowledge_base ? '✅ 启用' : '❌ 禁用'}</p>
                    <div class="context-subsection positivity-control">
                        <h4>积极性调节</h4>
                        <div class="positivity-row">
                            <label>当前值：<span class="positivity-value" data-student="${escapeHtml(student.student_name || '')}">${positivityDisplay}</span></label>
                            <span class="positivity-hint">拖拽滑块可调整 0 - 1</span>
                        </div>
                        <input
                            type="range"
                            min="0"
                            max="1"
                            step="0.01"
                            value="${positivity}"
                            class="positivity-slider"
                            data-student="${escapeHtml(student.student_name || '')}"
                        >
                    </div>
                    <div class="context-subsection">
                        <h4>短期记忆 (${shortTerm.length}/10)</h4>
                        ${memories}
                    </div>
                    <div class="context-subsection">
                        <h4>长期记忆</h4>
                        <p style="white-space: pre-wrap; word-wrap: break-word;">${escapeHtml(longTermDisplay)}</p>
                    </div>
                </div>
            `;
        }).join('');

        contextInfo.innerHTML = html;
        bindPositivityControls();
    } catch (error) {
        console.error('更新上下文错误:', error);
    }
}

function bindPositivityControls() {
    const container = document.getElementById('contextInfo');
    if (!container) return;
    const sliders = container.querySelectorAll('.positivity-slider');
    sliders.forEach((slider) => {
        const studentName = slider.dataset.student;
        const valueLabel = container.querySelector(`.positivity-value[data-student="${safeCssEscape(studentName)}"]`);
        slider.addEventListener('input', (event) => {
            if (valueLabel) {
                valueLabel.textContent = Number(event.target.value).toFixed(2);
            }
        });
        slider.addEventListener('change', (event) => {
            const value = Number(event.target.value);
            updateStudentPositivity(studentName, value);
        });
    });
}

async function updateStudentPositivity(studentName, value) {
    if (!studentName) return;
    try {
        const response = await fetch(`/api/students/${encodeURIComponent(studentName)}/positivity`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ positivity: value })
        });
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || '更新失败');
        }
        updateStatus(`已更新${studentName}的积极性为 ${value.toFixed(2)}`, 'success');
        if (isInitialized) {
            updateContext();
        }
    } catch (error) {
        console.error('更新积极性失败:', error);
        updateStatus(`${studentName}积极性更新失败: ${error.message}`, 'error');
    }
}

// ===== 图谱导入/导出（支持分学生） =====
async function importLatestGraphs() {
    const btn = document.getElementById('kgImportBtn');
    const status = document.getElementById('kgStatus');
    if (!btn || !status) return;
    btn.disabled = true; status.textContent = '正在导入最新图谱…';
    try {
        // 优先使用已初始化学生；否则使用当前选中的学生
        const studentNames = (activeStudents && activeStudents.length > 0)
            ? activeStudents
            : getSelectedStudentConfigs().map((c) => c.student_name);
        if (!studentNames.length) throw new Error('请先在左侧选择并初始化学生');
        const resp = await fetch('/api/graph/import_latest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ student_names: studentNames })
        });
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || '导入失败');
        const msg = (data.results || []).map((r) => `${r.student}${r.stage ? `(${r.stage})` : ''}`).join('、');
        status.textContent = `导入完成：${msg || '—'}`;
        updateStatus('已导入最新图谱', 'success');
    } catch (e) {
        status.textContent = `导入失败：${e.message}`;
        updateStatus(status.textContent, 'error');
    } finally {
        btn.disabled = false;
    }
}

async function exportGraphs() {
    const btn = document.getElementById('kgExportBtn');
    const status = document.getElementById('kgStatus');
    if (!btn || !status) return;
    btn.disabled = true; status.textContent = '正在导出本课图谱…';
    try {
        const studentNames = (activeStudents && activeStudents.length > 0)
            ? activeStudents
            : getSelectedStudentConfigs().map((c) => c.student_name);
        if (!studentNames.length) throw new Error('请先在左侧选择并初始化学生');
        const resp = await fetch('/api/graph/export', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ student_names: studentNames })
        });
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || '导出失败');
        const msg = (data.results || []).map((r) => `${r.student}${r.stage ? `(${r.stage})` : ''}`).join('、');
        status.textContent = `导出完成：${msg || '—'}`;
        updateStatus('已导出并更新 index.json', 'success');
    } catch (e) {
        status.textContent = `导出失败：${e.message}`;
        updateStatus(status.textContent, 'error');
    } finally {
        btn.disabled = false;
    }
}

// 批量/单个公共实现：逐学生更新UI状态
async function importLatestGraphsForStudents(studentNames = []) {
    if (!Array.isArray(studentNames) || studentNames.length === 0) return;
    const listEl = document.getElementById('studentList');
    const btnGlobal = document.getElementById('kgImportBtn'); // 兼容旧按钮，如不存在忽略
    if (btnGlobal) btnGlobal.disabled = true;
    try {
        // 置为进行中
        studentNames.forEach((name) => setStudentGraphStatus(name, '导入中…'));
        const resp = await fetch('/api/graph/import_latest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ student_names: studentNames })
        });
        const data = await resp.json();
        if (!data.success) {
            studentNames.forEach((name) => setStudentGraphStatus(name, `导入失败：${data.error || '未知错误'}`));
            return;
        }
        const resultMap = {};
        (data.results || []).forEach(r => { resultMap[r.student] = r; });
        studentNames.forEach((name) => {
            const r = resultMap[name];
            if (r && r.success) {
                setStudentGraphStatus(name, `导入完成：${r.stage || '—'}`, true);
            } else {
                setStudentGraphStatus(name, `导入失败：${r?.error || '未知错误'}`, false);
            }
        });
    } catch (e) {
        studentNames.forEach((name) => setStudentGraphStatus(name, `导入失败：${e.message}`));
    } finally {
        if (btnGlobal) btnGlobal.disabled = false;
    }
}

async function exportGraphsForStudents(studentNames = []) {
    if (!Array.isArray(studentNames) || studentNames.length === 0) return;
    const btnGlobal = document.getElementById('kgExportBtn'); // 兼容旧按钮
    if (btnGlobal) btnGlobal.disabled = true;
    try {
        studentNames.forEach((name) => setStudentGraphStatus(name, '导出中…'));
        const resp = await fetch('/api/graph/export', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ student_names: studentNames })
        });
        const data = await resp.json();
        if (!data.success) {
            studentNames.forEach((name) => setStudentGraphStatus(name, `导出失败：${data.error || '未知错误'}`));
            return;
        }
        const resultMap = {};
        (data.results || []).forEach(r => { resultMap[r.student] = r; });
        studentNames.forEach((name) => {
            const r = resultMap[name];
            if (r && r.success) {
                setStudentGraphStatus(name, `导出完成：${r.stage || '—'}`, true);
            } else {
                setStudentGraphStatus(name, `导出失败：${r?.error || '未知错误'}`, false);
            }
        });
    } catch (e) {
        studentNames.forEach((name) => setStudentGraphStatus(name, `导出失败：${e.message}`));
    } finally {
        if (btnGlobal) btnGlobal.disabled = false;
    }
}

function setStudentGraphStatus(studentName, text, ok = null) {
    const listEl = document.getElementById('studentList');
    if (!listEl) return;
    const itemEl = listEl.querySelector(`.student-item[data-student="${safeCssEscape(studentName)}"]`);
    if (!itemEl) return;
    const statusEl = itemEl.querySelector('.student-graph-status');
    if (!statusEl) return;
    statusEl.textContent = text || '';
    statusEl.style.marginLeft = '8px';
    statusEl.style.fontSize = '12px';
    statusEl.style.color = ok === true ? '#16a34a' : ok === false ? '#dc2626' : '#666';
}

// 更新状态显示
function updateStatus(message, type) {
    const statusDiv = document.getElementById('status');
    statusDiv.textContent = message;
    statusDiv.className = `status ${type}`;
    statusDiv.style.display = 'block';
    
    if (type === 'success') {
        setTimeout(() => {
            statusDiv.style.display = 'none';
        }, 3000);
    }
}

// HTML转义
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function safeCssEscape(value = '') {
    if (window.CSS && typeof window.CSS.escape === 'function') {
        return window.CSS.escape(value);
    }
    return String(value).replace(/([!"#$%&'()*+,.\/:;<=>?@\[\\\]^`{|}~])/g, '\\$1');
}

initializeStudentSelector();
initializeVrToggle();

// 回车发送消息
document.getElementById('messageInput').addEventListener('keypress', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// 更新上下文（每5秒）
setInterval(() => {
    if (isInitialized) {
        updateContext();
    }
}, 5000);

let speechRecorderStream = null;
let speechRecorderContext = null;
let speechRecorderProcessor = null;
let speechRecorderChunks = [];
let speechRecorderStarted = false;
const SPEECH_TARGET_SAMPLE_RATE = 16000;

function updateSpeechStatus(message, type = 'info') {
    const statusEl = document.getElementById('speechStatus');
    if (!statusEl) return;
    statusEl.textContent = message;
    statusEl.className = `speech-status ${type}`;
}

function updateSpeechButtons() {
    const startBtn = document.getElementById('speechStartBtn');
    const stopBtn = document.getElementById('speechStopBtn');
    if (!startBtn || !stopBtn) return;
    if (!isInitialized) {
        startBtn.disabled = true;
        stopBtn.disabled = true;
        return;
    }
    startBtn.disabled = speechRecorderStarted;
    stopBtn.disabled = !speechRecorderStarted;
}

async function startSpeechRecording() {
    if (speechRecorderStarted) {
        updateSpeechStatus('录音已经在进行中', 'running');
        return;
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        updateSpeechStatus('当前浏览器不支持麦克风访问', 'error');
        return;
    }
    updateSpeechStatus('正在请求麦克风权限…', 'info');
    speechRecorderChunks = [];
    try {
        speechRecorderStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        speechRecorderContext = new AudioContextClass();
        const source = speechRecorderContext.createMediaStreamSource(speechRecorderStream);
        speechRecorderProcessor = speechRecorderContext.createScriptProcessor(4096, 1, 1);
        source.connect(speechRecorderProcessor);
        speechRecorderProcessor.connect(speechRecorderContext.destination);
        speechRecorderProcessor.onaudioprocess = (event) => {
            const inputBuffer = event.inputBuffer.getChannelData(0);
            const downsampled = downsampleBuffer(inputBuffer, speechRecorderContext.sampleRate, SPEECH_TARGET_SAMPLE_RATE);
            if (!downsampled) return;
            const pcm = floatTo16BitPCM(downsampled);
            if (pcm) speechRecorderChunks.push(pcm);
        };
        speechRecorderStarted = true;
        updateSpeechButtons();
        updateSpeechStatus('录音中…点击停止结束录音并开始识别', 'running');
    } catch (error) {
        console.error('启动录音失败:', error);
        updateSpeechStatus(`录音启动失败：${error.message}`, 'error');
        stopSpeechRecording(true);
    }
}

async function stopSpeechRecording(isAuto = false) {
    if (!speechRecorderStarted) {
        cleanupSpeechRecorder();
        updateSpeechButtons();
        if (!isAuto) updateSpeechStatus('未检测到录音', 'info');
        return;
    }
    cleanupSpeechRecorder();
    updateSpeechButtons();

    if (!speechRecorderChunks.length) {
        updateSpeechStatus('录音内容为空', 'error');
        return;
    }

    updateSpeechStatus('正在生成音频文件并提交识别…', 'running');
    const wavBlob = buildWavBlob(speechRecorderChunks, SPEECH_TARGET_SAMPLE_RATE);
    speechRecorderChunks = [];

    try {
        const formData = new FormData();
        formData.append('audio', wavBlob, `record_${Date.now()}.wav`);
        const response = await fetch('/api/speech/transcribe', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || '识别失败');
        }
        const autoSend = document.getElementById('speechAutoSend')?.checked;
        const transcript = data.transcript || '';
        if (autoSend && transcript) {
            const inputEl = document.getElementById('messageInput');
            if (inputEl) {
                const needsBreak = inputEl.value && !inputEl.value.endsWith('\n');
                inputEl.value = `${inputEl.value}${needsBreak ? '\n' : ''}${transcript}`;
            }
        }
        updateSpeechStatus(transcript ? `识别完成：${transcript}` : '识别完成，未返回文本', transcript ? 'running' : 'info');
    } catch (error) {
        console.error('上传或识别失败:', error);
        updateSpeechStatus(`语音识别失败：${error.message}`, 'error');
    }
}

function cleanupSpeechRecorder() {
    if (speechRecorderProcessor) {
        speechRecorderProcessor.disconnect();
        speechRecorderProcessor.onaudioprocess = null;
        speechRecorderProcessor = null;
    }
    if (speechRecorderContext) {
        speechRecorderContext.close().catch(() => {});
        speechRecorderContext = null;
    }
    if (speechRecorderStream) {
        speechRecorderStream.getTracks().forEach((track) => track.stop());
        speechRecorderStream = null;
    }
    speechRecorderStarted = false;
}

function downsampleBuffer(buffer, inputSampleRate, outputSampleRate) {
    if (outputSampleRate >= inputSampleRate) {
        return buffer;
    }
    const ratio = inputSampleRate / outputSampleRate;
    const newLength = Math.round(buffer.length / ratio);
    const result = new Float32Array(newLength);
    let offsetResult = 0;
    let offsetBuffer = 0;
    while (offsetResult < result.length) {
        const nextOffset = Math.round((offsetResult + 1) * ratio);
        let accum = 0;
        let count = 0;
        for (let i = offsetBuffer; i < nextOffset && i < buffer.length; i++) {
            accum += buffer[i];
            count++;
        }
        result[offsetResult] = count ? accum / count : 0;
        offsetResult++;
        offsetBuffer = nextOffset;
    }
    return result;
}

function floatTo16BitPCM(floatBuffer) {
    if (!floatBuffer) return null;
    const result = new Int16Array(floatBuffer.length);
    for (let i = 0; i < floatBuffer.length; i++) {
        let s = Math.max(-1, Math.min(1, floatBuffer[i]));
        result[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return result;
}

function buildWavBlob(int16Chunks, sampleRate) {
    const totalLength = int16Chunks.reduce((sum, chunk) => sum + chunk.length, 0);
    const buffer = new ArrayBuffer(44 + totalLength * 2);
    const view = new DataView(buffer);

    function writeString(offset, str) {
        for (let i = 0; i < str.length; i++) {
            view.setUint8(offset + i, str.charCodeAt(i));
        }
    }

    writeString(0, 'RIFF');
    view.setUint32(4, 36 + totalLength * 2, true);
    writeString(8, 'WAVE');
    writeString(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeString(36, 'data');
    view.setUint32(40, totalLength * 2, true);

    let offset = 44;
    for (const chunk of int16Chunks) {
        for (let i = 0; i < chunk.length; i++, offset += 2) {
            view.setInt16(offset, chunk[i], true);
        }
    }

    return new Blob([buffer], { type: 'audio/wav' });
}

function initialiseSpeechControls() {
    const startBtn = document.getElementById('speechStartBtn');
    const stopBtn = document.getElementById('speechStopBtn');
    if (!startBtn || !stopBtn) return;
    startBtn.addEventListener('click', () => startSpeechRecording());
    stopBtn.addEventListener('click', () => stopSpeechRecording(false));
    updateSpeechButtons();
    updateSpeechStatus('语音识别未启动');
}

window.addEventListener('beforeunload', () => stopSpeechRecording(true));

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialiseSpeechControls);
} else {
    initialiseSpeechControls();
}

