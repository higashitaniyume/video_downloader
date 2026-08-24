/**
 * Video Downloader Web UI Client Logic
 */

document.addEventListener('DOMContentLoaded', () => {
  // State
  let currentResults = [];
  let pollInterval = null;
  let activeConfig = {};

  // DOM Elements
  const urlInput = document.getElementById('url-input');
  const btnPaste = document.getElementById('btn-paste');
  const btnClear = document.getElementById('btn-clear');
  const btnParse = document.getElementById('btn-parse');
  const btnParseText = btnParse.querySelector('.btn-text');
  const btnParseSpinner = btnParse.querySelector('.spinner');

  const batchBar = document.getElementById('batch-bar');
  const batchStats = document.getElementById('batch-stats');
  const displayOutDir = document.getElementById('display-out-dir');
  const btnSelectAll = document.getElementById('btn-select-all');
  const btnDownloadSelected = document.getElementById('btn-download-selected');

  const resultsContainer = document.getElementById('results-container');
  const emptyState = document.getElementById('empty-state');

  const tasksList = document.getElementById('tasks-list');
  const noTasksHint = document.getElementById('no-tasks');
  const taskCountBadge = document.getElementById('task-count-badge');
  const btnClearTasks = document.getElementById('btn-clear-tasks');

  const btnOpenFolder = document.getElementById('btn-open-folder');
  const btnOpenSettings = document.getElementById('btn-open-settings');
  const btnViewLogs = document.getElementById('btn-view-logs');

  // Modals
  const settingsModal = document.getElementById('settings-modal');
  const btnCloseSettings = document.getElementById('btn-close-settings');
  const btnCancelSettings = document.getElementById('btn-cancel-settings');
  const btnSaveSettings = document.getElementById('btn-save-settings');
  const btnTestProxy = document.getElementById('btn-test-proxy');
  const proxyTestResult = document.getElementById('proxy-test-result');

  const logsModal = document.getElementById('logs-modal');
  const btnCloseLogs = document.getElementById('btn-close-logs');
  const btnCloseLogsFooter = document.getElementById('btn-close-logs-footer');
  const btnRefreshLogs = document.getElementById('btn-refresh-logs');
  const logsViewer = document.getElementById('logs-viewer');

  const toastContainer = document.getElementById('toast-container');

  // ── Toast Notifications ─────────────────────────────────────
  function showToast(message, type = 'info', duration = 3000) {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    let icon = 'ℹ️';
    if (type === 'success') icon = '✅';
    if (type === 'error') icon = '❌';

    toast.innerHTML = `<span>${icon}</span> <span>${message}</span>`;
    toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(12px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }

  // ── Format Helper ───────────────────────────────────────────
  function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '';
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return (bytes / Math.pow(1024, i)).toFixed(1) + ' ' + sizes[i];
  }

  function getPlatformBadgeClass(platform) {
    const p = (platform || '').toLowerCase();
    if (p.includes('bili')) return 'badge-bilibili';
    if (p.includes('douyin')) return 'badge-douyin';
    if (p.includes('youtube')) return 'badge-youtube';
    if (p.includes('kuaishou')) return 'badge-kuaishou';
    if (p.includes('weibo')) return 'badge-weibo';
    if (p.includes('xiaohongshu')) return 'badge-xiaohongshu';
    if (p.includes('tiktok')) return 'badge-tiktok';
    if (p.includes('twitter')) return 'badge-twitter';
    return 'badge-default';
  }

  // ── Config Loading & Saving ─────────────────────────────────
  async function loadConfig() {
    try {
      const res = await fetch('/api/config');
      if (!res.ok) return;
      activeConfig = await res.json();
      displayOutDir.textContent = activeConfig.out_dir || './downloads';
      
      document.getElementById('cfg-proxy').value = activeConfig.proxy_url || '';
      document.getElementById('cfg-quality').value = activeConfig.quality || 'auto';
      document.getElementById('cfg-browser').value = activeConfig.ydl_cookies_from_browser || '';
      document.getElementById('cfg-cookie-file').value = activeConfig.ydl_cookies_file || '';
      document.getElementById('cfg-out-dir').value = activeConfig.out_dir || '';
    } catch (e) {
      console.error('Failed to load config', e);
    }
  }

  async function saveConfig() {
    const payload = {
      proxy_url: document.getElementById('cfg-proxy').value.trim(),
      quality: document.getElementById('cfg-quality').value,
      ydl_cookies_from_browser: document.getElementById('cfg-browser').value,
      ydl_cookies_file: document.getElementById('cfg-cookie-file').value.trim(),
      out_dir: document.getElementById('cfg-out-dir').value.trim(),
    };

    try {
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (res.ok) {
        showToast('设置已保存并生效', 'success');
        settingsModal.classList.add('hidden');
        await loadConfig();
      } else {
        showToast(data.error || '保存失败', 'error');
      }
    } catch (e) {
      showToast('无法连接到服务端', 'error');
    }
  }

  // ── Parse Logic ─────────────────────────────────────────────
  async function parseUrls() {
    const text = urlInput.value.trim();
    if (!text) {
      showToast('请先粘贴需要解析的视频或媒体链接', 'info');
      return;
    }

    btnParse.disabled = true;
    btnParseText.textContent = '正在解析...';
    btnParseSpinner.classList.remove('hidden');

    try {
      const res = await fetch('/api/parse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text })
      });
      const data = await res.json();

      if (!res.ok) {
        showToast(data.error || '解析失败', 'error');
        return;
      }

      currentResults = data.results || [];
      renderResults(currentResults);

      if (currentResults.length === 0) {
        showToast('未从文本中识别到可解析的有效链接', 'info');
      } else {
        const successCount = currentResults.filter(r => !r.is_error).length;
        showToast(`解析完成：共 ${currentResults.length} 条（成功 ${successCount} 条）`, 'success');
      }
    } catch (e) {
      showToast('网络请求异常，解析服务连接失败', 'error');
    } finally {
      btnParse.disabled = false;
      btnParseText.textContent = '⚡ 开始解析';
      btnParseSpinner.classList.add('hidden');
    }
  }

  function renderResults(results) {
    resultsContainer.innerHTML = '';

    if (!results || results.length === 0) {
      resultsContainer.appendChild(emptyState);
      batchBar.classList.add('hidden');
      return;
    }

    batchBar.classList.remove('hidden');
    batchStats.textContent = `已解析 ${results.length} 个资源`;

    results.forEach((res, resultIdx) => {
      const card = document.createElement('div');
      card.className = `result-card ${res.is_error ? 'is-error' : ''}`;

      // Cover Image via Proxy
      const coverUrl = res.cover_urls && res.cover_urls.length > 0 ? res.cover_urls[0] : '';
      let coverHtml = `<div class="cover-placeholder">${res.platform.toUpperCase()}</div>`;
      if (coverUrl) {
        const proxyCover = `/api/cover?url=${encodeURIComponent(coverUrl)}`;
        coverHtml = `<img src="${proxyCover}" class="cover-img" alt="封面" loading="lazy" onerror="this.parentElement.innerHTML='<div class=\\'cover-placeholder\\'>${res.platform.toUpperCase()}</div>'">`;
      }

      // Meta parts
      const metaParts = [res.author, res.duration_text, res.timestamp].filter(Boolean);
      const metaText = metaParts.join('  •  ');

      // Formats
      let formatsHtml = '';
      if (res.is_error) {
        formatsHtml = `<div class="error-text">❌ 解析失败：${res.error}</div>`;
      } else if (!res.items || res.items.length === 0) {
        formatsHtml = `<div class="hint">⚠️ 未检测到可供下载的媒体流</div>`;
      } else {
        formatsHtml = res.items.map((item, itemIdx) => {
          const isDefaultChecked = itemIdx === 0 ? 'checked' : '';
          const sizeStr = formatBytes(item.size_bytes);
          const sizeLabel = sizeStr ? ` (${sizeStr})` : '';
          const labelText = item.name || `${item.kind.toUpperCase()}${item.quality ? ' - ' + item.quality : ''}`;

          return `
            <label class="format-checkbox-label ${itemIdx === 0 ? 'checked' : ''}">
              <input type="checkbox" name="format_${resultIdx}" value="${item.index}" ${isDefaultChecked}>
              <span>${labelText}${sizeLabel}</span>
            </label>
          `;
        }).join('');
      }

      card.innerHTML = `
        <div class="cover-wrapper">
          ${coverHtml}
        </div>
        <div class="result-content">
          <div>
            <div class="result-header">
              <span class="badge ${getPlatformBadgeClass(res.platform)}">${res.platform}</span>
              <h3 class="result-title" title="${res.title}">${res.title}</h3>
            </div>
            ${metaText ? `<div class="result-meta">${metaText}</div>` : ''}
            <div class="result-formats">
              ${formatsHtml}
            </div>
          </div>
          ${!res.is_error && res.items && res.items.length > 0 ? `
            <div class="result-footer">
              <button class="btn btn-secondary btn-sm btn-download-single" data-result-idx="${resultIdx}">
                📥 下载此卡片选中项
              </button>
            </div>
          ` : ''}
        </div>
      `;

      // Checkbox style update
      card.querySelectorAll('input[type="checkbox"]').forEach(chk => {
        chk.addEventListener('change', (e) => {
          if (e.target.checked) {
            e.target.closest('.format-checkbox-label').classList.add('checked');
          } else {
            e.target.closest('.format-checkbox-label').classList.remove('checked');
          }
        });
      });

      // Single Download Button
      const btnSingle = card.querySelector('.btn-download-single');
      if (btnSingle) {
        btnSingle.addEventListener('click', () => {
          downloadFromCards([resultIdx]);
        });
      }

      resultsContainer.appendChild(card);
    });
  }

  // ── Download Dispatcher ─────────────────────────────────────
  async function downloadFromCards(targetResultIndices) {
    const tasksToSubmit = [];

    targetResultIndices.forEach(rIdx => {
      const res = currentResults[rIdx];
      if (!res || res.is_error) return;

      const checkedBoxes = document.querySelectorAll(`input[name="format_${rIdx}"]:checked`);
      const selectedIndices = Array.from(checkedBoxes).map(cb => parseInt(cb.value, 10));

      if (selectedIndices.length > 0) {
        tasksToSubmit.push({
          result: res,
          selected_indices: selectedIndices
        });
      }
    });

    if (tasksToSubmit.length === 0) {
      showToast('请至少勾选一个媒体格式档位', 'info');
      return;
    }

    try {
      const res = await fetch('/api/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tasks: tasksToSubmit,
          out_dir: activeConfig.out_dir || ''
        })
      });
      const data = await res.json();
      if (res.ok) {
        showToast(`已成功创建 ${data.task_ids.length} 个下载任务`, 'success');
        fetchTasks();
      } else {
        showToast(data.error || '创建下载任务失败', 'error');
      }
    } catch (e) {
      showToast('无法连接下载服务', 'error');
    }
  }

  // ── Tasks Live Polling ──────────────────────────────────────
  async function fetchTasks() {
    try {
      const res = await fetch('/api/tasks');
      if (!res.ok) return;
      const data = await res.json();
      renderTasks(data.tasks || []);
    } catch (e) {
      console.error('Fetch tasks failed', e);
    }
  }

  function renderTasks(tasks) {
    taskCountBadge.textContent = tasks.length;

    if (!tasks || tasks.length === 0) {
      tasksList.innerHTML = '<div id="no-tasks" class="no-tasks-hint">当前暂无正在进行的下载任务</div>';
      return;
    }

    tasksList.innerHTML = '';
    tasks.forEach(task => {
      const item = document.createElement('div');
      item.className = `task-item is-${task.status}`;

      let statusBadge = `<span class="badge badge-purple">${task.status}</span>`;
      let controlsHtml = '';

      if (task.status === 'downloading') {
        statusBadge = `<span class="badge" style="background: #3B82F6; color: #FFF;">下载中</span>`;
        controlsHtml = `
          <button class="btn btn-secondary btn-xs btn-task-pause" data-task-id="${task.task_id}">⏸️ 暂停</button>
          <button class="btn btn-ghost btn-xs btn-task-cancel" data-task-id="${task.task_id}" style="color: #EF4444;">⏹️ 取消</button>
        `;
      } else if (task.status === 'paused') {
        statusBadge = `<span class="badge" style="background: #F59E0B; color: #000;">已暂停</span>`;
        controlsHtml = `
          <button class="btn btn-primary btn-xs btn-task-resume" data-task-id="${task.task_id}">▶️ 继续</button>
          <button class="btn btn-ghost btn-xs btn-task-cancel" data-task-id="${task.task_id}" style="color: #EF4444;">⏹️ 取消</button>
        `;
      } else if (task.status === 'completed') {
        statusBadge = `<span class="badge badge-success" style="background: #10B981; color: #FFF;">✅ 已完成</span>`;
      } else if (task.status === 'failed') {
        statusBadge = `<span class="badge" style="background: #EF4444; color: #FFF;">❌ 失败</span>`;
      } else if (task.status === 'cancelled') {
        statusBadge = `<span class="badge" style="background: #64748B; color: #FFF;">已取消</span>`;
      }

      const percent = task.percent || 0;
      const speedStr = task.speed_text ? `⚡ ${task.speed_text}` : '';
      const etaStr = task.eta_text ? `⏱️ 剩余 ${task.eta_text}` : '';
      const progressDetails = [task.item_label, speedStr, etaStr].filter(Boolean).join('  |  ');

      item.innerHTML = `
        <div class="task-main">
          <div class="task-title" title="${task.title}">
            <span class="badge ${getPlatformBadgeClass(task.platform)}" style="margin-right: 6px;">${task.platform}</span>
            ${task.title}
          </div>
          <div class="task-controls">
            ${statusBadge}
            ${controlsHtml}
          </div>
        </div>
        <div class="progress-track">
          <div class="progress-fill" style="width: ${percent}%"></div>
        </div>
        <div class="task-sub">
          <span>${progressDetails || (task.error ? '❌ ' + task.error : '等待中...')}</span>
          <span>${percent.toFixed(1)}%</span>
        </div>
      `;

      // Task actions bindings
      const btnPause = item.querySelector('.btn-task-pause');
      if (btnPause) {
        btnPause.addEventListener('click', () => taskAction(task.task_id, 'pause'));
      }
      const btnResume = item.querySelector('.btn-task-resume');
      if (btnResume) {
        btnResume.addEventListener('click', () => taskAction(task.task_id, 'resume'));
      }
      const btnCancel = item.querySelector('.btn-task-cancel');
      if (btnCancel) {
        btnCancel.addEventListener('click', () => taskAction(task.task_id, 'cancel'));
      }

      tasksList.appendChild(item);
    });
  }

  async function taskAction(taskId, action) {
    try {
      await fetch(`/api/tasks/${taskId}/${action}`, { method: 'POST' });
      fetchTasks();
    } catch (e) {
      showToast(`操作失败: ${e}`, 'error');
    }
  }

  // ── Event Listeners ─────────────────────────────────────────

  // Parse button
  btnParse.addEventListener('click', parseUrls);

  // Paste button
  btnPaste.addEventListener('click', async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        urlInput.value = (urlInput.value ? urlInput.value + '\n' : '') + text;
        showToast('已从剪贴板粘贴内容', 'info');
      }
    } catch (e) {
      showToast('无法读取剪贴板，请手动 Ctrl+V 粘贴', 'error');
    }
  });

  // Clear button
  btnClear.addEventListener('click', () => {
    urlInput.value = '';
    currentResults = [];
    renderResults([]);
    showToast('输入与解析结果已清空', 'info');
  });

  // Select all / batch download
  btnSelectAll.addEventListener('click', () => {
    const allLabels = document.querySelectorAll('.format-checkbox-label');
    allLabels.forEach((label, idx) => {
      const chk = label.querySelector('input');
      chk.checked = true;
      label.classList.add('checked');
    });
    showToast('已勾选所有卡片格式', 'info');
  });

  btnDownloadSelected.addEventListener('click', () => {
    const indices = currentResults.map((_, idx) => idx);
    downloadFromCards(indices);
  });

  // Clear finished tasks
  btnClearTasks.addEventListener('click', async () => {
    try {
      await fetch('/api/tasks/clear', { method: 'POST' });
      fetchTasks();
      showToast('已清理已结束任务记录', 'info');
    } catch (e) {
      console.error(e);
    }
  });

  // Open download folder
  btnOpenFolder.addEventListener('click', async () => {
    try {
      const res = await fetch('/api/open-folder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder: activeConfig.out_dir || '' })
      });
      if (res.ok) {
        showToast('已在系统资源管理器中打开下载文件夹', 'success');
      } else {
        showToast('打开文件夹失败', 'error');
      }
    } catch (e) {
      showToast('连接服务端失败', 'error');
    }
  });

  // Settings Modal Handlers
  btnOpenSettings.addEventListener('click', () => {
    loadConfig();
    settingsModal.classList.remove('hidden');
  });
  btnCloseSettings.addEventListener('click', () => settingsModal.classList.add('hidden'));
  btnCancelSettings.addEventListener('click', () => settingsModal.classList.add('hidden'));
  btnSaveSettings.addEventListener('click', saveConfig);

  btnTestProxy.addEventListener('click', async () => {
    const proxy = document.getElementById('cfg-proxy').value.trim();
    proxyTestResult.textContent = '⏳ 正在测试代理连通性...';
    btnTestProxy.disabled = true;
    try {
      const res = await fetch('/api/proxy/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ proxy_url: proxy })
      });
      const data = await res.json();
      if (data.success) {
        proxyTestResult.textContent = `✅ ${data.message}`;
        proxyTestResult.style.color = '#10B981';
      } else {
        proxyTestResult.textContent = `❌ ${data.error || '测试失败'}`;
        proxyTestResult.style.color = '#EF4444';
      }
    } catch (e) {
      proxyTestResult.textContent = '❌ 测试请求发送失败';
      proxyTestResult.style.color = '#EF4444';
    } finally {
      btnTestProxy.disabled = false;
    }
  });

  // Logs Modal Handlers
  btnViewLogs.addEventListener('click', async () => {
    logsModal.classList.remove('hidden');
    await loadLogs();
  });
  btnCloseLogs.addEventListener('click', () => logsModal.classList.add('hidden'));
  btnCloseLogsFooter.addEventListener('click', () => logsModal.classList.add('hidden'));
  btnRefreshLogs.addEventListener('click', loadLogs);

  async function loadLogs() {
    logsViewer.textContent = '正在获取日志...';
    try {
      const res = await fetch('/api/logs');
      const data = await res.json();
      if (data.logs && data.logs.length > 0) {
        logsViewer.textContent = data.logs.join('\n');
        logsViewer.scrollTop = logsViewer.scrollHeight;
      } else {
        logsViewer.textContent = '（暂无日志）';
      }
    } catch (e) {
      logsViewer.textContent = `获取日志失败: ${e}`;
    }
  }

  // Init
  loadConfig();
  fetchTasks();
  pollInterval = setInterval(fetchTasks, 1000);
});
