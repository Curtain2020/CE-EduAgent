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
let currentClusterMode = 'none'; // 当前聚合模式
let clusterMap = {}; // 聚合节点映射：clusterId -> [nodeIds]
let clusterInfo = {}; // 聚合节点信息：clusterId -> {label, count, group}

// 初始化
document.addEventListener('DOMContentLoaded', function() {
    // 自动加载图谱
    loadKnowledgeGraph();
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
                    avoidOverlap: 1,
                    adjustSizes: false,
                    outboundAttractionDistribution: false
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
        document.getElementById('clusterMode').disabled = false;
        
        updateStatus(`加载成功: ${nodesData.length} 个节点, ${edgesData.length} 条边`, 'success');
        updateCounts(nodesData.length, edgesData.length);
        
        // 默认不聚合，用户可以选择
        // changeClusterMode('grade');
        
    } catch (error) {
        updateStatus('加载失败: ' + error.message, 'error');
        console.error('加载知识图谱错误:', error);
    }
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
                <label>状态:</label>
                <span>${node.status || -1}</span>
            </div>
            <div class="detail-actions">
                <button onclick="editNode('${node.id}')">编辑节点</button>
            </div>
        </div>
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
                <span>${escapeHtml(edge.type || '')}</span>
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
    document.getElementById('editNodeStatus').value = node.status || -1;
    
    document.getElementById('nodeEditModal').style.display = 'flex';
}

// 关闭节点编辑模态框
function closeNodeEditModal() {
    document.getElementById('nodeEditModal').style.display = 'none';
}

// 保存节点编辑
async function saveNodeEdit() {
    const uuid = document.getElementById('editNodeUuid').value;
    const nodeData = {
        uuid: uuid,
        node_name: document.getElementById('editNodeName').value,
        description: document.getElementById('editNodeDescription').value,
        grade: document.getElementById('editNodeGrade').value,
        subject: document.getElementById('editNodeSubject').value,
        publisher: document.getElementById('editNodePublisher').value,
        status: parseInt(document.getElementById('editNodeStatus').value) || -1
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
        description: document.getElementById('editEdgeDescription').value
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
        
        // 更新本地数据
        const edgeIndex = edgesData.findIndex(e => 
            e.start_uuid === edgeData.start_uuid && e.end_uuid === edgeData.end_uuid
        );
        if (edgeIndex !== -1) {
            edgesData[edgeIndex] = { ...edgesData[edgeIndex], ...edgeData };
            
            // 更新网络图
            const visEdges = network.body.data.edges;
            const edgeId = edgesData[edgeIndex].id;
            const visEdge = visEdges.get(edgeId);
            if (visEdge) {
                visEdge.label = edgeData.type;
                visEdge.title = edgeData.description || edgeData.type;
                visEdges.update(visEdge);
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

// 获取节点颜色
function getNodeColor(node) {
    const status = node.status || -1;
    if (status === 1) {
        return { background: '#d4edda', border: '#28a745' };
    } else if (status === 0) {
        return { background: '#fff3cd', border: '#ffc107' };
    } else {
        return { background: '#f8f9fa', border: '#6c757d' };
    }
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
    switch (status) {
        case 1:
            return '已掌握';
        case 0:
            return '学习中';
        case -1:
        default:
            return '未学习';
    }
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

