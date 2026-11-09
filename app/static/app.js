const state = {
    token: localStorage.getItem("matrix_jwt") || null,
    user: null,
    activeTaskId: null,
    pollTimer: null,
    adminTimer: null,
    maxMatrixSize: 600,
    minMatrixSize: 2,
};

function updateServedBy(headers) {
    const server = headers.get("X-Served-By");
    if (server) {
        document.getElementById("servedByBadge").textContent = server;
    }
}

async function apiFetch(path, options = {}) {
    const headers = Object.assign({ "Content-Type": "application/json" }, options.headers || {});
    if (state.token) {
        headers["Authorization"] = `Bearer ${state.token}`;
    }
    const response = await fetch(`/api${path}`, Object.assign({}, options, { headers }));
    updateServedBy(response.headers);
    if (response.status === 204) {
        return null;
    }
    const data = await response.json();
    if (!response.ok) {
        const msg = typeof data.detail === "string"
            ? data.detail
            : JSON.stringify(data.detail || "Помилка запиту");
        throw new Error(msg);
    }
    return data;
}

function buildManualGrid(dim) {
    const clamped = Math.max(2, Math.min(8, dim));
    const container = document.getElementById("matrixGridContainer");
    container.style.gridTemplateColumns = `repeat(${clamped}, 1fr)`;
    container.innerHTML = "";
    for (let i = 0; i < clamped; i++) {
        for (let j = 0; j < clamped; j++) {
            const inp = document.createElement("input");
            inp.type = "number";
            inp.step = "any";
            inp.value = i === j ? "4" : "1";
            inp.dataset.row = String(i);
            inp.dataset.col = String(j);
            container.appendChild(inp);
        }
    }
}

function readManualGrid(dim) {
    const clamped = Math.max(2, Math.min(8, dim));
    const inputs = document.querySelectorAll("#matrixGridContainer input");
    const mat = Array.from({ length: clamped }, () => Array(clamped).fill(0));
    inputs.forEach((inp) => {
        const r = parseInt(inp.dataset.row, 10);
        const c = parseInt(inp.dataset.col, 10);
        mat[r][c] = parseFloat(inp.value || "0");
    });
    return mat;
}

function validateMatrixInputClientSide() {
    const sizeVal = parseInt(document.getElementById("matrixSizeInput").value || "0", 10);
    const warnBox = document.getElementById("clientValidationWarning");
    if (sizeVal < state.minMatrixSize || sizeVal > state.maxMatrixSize) {
        warnBox.textContent = `Увага (клієнтська перевірка): розмірність N=${sizeVal} виходить за межі [${state.minMatrixSize}..${state.maxMatrixSize}]. Сервер відхилить такий запит.`;
        warnBox.classList.remove("hidden");
        return false;
    }
    warnBox.classList.add("hidden");
    return true;
}

function renderActiveTask(task) {
    document.getElementById("noActiveTaskBox").classList.add("hidden");
    document.getElementById("activeTaskCard").classList.remove("hidden");

    document.getElementById("activeTaskId").textContent = `№${task.id}`;
    document.getElementById("activeTaskSize").textContent = `${task.matrix_size} × ${task.matrix_size}`;
    document.getElementById("activeTaskStatusBadge").textContent = task.status;
    document.getElementById("activeTaskStage").textContent = task.current_stage;
    document.getElementById("activeTaskPercent").textContent = `${task.progress}%`;
    document.getElementById("activeTaskProgressFill").style.width = `${task.progress}%`;
    document.getElementById("activeTaskWorker").textContent = task.worker_hostname || "очікує";
    document.getElementById("activeTaskTime").textContent = task.execution_time_sec ? `${task.execution_time_sec} с` : "-";
    document.getElementById("activeTaskResidual").textContent = task.residual_norm !== null && task.residual_norm !== undefined ? String(task.residual_norm) : "-";

    const qBanner = document.getElementById("queueEtaBanner");
    if (task.queue_message) {
        qBanner.textContent = task.queue_message;
        qBanner.classList.remove("hidden");
    } else {
        qBanner.classList.add("hidden");
    }

    const errBanner = document.getElementById("activeTaskErrorBanner");
    if (task.error_message) {
        errBanner.textContent = task.error_message;
        errBanner.classList.remove("hidden");
    } else {
        errBanner.classList.add("hidden");
    }

    const cancelBtn = document.getElementById("cancelActiveTaskBtn");
    if (task.status === "QUEUED" || task.status === "PROCESSING") {
        cancelBtn.classList.remove("hidden");
    } else {
        cancelBtn.classList.add("hidden");
    }

    const viewResBtn = document.getElementById("viewResultMatrixBtn");
    if (task.status === "COMPLETED") {
        viewResBtn.classList.remove("hidden");
    } else {
        viewResBtn.classList.add("hidden");
        document.getElementById("matrixResultModal").classList.add("hidden");
    }
}

async function pollActiveTask() {
    if (!state.activeTaskId || !state.token) {
        return;
    }
    try {
        const task = await apiFetch(`/tasks/${state.activeTaskId}`);
        renderActiveTask(task);
        if (["COMPLETED", "FAILED", "CANCELLED", "TIMEOUT"].includes(task.status)) {
            clearInterval(state.pollTimer);
            state.pollTimer = null;
            await loadTaskHistory();
        }
    } catch (_) {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
    }
}

function startPollingTask(taskId) {
    state.activeTaskId = taskId;
    if (state.pollTimer) {
        clearInterval(state.pollTimer);
    }
    pollActiveTask();
    state.pollTimer = setInterval(pollActiveTask, 1200);
}

async function loadTaskHistory() {
    if (!state.token) {
        return;
    }
    const data = await apiFetch("/tasks");
    document.getElementById("historyCountBadge").textContent = String(data.total);
    document.getElementById("activeQuotaText").textContent = `${data.active_count} / ${data.max_active_limit}`;
    document.getElementById("historyQuotaText").textContent = `${data.total} / ${data.max_history_limit}`;

    const tbody = document.getElementById("historyTableBody");
    tbody.innerHTML = "";
    data.items.forEach((t) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>№${t.id}</td>
            <td>${t.matrix_size}×${t.matrix_size}</td>
            <td><span class="status-badge">${t.status}</span></td>
            <td>${t.progress}% — ${t.current_stage}</td>
            <td>${t.worker_hostname || "-"}</td>
            <td>${t.execution_time_sec ? t.execution_time_sec + " с" : "-"}</td>
            <td>${t.residual_norm !== null && t.residual_norm !== undefined ? t.residual_norm : "-"}</td>
            <td>
                <button class="btn btn-outline btn-sm select-task-btn" data-id="${t.id}">Відкрити</button>
                ${["QUEUED", "PROCESSING"].includes(t.status)
                    ? `<button class="btn btn-danger btn-sm cancel-row-btn" data-id="${t.id}">Скасувати</button>`
                    : `<button class="btn btn-danger btn-sm delete-row-btn" data-id="${t.id}">Видалити</button>`
                }
            </td>
        `;
        tbody.appendChild(tr);
    });

    tbody.querySelectorAll(".select-task-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            const id = parseInt(btn.dataset.id, 10);
            document.querySelector('[data-target="viewCompute"]').click();
            startPollingTask(id);
        });
    });

    tbody.querySelectorAll(".cancel-row-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const id = parseInt(btn.dataset.id, 10);
            await apiFetch(`/tasks/${id}/cancel`, { method: "POST" });
            await loadTaskHistory();
            if (state.activeTaskId === id) {
                pollActiveTask();
            }
        });
    });

    tbody.querySelectorAll(".delete-row-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const id = parseInt(btn.dataset.id, 10);
            await apiFetch(`/tasks/${id}`, { method: "DELETE" });
            await loadTaskHistory();
        });
    });
}

async function loadAdminOverview() {
    if (!state.user || state.user.role !== "admin") {
        return;
    }
    try {
        const overview = await apiFetch("/admin/overview");
        document.getElementById("adminCpuText").textContent = `${overview.system_metrics.cpu_percent}%`;
        document.getElementById("adminCpuFill").style.width = `${overview.system_metrics.cpu_percent}%`;
        document.getElementById("adminRamText").textContent =
            `${overview.system_metrics.memory_percent}% (${overview.system_metrics.memory_used_mb} МБ)`;
        document.getElementById("adminRamFill").style.width = `${overview.system_metrics.memory_percent}%`;

        document.getElementById("adminWorkersCount").textContent =
            `${overview.autoscaler.current_workers} / ${overview.autoscaler.max_workers}`;
        document.getElementById("adminMinWorkers").textContent = String(overview.autoscaler.min_workers);
        document.getElementById("adminMaxWorkers").textContent = String(overview.autoscaler.max_workers);
        document.getElementById("adminLastScaleAction").textContent = overview.autoscaler.last_action;

        const bList = document.getElementById("adminBackendNodesList");
        bList.innerHTML = "";
        overview.backend_nodes.forEach((b) => {
            const li = document.createElement("li");
            li.textContent = `${b.hostname} — ${b.status}${b.is_current_responder ? " (поточний)" : ""}`;
            bList.appendChild(li);
        });

        const wList = document.getElementById("adminWorkerNodesList");
        wList.innerHTML = "";
        overview.worker_nodes.forEach((w) => {
            const li = document.createElement("li");
            li.textContent = w.active_task_id
                ? `${w.name}: BUSY (Задача №${w.active_task_id}, ${w.active_progress}%)`
                : `${w.name}: IDLE (вільний)`;
            wList.appendChild(li);
        });

        const tasks = await apiFetch("/admin/tasks");
        const tbody = document.getElementById("adminTasksTableBody");
        tbody.innerHTML = "";
        tasks.forEach((t) => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>№${t.id}</td>
                <td>${t.username}</td>
                <td>${t.matrix_size}×${t.matrix_size}</td>
                <td><span class="status-badge">${t.status}</span></td>
                <td>${t.progress}%</td>
                <td>${t.current_stage}</td>
                <td>${t.worker_hostname || "-"}</td>
                <td>
                    ${["QUEUED", "PROCESSING"].includes(t.status)
                        ? `<button class="btn btn-danger btn-sm admin-kill-btn" data-id="${t.id}">Зупинити</button>`
                        : "-"
                    }
                </td>
            `;
            tbody.appendChild(tr);
        });

        tbody.querySelectorAll(".admin-kill-btn").forEach((btn) => {
            btn.addEventListener("click", async () => {
                const id = parseInt(btn.dataset.id, 10);
                await apiFetch(`/admin/tasks/${id}/cancel`, { method: "POST" });
                await loadAdminOverview();
            });
        });
    } catch (_) {}
}

function enterAuthenticatedMode(user) {
    state.user = user;
    state.maxMatrixSize = user.max_matrix_size || 600;
    document.getElementById("maxSizeLabel").textContent = String(state.maxMatrixSize);
    document.getElementById("authSection").classList.add("hidden");
    document.getElementById("workspaceSection").classList.remove("hidden");
    document.getElementById("userChip").classList.remove("hidden");
    document.getElementById("currentUsername").textContent = user.username;
    document.getElementById("currentUserRole").textContent = user.role;

    const adminBtn = document.getElementById("adminNavBtn");
    if (user.role === "admin") {
        adminBtn.classList.remove("hidden");
        loadAdminOverview();
    } else {
        adminBtn.classList.add("hidden");
    }
    loadTaskHistory();
}

async function initSession() {
    buildManualGrid(4);
    try {
        await apiFetch("/cluster/node");
    } catch (_) {}

    if (!state.token) {
        return;
    }
    try {
        const user = await apiFetch("/auth/me");
        enterAuthenticatedMode(user);
    } catch (_) {
        localStorage.removeItem("matrix_jwt");
        state.token = null;
    }
}

document.getElementById("tabLoginBtn").addEventListener("click", () => {
    document.getElementById("tabLoginBtn").classList.add("active");
    document.getElementById("tabRegisterBtn").classList.remove("active");
    document.getElementById("loginForm").classList.remove("hidden");
    document.getElementById("registerForm").classList.add("hidden");
});

document.getElementById("tabRegisterBtn").addEventListener("click", () => {
    document.getElementById("tabRegisterBtn").classList.add("active");
    document.getElementById("tabLoginBtn").classList.remove("active");
    document.getElementById("registerForm").classList.remove("hidden");
    document.getElementById("loginForm").classList.add("hidden");
});

document.getElementById("fillAdminBtn").addEventListener("click", () => {
    document.getElementById("loginUsername").value = "admin";
    document.getElementById("loginPassword").value = "admin123";
});

document.getElementById("loginForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = document.getElementById("authError");
    err.classList.add("hidden");
    try {
        const res = await apiFetch("/auth/login", {
            method: "POST",
            body: JSON.stringify({
                username: document.getElementById("loginUsername").value.trim(),
                password: document.getElementById("loginPassword").value,
            }),
        });
        state.token = res.access_token;
        localStorage.setItem("matrix_jwt", state.token);
        enterAuthenticatedMode(res.user);
    } catch (ex) {
        err.textContent = ex.message;
        err.classList.remove("hidden");
    }
});

document.getElementById("registerForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = document.getElementById("authError");
    err.classList.add("hidden");
    try {
        const res = await apiFetch("/auth/register", {
            method: "POST",
            body: JSON.stringify({
                username: document.getElementById("regUsername").value.trim(),
                email: document.getElementById("regEmail").value.trim(),
                password: document.getElementById("regPassword").value,
            }),
        });
        state.token = res.access_token;
        localStorage.setItem("matrix_jwt", state.token);
        enterAuthenticatedMode(res.user);
    } catch (ex) {
        err.textContent = ex.message;
        err.classList.remove("hidden");
    }
});

document.getElementById("logoutBtn").addEventListener("click", () => {
    localStorage.removeItem("matrix_jwt");
    state.token = null;
    state.user = null;
    if (state.pollTimer) {
        clearInterval(state.pollTimer);
    }
    document.getElementById("workspaceSection").classList.add("hidden");
    document.getElementById("userChip").classList.add("hidden");
    document.getElementById("authSection").classList.remove("hidden");
});

document.querySelectorAll(".nav-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
        document.querySelectorAll(".nav-tab").forEach((t) => t.classList.remove("active"));
        document.querySelectorAll(".view-pane").forEach((p) => p.classList.add("hidden"));
        tab.classList.add("active");
        const target = tab.dataset.target;
        document.getElementById(target).classList.remove("hidden");
        if (target === "viewHistory") {
            loadTaskHistory();
        } else if (target === "viewAdmin") {
            loadAdminOverview();
        }
    });
});

document.getElementById("matrixSizeInput").addEventListener("input", validateMatrixInputClientSide);

document.getElementById("randomMatrixCheck").addEventListener("change", (e) => {
    const wrap = document.getElementById("manualMatrixWrap");
    if (e.target.checked) {
        wrap.classList.add("hidden");
    } else {
        wrap.classList.remove("hidden");
        const dim = parseInt(document.getElementById("matrixSizeInput").value || "4", 10);
        buildManualGrid(dim);
    }
});

document.getElementById("buildGridBtn").addEventListener("click", () => {
    const dim = parseInt(document.getElementById("matrixSizeInput").value || "4", 10);
    buildManualGrid(dim);
});

document.getElementById("createTaskForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const errBox = document.getElementById("taskFormError");
    errBox.classList.add("hidden");

    const sizeVal = parseInt(document.getElementById("matrixSizeInput").value || "0", 10);
    const isRandom = document.getElementById("randomMatrixCheck").checked;
    validateMatrixInputClientSide();

    const body = {
        matrix_size: sizeVal,
        generate_random: isRandom,
    };
    if (!isRandom) {
        body.input_matrix = readManualGrid(sizeVal);
    }

    try {
        const created = await apiFetch("/tasks", {
            method: "POST",
            body: JSON.stringify(body),
        });
        renderActiveTask(created);
        startPollingTask(created.id);
        await loadTaskHistory();
    } catch (ex) {
        errBox.textContent = ex.message;
        errBox.classList.remove("hidden");
    }
});

document.getElementById("cancelActiveTaskBtn").addEventListener("click", async () => {
    if (!state.activeTaskId) {
        return;
    }
    const updated = await apiFetch(`/tasks/${state.activeTaskId}/cancel`, { method: "POST" });
    renderActiveTask(updated);
    await loadTaskHistory();
});

document.getElementById("viewResultMatrixBtn").addEventListener("click", async () => {
    if (!state.activeTaskId) {
        return;
    }
    const res = await apiFetch(`/tasks/${state.activeTaskId}/result`);
    const modal = document.getElementById("matrixResultModal");
    const pre = document.getElementById("matrixResultPre");
    const slice = (res.inverse_matrix || []).slice(0, 6).map((r) => r.slice(0, 6));
    pre.textContent = JSON.stringify(slice, null, 2);
    modal.classList.remove("hidden");
});

document.getElementById("refreshHistoryBtn").addEventListener("click", loadTaskHistory);
document.getElementById("refreshAdminBtn").addEventListener("click", loadAdminOverview);

document.getElementById("scaleUpBtn").addEventListener("click", async () => {
    const err = document.getElementById("adminScaleError");
    err.classList.add("hidden");
    try {
        const currentText = document.getElementById("adminWorkersCount").textContent;
        const curr = parseInt(currentText.split("/")[0].trim(), 10) || 2;
        await apiFetch("/admin/workers/scale", {
            method: "POST",
            body: JSON.stringify({ target_workers: curr + 1, auto_scale_enabled: false }),
        });
        await loadAdminOverview();
    } catch (ex) {
        err.textContent = ex.message;
        err.classList.remove("hidden");
    }
});

document.getElementById("scaleDownBtn").addEventListener("click", async () => {
    const err = document.getElementById("adminScaleError");
    err.classList.add("hidden");
    try {
        const currentText = document.getElementById("adminWorkersCount").textContent;
        const curr = parseInt(currentText.split("/")[0].trim(), 10) || 2;
        await apiFetch("/admin/workers/scale", {
            method: "POST",
            body: JSON.stringify({ target_workers: Math.max(1, curr - 1), auto_scale_enabled: false }),
        });
        await loadAdminOverview();
    } catch (ex) {
        err.textContent = ex.message;
        err.classList.remove("hidden");
    }
});

document.getElementById("testLbBtn").addEventListener("click", async () => {
    const toast = document.getElementById("lbToast");
    const responders = [];
    for (let i = 0; i < 4; i++) {
        try {
            const info = await apiFetch("/cluster/node");
            responders.push(info.instance_hostname);
        } catch (_) {}
    }
    toast.textContent = `Серія з 4 запитів до кластера (Round Robin): ${responders.join(" → ")}`;
    toast.classList.remove("hidden");
    setTimeout(() => toast.classList.add("hidden"), 6000);
});

initSession();
