// 全局变量
let isInitialized = false;
let isLoading = false;

// 初始化学生
async function initStudent() {
    if (isLoading) return;
    
    const studentName = document.getElementById('studentName').value.trim() || '小明';
    const enableLongTermMemory = document.getElementById('enableLongTermMemory').checked;
    const enableKnowledgeBase = document.getElementById('enableKnowledgeBase').checked;
    
    isLoading = true;
    updateStatus('正在初始化虚拟学生...', 'success');
    
    try {
        const response = await fetch('/api/init', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                student_name: studentName,
                enable_long_term_memory: enableLongTermMemory,
                enable_knowledge_base: enableKnowledgeBase
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            isInitialized = true;
            updateStatus(`虚拟学生 ${data.student_name} 初始化成功！`, 'success');
            updateSpeechButtons();
            
            // 更新UI
            document.getElementById('initBtn').style.display = 'none';
            document.getElementById('resetBtn').style.display = 'inline-block';
            document.getElementById('messageInput').disabled = false;
            document.getElementById('sendBtn').disabled = false;
            document.getElementById('studentName').disabled = true;
            document.getElementById('enableLongTermMemory').disabled = true;
            document.getElementById('enableKnowledgeBase').disabled = true;
            
            // 清空聊天记录
            document.getElementById('chatMessages').innerHTML = '';
            
            // 添加欢迎消息
            addMessage('assistant', `你好，老师！我是${data.student_name}，${enableKnowledgeBase ? '已启用认知增强模式' : '已启用基础模式'}，准备开始学习！`);
            
            // 更新上下文
            updateContext();
        } else {
            updateStatus('初始化失败: ' + data.error, 'error');
        }
    } catch (error) {
        updateStatus('初始化失败: ' + error.message, 'error');
        console.error('初始化错误:', error);
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
        document.getElementById('studentName').disabled = false;
        document.getElementById('enableLongTermMemory').disabled = false;
        document.getElementById('enableKnowledgeBase').disabled = false;
        
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
    addMessage('user', message);
    input.value = '';
    
    // 显示加载状态
    const loadingId = addMessage('assistant', '正在思考...', true);
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
        
        if (data.success) {
            // 添加助手回复
            addMessage('assistant', data.response, false, data.tool_calls, data.intermediate_steps);
            
            // 更新上下文
            updateContext();
        } else {
            addMessage('assistant', '抱歉，处理消息时出错: ' + data.error);
        }
    } catch (error) {
        // 移除加载消息
        const loadingElement = document.getElementById(loadingId);
        if (loadingElement) {
            loadingElement.remove();
        }
        
        addMessage('assistant', '抱歉，发送消息时出错: ' + error.message);
        console.error('发送消息错误:', error);
    } finally {
        isLoading = false;
        document.getElementById('sendBtn').disabled = false;
        input.focus();
    }
}

// 添加消息到聊天界面
function addMessage(type, content, isLoading = false, toolCalls = [], intermediateSteps = []) {
    const messagesContainer = document.getElementById('chatMessages');
    const messageId = 'msg-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;
    messageDiv.id = messageId;
    
    const messageContent = document.createElement('div');
    messageContent.className = 'message-content';
    
    if (type === 'user') {
        messageContent.innerHTML = `
            <div class="message-header">老师</div>
            <div>${escapeHtml(content)}</div>
        `;
    } else {
        let html = `
            <div class="message-header">学生</div>
            <div>${escapeHtml(content)}</div>
        `;
        
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
    try {
        const response = await fetch('/api/context');
        const data = await response.json();
        
        if (data.success) {
            const contextInfo = document.getElementById('contextInfo');
            let html = '';
            
            // 学生信息
            html += `<div class="context-section">`;
            html += `<h3>学生信息</h3>`;
            html += `<p><span class="label">姓名:</span> ${escapeHtml(data.student_name)}</p>`;
            html += `<p><span class="label">长期记忆:</span> ${data.enable_long_term_memory ? '✅ 启用' : '❌ 禁用'}</p>`;
            html += `<p><span class="label">认知增强:</span> ${data.enable_knowledge_base ? '✅ 启用' : '❌ 禁用'}</p>`;
            html += `</div>`;
            
            // 短期记忆
            html += `<div class="context-section">`;
            html += `<h3>短期记忆 (${data.short_term_memory.length}/10)</h3>`;
            if (data.short_term_memory.length === 0) {
                html += `<p style="color: #999;">暂无短期记忆</p>`;
            } else {
                data.short_term_memory.forEach((conv, index) => {
                    html += `<div class="memory-item">`;
                    html += `<div class="timestamp">${new Date(conv.timestamp).toLocaleString()}</div>`;
                    html += `<div class="user-message">老师: ${escapeHtml(conv.user_message)}</div>`;
                    html += `<div class="assistant-message">学生: ${escapeHtml(conv.student_response.substring(0, 100))}${conv.student_response.length > 100 ? '...' : ''}</div>`;
                    html += `</div>`;
                });
            }
            html += `</div>`;
            
            // 长期记忆
            html += `<div class="context-section">`;
            html += `<h3>长期记忆</h3>`;
            if (data.long_term_context && data.long_term_context !== '长期记忆功能已禁用或未创建线程。' && data.long_term_context !== '没有找到相关的长期记忆。') {
                html += `<p style="white-space: pre-wrap; word-wrap: break-word;">${escapeHtml(data.long_term_context.substring(0, 500))}${data.long_term_context.length > 500 ? '...' : ''}</p>`;
            } else {
                html += `<p style="color: #999;">${data.long_term_context || '暂无长期记忆'}</p>`;
            }
            html += `</div>`;
            
            contextInfo.innerHTML = html;
        }
    } catch (error) {
        console.error('更新上下文错误:', error);
    }
}

// 更新状态显示
function updateStatus(message, type) {
    const statusDiv = document.getElementById('status');
    statusDiv.textContent = message;
    statusDiv.className = `status ${type}`;
    
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
