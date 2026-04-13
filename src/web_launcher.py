#!/usr/bin/env python3
"""
GUI Launcher using pywebview.
Provides a visual interface for configuring and launching forensic tasks.
"""

import json
import logging
import multiprocessing
import os
import signal
import threading
import time
import sys
from pathlib import Path

logger = logging.getLogger(__name__)
webview = None

# ==================== HTML Template ====================

HTML_CONTENT = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>Android Automated Forensic Tool</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
    background: #f0f2f5;
    color: #333;
    min-height: 100vh;
}

.container {
    max-width: 640px;
    margin: 0 auto;
    padding: 30px 24px;
}

.header {
    display: flex;
    justify-content: center;
    align-items: center;
    position: relative;
    margin-bottom: 28px;
}

h1 {
    text-align: center;
    font-size: 20px;
    font-weight: 600;
    color: #1a1a1a;
}

.lang-switch {
    position: absolute;
    right: 0;
    top: 50%;
    transform: translateY(-50%);
    display: flex;
    border: 1px solid #d9d9d9;
    border-radius: 6px;
    overflow: hidden;
    font-size: 12px;
}

.lang-switch button {
    padding: 4px 10px;
    border: none;
    background: #fff;
    color: #666;
    cursor: pointer;
    font-size: 12px;
    transition: all 0.2s;
}

.lang-switch button.active {
    background: #4096ff;
    color: #fff;
}

.lang-switch button:hover:not(.active) {
    background: #f0f0f0;
}

.card {
    background: #fff;
    border-radius: 10px;
    padding: 24px;
    margin-bottom: 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

.card-title {
    font-size: 15px;
    font-weight: 600;
    color: #555;
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 1px solid #eee;
}

.form-group {
    margin-bottom: 16px;
}

.form-group:last-child {
    margin-bottom: 0;
}

label {
    display: block;
    font-size: 13px;
    color: #666;
    margin-bottom: 6px;
    font-weight: 500;
}

input[type="number"], select {
    width: 100%;
    padding: 8px 12px;
    border: 1px solid #d9d9d9;
    border-radius: 6px;
    font-size: 14px;
    color: #333;
    background: #fff;
    transition: border-color 0.2s;
    outline: none;
}

input[type="number"]:focus, select:focus {
    border-color: #4096ff;
    box-shadow: 0 0 0 2px rgba(64,150,255,0.1);
}

.inline-inputs {
    display: flex;
    gap: 10px;
    align-items: center;
}

.inline-inputs input {
    flex: 1;
}

.inline-inputs .separator {
    color: #999;
    font-size: 14px;
    flex-shrink: 0;
}

.file-select {
    display: flex;
    gap: 10px;
    align-items: center;
}

.file-select .file-path {
    flex: 1;
    padding: 8px 12px;
    border: 1px solid #d9d9d9;
    border-radius: 6px;
    font-size: 13px;
    color: #666;
    background: #fafafa;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    min-height: 36px;
    line-height: 20px;
}

.btn {
    padding: 8px 20px;
    border: none;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    flex-shrink: 0;
}

.btn-default {
    background: #f0f0f0;
    color: #333;
}

.btn-default:hover {
    background: #e0e0e0;
}

.btn-primary {
    background: #4096ff;
    color: #fff;
    width: 100%;
    padding: 12px;
    font-size: 16px;
    font-weight: 600;
    margin-top: 8px;
}

.btn-primary:hover {
    background: #1677ff;
}

.btn-primary:disabled {
    background: #a0c4ff;
    cursor: not-allowed;
}

.btn-stop {
    background: #ff4d4f;
    color: #fff;
    width: 100%;
    padding: 12px;
    font-size: 16px;
    font-weight: 600;
    margin-top: 8px;
}

.btn-stop:hover {
    background: #cf1322;
}

.hint {
    font-size: 12px;
    color: #999;
    margin-top: 4px;
}

.log-area {
    width: 100%;
    height: 200px;
    background: #1e1e1e;
    color: #d4d4d4;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px;
    padding: 12px;
    border-radius: 6px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-all;
    line-height: 1.5;
}

.status-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 12px;
}

.status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #d9d9d9;
}

.status-dot.idle { background: #d9d9d9; }
.status-dot.running { background: #52c41a; animation: pulse 1.5s infinite; }
.status-dot.stopping { background: #faad14; animation: pulse 1.5s infinite; }
.status-dot.error { background: #ff4d4f; }
.status-dot.done { background: #52c41a; }

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
}

.status-text {
    font-size: 13px;
    color: #666;
}

.parallel-options {
    display: none;
}

.parallel-options.visible {
    display: block;
}
</style>
</head>
<body>

<div class="container">
    <div class="header">
        <h1 data-i18n="title"></h1>
        <div class="lang-switch">
            <button id="langZh" class="active" onclick="switchLang('zh')">中文</button>
            <button id="langEn" onclick="switchLang('en')">EN</button>
        </div>
    </div>

    <!-- Task Source -->
    <div class="card">
        <div class="card-title" data-i18n="card_task_file"></div>
        <div class="form-group">
            <label data-i18n="label_task_source"></label>
            <select id="taskSource" onchange="onTaskSourceChange()">
                <option value="database" data-i18n-opt="opt_from_database"></option>
                <option value="file" data-i18n-opt="opt_from_file"></option>
            </select>
        </div>
        <div id="dbSourceGroup">
            <div class="form-group">
                <label data-i18n="label_batch_size"></label>
                <input type="number" id="batchSize" value="100" min="1" max="1000" step="10">
                <div class="hint" data-i18n="hint_batch_size"></div>
            </div>
            <div class="form-group">
                <button class="btn btn-default" id="btnTestDb" onclick="testDbConnection()" data-i18n="btn_test_db"></button>
                <span class="hint" id="dbTestResult"></span>
            </div>
        </div>
        <div id="fileSourceGroup" class="form-group" style="display:none;">
            <label data-i18n="label_select_file"></label>
            <div class="file-select">
                <div class="file-path" id="filePath" data-i18n-default="no_file_selected"></div>
                <button class="btn btn-default" onclick="selectFile()" data-i18n="btn_browse"></button>
            </div>
        </div>
    </div>

    <!-- Anti-bot Settings -->
    <div class="card">
        <div class="card-title" data-i18n="card_antibot"></div>
        <div class="form-group">
            <label data-i18n="label_protection_range"></label>
            <div class="inline-inputs">
                <input type="number" id="protectionMin" value="25" min="5" max="120" step="1">
                <span class="separator">~</span>
                <input type="number" id="protectionMax" value="35" min="5" max="120" step="1">
            </div>
            <div class="hint" data-i18n="hint_protection"></div>
        </div>
    </div>

    <!-- Execution Settings -->
    <div class="card">
        <div class="card-title" data-i18n="card_exec_settings"></div>
        <div class="form-group">
            <label data-i18n="label_exec_mode"></label>
            <select id="execMode" onchange="onModeChange()">
                <option value="sequential" data-i18n-opt="opt_sequential"></option>
                <option value="parallel" data-i18n-opt="opt_parallel"></option>
            </select>
        </div>

        <div class="parallel-options" id="parallelOptions">
            <div class="form-group">
                <label data-i18n="label_device_ids"></label>
                <input type="text" id="deviceIds" data-i18n-ph="ph_device_ids" style="width:100%;padding:8px 12px;border:1px solid #d9d9d9;border-radius:6px;font-size:14px;outline:none;">
            </div>
            <div class="form-group">
                <label data-i18n="label_strategy"></label>
                <select id="strategy">
                    <option value="round_robin" data-i18n-opt="opt_round_robin"></option>
                    <option value="load_balance" data-i18n-opt="opt_load_balance"></option>
                    <option value="random" data-i18n-opt="opt_random"></option>
                </select>
            </div>
        </div>

        <div class="form-group">
            <label data-i18n="label_video_duration"></label>
            <input type="number" id="videoDuration" value="30" min="5" max="300" step="5">
        </div>
        <div class="form-group">
            <label data-i18n="label_group_size"></label>
            <input type="number" id="groupSize" value="3" min="1" max="10" step="1">
            <div class="hint" data-i18n="hint_group_size"></div>
        </div>
    </div>

    <!-- Start Button -->
    <div id="startSection">
        <button class="btn btn-primary" id="btnStart" onclick="startExecution()" data-i18n="btn_start"></button>
    </div>
    <div id="stopSection" style="display:none;">
        <button class="btn btn-stop" id="btnStop" onclick="stopExecution()" data-i18n="btn_stop"></button>
    </div>

    <!-- Log Output -->
    <div class="card" id="logCard" style="display:none;">
        <div class="card-title" data-i18n="card_log"></div>
        <div class="status-bar">
            <div class="status-dot" id="statusDot"></div>
            <span class="status-text" id="statusText"></span>
        </div>
        <div class="log-area" id="logArea"></div>
    </div>
</div>

<script>
// ==================== i18n ====================
const LANG = {
    zh: {
        title: 'Android 自动化取证工具',
        card_task_file: '任务来源',
        label_task_source: '任务来源',
        opt_from_file: '从文件加载',
        opt_from_database: '从数据库加载',
        label_select_file: '选择任务文件 (JSON / CSV / TXT)',
        no_file_selected: '未选择文件',
        btn_browse: '浏览...',
        label_batch_size: '每批加载任务数',
        hint_batch_size: '从数据库每次读取的待取证任务数量。',
        btn_test_db: '测试数据库连接',
        db_test_ok: '连接成功！待取证任务: {count} 条',
        db_test_fail: '连接失败: {error}',
        db_test_no_config: '未找到 config/database.json，请先配置数据库。',
        card_antibot: '防封控设置',
        label_protection_range: '防封控时间范围（分钟）',
        hint_protection: '最小 5 分钟。每个周期在此范围内随机取值，自动分配为模拟浏览 + 冷却时段。',
        card_exec_settings: '执行设置',
        label_exec_mode: '执行模式',
        opt_sequential: '单设备 - 顺序执行',
        opt_parallel: '多设备 - 并行执行',
        label_device_ids: '设备 ID（逗号分隔，留空自动检测）',
        ph_device_ids: '例如 device1,device2',
        label_strategy: '任务分配策略',
        opt_round_robin: '轮询分配',
        opt_load_balance: '负载均衡',
        opt_random: '随机分配',
        label_video_duration: '视频录制时长（秒）',
        label_group_size: '每条证据最大商品数',
        hint_group_size: '按店铺分组，每组最多收录的商品数。',
        btn_start: '开始执行',
        btn_stop: '停止执行',
        card_log: '执行日志',
        status_idle: '空闲',
        status_running: '运行中',
        status_stopping: '正在停止',
        status_done: '已完成',
        status_error: '错误',
        alert_no_file: '请先选择任务文件。',
        alert_invalid_duration: '请输入有效的防封控时间。',
        alert_min_duration: '防封控时间最小为 5 分钟。',
        alert_min_gt_max: '最小时间不能大于最大时间。',
        log_stop_sent: '[INFO] 已发送停止信号，等待当前任务完成...',
        status_running_progress: '运行中... ({completed}/{total})',
        status_stopping_detail: '正在停止，等待当前操作退出...',
        status_done_detail: '已完成（{completed} 成功，{failed} 失败）',
        status_error_detail: '错误：{error}',
    },
    en: {
        title: 'Android Automated Forensic Tool',
        card_task_file: 'Task Source',
        label_task_source: 'Task source',
        opt_from_file: 'Load from file',
        opt_from_database: 'Load from database',
        label_select_file: 'Select task file (JSON / CSV / TXT)',
        no_file_selected: 'No file selected',
        btn_browse: 'Browse...',
        label_batch_size: 'Batch size',
        hint_batch_size: 'Number of pending tasks to load from database per batch.',
        btn_test_db: 'Test DB Connection',
        db_test_ok: 'Connected! Pending tasks: {count}',
        db_test_fail: 'Connection failed: {error}',
        db_test_no_config: 'config/database.json not found. Please configure database first.',
        card_antibot: 'Anti-bot Protection Settings',
        label_protection_range: 'Protection duration range (minutes)',
        hint_protection: 'Minimum 5 min. Each cycle randomly picks a value in this range, then auto-splits into browse simulation + cooldown segments.',
        card_exec_settings: 'Execution Settings',
        label_exec_mode: 'Execution mode',
        opt_sequential: 'Single device - Sequential',
        opt_parallel: 'Multi-device - Parallel',
        label_device_ids: 'Device IDs (comma-separated, leave empty to auto-detect)',
        ph_device_ids: 'e.g. device1,device2',
        label_strategy: 'Dispatch strategy',
        opt_round_robin: 'Round Robin',
        opt_load_balance: 'Load Balance',
        opt_random: 'Random',
        label_video_duration: 'Video recording duration (seconds)',
        label_group_size: 'Max products per evidence',
        hint_group_size: 'Group by shop, max products per group.',
        btn_start: 'Start Execution',
        btn_stop: 'Stop Execution',
        card_log: 'Execution Log',
        status_idle: 'Idle',
        status_running: 'Running',
        status_stopping: 'Stopping',
        status_done: 'Completed',
        status_error: 'Error',
        alert_no_file: 'Please select a task file first.',
        alert_invalid_duration: 'Please enter valid protection duration values.',
        alert_min_duration: 'Minimum protection duration is 5 minutes.',
        alert_min_gt_max: 'Minimum duration cannot be greater than maximum.',
        log_stop_sent: '[INFO] Stop signal sent, waiting for current task to finish...',
        status_running_progress: 'Running... ({completed}/{total})',
        status_stopping_detail: 'Stopping, waiting for current operation to exit...',
        status_done_detail: 'Completed ({completed} success, {failed} failed)',
        status_error_detail: 'Error: {error}',
    }
};

let currentLang = 'zh';

function T(key, params) {
    let text = LANG[currentLang][key] || LANG['en'][key] || key;
    if (params) {
        for (const [k, v] of Object.entries(params)) {
            text = text.replace('{' + k + '}', v);
        }
    }
    return text;
}

function switchLang(lang) {
    currentLang = lang;
    document.getElementById('langZh').className = lang === 'zh' ? 'active' : '';
    document.getElementById('langEn').className = lang === 'en' ? 'active' : '';
    applyLang();
}

function applyLang() {
    // data-i18n: set textContent
    document.querySelectorAll('[data-i18n]').forEach(el => {
        el.textContent = T(el.getAttribute('data-i18n'));
    });
    // data-i18n-default: set textContent only if no user content (file path)
    document.querySelectorAll('[data-i18n-default]').forEach(el => {
        if (!el.dataset.userContent) {
            el.textContent = T(el.getAttribute('data-i18n-default'));
        }
    });
    // data-i18n-opt: set option text
    document.querySelectorAll('[data-i18n-opt]').forEach(el => {
        el.textContent = T(el.getAttribute('data-i18n-opt'));
    });
    // data-i18n-ph: set placeholder
    document.querySelectorAll('[data-i18n-ph]').forEach(el => {
        el.placeholder = T(el.getAttribute('data-i18n-ph'));
    });
    // Update status text if idle
    const statusEl = document.getElementById('statusText');
    if (statusEl && statusEl.dataset.statusKey) {
        statusEl.textContent = T(statusEl.dataset.statusKey);
    }
}

// ==================== App Logic ====================
let selectedFilePath = null;
let logPollTimer = null;

function onModeChange() {
    const mode = document.getElementById('execMode').value;
    const opts = document.getElementById('parallelOptions');
    if (mode === 'parallel') {
        opts.classList.add('visible');
    } else {
        opts.classList.remove('visible');
    }
}

function onTaskSourceChange() {
    const source = document.getElementById('taskSource').value;
    const fileGroup = document.getElementById('fileSourceGroup');
    const dbGroup = document.getElementById('dbSourceGroup');
    if (source === 'database') {
        fileGroup.style.display = 'none';
        dbGroup.style.display = 'block';
    } else {
        fileGroup.style.display = 'block';
        dbGroup.style.display = 'none';
    }
}

async function testDbConnection() {
    const btn = document.getElementById('btnTestDb');
    const result = document.getElementById('dbTestResult');
    btn.disabled = true;
    result.textContent = '...';
    result.style.color = '#999';

    try {
        const res = await pywebview.api.test_db_connection();
        if (res && res.success) {
            result.textContent = T('db_test_ok', {count: res.pending_count});
            result.style.color = '#52c41a';
        } else {
            result.textContent = T('db_test_fail', {error: res ? res.error : 'Unknown'});
            result.style.color = '#ff4d4f';
        }
    } catch (e) {
        result.textContent = T('db_test_fail', {error: String(e)});
        result.style.color = '#ff4d4f';
    }
    btn.disabled = false;
}

async function selectFile() {
    const result = await pywebview.api.select_task_file();
    if (result) {
        selectedFilePath = result;
        const el = document.getElementById('filePath');
        el.textContent = result;
        el.title = result;
        el.dataset.userContent = 'true';
    }
}

function validate() {
    const taskSource = document.getElementById('taskSource').value;
    if (taskSource === 'file' && !selectedFilePath) {
        alert(T('alert_no_file'));
        return false;
    }

    const pMin = parseInt(document.getElementById('protectionMin').value);
    const pMax = parseInt(document.getElementById('protectionMax').value);

    if (isNaN(pMin) || isNaN(pMax)) {
        alert(T('alert_invalid_duration'));
        return false;
    }

    if (pMin < 5) {
        alert(T('alert_min_duration'));
        return false;
    }

    if (pMin > pMax) {
        alert(T('alert_min_gt_max'));
        return false;
    }

    return true;
}

async function startExecution() {
    if (!validate()) return;

    const params = {
        task_file: selectedFilePath,
        task_source: document.getElementById('taskSource').value,
        protection_min: parseInt(document.getElementById('protectionMin').value),
        protection_max: parseInt(document.getElementById('protectionMax').value),
        exec_mode: document.getElementById('execMode').value,
        video_duration: parseInt(document.getElementById('videoDuration').value),
        group_size: parseInt(document.getElementById('groupSize').value),
        batch_size: parseInt(document.getElementById('batchSize').value) || 100,
        device_ids: document.getElementById('deviceIds').value.trim(),
        strategy: document.getElementById('strategy').value,
        lang: currentLang === 'zh' ? 'zh_CN' : 'en_US',
    };

    // Show log area
    document.getElementById('logCard').style.display = 'block';
    document.getElementById('logArea').textContent = '';
    setStatus('running', T('status_running'));

    // Toggle buttons
    document.getElementById('startSection').style.display = 'none';
    document.getElementById('stopSection').style.display = 'block';

    // Start execution
    const result = await pywebview.api.start_execution(params);
    if (result && result.error) {
        appendLog('[ERROR] ' + result.error);
        setStatus('error', T('status_error'));
        document.getElementById('startSection').style.display = 'block';
        document.getElementById('stopSection').style.display = 'none';
        return;
    }

    // Start polling logs
    startLogPolling();
}

async function stopExecution() {
    await pywebview.api.stop_execution();
    appendLog(T('log_stop_sent'));
}

function startLogPolling() {
    if (logPollTimer) clearInterval(logPollTimer);
    logPollTimer = setInterval(async () => {
        const status = await pywebview.api.get_status();
        if (!status) return;

        // Append new logs
        if (status.new_logs && status.new_logs.length > 0) {
            for (const line of status.new_logs) {
                appendLog(line);
            }
        }

        // Update status
        if (status.state === 'running') {
            setStatus('running', T('status_running_progress', {completed: status.completed || 0, total: status.total || 0}));
        } else if (status.state === 'stopping') {
            setStatus('stopping', T('status_stopping_detail'));
        } else if (status.state === 'done') {
            setStatus('done', T('status_done_detail', {completed: status.completed || 0, failed: status.failed || 0}));
            clearInterval(logPollTimer);
            logPollTimer = null;
            document.getElementById('startSection').style.display = 'block';
            document.getElementById('stopSection').style.display = 'none';
        } else if (status.state === 'error') {
            setStatus('error', T('status_error_detail', {error: status.error || 'Unknown'}));
            clearInterval(logPollTimer);
            logPollTimer = null;
            document.getElementById('startSection').style.display = 'block';
            document.getElementById('stopSection').style.display = 'none';
        }
    }, 1000);
}

function appendLog(text) {
    const area = document.getElementById('logArea');
    area.textContent += text + '\\n';
    area.scrollTop = area.scrollHeight;
}

function setStatus(state, text) {
    const dot = document.getElementById('statusDot');
    dot.className = 'status-dot ' + state;
    const statusEl = document.getElementById('statusText');
    statusEl.textContent = text;
    // Store key for lang switch refresh
    if (state === 'idle') statusEl.dataset.statusKey = 'status_idle';
    else delete statusEl.dataset.statusKey;
}

// Initialize language on page load
document.addEventListener('DOMContentLoaded', () => {
    applyLang();
    setStatus('idle', T('status_idle'));
});
</script>

</body>
</html>
"""


# ==================== Log Capture Handler ====================

class GUILogHandler(logging.Handler):
    """Captures log messages for the GUI display."""

    def __init__(self):
        super().__init__()
        self._logs = []
        self._lock = threading.Lock()

    def emit(self, record):
        try:
            msg = self.format(record)
            with self._lock:
                self._logs.append(msg)
        except Exception:
            pass

    def get_new_logs(self):
        with self._lock:
            logs = self._logs[:]
            self._logs.clear()
        return logs


# ==================== API Class ====================

class LauncherAPI:
    """Python API exposed to the pywebview frontend."""

    def __init__(self):
        self.window = None
        self._execution_process = None
        self._log_queue = None
        self._state = 'idle'  # idle, running, done, error
        self._error = None
        self._stats = {}
        self._stop_requested = False

        # Log capture
        self._log_handler = GUILogHandler()
        self._log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        self._log_poll_thread = None

    def select_task_file(self):
        """Open native file dialog to select task file."""
        if not self.window:
            return None

        result = self.window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=(
                'Task Files (*.json;*.csv;*.txt)',
                'JSON Files (*.json)',
                'CSV Files (*.csv)',
                'Text Files (*.txt)',
                'All Files (*.*)',
            )
        )

        if result and len(result) > 0:
            return result[0]
        return None

    def test_db_connection(self):
        """Test database connection and return pending task count."""
        try:
            db_config = Path(__file__).parent.parent / 'config' / 'database.json'
            if not db_config.exists():
                return {'success': False, 'error': 'config/database.json not found'}

            # Ensure src is in path
            src_dir = str(Path(__file__).parent)
            if src_dir not in sys.path:
                sys.path.insert(0, src_dir)

            from task.db_task_loader import DBTaskLoader
            loader = DBTaskLoader(str(db_config))
            count = loader.get_pending_count()
            loader.close()
            return {'success': True, 'pending_count': count}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def start_execution(self, params):
        """Start forensic execution in a subprocess (so SIGINT can interrupt it)."""
        if self._state == 'running':
            return {'error': 'Already running'}

        self._state = 'running'
        self._error = None
        self._stats = {}
        self._stop_requested = False

        # Create a multiprocessing queue for log messages from subprocess
        self._log_queue = multiprocessing.Queue()

        # Start execution in a subprocess
        self._execution_process = multiprocessing.Process(
            target=_subprocess_worker,
            args=(params, self._log_queue),
            daemon=True
        )
        self._execution_process.start()

        # Start a thread to poll log messages from the subprocess queue
        self._log_poll_thread = threading.Thread(
            target=self._poll_subprocess_logs,
            daemon=True
        )
        self._log_poll_thread.start()

        return {'status': 'started'}

    def stop_execution(self):
        """Stop execution by sending SIGINT to subprocess (same as Ctrl+C)."""
        if self._execution_process and self._execution_process.is_alive():
            self._stop_requested = True
            self._state = 'stopping'
            # Send SIGINT directly to the subprocess - this interrupts time.sleep(),
            # subprocess calls, etc. exactly like Ctrl+C
            os.kill(self._execution_process.pid, signal.SIGINT)
            logger.info("SIGINT sent to execution subprocess (equivalent to Ctrl+C)")
        return {'status': 'stop_requested'}

    def get_status(self):
        """Get current execution status and new log lines."""
        new_logs = self._log_handler.get_new_logs()

        return {
            'state': self._state,
            'new_logs': new_logs,
            'completed': self._stats.get('completed', 0),
            'failed': self._stats.get('failed', 0),
            'total': self._stats.get('total_tasks', 0),
            'error': self._error,
        }

    def _poll_subprocess_logs(self):
        """Poll log messages from the subprocess queue and update state."""
        import queue as queue_module
        while True:
            # Check if subprocess is still alive
            proc_alive = self._execution_process and self._execution_process.is_alive()

            # Drain all available log messages
            while True:
                try:
                    msg = self._log_queue.get_nowait()
                    if isinstance(msg, dict):
                        # Control message from subprocess
                        if msg.get('type') == 'done':
                            self._state = 'done'
                        elif msg.get('type') == 'error':
                            self._state = 'error'
                            self._error = msg.get('error', 'Unknown error')
                        elif msg.get('type') == 'interrupted':
                            self._state = 'stopping'
                    else:
                        # Log line
                        self._log_handler._logs.append(str(msg))
                except queue_module.Empty:
                    break

            if not proc_alive and self._state in ('running', 'stopping'):
                # Process exited without sending a done/error message
                exitcode = self._execution_process.exitcode
                if exitcode == 0 or exitcode == -2:  # -2 = SIGINT on some systems
                    self._state = 'done'
                else:
                    self._state = 'error'
                    self._error = f'Process exited with code {exitcode}'

            if not proc_alive:
                break

            time.sleep(0.5)


def _subprocess_worker(params, log_queue):
    """
    Run forensic execution in a subprocess.
    This function runs in a separate process so SIGINT can interrupt time.sleep() etc.
    """
    import logging
    import sys
    from pathlib import Path

    # Set up logging to send messages to the queue
    class QueueLogHandler(logging.Handler):
        def __init__(self, q):
            super().__init__()
            self.queue = q
        def emit(self, record):
            try:
                msg = self.format(record)
                self.queue.put(msg)
            except Exception:
                pass

    # Configure logging for this subprocess
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()
    queue_handler = QueueLogHandler(log_queue)
    queue_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    root_logger.addHandler(queue_handler)

    # Also keep file handler
    log_dir = Path(__file__).parent.parent / 'logs'
    log_dir.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(log_dir / 'evidence.log', encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    root_logger.addHandler(file_handler)

    logger = logging.getLogger(__name__)

    try:
        task_file = params.get('task_file', '')
        task_source = params.get('task_source', 'file')
        protection_min = params.get('protection_min', 25)
        protection_max = params.get('protection_max', 35)
        exec_mode = params.get('exec_mode', 'sequential')
        video_duration = params.get('video_duration', 30)
        group_size = params.get('group_size', 3)
        batch_size = params.get('batch_size', 100)
        device_ids_str = params.get('device_ids', '')
        strategy = params.get('strategy', 'round_robin')
        lang = params.get('lang', 'en_US')

        # Set log language to match GUI language
        from locales import set_language
        set_language(lang)

        # Validate file exists (file mode only)
        if task_source == 'file' and not Path(task_file).exists():
            log_queue.put({'type': 'error', 'error': f'Task file not found: {task_file}'})
            return

        # Build protection duration override
        protection_duration = [protection_min, protection_max]

        logger.info(f"Starting execution: source={task_source}, protection={protection_min}-{protection_max}min, mode={exec_mode}, group_size={group_size}")

        # Need to ensure src is in path for imports
        src_dir = str(Path(__file__).parent)
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)

        device_ids = None
        if device_ids_str:
            normalized_device_ids = device_ids_str.replace('，', ',')
            device_ids = [d.strip() for d in normalized_device_ids.split(',') if d.strip()]

        # Database mode
        if task_source == 'database':
            from main import run_grouped_batch_mode, run_parallel_grouped_db_mode
            db_config = str(Path(__file__).parent.parent / 'config' / 'database.json')

            if exec_mode == 'parallel':
                success = run_parallel_grouped_db_mode(
                    device_ids=device_ids,
                    video_duration=video_duration,
                    enable_antibot=True,
                    strategy=strategy,
                    protection_duration=protection_duration,
                    group_size=group_size,
                    db_config_path=db_config,
                    batch_size=batch_size,
                )
            else:
                success = run_grouped_batch_mode(
                    task_file=None,
                    device_id=None,
                    video_duration=video_duration,
                    enable_antibot=True,
                    protection_duration=protection_duration,
                    group_size=group_size,
                    db_config_path=db_config,
                    batch_size=batch_size,
                )
        # Grouped mode (file source, group_size > 0)
        elif group_size > 0:
            from main import run_grouped_batch_mode

            success = run_grouped_batch_mode(
                task_file=task_file,
                device_id=None,
                video_duration=video_duration,
                enable_antibot=True,
                protection_duration=protection_duration,
                group_size=group_size,
            )
        elif exec_mode == 'parallel':
            from core.parallel_executor import run_parallel_mode

            success = run_parallel_mode(
                task_file=task_file,
                device_ids=device_ids,
                video_duration=video_duration,
                enable_antibot=True,
                strategy=strategy,
                protection_duration=protection_duration
            )
        else:
            from main import run_batch_mode

            success = run_batch_mode(
                task_file=task_file,
                device_id=None,
                video_duration=video_duration,
                enable_antibot=True,
                protection_duration=protection_duration
            )

        logger.info(f"Execution finished: {'success' if success else 'with failures'}")
        log_queue.put({'type': 'done'})

    except KeyboardInterrupt:
        logger.warning("Execution interrupted by user (stop button)")
        log_queue.put({'type': 'interrupted'})

    except Exception as e:
        logger.error(f"Execution error: {e}", exc_info=True)
        log_queue.put({'type': 'error', 'error': str(e)})


# ==================== WebView2 Check ====================

def _check_webview2_available() -> bool:
    """Check if WebView2 Runtime is available (Windows only)."""
    if sys.platform != 'win32':
        return True  # Not needed on macOS/Linux

    try:
        import winreg
        # Check both 32-bit and 64-bit registry locations
        registry_paths = [
            (winreg.HKEY_LOCAL_MACHINE,
             r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BEE-13A6A2E75E11}"),
            (winreg.HKEY_LOCAL_MACHINE,
             r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BEE-13A6A2E75E11}"),
            (winreg.HKEY_CURRENT_USER,
             r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BEE-13A6A2E75E11}"),
        ]

        for hkey, path in registry_paths:
            try:
                key = winreg.OpenKey(hkey, path)
                version, _ = winreg.QueryValueEx(key, "pv")
                winreg.CloseKey(key)
                if version:
                    logger.info(f"WebView2 Runtime found: v{version}")
                    return True
            except (FileNotFoundError, OSError):
                continue

        return False
    except ImportError:
        # winreg not available (non-Windows)
        return True


def _install_webview2():
    """Attempt to install WebView2 Runtime from bundled bootstrapper."""
    import subprocess

    # Look for bootstrapper in common locations
    bootstrapper_paths = [
        Path(__file__).parent.parent / "MicrosoftEdgeWebview2Setup.exe",
        Path(__file__).parent.parent / "build" / "resources" / "MicrosoftEdgeWebview2Setup.exe",
        Path(sys.executable).parent / "MicrosoftEdgeWebview2Setup.exe",
    ]

    for path in bootstrapper_paths:
        if path.exists():
            logger.info(f"Installing WebView2 from: {path}")
            try:
                result = subprocess.run(
                    [str(path), "/silent", "/install"],
                    timeout=120,
                )
                return result.returncode == 0
            except Exception as e:
                logger.error(f"WebView2 installation failed: {e}")
                return False

    logger.warning("WebView2 bootstrapper not found")
    return False


# ==================== Launch Function ====================

def launch_gui():
    """Launch the pywebview GUI window."""
    global webview
    if webview is None:
        import webview as _webview
        webview = _webview

    # Check WebView2 on Windows
    if sys.platform == 'win32' and not _check_webview2_available():
        logger.warning("WebView2 Runtime not detected, attempting installation...")
        if not _install_webview2():
            print("ERROR: WebView2 Runtime is required but not installed.")
            print("Please download and install it from:")
            print("  https://developer.microsoft.com/en-us/microsoft-edge/webview2/")
            print("Or run the bundled installer: MicrosoftEdgeWebview2Setup.exe")
            sys.exit(1)

    api = LauncherAPI()

    window = webview.create_window(
        title='Android Automated Forensic Tool',
        html=HTML_CONTENT,
        js_api=api,
        width=720,
        height=820,
        resizable=True,
        min_size=(600, 700),
    )

    api.window = window

    webview.start(debug=False)


def main():
    """Program entry point for standalone GUI executable."""
    multiprocessing.freeze_support()
    if "--subprocess-ocr" in sys.argv:
        from core.ocr_engine import _subprocess_cli
        raise SystemExit(_subprocess_cli())
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    launch_gui()


if __name__ == '__main__':
    main()
