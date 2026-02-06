// 知识图谱可视化与编辑系统
let network = null;
let nodes = null;
let edges = null;
let nodesData = [];
let edgesData = [];
let currentSelectedNode = null;
let currentSelectedEdge = null;
let allNodesData = []; // 保存所有原始节点数据
let allEdgesData = []; // 保存所有原始边数据
let currentClusterMode = 'grade_status'; // 固定按年级聚合
let clusterMap = {}; // 聚合节点映射：clusterId -> [nodeIds]
let clusterInfo = {}; // 聚合节点信息：clusterId -> {label, count, group}

// 版本管理状态
let kgIndex = null;               // index.json
let currentStudentCN = null;      // 学生中文名
let currentStage = null;          // 主版本
let compareStage = null;          // 对比版本

// 初始化
document.addEventListener('DOMContentLoaded', async function() {
    // 初始化学生/版本选择
    await initVersionSelectors();
    // 加载图谱（如果版本选择已完成）
    if (currentStudentCN && currentStage) {
        await loadSelectedGraph();
    } else {
        loadKnowledgeGraph();
    }
});

// 加载知识图谱
async function loadKnowledgeGraph() {
    try {
        updateStatus('正在加载知识图谱...', 'loading');
        
        const response = await fetch('/api/kg/load');
        const data = await response.json();
        
        if (!data.success) {
            updateStatus('加载失败: ' + data.error, 'error');
            return;
        }
        
        // 保存原始数据
        allNodesData = data.nodes || [];
        allEdgesData = data.edges || [];
        nodesData = allNodesData;
        edgesData = allEdgesData;
        
        // 调试：检查数据
        console.log(`加载数据: ${allNodesData.length} 个节点, ${allEdgesData.length} 条边`);
        
        // 检查出版社+年级分布
        const publisherGradeDistribution = {};
        const gradeSet = new Set();
        const publisherSet = new Set();
        
        for (const node of allNodesData) {
            const publisher = node.publisher || '未分类';
            const grade = node.grade || '未分类';
            const key = `${publisher} - ${grade}`;
            publisherGradeDistribution[key] = (publisherGradeDistribution[key] || 0) + 1;
            gradeSet.add(grade);
            publisherSet.add(publisher);
        }
        
        console.log('出版社+年级分布:', publisherGradeDistribution);
        console.log('所有年级:', Array.from(gradeSet).sort());
        console.log('所有出版社:', Array.from(publisherSet).sort());
        console.log('出版社+年级组合总数:', Object.keys(publisherGradeDistribution).length);
        
        // 确保节点ID唯一
        const nodeIdSet = new Set();
        const uniqueNodesData = [];
        for (const node of nodesData) {
            if (!node.id) continue;
            if (!nodeIdSet.has(node.id)) {
                nodeIdSet.add(node.id);
                uniqueNodesData.push(node);
            }
        }
        nodesData = uniqueNodesData;
        
        // 确保边ID唯一，并处理重复的边
        const edgeIdSet = new Set();
        const uniqueEdgesData = [];
        let edgeCounter = 0;
        for (const edge of edgesData) {
            let edgeId = edge.id;
            // 如果ID已存在，生成新的唯一ID
            if (edgeIdSet.has(edgeId)) {
                edgeId = `${edge.id}-dup-${edgeCounter++}`;
            }
            if (edgeId) {
                edgeIdSet.add(edgeId);
                uniqueEdgesData.push({
                    ...edge,
                    id: edgeId
                });
            }
        }
        edgesData = uniqueEdgesData;
        
        // 转换为vis.js格式
        const visNodes = new vis.DataSet(nodesData.map(node => ({
            id: node.id,
            label: node.label,
            title: node.description || node.label,
            uuid: node.uuid,
            color: getNodeColor(node),
            font: { size: 14 },
            shape: 'box',
            margin: 10
        })));
        
        const visEdges = new vis.DataSet(edgesData.map(edge => ({
            id: edge.id,
            from: edge.from,
            to: edge.to,
            label: edge.label,
            title: edge.description || edge.label,
            arrows: 'to',
            color: getEdgeColor(edge.type),
            font: { size: 12, align: 'middle' }
        })));
        
        // 创建网络图
        const container = document.getElementById('knowledgeGraph');
        const graphData = {
            nodes: visNodes,
            edges: visEdges
        };
        
        const options = {
            nodes: {
                shape: 'box',
                font: {
                    size: 14,
                    color: '#333'
                },
                borderWidth: 2,
                shadow: false, // 禁用阴影，提高性能
                scaling: {
                    min: 10,
                    max: 30,
                    label: {
                        enabled: true,
                        min: 12,
                        max: 20
                    }
                },
                chosen: {
                    node: function(values, id, selected, hovering) {
                        if (selected || hovering) {
                            values.borderWidth = 4;
                            values.borderColor = '#667eea';
                        }
                    }
                }
            },
            edges: {
                arrows: {
                    to: {
                        enabled: true,
                        scaleFactor: 0.8
                    }
                },
                font: {
                    size: 12,
                    align: 'middle',
                    color: '#666'
                },
                smooth: {
                    type: 'dynamic', // 使用动态平滑，性能更好
                    roundness: 0.5
                },
                color: {
                    color: '#848484',
                    highlight: '#667eea'
                },
                width: 2,
                chosen: {
                    edge: function(values, id, selected, hovering) {
                        if (selected || hovering) {
                            values.width = 4;
                            values.color = '#667eea';
                        }
                    }
                },
                selectionWidth: 2, // 减少选中时的宽度变化
                shadow: false // 禁用阴影，提高性能
            },
            physics: {
                enabled: true,
                stabilization: {
                    enabled: true,
                    iterations: 200, // 增加迭代次数，确保稳定
                    fit: true,
                    updateInterval: 25
                },
                solver: 'forceAtlas2Based',
                forceAtlas2Based: {
                    gravitationalConstant: -50,
                    centralGravity: 0.01,
                    springLength: 100,
                    springConstant: 0.08,
                    damping: 0.9, // 增加阻尼，让节点更快稳定
                    avoidOverlap: 1
                },
                timestep: 0.35, // 减小时间步长，让节点更稳定
                adaptiveTimestep: true,
                barnesHut: {
                    gravitationalConstant: -2000,
                    centralGravity: 0.3,
                    springLength: 100,
                    springConstant: 0.04,
                    damping: 0.9,
                    avoidOverlap: 1
                }
            },
            interaction: {
                hover: true,
                tooltipDelay: 200, // 增加延迟，减少频繁计算
                hideEdgesOnDrag: true, // 拖拽时隐藏边，提高性能
                hideEdgesOnZoom: false,
                zoomView: true,
                dragView: true,
                selectConnectedEdges: false // 禁用选中连接边的功能，提高性能
            },
            layout: {
                improvedLayout: true
            }
        };
        
        network = new vis.Network(container, graphData, options);
        
        // 稳定化完成后禁用物理引擎，让节点位置固定
        network.on('stabilizationEnd', function() {
            network.setOptions({
                physics: {
                    enabled: false // 稳定化完成后禁用物理引擎，节点不再移动
                }
            });
            console.log('节点布局稳定完成，物理引擎已禁用');
        });
        
        // 事件监听
        network.on('click', function(params) {
            if (params.nodes.length > 0) {
                const nodeId = params.nodes[0];
                selectNode(nodeId);
            } else if (params.edges.length > 0) {
                const edgeId = params.edges[0];
                selectEdge(edgeId);
            } else {
                clearSelection();
            }
        });
        
        network.on('doubleClick', function(params) {
            if (params.nodes.length > 0) {
                const nodeId = params.nodes[0];
                // 检查是否是聚合节点
                if (nodeId.startsWith('cluster_')) {
                    // 检查是否是年级聚合节点（需要展开到状态分组）
                    if (nodeId.startsWith('cluster_grade_status_grade_')) {
                        expandGradeCluster(nodeId);
                    } 
                    // 检查是否是状态聚合节点（需要展开到原始节点）
                    else if (nodeId.startsWith('cluster_grade_status_status_')) {
                        expandCluster(nodeId);
                    } 
                    // 其他聚合节点
                    else {
                        expandCluster(nodeId);
                    }
                } else {
                    editNode(nodeId);
                }
            } else if (params.edges.length > 0) {
                const edgeId = params.edges[0];
                editEdge(edgeId);
            }
        });
        
        network.on('oncontext', function(params) {
            if (params.event) {
                params.event.preventDefault();
            }
            if (params.nodes.length > 0) {
                const nodeId = params.nodes[0];
                editNode(nodeId);
            } else if (params.edges.length > 0) {
                const edgeId = params.edges[0];
                editEdge(edgeId);
            }
        });
        
        // 启用保存按钮
        document.getElementById('saveBtn').disabled = false;
        document.getElementById('resetViewBtn').disabled = false;
        document.getElementById('fitViewBtn').disabled = false;
        // 固定聚合，无需启用聚合选择控件
        
        updateStatus(`加载成功: ${nodesData.length} 个节点, ${edgesData.length} 条边`, 'success');
        updateCounts(nodesData.length, edgesData.length);
        
        // 默认并固定为按年级聚合
        applyClusterMode('grade_status');
        
    } catch (error) {
        updateStatus('加载失败: ' + error.message, 'error');
        console.error('加载知识图谱错误:', error);
    }
}

// ====== 版本管理：加载 index，下拉选择，加载/设为当前/对比 ======
async function initVersionSelectors() {
    try {
        const resp = await fetch('/api/graph/index');
        const data = await resp.json();
        if (!data.success) return;
        kgIndex = data.data || {};
        const stuSel = document.getElementById('kgStudentSelect');
        const stageSel = document.getElementById('kgStageSelect');
        const cmpSel = document.getElementById('kgCompareStageSelect');
        if (!stuSel || !stageSel || !cmpSel) return;

        stuSel.innerHTML = '';
        Object.keys(kgIndex).forEach(cn => {
            const opt = document.createElement('option');
            opt.value = cn; opt.textContent = cn;
            // 默认选择崔展豪
            if (cn === '崔展豪') {
                opt.selected = true;
            }
            stuSel.appendChild(opt);
        });
        // 默认选择崔展豪作为学生
        currentStudentCN = '崔展豪' in kgIndex ? '崔展豪' : (stuSel.value || Object.keys(kgIndex)[0] || null);
        fillStagesFor(currentStudentCN);

        stuSel.addEventListener('change', () => {
            currentStudentCN = stuSel.value;
            fillStagesFor(currentStudentCN);
        });
    } catch (e) {
        console.warn('加载 index.json 失败', e);
    }
}

function fillStagesFor(studentCN) {
    const stageSel = document.getElementById('kgStageSelect');
    const cmpSel = document.getElementById('kgCompareStageSelect');
    const meta = document.getElementById('kgMetaInfo');
    if (!kgIndex || !kgIndex[studentCN]) return;
    const info = kgIndex[studentCN];
    const stages = info.stages || {};
    const current = info.current_stage;

    const sortedStages = Object.keys(stages).sort();
    stageSel.innerHTML = '';
    cmpSel.innerHTML = '<option value="">(不选择)</option>';
    sortedStages.forEach(ts => {
        const opt = document.createElement('option');
        opt.value = ts;
        opt.textContent = `${ts}${ts===current?'（当前）':''}`;
        stageSel.appendChild(opt);

        const opt2 = document.createElement('option');
        opt2.value = ts; opt2.textContent = ts;
        cmpSel.appendChild(opt2);
    });
    stageSel.value = current || sortedStages.at(-1) || '';
    currentStage = stageSel.value;
    meta.textContent = `当前学生：${studentCN}，当前版本：${current || '—'}`;
}

async function loadSelectedGraph() {
    const stu = document.getElementById('kgStudentSelect')?.value;
    const stage = document.getElementById('kgStageSelect')?.value;
    if (!stu || !stage) {
        updateStatus('请选择学生与版本后再加载图谱', 'error');
        return;
    }
    currentStudentCN = stu; currentStage = stage;
    try {
        updateStatus('正在加载图谱...', 'loading');
        const res = await fetch(`/api/kg/graph?student=${encodeURIComponent(stu)}&stage=${encodeURIComponent(stage)}`);
        const data = await res.json();
        if (!data.success) { updateStatus('加载失败：'+(data.error||''),'error'); return; }
        const { visNodes, visEdges } = normalizeGraphForVis(data.nodes, data.edges);
        allNodesData = visNodes;
        allEdgesData = visEdges;
        // 同步用于详情/编辑的数据源
        nodesData = allNodesData.slice();
        edgesData = allEdgesData.slice();
        // 确保网络实例已初始化
        initNetworkIfNeeded();
        applyClusterMode('grade_status');
        const wrap = document.getElementById('kgDiffSummary');
        if (wrap) { wrap.style.display = 'none'; wrap.innerHTML=''; }
        updateStatus(`加载成功: ${allNodesData.length} 个节点, ${allEdgesData.length} 条边`, 'success');
    } catch (e) {
        updateStatus('加载失败：'+(e.message||e), 'error');
        console.error('loadSelectedGraph error:', e);
    }
}

// 若尚未创建 network，则以通用配置初始化
function initNetworkIfNeeded() {
    if (network) return;
    const container = document.getElementById('knowledgeGraph');
    if (!container) return;
    const empty = { nodes: new vis.DataSet([]), edges: new vis.DataSet([]) };
    const options = {
        nodes: {
            shape: 'box',
            font: { size: 14, color: '#333' },
            borderWidth: 2,
            shadow: false,
            scaling: { min: 10, max: 30, label: { enabled: true, min: 12, max: 20 } },
            chosen: { node: function(values, id, selected, hovering) {
                if (selected || hovering) { values.borderWidth = 4; values.borderColor = '#667eea'; }
            }}
        },
        edges: {
            arrows: { to: { enabled: true, scaleFactor: 0.8 } },
            font: { size: 12, align: 'middle', color: '#666' },
            smooth: { type: 'dynamic', roundness: 0.5 },
            color: { color: '#848484', highlight: '#667eea' },
            width: 2,
            chosen: { edge: function(values, id, selected, hovering) {
                if (selected || hovering) { values.width = 4; values.color = '#667eea'; }
            }},
            selectionWidth: 2,
            shadow: false
        },
        physics: {
            enabled: true,
            stabilization: { enabled: true, iterations: 200, fit: true, updateInterval: 25 },
            solver: 'forceAtlas2Based',
            forceAtlas2Based: {
                gravitationalConstant: -50, centralGravity: 0.01,
                springLength: 100, springConstant: 0.08,
                damping: 0.9, avoidOverlap: 1
            },
            timestep: 0.35, adaptiveTimestep: true
        },
        interaction: {
            hover: true, tooltipDelay: 200,
            hideEdgesOnDrag: true, hideEdgesOnZoom: false,
            zoomView: true, dragView: true, selectConnectedEdges: false
        },
        layout: { improvedLayout: true }
    };
    network = new vis.Network(container, empty, options);
    network.on('stabilizationEnd', function() {
        network.setOptions({ physics: { enabled: false } });
    });
    // 关键事件：点击/双击支持展开
    network.on('click', function(params) {
        if (params.nodes && params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            // 聚合节点不展示详情，仅用于展开
            if (typeof nodeId === 'string' && nodeId.startsWith('cluster_')) {
                return;
            }
            selectNode(nodeId);
            return;
        }
        if (params.edges && params.edges.length > 0) {
            const edgeId = params.edges[0];
            selectEdge(edgeId);
            return;
        }
        clearSelection();
    });
    network.on('doubleClick', function(params) {
        if (params.nodes && params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            if (typeof nodeId === 'string' && nodeId.startsWith('cluster_')) {
                if (nodeId.startsWith('cluster_grade_status_grade_')) {
                    expandGradeCluster(nodeId);
                } else if (nodeId.startsWith('cluster_grade_status_status_')) {
                    expandCluster(nodeId);
                } else {
                    expandCluster(nodeId);
                }
            } else if (nodeId) {
                editNode(nodeId);
            }
        } else if (params.edges && params.edges.length > 0) {
            const edgeId = params.edges[0];
            if (edgeId) editEdge(edgeId);
        }
    });
}

async function setSelectedAsCurrent() {
    const stu = document.getElementById('kgStudentSelect')?.value;
    const stage = document.getElementById('kgStageSelect')?.value;
    if (!stu || !stage) return;
    const resp = await fetch('/api/graph/set_current', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ student: stu, stage })
    });
    const data = await resp.json();
    if (!data.success) { updateStatus('设置当前版本失败：'+(data.error||''),'error'); return; }
    // 不刷新整体选择，仅在内存与UI中标注当前版本
    if (kgIndex && kgIndex[stu]) {
        kgIndex[stu].current_stage = stage;
    }
    // 更新下拉选项的“（当前）”标记
    const stageSel = document.getElementById('kgStageSelect');
    if (stageSel) {
        for (let i = 0; i < stageSel.options.length; i++) {
            const opt = stageSel.options[i];
            const rawVal = opt.value;
            // 去掉旧标记
            opt.textContent = rawVal + (rawVal === stage ? '（当前）' : '');
        }
    }
    const meta = document.getElementById('kgMetaInfo');
    if (meta) meta.textContent = `当前学生：${stu}，当前版本：${stage}`;
    updateStatus('已设置为当前版本（无需刷新）','success');
}

async function compareTwoStages() {
    const stu = document.getElementById('kgStudentSelect')?.value;
    const stageA = document.getElementById('kgStageSelect')?.value;
    const stageB = document.getElementById('kgCompareStageSelect')?.value;
    if (!stu || !stageA || !stageB) { updateStatus('请选择学生与两个版本','error'); return; }
    if (stageA === stageB) { updateStatus('两个版本不能相同','error'); return; }
    const [resA, resB] = await Promise.all([
        fetch(`/api/kg/graph?student=${encodeURIComponent(stu)}&stage=${encodeURIComponent(stageA)}`).then(r=>r.json()),
        fetch(`/api/kg/graph?student=${encodeURIComponent(stu)}&stage=${encodeURIComponent(stageB)}`).then(r=>r.json())
    ]);
    if (!resA.success || !resB.success) { updateStatus('加载版本数据失败','error'); return; }
    // 按要求：比较“目标版本 -> 基准版本”
    // stageA = 目标版本（当前选择的版本），stageB = 基准版本（对比版本）
    const base = normalizeGraphForVis(resB.nodes, resB.edges);   // 基准
    const target = normalizeGraphForVis(resA.nodes, resA.edges); // 目标
    const diff = diffGraphs(base, target);
    // 不改变当前画布，只生成摘要
    renderDiffSummary(stu, stageA, stageB, diff);
}

function normalizeGraphForVis(nodes, edges) {
    const visNodes = (nodes||[]).map(n => {
        const p = n.properties || {};
        // 解析 QA 对（可能为数组或 JSON 字符串）
        let qaPairs = [];
        if (Array.isArray(p.bloom_qa_pairs)) {
            qaPairs = p.bloom_qa_pairs;
        } else if (typeof p.bloom_qa_pairs === 'string') {
            try { qaPairs = JSON.parse(p.bloom_qa_pairs) || []; } catch(e) { qaPairs = []; }
        }
        // 统一 status 为三维向量（仅 0/1；1 保留为 1，其它→0）
        const ensureStatusVector = (val) => {
            const toBin = (x) => {
                const v = parseInt(x, 10);
                return v === 1 ? 1 : 0;
            };
            if (Array.isArray(val) && val.length === 3) {
                return [toBin(val[0]), toBin(val[1]), toBin(val[2])];
            }
            const iv = (val === undefined || val === null) ? 0 : parseInt(val, 10);
            return [toBin(iv), 0, 0];
        };
        const statusVec = ensureStatusVector(p.status);
        return {
            id: p.uuid || p.node_name || Math.random().toString(36).slice(2),
            uuid: p.uuid,
            node_name: p.node_name,
            label: p.node_name,
            description: p.description,
            grade: p.grade,
            subject: p.subject,
            publisher: p.publisher,
            status: statusVec,
            bloom_qa_pairs: qaPairs
        };
    });
    const visEdges = (edges||[]).map((e, i) => ({
        id: `e_${i}_${e.start_uuid}_${e.end_uuid}_${e.type}`,
        from: e.start_uuid,
        to: e.end_uuid,
        type: e.type,
        label: e.type,
        description: (e.properties||{}).description || ''
    }));
    return { visNodes, visEdges };
}

function diffGraphs(base, target) {
    const bNodes = new Map((base.visNodes||[]).map(n => [n.uuid, n]));
    const tNodes = new Map((target.visNodes||[]).map(n => [n.uuid, n]));
    const bEdges = new Set((base.visEdges||[]).map(e => `${e.from}|${e.type}|${e.to}`));
    const tEdges = new Set((target.visEdges||[]).map(e => `${e.from}|${e.type}|${e.to}`));

    const addedNodes = [];
    const removedNodes = [];
    const changedNodes = [];

    tNodes.forEach((tn, id) => {
        if (!bNodes.has(id)) {
            addedNodes.push(tn);
        } else {
            const bn = bNodes.get(id);
            const changedFields = [];
            const deepEqualStatus = (a, b) => {
                if (Array.isArray(a) && Array.isArray(b) && a.length === b.length) {
                    for (let i = 0; i < a.length; i++) {
                        if (String(a[i]) !== String(b[i])) return false;
                    }
                    return true;
                }
                return String(a) === String(b);
            };
            ['node_name','description','grade','subject','publisher','status'].forEach(k => {
                if (k === 'status') {
                    if (!deepEqualStatus(bn[k], tn[k])) changedFields.push({field:k, from:bn[k], to:tn[k]});
                } else {
                    if (String(bn[k]||'') !== String(tn[k]||'')) changedFields.push({field:k, from:bn[k], to:tn[k]});
                }
            });
            if (changedFields.length) changedNodes.push({ node: tn, changes: changedFields });
        }
    });
    bNodes.forEach((bn, id) => { if (!tNodes.has(id)) removedNodes.push(bn); });

    const addedEdges = [];
    const removedEdges = [];
    tEdges.forEach(key => { if (!bEdges.has(key)) addedEdges.push(key); });
    bEdges.forEach(key => { if (!tEdges.has(key)) removedEdges.push(key); });
    return { addedNodes, removedNodes, changedNodes, addedEdges, removedEdges };
}

function applyDiffHighlight(diff) {
    if (!network) return;
    const visNodes = network.body.data.nodes;
    const visEdges = network.body.data.edges;
    const green = { background:'#d1fae5', border:'#10b981' };
    const orange = { background:'#fff7ed', border:'#f59e0b' };
    diff.addedNodes.forEach(n => { if (visNodes.get(n.uuid)) visNodes.update({ id: n.uuid, color: green, borderWidth: 3 }); });
    diff.changedNodes.forEach(({node:n}) => { if (visNodes.get(n.uuid)) visNodes.update({ id: n.uuid, color: orange, borderWidth: 3 }); });
    diff.addedEdges.forEach(k => {
        const e = Array.from(visEdges.get()).find(e => `${e.from}|${e.label||''}|${e.to}` === k || `${e.from}|${e.type||''}|${e.to}` === k);
        if (e) visEdges.update({ id: e.id, width: 4, color: { color:'#10b981', highlight:'#10b981' } });
    });
}

function renderDiffSummary(studentCN, stageA, stageB, diff) {
    const wrap = document.getElementById('kgDiffSummary');
    if (!wrap) return;
    // 仅展示：变更了哪个年级的哪个节点，status 变化情况
    // 从变更节点中筛选出 status 发生变化的项
    const statusChanged = (diff.changedNodes || []).map(item => {
        const statusChange = (item.changes || []).find(ch => ch.field === 'status');
        if (!statusChange) return null;
        const node = item.node || {};
        // 强化：将 "x,y,z" 或 单值 映射为三维向量或保持原值，便于后续比较
        const toVec = (v) => {
            if (Array.isArray(v)) return v;
            if (typeof v === 'string') {
                const parts = v.split(',').map(s => s.trim());
                if (parts.length === 3 && parts.every(p => /^-?\d+$/.test(p))) {
                    return parts.map(x => parseInt(x, 10));
                }
            }
            return v;
        };
        const fromN = toVec(statusChange.from);
        const toN = toVec(statusChange.to);
        return {
            grade: node.grade || '未分类',
            name: node.node_name || node.uuid || '',
            from: fromN,
            to: toN
        };
    }).filter(Boolean);

    // 按年级分组
    const byGrade = {};
    statusChanged.forEach(entry => {
        if (!byGrade[entry.grade]) byGrade[entry.grade] = [];
        byGrade[entry.grade].push(entry);
    });

    // 生成摘要文本
    const lines = [];
    // 文案：目标版本 -> 基准版本
    lines.push(`对比学生：${studentCN}，目标版本：${stageA} → 基准版本：${stageB}`);
    if (statusChanged.length === 0) {
        lines.push('本次对比未发现状态（status）变更。');
    } else {
        Object.keys(byGrade).sort().forEach(grade => {
            lines.push(`年级：${grade}`);
            byGrade[grade].forEach(e => {
                // 跳过完全相同的情况
                const sameScalar = (!Array.isArray(e.from) && !Array.isArray(e.to) && String(e.from) === String(e.to));
                const sameVector = (Array.isArray(e.from) && Array.isArray(e.to) &&
                                    e.from.length === e.to.length &&
                                    e.from.every((v, i) => String(v) === String(e.to[i])));
                if (sameScalar || sameVector) return;

                if (Array.isArray(e.from) && Array.isArray(e.to) && e.from.length === 3 && e.to.length === 3) {
                    const dims = ['记忆/理解', '应用/分析', '评价/创造'];
                    let anyDim = false;
                    const dimLines = [];
                    for (let i = 0; i < 3; i++) {
                        if (e.from[i] !== e.to[i]) {
                            anyDim = true;
                            dimLines.push(`      • ${dims[i]}：${String(e.from[i])} → ${String(e.to[i])}`);
                        }
                    }
                    if (anyDim) {
                        lines.push(`  - 节点：${e.name}`);
                        dimLines.forEach(dl => lines.push(dl));
                    }
                } else {
                    lines.push(`  - 节点：${e.name}，status：${String(e.from)} → ${String(e.to)}`);
                }
            });
        });
    }
    // 使用更紧凑的黄框摘要可视化（限制尺寸 + 列表格式 + 表情）
    const header = `
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
        <span style="font-weight:700;">📝 版本对比摘要</span>
        <span style="font-size:12px;color:#b45309;">（目标：${studentCN ? '👩‍🎓 ' + studentCN : ''} ${stageA} → 基准：${stageB}）</span>
      </div>
    `;
    let bodyHtml = '';
    if (statusChanged.length === 0) {
        bodyHtml = `<div style="color:#b45309;">✅ 本次对比未发现状态（status）变更</div>`;
    } else {
        const gradeKeys = Object.keys(byGrade).sort();
        bodyHtml = gradeKeys.map(grade => {
            const items = byGrade[grade]
              .map(e => `<li style="margin:2px 0;">🔸 <span style="font-weight:600;">${escapeHtml(e.name)}</span> <span style="opacity:.75;">status</span>：<span style="color:#16a34a;">${String(e.from)}</span> → <span style="color:#dc2626;">${String(e.to)}</span></li>`)
              .join('');
            return `
              <div style="margin:6px 0 8px;">
                <div style="font-weight:600;margin:2px 0;">🗂️ 年级：${escapeHtml(grade)}</div>
                <ul style="margin:0 0 0 18px;padding:0;">${items}</ul>
              </div>
            `;
        }).join('');
    }
    wrap.innerHTML = `
      <div style="
        display:inline-block;
        padding:8px 10px;
        border:1px solid #f59e0b;
        background:#FFFBEB;
        color:#92400e;
        border-radius:8px;
        line-height:1.55;
        box-shadow:0 1px 2px rgba(0,0,0,0.06);
        max-width:520px;
        max-height:180px;
        overflow:auto;
      ">
        ${header}
        <div style="font-size:12.5px;">
          ${bodyHtml}
        </div>
      </div>
    `;
    wrap.style.display = 'block';
}
// 保存知识图谱
async function saveKnowledgeGraph() {
    if (!confirm('确定要保存知识图谱吗？这将覆盖原文件（已自动创建备份）。')) {
        return;
    }
    
    try {
        updateStatus('正在保存知识图谱...', 'loading');
        
        const response = await fetch('/api/kg/save', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                nodes: nodesData,
                edges: edgesData
            })
        });
        
        const data = await response.json();
        
        if (!data.success) {
            updateStatus('保存失败: ' + data.error, 'error');
            return;
        }
        
        updateStatus(`保存成功: ${data.nodes_count} 个节点, ${data.edges_count} 条边`, 'success');
        
    } catch (error) {
        updateStatus('保存失败: ' + error.message, 'error');
        console.error('保存知识图谱错误:', error);
    }
}

// 上传到图数据库
async function uploadToGraphDB() {
    if (!confirm('确定要将当前图谱上传到图数据库吗？')) {
        return;
    }
    
    try {
        updateStatus('正在上传到图数据库...', 'loading');
        
        const response = await fetch('/api/kg/upload', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                nodes: nodesData,
                edges: edgesData,
                student: currentStudentCN
            })
        });
        
        const data = await response.json();
        
        if (!data.success) {
            updateStatus('上传失败: ' + data.error, 'error');
            return;
        }
        
        updateStatus(`上传成功: ${data.nodes_count} 个节点, ${data.edges_count} 条边已上传到图数据库`, 'success');
        
    } catch (error) {
        updateStatus('上传失败: ' + error.message, 'error');
        console.error('上传到图数据库错误:', error);
    }
}

// 从图数据库拉取
async function pullFromGraphDB() {
    if (!currentStudentCN) {
        updateStatus('请先选择学生', 'error');
        return;
    }
    
    if (!confirm(`确定要从图数据库拉取 ${currentStudentCN} 的最新图谱吗？这将创建一个新版本并自动加载。`)) {
        return;
    }
    
    try {
        updateStatus('正在从图数据库拉取图谱...', 'loading');
        
        const response = await fetch('/api/kg/pull', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                student: currentStudentCN
            })
        });
        
        const data = await response.json();
        
        if (!data.success) {
            updateStatus('拉取失败: ' + data.error, 'error');
            return;
        }
        
        // 重新加载版本列表
        await initVersionSelectors();
        fillStagesFor(currentStudentCN);
        
        // 保存原始数据
        allNodesData = data.nodes || [];
        allEdgesData = data.edges || [];
        nodesData = allNodesData;
        edgesData = allEdgesData;
        
        // 确保网络实例已初始化
        initNetworkIfNeeded();
        
        // 转换为vis.js格式
        const visNodes = new vis.DataSet(nodesData.map(node => ({
            id: node.id,
            label: node.label,
            title: node.description || node.label,
            uuid: node.uuid,
            color: getNodeColor(node),
            font: { size: 14 },
            shape: 'box',
            margin: 10
        })));
        
        const visEdges = new vis.DataSet(edgesData.map(edge => ({
            id: edge.id,
            from: edge.from,
            to: edge.to,
            label: edge.label,
            title: edge.description || edge.label,
            arrows: 'to',
            color: getEdgeColor(edge.type),
            font: { size: 12, align: 'middle' }
        })));
        
        // 更新网络数据
        network.setData({
            nodes: visNodes,
            edges: visEdges
        });
        
        // 应用聚合
        applyClusterMode('grade_status');
        
        // 提示用户
        updateStatus(`拉取成功: 已创建并加载新版本 ${data.new_version}，包含 ${data.nodes_count} 个节点和 ${data.edges_count} 条边。`, 'success');
        updateCounts(data.nodes_count, data.edges_count);
        
    } catch (error) {
        updateStatus('拉取失败: ' + error.message, 'error');
        console.error('从图数据库拉取错误:', error);
    }
}

// 删除当前版本
async function deleteCurrentVersion() {
    if (!currentStudentCN || !currentStage) {
        updateStatus('请先选择学生和版本', 'error');
        return;
    }
    
    if (!confirm(`确定要删除 ${currentStudentCN} 的当前版本 ${currentStage} 吗？此操作不可恢复。`)) {
        return;
    }
    
    try {
        updateStatus('正在删除当前版本...', 'loading');
        
        const response = await fetch('/api/kg/delete_version', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                student: currentStudentCN,
                stage: currentStage
            })
        });
        
        const data = await response.json();
        
        if (!data.success) {
            updateStatus('删除失败: ' + data.error, 'error');
            return;
        }
        
        // 重新加载版本列表
        await initVersionSelectors();
        fillStagesFor(currentStudentCN);
        
        // 提示用户
        updateStatus(`删除成功: 已删除版本 ${currentStage}`, 'success');
        
    } catch (error) {
        updateStatus('删除失败: ' + error.message, 'error');
        console.error('删除版本错误:', error);
    }
}

// 选择节点
function selectNode(nodeId) {
    currentSelectedNode = nodesData.find(n => n.id === nodeId);
    currentSelectedEdge = null;
    
    if (currentSelectedNode) {
        showNodeDetail(currentSelectedNode);
    }
}

// 选择边
function selectEdge(edgeId) {
    currentSelectedEdge = edgesData.find(e => e.id === edgeId);
    currentSelectedNode = null;
    
    if (currentSelectedEdge) {
        showEdgeDetail(currentSelectedEdge);
    }
}

// 清除选择
function clearSelection() {
    currentSelectedNode = null;
    currentSelectedEdge = null;
    document.getElementById('detailContent').innerHTML = '<p class="placeholder">点击节点或边查看详情</p>';
}

// 显示节点详情
function showNodeDetail(node) {
    const detailContent = document.getElementById('detailContent');
    const renderStatusBadges = (vec) => {
        const v = Array.isArray(vec) && vec.length === 3 ? vec : [0,0,0];
        const badge = (label, val, colorBg, colorBorder) => `
            <span style="display:inline-block;padding:2px 6px;border-radius:12px;margin-right:6px;
                         font-size:12px;border:1px solid ${colorBorder};
                         background:${val>0 ? colorBg : '#f3f4f6'};color:${val>0 ? '#111827' : '#6b7280'};">
              ${label}: ${val}
            </span>`;
        return `
          <div style="margin-top:4px;">
            ${badge('记忆/理解', v[0], '#DBEAFE', '#93C5FD')}
            ${badge('应用/分析', v[1], '#DCFCE7', '#86EFAC')}
            ${badge('评价/创造', v[2], '#EDE9FE', '#C4B5FD')}
            <span style="margin-left:6px;color:#6b7280;font-size:12px;">raw: [${v.join(', ')}]</span>
          </div>
        `;
    };
    // QA 列表（默认展示前5条，可展开更多）
    let qaHtml = '';
    const qa = Array.isArray(node.bloom_qa_pairs) ? node.bloom_qa_pairs : [];
    if (qa.length > 0) {
        const maxShow = 5;
        const head = qa.slice(0, maxShow).map((item, idx) => {
            const level = item.level_zh || item.level || '—';
            const q = (item.question || '').toString();
            const a = (item.answer || '').toString();
            return `
                <div style="border:1px solid #e5e7eb;border-radius:6px;padding:8px;margin:6px 0;">
                    <div style="font-weight:600;color:#374151;">${idx+1}. ${escapeHtml(level)}</div>
                    <div style="color:#4b5563;margin-top:4px;">❓ ${escapeHtml(q)}</div>
                    <div style="color:#111827;margin-top:2px;">✅ ${escapeHtml(a)}</div>
                </div>
            `;
        }).join('');
        const tailCount = qa.length - maxShow;
        const tailBtn = tailCount > 0
            ? `<button id="qaExpandBtn" style="margin-top:6px;padding:4px 8px;border:1px solid #d1d5db;border-radius:6px;background:#fff;cursor:pointer;">展开剩余 ${tailCount} 条</button>`
            : '';
        qaHtml = `
            <div class="detail-section">
                <h3>认知问答对（${qa.length}）</h3>
                <div id="qaList">${head}</div>
                ${tailBtn}
            </div>
        `;
        // 绑定一次性展开逻辑
        setTimeout(() => {
            const btn = document.getElementById('qaExpandBtn');
            if (!btn) return;
            btn.addEventListener('click', () => {
                const list = document.getElementById('qaList');
                const more = qa.slice(maxShow).map((item, idx) => {
                    const level = item.level_zh || item.level || '—';
                    const q = (item.question || '').toString();
                    const a = (item.answer || '').toString();
                    const seq = idx + maxShow + 1;
                    return `
                        <div style="border:1px solid #e5e7eb;border-radius:6px;padding:8px;margin:6px 0;">
                            <div style="font-weight:600;color:#374151;">${seq}. ${escapeHtml(level)}</div>
                            <div style="color:#4b5563;margin-top:4px;">❓ ${escapeHtml(q)}</div>
                            <div style="color:#111827;margin-top:2px;">✅ ${escapeHtml(a)}</div>
                        </div>
                    `;
                }).join('');
                if (list) list.insertAdjacentHTML('beforeend', more);
                btn.remove();
            });
        }, 0);
    }

    let html = `
        <div class="detail-section">
            <h3>节点详情</h3>
            <div class="detail-item">
                <label>节点名称:</label>
                <span>${escapeHtml(node.node_name || '')}</span>
            </div>
            <div class="detail-item">
                <label>UUID:</label>
                <span class="uuid">${escapeHtml(node.uuid || '')}</span>
            </div>
            <div class="detail-item">
                <label>描述:</label>
                <span>${escapeHtml(node.description || '')}</span>
            </div>
            <div class="detail-item">
                <label>年级:</label>
                <span>${escapeHtml(node.grade || '')}</span>
            </div>
            <div class="detail-item">
                <label>学科:</label>
                <span>${escapeHtml(node.subject || '')}</span>
            </div>
            <div class="detail-item">
                <label>出版社:</label>
                <span>${escapeHtml(node.publisher || '')}</span>
            </div>
            <div class="detail-item">
                <label>掌握向量:</label>
                <span>${renderStatusBadges(node.status)}</span>
            </div>
            <div class="detail-actions">
                <button onclick="editNode('${node.id}')">编辑节点</button>
            </div>
        </div>
        ${qaHtml}
    `;
    detailContent.innerHTML = html;
}

// 显示边详情
function showEdgeDetail(edge) {
    const detailContent = document.getElementById('detailContent');
    let html = `
        <div class="detail-section">
            <h3>边详情</h3>
            <div class="detail-item">
                <label>关系类型:</label>
                <span>${escapeHtml(edge.type || edge.label || '')}</span>
            </div>
            <div class="detail-item">
                <label>描述:</label>
                <span>${escapeHtml(edge.description || '')}</span>
            </div>
            <div class="detail-item">
                <label>起始节点:</label>
                <span class="uuid">${escapeHtml(edge.start_uuid || '')}</span>
            </div>
            <div class="detail-item">
                <label>目标节点:</label>
                <span class="uuid">${escapeHtml(edge.end_uuid || '')}</span>
            </div>
            <div class="detail-actions">
                <button onclick="editEdge('${edge.id}')">编辑边</button>
            </div>
        </div>
    `;
    detailContent.innerHTML = html;
}

// 编辑节点
function editNode(nodeId) {
    const node = nodesData.find(n => n.id === nodeId);
    if (!node) return;
    
    document.getElementById('editNodeUuid').value = node.uuid;
    document.getElementById('editNodeName').value = node.node_name || '';
    document.getElementById('editNodeDescription').value = node.description || '';
    document.getElementById('editNodeGrade').value = node.grade || '';
    document.getElementById('editNodeSubject').value = node.subject || '';
    document.getElementById('editNodePublisher').value = node.publisher || '';
    // 设置三维向量复选框
    (function setStatusNumbers(){
        const v = (Array.isArray(node.status) && node.status.length === 3) ? node.status : [0,0,0];
        const wrap = document.getElementById('editStatusVector');
        if (!wrap) return;
        const nums = wrap.querySelectorAll('.status-number');
        nums.forEach(input => {
            const idx = parseInt(input.getAttribute('data-index'), 10);
            input.value = v[idx];
        });
    })();

    // 渲染 QA 编辑区域
    renderQaEditor(Array.isArray(node.bloom_qa_pairs) ? node.bloom_qa_pairs : []);
    const addBtn = document.getElementById('qaAddBtn');
    if (addBtn) {
        addBtn.onclick = () => addQaRow();
    }
    
    document.getElementById('nodeEditModal').style.display = 'flex';
}

// ===== QA 编辑辅助 =====
function renderQaEditor(pairs) {
    const wrap = document.getElementById('editNodeQA');
    if (!wrap) return;
    const safePairs = Array.isArray(pairs) ? pairs : [];
    wrap.innerHTML = safePairs.map((p, idx) => qaRowTemplate(p, idx)).join('');
}

function qaRowTemplate(p = {}, idx = 0) {
    const level = (p.level_zh || p.level || '').toString();
    const q = (p.question || '').toString();
    const a = (p.answer || '').toString();
    return `
    <div class="qa-row" style="border:1px solid #e5e7eb;border-radius:6px;padding:8px;margin:6px 0;">
        <div style="display:flex;gap:8px;align-items:center;margin-bottom:6px;">
            <label style="min-width:56px;color:#374151;">等级</label>
            <input type="text" class="qa-level" value="${escapeHtml(level)}" placeholder="如：记忆/理解/Apply…" style="flex:1;">
            <button type="button" class="qa-del-btn" title="删除" style="padding:4px 8px;border:1px solid #ef4444;background:#fff;color:#ef4444;border-radius:6px;cursor:pointer;">删除</button>
        </div>
        <div style="display:flex;gap:8px;align-items:flex-start;margin-bottom:6px;">
            <label style="min-width:56px;color:#374151;">问题</label>
            <textarea class="qa-question" rows="2" style="flex:1;">${escapeHtml(q)}</textarea>
        </div>
        <div style="display:flex;gap:8px;align-items:flex-start;">
            <label style="min-width:56px;color:#374151;">答案</label>
            <textarea class="qa-answer" rows="2" style="flex:1;">${escapeHtml(a)}</textarea>
        </div>
    </div>
    `;
}

function addQaRow() {
    const wrap = document.getElementById('editNodeQA');
    if (!wrap) return;
    wrap.insertAdjacentHTML('beforeend', qaRowTemplate({}, 0));
    bindQaDeleteButtons();
}

function bindQaDeleteButtons() {
    const wrap = document.getElementById('editNodeQA');
    if (!wrap) return;
    wrap.querySelectorAll('.qa-del-btn').forEach(btn => {
        if (btn.dataset.bound === '1') return;
        btn.dataset.bound = '1';
        btn.addEventListener('click', () => {
            const row = btn.closest('.qa-row');
            if (row) row.remove();
        });
    });
}

function collectQaFromEditor() {
    const wrap = document.getElementById('editNodeQA');
    if (!wrap) return [];
    const rows = Array.from(wrap.querySelectorAll('.qa-row'));
    const result = rows.map(row => {
        const level = (row.querySelector('.qa-level')?.value || '').trim();
        const question = (row.querySelector('.qa-question')?.value || '').trim();
        const answer = (row.querySelector('.qa-answer')?.value || '').trim();
        const obj = {};
        if (level) obj.level_zh = level;
        if (question) obj.question = question;
        if (answer) obj.answer = answer;
        return obj;
    }).filter(o => Object.keys(o).length > 0);
    return result;
}
// 关闭节点编辑模态框
function closeNodeEditModal() {
    document.getElementById('nodeEditModal').style.display = 'none';
}

// 保存节点编辑
async function saveNodeEdit() {
    const uuid = document.getElementById('editNodeUuid').value;
    const qaPairs = collectQaFromEditor();
    // 收集三维向量
    const statusVec = (() => {
        const wrap = document.getElementById('editStatusVector');
        const nums = wrap ? wrap.querySelectorAll('.status-number') : [];
        const v = [0,0,0];
        nums.forEach(input => {
            const idx = parseInt(input.getAttribute('data-index'), 10);
            const val = parseInt(input.value, 10);
            if (!isNaN(idx) && idx >= 0 && idx < 3) {
                v[idx] = isNaN(val) ? 0 : Math.max(-2, Math.min(2, val));
            }
        });
        return v;
    })();
    const nodeData = {
        uuid: uuid,
        node_name: document.getElementById('editNodeName').value,
        description: document.getElementById('editNodeDescription').value,
        grade: document.getElementById('editNodeGrade').value,
        subject: document.getElementById('editNodeSubject').value,
        publisher: document.getElementById('editNodePublisher').value,
        status: statusVec,
        student: document.getElementById('kgStudentSelect')?.value || '',
        stage: document.getElementById('kgStageSelect')?.value || '',
        bloom_qa_pairs: qaPairs
    };
    
    try {
        updateStatus('正在保存节点...', 'loading');
        
        const response = await fetch('/api/kg/node/update', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(nodeData)
        });
        
        const data = await response.json();
        
        if (!data.success) {
            updateStatus('保存失败: ' + data.error, 'error');
            return;
        }
        
        // 更新本地数据
        const nodeIndex = nodesData.findIndex(n => n.uuid === uuid);
        if (nodeIndex !== -1) {
            nodesData[nodeIndex] = { ...nodesData[nodeIndex], ...nodeData };
            
            // 更新网络图
            const visNodes = network.body.data.nodes;
            const visNode = visNodes.get(nodesData[nodeIndex].id);
            if (visNode) {
                visNode.label = nodeData.node_name;
                visNode.title = nodeData.description || nodeData.node_name;
                visNodes.update(visNode);
            }
        }
        
        closeNodeEditModal();
        updateStatus('节点保存成功', 'success');
        
        // 如果当前选中了这个节点，刷新详情
        if (currentSelectedNode && currentSelectedNode.uuid === uuid) {
            selectNode(nodesData[nodeIndex].id);
        }
        
    } catch (error) {
        updateStatus('保存失败: ' + error.message, 'error');
        console.error('保存节点错误:', error);
    }
}

// 编辑边
function editEdge(edgeId) {
    const edge = edgesData.find(e => e.id === edgeId);
    if (!edge) return;
    
    document.getElementById('editEdgeStartUuid').value = edge.start_uuid;
    document.getElementById('editEdgeEndUuid').value = edge.end_uuid;
    document.getElementById('editEdgeType').value = edge.type || '';
    document.getElementById('editEdgeDescription').value = edge.description || '';
    
    document.getElementById('edgeEditModal').style.display = 'flex';
}

// 关闭边编辑模态框
function closeEdgeEditModal() {
    document.getElementById('edgeEditModal').style.display = 'none';
}

// 保存边编辑
async function saveEdgeEdit() {
    const edgeData = {
        start_uuid: document.getElementById('editEdgeStartUuid').value,
        end_uuid: document.getElementById('editEdgeEndUuid').value,
        type: document.getElementById('editEdgeType').value,
        description: document.getElementById('editEdgeDescription').value,
        student: document.getElementById('kgStudentSelect')?.value || '',
        stage: document.getElementById('kgStageSelect')?.value || ''
    };
    
    try {
        updateStatus('正在保存边...', 'loading');
        
        const response = await fetch('/api/kg/edge/update', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(edgeData)
        });
        
        const data = await response.json();
        
        if (!data.success) {
            updateStatus('保存失败: ' + data.error, 'error');
            return;
        }
        
        // 更新本地数据：优先通过 id 匹配
        let edgeIndex = -1;
        if (currentSelectedEdge && currentSelectedEdge.id) {
            edgeIndex = edgesData.findIndex(e => e.id === currentSelectedEdge.id);
        }
        if (edgeIndex === -1) {
            edgeIndex = edgesData.findIndex(e => e.start_uuid === edgeData.start_uuid && e.end_uuid === edgeData.end_uuid);
        }
        if (edgeIndex !== -1) {
            edgesData[edgeIndex] = { ...edgesData[edgeIndex], ...edgeData };
        }
        // 更新网络图
        const visEdges = network.body.data.edges;
        if (currentSelectedEdge && currentSelectedEdge.id && visEdges.get(currentSelectedEdge.id)) {
            const visEdge = visEdges.get(currentSelectedEdge.id);
            visEdges.update({ id: visEdge.id, label: edgeData.type, title: edgeData.description || edgeData.type });
        } else if (edgeIndex !== -1) {
            const eid = edgesData[edgeIndex].id;
            if (eid && visEdges.get(eid)) {
                visEdges.update({ id: eid, label: edgeData.type, title: edgeData.description || edgeData.type });
            }
        }
        
        closeEdgeEditModal();
        updateStatus('边保存成功', 'success');
        
        // 如果当前选中了这条边，刷新详情
        if (currentSelectedEdge && 
            currentSelectedEdge.start_uuid === edgeData.start_uuid && 
            currentSelectedEdge.end_uuid === edgeData.end_uuid) {
            selectEdge(edgesData[edgeIndex].id);
        }
        
    } catch (error) {
        updateStatus('保存失败: ' + error.message, 'error');
        console.error('保存边错误:', error);
    }
}

// 重置视图
function resetView() {
    if (network) {
        network.fit();
    }
}

// 适应窗口
function fitView() {
    if (network) {
        network.fit({
            animation: {
                duration: 500,
                easingFunction: 'easeInOutQuad'
            },
            padding: 50
        });
    }
}

// 放大
function zoomIn() {
    if (network) {
        const currentScale = network.getScale();
        const newScale = Math.min(currentScale * 1.2, 5); // 最大放大5倍
        network.moveTo({
            scale: newScale,
            animation: {
                duration: 300,
                easingFunction: 'easeInOutQuad'
            }
        });
    }
}

// 缩小
function zoomOut() {
    if (network) {
        const currentScale = network.getScale();
        const newScale = Math.max(currentScale * 0.8, 0.1); // 最小缩小到0.1倍
        network.moveTo({
            scale: newScale,
            animation: {
                duration: 300,
                easingFunction: 'easeInOutQuad'
            }
        });
    }
}

// 重置缩放
function resetZoom() {
    if (network) {
        network.moveTo({
            scale: 1,
            animation: {
                duration: 500,
                easingFunction: 'easeInOutQuad'
            }
        });
    }
}

// 返回上一级：恢复为按年级聚合视图
function goBackOneLevel() {
    if (!network) return;
    try {
        applyClusterMode('grade_status');
        updateStatus('已返回年级聚合视图', 'success');
    } catch (e) {
        console.warn('goBackOneLevel error:', e);
    }
}

// 获取节点颜色
function getNodeColor(node) {
    const s = (node && 'status' in node) ? node.status : 0;
    const isLearned = Array.isArray(s) ? s.some(v => parseInt(v,10) === 1) : (parseInt(s,10) === 1);
    if (isLearned) {
        // 已学习：绿色
        return { background: '#d1fae5', border: '#10b981' };
    }
    // 未学习（全部为0或非1）：灰色
    return { background: '#f3f4f6', border: '#d1d5db' };
}

// 获取边颜色
function getEdgeColor(type) {
    const colorMap = {
        '前置知识': '#667eea',
        '包含': '#28a745',
        '区分排斥': '#dc3545',
        '一般关联': '#6c757d'
    };
    return colorMap[type] || '#848484';
}

// 更新状态
function updateStatus(message, type) {
    const statusText = document.getElementById('statusText');
    statusText.textContent = message;
    statusText.className = `status ${type}`;
}

// 更新计数
function updateCounts(nodeCount, edgeCount) {
    // nodeCount 和 edgeCount 可能是数字或字符串（聚合模式时显示格式化的字符串）
    document.getElementById('nodeCount').textContent = `节点: ${nodeCount}`;
    document.getElementById('edgeCount').textContent = `边: ${edgeCount}`;
}

// HTML转义
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 改变聚合模式
function changeClusterMode() {
    const mode = document.getElementById('clusterMode').value;
    currentClusterMode = mode;
    
    if (mode === 'none') {
        // 不聚合，显示所有节点
        applyClusterMode('none');
        document.getElementById('expandAllBtn').style.display = 'none';
        document.getElementById('collapseAllBtn').style.display = 'none';
    } else {
        // 应用聚合
        applyClusterMode(mode);
        document.getElementById('expandAllBtn').style.display = 'inline-block';
        document.getElementById('collapseAllBtn').style.display = 'inline-block';
        document.getElementById('expandAllBtn').disabled = false;
        document.getElementById('collapseAllBtn').disabled = false;
    }
}

// 应用聚合模式
function applyClusterMode(mode) {
    if (!network) return;
    
    if (mode === 'none') {
        // 显示所有原始节点
        createGraphFromData(allNodesData, allEdgesData);
        return;
    }
    
    // 根据模式分组节点
    const groups = {};
    let totalNodesInGroups = 0; // 统计被分组的节点数
    
    for (const node of allNodesData) {
        let groupKey = '';
        let groupLabel = '';
        
        switch (mode) {
            case 'grade_status':
                // 按年级聚合（年级内按状态分组）
                const grade = (node.grade || '未分类').trim();
                groupKey = grade; // 第一层：按年级分组
                groupLabel = `年级: ${grade}`;
                break;
        }
        
        if (!groups[groupKey]) {
            groups[groupKey] = {
                label: groupLabel,
                nodes: []
            };
        }
        groups[groupKey].nodes.push(node);
        totalNodesInGroups++;
    }
    
    // 检查是否有节点丢失
    if (totalNodesInGroups !== allNodesData.length) {
        console.warn(`警告: 有 ${allNodesData.length - totalNodesInGroups} 个节点未被分组`);
        updateStatus(`警告: 有 ${allNodesData.length - totalNodesInGroups} 个节点未被分组`, 'error');
    }
    
    // 创建聚合节点和边
    const clusterNodes = [];
    const clusterEdges = [];
    clusterMap = {};
    clusterInfo = {};
    
    // 统计信息
    let totalNodesInClusters = 0;
    let totalGroups = 0;
    
    // 为每个分组创建聚合节点
    for (const [groupKey, groupData] of Object.entries(groups)) {
        if (groupData.nodes.length === 0) continue;
        
        totalGroups++;
        totalNodesInClusters += groupData.nodes.length;
        
        // 生成唯一的聚合节点ID
        // 使用分组键的hash值来确保唯一性，避免中文字符被替换导致重复
        let clusterId;
        try {
            // 方法1：使用简单的hash函数（如果浏览器支持）
            if (typeof btoa !== 'undefined') {
                // 使用base64编码，但需要处理非ASCII字符
                const encoded = btoa(encodeURIComponent(groupKey)).replace(/[^a-zA-Z0-9]/g, '_');
                // 如果是年级聚合模式，使用特殊的前缀以便识别
                if (mode === 'grade_status') {
                    clusterId = `cluster_grade_status_grade_${encoded}`;
                } else {
                    clusterId = `cluster_${mode}_${encoded}`;
                }
            } else {
                // 方法2：使用分组索引作为后缀确保唯一性
                if (mode === 'grade_status') {
                    clusterId = `cluster_grade_status_grade_${totalGroups}`;
                } else {
                    clusterId = `cluster_${mode}_${totalGroups}`;
                }
            }
        } catch (e) {
            // 方法3：如果编码失败，使用索引
            if (mode === 'grade_status') {
                clusterId = `cluster_grade_status_grade_${totalGroups}`;
            } else {
                clusterId = `cluster_${mode}_${totalGroups}`;
            }
        }
        
        // 确保ID唯一（如果仍然重复，使用索引）
        let finalClusterId = clusterId;
        let idIndex = 1;
        while (clusterNodes.some(c => c.id === finalClusterId)) {
            finalClusterId = `${clusterId}_${idIndex}`;
            idIndex++;
        }
        clusterId = finalClusterId;
        
        // 调试：检查ID生成
        if (clusterNodes.some(c => c.id === clusterId)) {
            console.warn(`警告: 聚合节点ID重复: ${clusterId}, 分组键: ${groupKey}`);
        }
        // 保存该分组的所有节点ID
        clusterMap[clusterId] = groupData.nodes.map(n => n.id);
        
        // 如果是年级聚合，需要保存年级信息和状态分组信息
        if (mode === 'grade_status') {
            // 在该年级内按状态分组
            const statusGroups = {};
            for (const node of groupData.nodes) {
                const status = node.status !== undefined ? node.status : -1;
                const statusName = getStatusName(status);
                if (!statusGroups[statusName]) {
                    statusGroups[statusName] = [];
                }
                statusGroups[statusName].push(node);
            }
            
            clusterInfo[clusterId] = {
                label: groupData.label,
                count: groupData.nodes.length,
                group: groupKey,
                grade: groupKey,
                statusGroups: statusGroups
            };
        } else {
            clusterInfo[clusterId] = {
                label: groupData.label,
                count: groupData.nodes.length,
                group: groupKey
            };
        }
        
        // 创建聚合节点
        clusterNodes.push({
            id: clusterId,
            label: `${groupData.label} (${groupData.nodes.length})`,
            title: `包含 ${groupData.nodes.length} 个节点，双击展开查看该年级的节点`,
            shape: 'ellipse',
            color: {
                background: '#667eea',
                border: '#5568d3',
                highlight: {
                    background: '#5568d3',
                    border: '#4458c2'
                }
            },
            font: {
                size: 16,
                color: '#fff',
                bold: true
            },
            size: 30,
            borderWidth: 3
        });
    }
    
    // 创建聚合节点之间的边（基于原始边的连接）
    const edgeMap = new Map();
    for (const edge of allEdgesData) {
        const fromNode = allNodesData.find(n => n.id === edge.from);
        const toNode = allNodesData.find(n => n.id === edge.to);
        
        if (!fromNode || !toNode) continue;
        
        let fromCluster = null;
        let toCluster = null;
        
        for (const [clusterId, nodeIds] of Object.entries(clusterMap)) {
            if (nodeIds.includes(edge.from)) {
                fromCluster = clusterId;
            }
            if (nodeIds.includes(edge.to)) {
                toCluster = clusterId;
            }
        }
        
        if (fromCluster && toCluster && fromCluster !== toCluster) {
            const edgeKey = `${fromCluster}-${toCluster}`;
            if (!edgeMap.has(edgeKey)) {
                edgeMap.set(edgeKey, {
                    from: fromCluster,
                    to: toCluster,
                    count: 0
                });
            }
            edgeMap.get(edgeKey).count++;
        }
    }
    
    // 添加聚合边
    for (const [edgeKey, edgeData] of edgeMap.entries()) {
        clusterEdges.push({
            id: `cluster_edge_${edgeKey}`,
            from: edgeData.from,
            to: edgeData.to,
            label: edgeData.count > 1 ? `${edgeData.count}条` : '',
            title: `包含 ${edgeData.count} 条原始边`,
            arrows: 'to',
            color: {
                color: '#848484',
                highlight: '#667eea'
            },
            width: Math.min(edgeData.count, 5),
            dashes: false
        });
    }
    
    // 验证所有节点都被分组
    if (totalNodesInClusters !== allNodesData.length) {
        console.error(`错误: 聚合节点总数 (${totalNodesInClusters}) 与原始节点数 (${allNodesData.length}) 不匹配`);
        updateStatus(`错误: 有 ${allNodesData.length - totalNodesInClusters} 个节点未被聚合`, 'error');
    } else {
        console.log(`成功聚合: ${totalGroups} 个分组, 包含 ${totalNodesInClusters} 个原始节点`);
        updateStatus(`成功聚合: ${totalGroups} 个分组, 包含 ${totalNodesInClusters} 个原始节点`, 'success');
    }
    
    // 调试：显示所有聚合节点的信息
    console.log('聚合节点详情:');
    console.log(`总共创建了 ${clusterNodes.length} 个聚合节点`);
    for (const cluster of clusterNodes) {
        console.log(`  - ${cluster.label} (ID: ${cluster.id})`);
    }
    
    // 检查是否有重复的聚合节点ID
    const clusterIds = clusterNodes.map(c => c.id);
    const uniqueClusterIds = new Set(clusterIds);
    if (clusterIds.length !== uniqueClusterIds.size) {
        console.error('警告: 发现重复的聚合节点ID!');
        const duplicates = clusterIds.filter((id, index) => clusterIds.indexOf(id) !== index);
        console.error('重复的ID:', duplicates);
    }
    
    // 更新图谱
    createGraphFromData(clusterNodes, clusterEdges);
    
    // 自动适应视图，确保所有节点都可见
    // 需要等待网络图稳定后再适应视图
    setTimeout(() => {
        if (network) {
            // 先停止物理引擎
            network.setOptions({
                physics: {
                    enabled: false
                }
            });
            
            // 适应视图
            network.fit({
                animation: {
                    duration: 500,
                    easingFunction: 'easeInOutQuad'
                },
                padding: 50
            });
            
            // 重新启用物理引擎（可选）
            setTimeout(() => {
                network.setOptions({
                    physics: {
                        enabled: true,
                        stabilization: {
                            enabled: true,
                            iterations: 50,
                            fit: true
                        },
                        solver: 'forceAtlas2Based',
                        forceAtlas2Based: {
                            gravitationalConstant: -50,
                            centralGravity: 0.01,
                            springLength: 150,
                            springConstant: 0.08,
                            damping: 0.4,
                            avoidOverlap: 1
                        }
                    }
                });
            }, 600);
        }
    }, 200);
}

// 从数据创建图谱
function createGraphFromData(nodesToShow, edgesToShow) {
    if (!network) return;
    
    // 确保节点ID唯一
    const nodeIdSet = new Set();
    const uniqueNodes = [];
    for (const node of nodesToShow) {
        if (!node.id) continue;
        if (!nodeIdSet.has(node.id)) {
            nodeIdSet.add(node.id);
            uniqueNodes.push(node);
        }
    }
    
    // 确保边ID唯一
    const edgeIdSet = new Set();
    const uniqueEdges = [];
    let edgeCounter = 0;
    for (const edge of edgesToShow) {
        let edgeId = edge.id || `edge_${edgeCounter++}`;
        if (edgeIdSet.has(edgeId)) {
            edgeId = `${edge.id || `edge_${edgeCounter++}`}-dup-${edgeCounter++}`;
        }
        if (edgeId) {
            edgeIdSet.add(edgeId);
            uniqueEdges.push({
                ...edge,
                id: edgeId
            });
        }
    }
    
    // 转换为vis.js格式
    const visNodes = new vis.DataSet(uniqueNodes.map(node => {
        const visNode = {
            id: node.id,
            label: node.label || node.node_name || '未命名',
            title: node.title || node.description || node.label || node.node_name || '',
            color: node.color || getNodeColor(node),
            font: node.font || { size: 14 },
            shape: node.shape || 'box',
            margin: node.margin || 10
        };
        
        if (node.size) visNode.size = node.size;
        if (node.borderWidth !== undefined) visNode.borderWidth = node.borderWidth;
        if (node.uuid) visNode.uuid = node.uuid;
        
        return visNode;
    }));
    
    const visEdges = new vis.DataSet(uniqueEdges.map(edge => ({
        id: edge.id,
        from: edge.from,
        to: edge.to,
        label: edge.label || '',
        title: edge.title || edge.description || edge.label || '',
        arrows: edge.arrows || 'to',
        color: edge.color || getEdgeColor(edge.type),
        font: edge.font || { size: 12, align: 'middle' },
        width: edge.width || 2,
        dashes: edge.dashes !== undefined ? edge.dashes : false
    })));
    
    // 更新网络图
    network.setData({
        nodes: visNodes,
        edges: visEdges
    });
    
    // 更新显示计数（显示聚合节点数和原始节点数）
    if (currentClusterMode !== 'none') {
        const totalOriginalNodes = allNodesData.length;
        const totalOriginalEdges = allEdgesData.length;
        updateCounts(`${uniqueNodes.length} (聚合) / ${totalOriginalNodes} (原始)`, 
                    `${uniqueEdges.length} (聚合) / ${totalOriginalEdges} (原始)`);
    } else {
        updateCounts(uniqueNodes.length, uniqueEdges.length);
    }
    
    // 强制适应视图，确保所有节点可见
    if (network && uniqueNodes.length > 0) {
        // 等待数据更新完成
        setTimeout(() => {
            try {
                network.fit({
                    animation: {
                        duration: 500,
                        easingFunction: 'easeInOutQuad'
                    },
                    padding: 100
                });
            } catch (e) {
                console.warn('适应视图失败:', e);
            }
        }, 100);
    }
}

// 展开聚合节点
function expandCluster(clusterId) {
    if (!clusterMap[clusterId]) return;
    
    const nodeIds = clusterMap[clusterId];
    const info = clusterInfo[clusterId];
    
    // 获取该聚合节点内的节点
    const clusterNodes = allNodesData.filter(n => nodeIds.includes(n.id));
    
    // 获取这些节点之间的边
    const clusterEdges = allEdgesData.filter(e => 
        nodeIds.includes(e.from) && nodeIds.includes(e.to)
    );
    
    // 获取连接到这些节点的外部边
    const externalEdges = allEdgesData.filter(e => 
        (nodeIds.includes(e.from) && !nodeIds.includes(e.to)) ||
        (!nodeIds.includes(e.from) && nodeIds.includes(e.to))
    );
    
    // 获取外部连接的节点
    const externalNodeIds = new Set();
    for (const edge of externalEdges) {
        if (nodeIds.includes(edge.from)) {
            externalNodeIds.add(edge.to);
        } else {
            externalNodeIds.add(edge.from);
        }
    }
    const externalNodes = allNodesData.filter(n => externalNodeIds.has(n.id));
    
    // 创建新的节点和边列表（移除聚合节点，添加展开的节点）
    const currentNodes = network.body.data.nodes.get();
    const currentEdges = network.body.data.edges.get();
    
    const newNodes = currentNodes
        .filter(n => n.id !== clusterId)
        .concat(clusterNodes.map(n => ({
            id: n.id,
            label: n.label || n.node_name || '未命名',
            title: n.description || n.label || n.node_name || '',
            uuid: n.uuid,
            color: getNodeColor(n),
            font: { size: 14 },
            shape: 'box',
            margin: 10
        })))
        .concat(externalNodes.map(n => ({
            id: n.id,
            label: n.label || n.node_name || '未命名',
            title: n.description || n.label || n.node_name || '',
            uuid: n.uuid,
            color: getNodeColor(n),
            font: { size: 14 },
            shape: 'box',
            margin: 10
        })));
    
    const newEdges = currentEdges
        .filter(e => e.from !== clusterId && e.to !== clusterId)
        .concat(clusterEdges.map(e => ({
            id: e.id,
            from: e.from,
            to: e.to,
            label: e.label || '',
            title: e.description || e.title || '',
            arrows: 'to',
            color: getEdgeColor(e.type),
            font: { size: 12, align: 'middle' }
        })))
        .concat(externalEdges.map(e => ({
            id: e.id,
            from: e.from,
            to: e.to,
            label: e.label || '',
            title: e.description || e.title || '',
            arrows: 'to',
            color: getEdgeColor(e.type),
            font: { size: 12, align: 'middle' }
        })));
    
    // 更新图谱
    network.setData({
        nodes: new vis.DataSet(newNodes),
        edges: new vis.DataSet(newEdges)
    });
    
    // 移除已展开的聚合节点
    delete clusterMap[clusterId];
    delete clusterInfo[clusterId];
}

// 获取状态名称
function getStatusName(status) {
    // 二值向量规则：只要有一个 1 即视为“已掌握”，否则“未学习”
    if (Array.isArray(status)) {
        const learned = status.some(v => parseInt(v, 10) === 1);
        return learned ? '已掌握' : '未学习';
    }
    const v = parseInt(status, 10);
    return v === 1 ? '已掌握' : '未学习';
}

// 展开年级聚合节点（按状态分组显示）
function expandGradeCluster(clusterId) {
    if (!clusterMap[clusterId] || !clusterInfo[clusterId]) return;
    
    const info = clusterInfo[clusterId];
    const grade = info.grade;
    const statusGroups = info.statusGroups;
    
    if (!statusGroups) {
        // 如果没有状态分组信息，使用普通的展开方式
        expandCluster(clusterId);
        return;
    }
    
    // 获取该年级的所有节点
    const gradeNodes = allNodesData.filter(n => n.grade === grade);
    
    // 创建状态聚合节点
    const statusClusterNodes = [];
    const statusClusterEdges = [];
    const statusClusterMap = {};
    
    // 为每个状态创建聚合节点
    for (const [statusName, nodes] of Object.entries(statusGroups)) {
        if (nodes.length === 0) continue;
        
        const statusClusterId = `cluster_grade_status_status_${grade}_${statusName}`;
        statusClusterMap[statusClusterId] = nodes.map(n => n.id);
        
        // 根据状态设置颜色
        let statusColor = { background: '#f8f9fa', border: '#6c757d' };
        if (statusName === '已掌握') {
            statusColor = { background: '#d4edda', border: '#28a745' };
        } else if (statusName === '学习中') {
            statusColor = { background: '#fff3cd', border: '#ffc107' };
        }
        
        statusClusterNodes.push({
            id: statusClusterId,
            label: `${statusName} (${nodes.length})`,
            title: `${grade} - ${statusName}: ${nodes.length} 个节点，双击展开`,
            shape: 'box',
            color: statusColor,
            font: { size: 14, color: '#333' },
            size: 25,
            borderWidth: 2
        });
    }
    
    // 获取该年级内的边（只显示年级内的连接）
    const gradeEdges = allEdgesData.filter(e => {
        const fromNode = allNodesData.find(n => n.id === e.from);
        const toNode = allNodesData.find(n => n.id === e.to);
        return fromNode && toNode && fromNode.grade === grade && toNode.grade === grade;
    });
    
    // 创建状态聚合节点之间的边
    const statusEdgeMap = new Map();
    for (const edge of gradeEdges) {
        const fromNode = allNodesData.find(n => n.id === edge.from);
        const toNode = allNodesData.find(n => n.id === edge.to);
        
        if (!fromNode || !toNode) continue;
        
        const fromStatus = getStatusName(fromNode.status !== undefined ? fromNode.status : -1);
        const toStatus = getStatusName(toNode.status !== undefined ? toNode.status : -1);
        
        let fromStatusCluster = null;
        let toStatusCluster = null;
        
        for (const [statusClusterId, nodeIds] of Object.entries(statusClusterMap)) {
            if (nodeIds.includes(edge.from)) {
                fromStatusCluster = statusClusterId;
            }
            if (nodeIds.includes(edge.to)) {
                toStatusCluster = statusClusterId;
            }
        }
        
        if (fromStatusCluster && toStatusCluster && fromStatusCluster !== toStatusCluster) {
            const edgeKey = `${fromStatusCluster}-${toStatusCluster}`;
            if (!statusEdgeMap.has(edgeKey)) {
                statusEdgeMap.set(edgeKey, {
                    from: fromStatusCluster,
                    to: toStatusCluster,
                    count: 0
                });
            }
            statusEdgeMap.get(edgeKey).count++;
        }
    }
    
    // 添加状态聚合边
    for (const [edgeKey, edgeData] of statusEdgeMap.entries()) {
        statusClusterEdges.push({
            id: `status_edge_${edgeKey}`,
            from: edgeData.from,
            to: edgeData.to,
            label: edgeData.count > 1 ? `${edgeData.count}条` : '',
            title: `包含 ${edgeData.count} 条原始边`,
            arrows: 'to',
            color: { color: '#848484', highlight: '#667eea' },
            width: Math.min(edgeData.count, 5),
            dashes: false
        });
    }
    
    // 获取当前显示的所有节点
    const currentNodes = network.body.data.nodes.get();
    const currentEdges = network.body.data.edges.get();
    
    // 过滤掉：
    // 1. 被展开的年级聚合节点
    // 2. 其他年级的聚合节点（只保留当前年级）
    const newNodes = currentNodes
        .filter(n => {
            // 保留被展开的年级聚合节点（会被替换为状态分组节点）
            if (n.id === clusterId) return false;
            // 过滤掉其他年级的聚合节点
            if (n.id.startsWith('cluster_grade_status_grade_')) {
                return false; // 隐藏所有年级聚合节点
            }
            // 保留其他节点（可能是状态分组节点或其他节点）
            return true;
        })
        .concat(statusClusterNodes.map(n => ({
            id: n.id,
            label: n.label,
            title: n.title,
            color: n.color,
            font: n.font,
            shape: n.shape,
            size: n.size,
            borderWidth: n.borderWidth
        })));
    
    // 过滤边：只保留当前年级内的边
    const newEdges = currentEdges
        .filter(e => {
            // 过滤掉连接到被展开的年级聚合节点的边
            if (e.from === clusterId || e.to === clusterId) return false;
            // 过滤掉连接到其他年级聚合节点的边
            if (e.from.startsWith('cluster_grade_status_grade_') || 
                e.to.startsWith('cluster_grade_status_grade_')) {
                return false;
            }
            // 保留其他边（可能是状态分组节点之间的边）
            return true;
        })
        .concat(statusClusterEdges.map(e => ({
            id: e.id,
            from: e.from,
            to: e.to,
            label: e.label || '',
            title: e.title || '',
            arrows: e.arrows || 'to',
            color: e.color,
            width: e.width || 2,
            dashes: e.dashes !== undefined ? e.dashes : false
        })));
    
    // 更新图谱（只显示该年级的节点，按状态分组）
    network.setData({
        nodes: new vis.DataSet(newNodes),
        edges: new vis.DataSet(newEdges)
    });
    
    // 更新clusterMap，添加状态聚合节点映射
    for (const [statusClusterId, nodeIds] of Object.entries(statusClusterMap)) {
        clusterMap[statusClusterId] = nodeIds;
        clusterInfo[statusClusterId] = {
            label: statusClusterNodes.find(n => n.id === statusClusterId)?.label || '',
            count: nodeIds.length,
            status: Object.keys(statusGroups).find(s => statusClusterId.includes(s)),
            grade: grade
        };
    }
    
    // 移除已展开的年级聚合节点
    delete clusterMap[clusterId];
    delete clusterInfo[clusterId];
    
    // 适应视图
    setTimeout(() => {
        if (network) {
            network.fit({
                animation: {
                    duration: 500,
                    easingFunction: 'easeInOutQuad'
                },
                padding: 100
            });
        }
    }, 100);
    
    // 更新计数
    updateCounts(`${statusClusterNodes.length} (状态分组)`, `${statusClusterEdges.length} (状态分组)`);
}

// 展开全部聚合节点
function expandAllClusters() {
    const clusterIds = Object.keys(clusterMap);
    if (clusterIds.length === 0) return;
    
    // 展开所有聚合节点，显示所有原始节点
    createGraphFromData(allNodesData, allEdgesData);
    clusterMap = {};
    clusterInfo = {};
}

// 折叠全部聚合节点
function collapseAllClusters() {
    if (currentClusterMode === 'none') return;
    applyClusterMode(currentClusterMode);
}

