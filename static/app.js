"use strict";

/* ====== 상태 ====== */
const S = { file: null, fmt: "", cat: "", target: "", mode: "convert", token: null, busy: false };
let CAPS = null;
const $ = (id) => document.getElementById(id);

const CAT_NAME = { doc: "문서", pres: "프레젠테이션", sheet: "스프레드시트", image: "이미지", pdf: "PDF" };
const CAT_ORDER = ["doc", "pres", "sheet", "image", "pdf"];

/* ====== 테마 ====== */
function setTheme(t) {
  document.documentElement.setAttribute("data-theme", t);
  $("themeColor").setAttribute("content", t === "dark" ? "#0d1120" : "#eef1fb");
}
(function initTheme() {
  let saved = null;
  try { saved = localStorage.getItem("theme"); } catch (_) {}
  const sysDark = window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches;
  setTheme(saved || (sysDark ? "dark" : "light"));
})();
$("themeToggle").addEventListener("click", () => {
  const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
  setTheme(next);
  try { localStorage.setItem("theme", next); } catch (_) {}
});

/* ====== 단계 전환 ====== */
function showStep(step) {
  $("sDrop").hidden = step !== "drop";
  $("sPick").hidden = step !== "pick";
  $("sProgress").hidden = step !== "progress";
  $("sResult").hidden = step !== "result";
  $("errorBox").hidden = true;
}
function showError(msg, step) {
  showStep(step || (S.file ? "pick" : "drop"));
  $("errorMsg").textContent = msg;
  $("errorBox").hidden = false;
}
$("errorClose").addEventListener("click", () => { $("errorBox").hidden = true; });

/* ====== 유틸 ====== */
function formatSize(b) {
  if (b < 1024) return b + " B";
  if (b < 1024 * 1024) return (b / 1024).toFixed(1) + " KB";
  return (b / (1024 * 1024)).toFixed(1) + " MB";
}
function extOf(name) { return (name.split(".").pop() || "").toLowerCase(); }
function truncMid(s, n) { return s.length <= n ? s : s.slice(0, n - 8) + "…" + s.slice(-6); }

function refinedHint(value, hint, cat) {
  if (value === "docx") {
    return cat === "doc"
      ? "MS 워드·구글 문서에서 열고 편집할 수 있습니다. 복잡한 서식은 일부 달라질 수 있습니다."
      : "각 페이지가 이미지로 들어갑니다. 모양은 원본 그대로지만 글자 편집은 제한됩니다.";
  }
  if (value === "pptx" && cat !== "pres") {
    return "각 페이지가 이미지 슬라이드로 들어갑니다. 모양은 유지되지만 편집은 제한됩니다.";
  }
  return hint;
}

/* ====== 파일 선택 ====== */
function pickFile(file) {
  const fmt = extOf(file.name);
  if (!CAPS || !CAPS.formats[fmt]) {
    return showError("지원하지 않는 형식입니다. HWP·오피스·PDF·이미지 파일을 올려주세요.");
  }
  const maxMb = CAPS.max_upload_mb || 100;
  if (file.size > maxMb * 1024 * 1024) return showError(`파일이 너무 큽니다. 최대 ${maxMb}MB까지 가능합니다.`);
  if (file.size === 0) return showError("빈 파일입니다.");

  const meta = CAPS.formats[fmt];
  S.file = file; S.fmt = fmt; S.cat = meta.category; S.mode = "convert"; S.token = null;

  const badge = $("fileBadge");
  badge.textContent = (fmt === "jpeg" ? "jpg" : fmt).toUpperCase();
  badge.setAttribute("data-cat", meta.category);
  $("fileName").textContent = file.name;
  $("fileName").title = file.name;
  $("fileSize").textContent = `${CAT_NAME[meta.category] || ""} · ${formatSize(file.size)}`;

  $("pwPanel").hidden = true;
  $("pwInput").value = "";
  $("pwMsg").hidden = true;

  renderTargets(meta);
  setConvertMode("convert");
  showStep("pick");
}

function renderTargets(meta) {
  const box = $("targetOptions");
  box.innerHTML = "";
  let saved = null;
  try { saved = localStorage.getItem("lastTarget:" + meta.category); } catch (_) {}
  const def = meta.targets.find((t) => t.value === saved) ? saved : meta.targets[0].value;

  meta.targets.forEach((t) => {
    const label = document.createElement("label");
    const input = document.createElement("input");
    input.type = "radio"; input.name = "target"; input.value = t.value;
    input.checked = t.value === def;
    input.addEventListener("change", () => selectTarget(t.value));
    label.appendChild(input);
    label.appendChild(document.createTextNode(t.label));
    box.appendChild(label);
  });
  selectTarget(def);
}

function selectTarget(value) {
  S.target = value;
  const t = (CAPS.formats[S.fmt].targets.find((x) => x.value === value)) ||
            (value === "unlock" ? CAPS.unlock : null);
  $("targetHint").textContent = t ? refinedHint(value, t.hint, S.cat) : "";
  try { if (value !== "unlock") localStorage.setItem("lastTarget:" + S.cat, value); } catch (_) {}
}

/* ====== 변환 버튼 모드 ====== */
function setConvertMode(mode) {
  S.mode = mode;
  $("convertBtnText").textContent = mode === "password" ? "암호 해제 후 변환" : "변환하기";
}

/* ====== 업로드(진행률 표시) ====== */
function xhrUpload(form, onProgress) {
  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/convert");
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded / e.total); };
    xhr.onload = () => { let b = null; try { b = JSON.parse(xhr.responseText); } catch (_) {} resolve({ status: xhr.status, body: b }); };
    xhr.onerror = () => resolve({ status: 0, body: null });
    xhr.send(form);
  });
}
function setProgress(pct) {
  const sp = $("spinner");
  sp.classList.add("determinate");
  const circ = 2 * Math.PI * 20;
  sp.querySelector(".sp-arc").style.strokeDasharray = `${(pct * circ).toFixed(1)} ${circ.toFixed(1)}`;
  $("progressText").textContent = `업로드 중… ${Math.round(pct * 100)}%`;
  $("progressSub").textContent = "파일을 서버로 안전하게 전송하고 있습니다.";
}
function setProcessing(text) {
  $("spinner").classList.remove("determinate");
  $("spinner").querySelector(".sp-arc").style.strokeDasharray = "";
  $("progressText").textContent = text || "변환 중입니다…";
  $("progressSub").textContent = "문서 크기에 따라 수 초~수십 초 걸릴 수 있습니다.";
}

/* ====== 변환 / 암호 해제 ====== */
async function doConvert() {
  if (S.busy || !S.file || !S.target) return;
  if (S.mode === "password") return submitPassword(S.target);

  S.busy = true;
  showStep("progress"); setProgress(0);
  const form = new FormData();
  form.append("file", S.file);
  form.append("target", S.target);

  const { status, body } = await xhrUpload(form, (p) => { if (p < 1) setProgress(p); else setProcessing(); });
  S.busy = false;

  if (status === 0) return showError("서버에 연결할 수 없습니다. 네트워크를 확인해주세요.");
  if (status === 200 && body && body.ok) return showResult(body);
  if (status === 200 && body && body.need_password) {
    S.token = body.token;
    enterPasswordMode();
    return;
  }
  showError((body && body.detail) || "변환 중 오류가 발생했습니다.");
}

function enterPasswordMode() {
  showStep("pick");
  $("pwPanel").hidden = false;
  $("pwMsg").hidden = true;
  setConvertMode("password");
  const el = $("pwInput"); el.value = ""; setTimeout(() => el.focus(), 50);
}

async function submitPassword(targetValue) {
  const pw = $("pwInput").value;
  if (!pw) { $("pwMsg").textContent = "비밀번호를 입력하세요."; $("pwMsg").hidden = false; return; }
  if (S.busy || !S.token) return;

  S.busy = true;
  showStep("progress"); setProcessing("암호를 해제하고 변환하는 중…");
  const form = new FormData();
  form.append("token", S.token);
  form.append("password", pw);
  form.append("target", targetValue || S.target);

  let res;
  try {
    const r = await fetch("/api/password", { method: "POST", body: form });
    res = { status: r.status, body: await r.json().catch(() => null) };
  } catch (_) { res = { status: 0, body: null }; }
  S.busy = false;

  const { status, body } = res;
  if (status === 0) return showError("서버에 연결할 수 없습니다.");
  if (status === 200 && body && body.ok) return showResult(body);
  if (status === 200 && body && body.need_password) {
    showStep("pick");
    $("pwPanel").hidden = false;
    const left = body.attempts_left != null ? ` (남은 시도 ${body.attempts_left}회)` : "";
    $("pwMsg").textContent = (body.error || "비밀번호가 올바르지 않습니다.") + left;
    $("pwMsg").hidden = false;
    const el = $("pwInput"); el.value = ""; setTimeout(() => el.focus(), 50);
    return;
  }
  if (status === 404) { // 대기 파일 만료 → 처음부터
    S.token = null;
    return showError("시간이 초과되어 파일이 삭제되었습니다. 파일을 다시 올려주세요.", "drop");
  }
  showError((body && body.detail) || "변환 중 오류가 발생했습니다.");
}

function showResult(body) {
  const link = $("downloadLink");
  link.href = "/api/download/" + encodeURIComponent(body.token);
  link.setAttribute("download", body.filename);
  $("downloadText").textContent = truncMid(body.filename, 30) + " 내려받기";
  showStep("result");
}

/* ====== 리셋 ====== */
function reset() {
  S.file = null; S.fmt = ""; S.target = ""; S.mode = "convert"; S.token = null;
  $("fileInput").value = "";
  $("pwPanel").hidden = true; $("pwInput").value = ""; $("pwMsg").hidden = true;
  showStep("drop");
}

/* ====== 지원 변환 매트릭스 ====== */
function buildMatrix() {
  const body = $("matrixBody");
  body.innerHTML = "";
  const byCat = {};
  Object.entries(CAPS.formats).forEach(([fmt, m]) => {
    (byCat[m.category] = byCat[m.category] || []).push([fmt, m]);
  });
  CAT_ORDER.forEach((cat) => {
    (byCat[cat] || []).forEach(([fmt, m]) => {
      const row = document.createElement("div");
      row.className = "matrix-row";
      const from = document.createElement("span");
      from.className = "matrix-from";
      from.textContent = (fmt === "jpeg" ? "jpg" : fmt).toUpperCase();
      const to = document.createElement("span");
      to.className = "matrix-to";
      to.textContent = "→ " + m.targets.map((t) => t.label.replace(/\s*\(.*\)/, "")).join(", ");
      row.appendChild(from); row.appendChild(to);
      body.appendChild(row);
    });
  });
}

/* ====== 이벤트 바인딩 ====== */
const dz = $("dropzone");
dz.addEventListener("click", () => $("fileInput").click());
dz.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("fileInput").click(); } });
$("fileInput").addEventListener("change", (e) => { if (e.target.files.length) pickFile(e.target.files[0]); });

const card = $("card");
["dragenter", "dragover"].forEach((ev) => card.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("dragover"); }));
["dragleave", "drop"].forEach((ev) => card.addEventListener(ev, (e) => {
  e.preventDefault();
  if (ev === "dragleave" && card.contains(e.relatedTarget)) return;
  dz.classList.remove("dragover");
}));
card.addEventListener("drop", (e) => { if (e.dataTransfer.files.length) pickFile(e.dataTransfer.files[0]); });
document.addEventListener("paste", (e) => { const f = e.clipboardData && e.clipboardData.files; if (f && f.length) pickFile(f[0]); });

$("clearFile").addEventListener("click", reset);
$("restartBtn").addEventListener("click", reset);
$("convertBtn").addEventListener("click", doConvert);
$("unlockOnlyBtn").addEventListener("click", () => submitPassword("unlock"));
$("pwInput").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); submitPassword(S.target); } });
$("pwToggle").addEventListener("click", () => {
  const el = $("pwInput");
  el.type = el.type === "password" ? "text" : "password";
  el.focus();
});

/* ====== 설치(PWA) 안내 ====== */
let deferredPrompt = null;
window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); deferredPrompt = e; $("installBtn").hidden = false; });
$("installBtn").addEventListener("click", async () => {
  if (!deferredPrompt) return;
  deferredPrompt.prompt();
  await deferredPrompt.userChoice;
  deferredPrompt = null; $("installBtn").hidden = true;
});
window.addEventListener("appinstalled", () => { $("installBtn").hidden = true; deferredPrompt = null; });

/* ====== 초기화 ====== */
(async function init() {
  showStep("drop");
  try {
    const r = await fetch("/api/capabilities");
    CAPS = await r.json();
    buildMatrix();
  } catch (_) {
    showError("서버 정보를 불러오지 못했습니다. 새로고침 해주세요.");
  }
})();

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
}
