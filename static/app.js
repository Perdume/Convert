"use strict";

const MAX_BYTES = 50 * 1024 * 1024;
const EXT_TO_FMT = { hwp: "hwp", ppt: "ppt", pptx: "pptx", pdf: "pdf" };
const TARGETS = {
  hwp:  [{ value: "pdf", label: "PDF" }, { value: "pptx", label: "PPT (PPTX)" },
         { value: "docx", label: "워드 (DOCX)" }],
  ppt:  [{ value: "pdf", label: "PDF" }, { value: "hwpx", label: "한글 (HWPX)" },
         { value: "docx", label: "워드 (DOCX)" }],
  pptx: [{ value: "pdf", label: "PDF" }, { value: "hwpx", label: "한글 (HWPX)" },
         { value: "docx", label: "워드 (DOCX)" }],
  pdf:  [{ value: "pptx", label: "PPT (PPTX)" }, { value: "hwpx", label: "한글 (HWPX)" },
         { value: "docx", label: "워드 (DOCX)" }],
};

// 형식별 안내 문구: [소스형식 무관 기본, HWP 소스일 때]
const HINTS = {
  pdf:  "어디서나 동일하게 보이는 문서 형식입니다.",
  pptx: "각 페이지가 고해상도 이미지 슬라이드로 들어갑니다. 모양은 원본 그대로지만 텍스트 편집은 제한됩니다.",
  hwpx: "한글 2014 이상에서 열리는 형식입니다. 각 페이지가 이미지로 들어가 모양은 유지되지만 텍스트 편집은 제한됩니다.",
  docx: "한컴오피스가 없어도 MS 워드·구글 문서(Docs)에서 열 수 있습니다.",
};
const HINT_DOCX_FROM_HWP = "한컴오피스가 없어도 MS 워드·구글 문서(Docs)에서 열고 편집할 수 있습니다. 복잡한 서식은 일부 달라질 수 있습니다.";
const HINT_DOCX_FROM_PAGES = "한컴오피스나 오피스 프로그램이 없어도 MS 워드·구글 문서(Docs)에서 열 수 있습니다. 각 페이지가 이미지로 들어가 텍스트 편집은 제한됩니다.";

const $ = (id) => document.getElementById(id);
let selectedFile = null;

function show(step) {
  $("dropzoneIdle").hidden = step !== "idle";
  $("dropzoneFile").hidden = step === "idle";
  $("dropzone").hidden = step === "progress" || step === "result";
  $("targetSection").hidden = step !== "picked";
  $("progress").hidden = step !== "progress";
  $("result").hidden = step !== "result";
  $("error").hidden = true;
}

function showError(msg) {
  $("errorMsg").textContent = msg;
  $("error").hidden = false;
  $("progress").hidden = true;
  $("dropzone").hidden = false;
  if (selectedFile) $("targetSection").hidden = false;
}

function formatSize(bytes) {
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

function pickFile(file) {
  const ext = (file.name.split(".").pop() || "").toLowerCase();
  const fmt = EXT_TO_FMT[ext];
  if (!fmt) return showError("지원하지 않는 형식입니다. HWP, PPT/PPTX, PDF 파일만 가능합니다.");
  if (file.size > MAX_BYTES) return showError("파일이 너무 큽니다. 최대 50MB까지 가능합니다.");
  if (file.size === 0) return showError("빈 파일입니다.");

  selectedFile = file;
  $("fileName").textContent = file.name;
  $("fileSize").textContent = formatSize(file.size);

  const opts = $("targetOptions");
  opts.innerHTML = "";
  TARGETS[fmt].forEach((t, i) => {
    const label = document.createElement("label");
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "target";
    input.value = t.value;
    if (t.value === preferredTarget(fmt)) input.checked = true;
    input.addEventListener("change", () => { rememberTarget(fmt, t.value); updateHint(fmt); });
    label.appendChild(input);
    label.appendChild(document.createTextNode(t.label));
    opts.appendChild(label);
  });
  if (!opts.querySelector("input:checked")) opts.querySelector("input").checked = true;
  updateHint(fmt);
  $("convertBtn").disabled = false;
  show("picked");
}

// 마지막으로 고른 변환 형식을 원본 형식별로 기억 (저장소를 쓸 수 없으면 조용히 무시)
function preferredTarget(fmt) {
  try { return localStorage.getItem("target:" + fmt) || TARGETS[fmt][0].value; }
  catch (_) { return TARGETS[fmt][0].value; }
}
function rememberTarget(fmt, value) {
  try { localStorage.setItem("target:" + fmt, value); } catch (_) { /* 무시 */ }
}

function updateHint(srcFmt) {
  const checked = document.querySelector('input[name="target"]:checked');
  if (!checked) return;
  let hint = HINTS[checked.value] || "";
  if (checked.value === "docx") {
    hint = srcFmt === "hwp" ? HINT_DOCX_FROM_HWP : HINT_DOCX_FROM_PAGES;
  }
  $("targetHint").textContent = hint;
}

function setProgress(text, percent) {
  $("progressText").textContent = text;
  const bar = $("progressBar");
  bar.hidden = percent == null;
  if (percent != null) bar.value = percent;
}

function sendOnce(file, target) {
  return new Promise((resolve) => {
    const form = new FormData();
    form.append("file", file);
    form.append("target", target);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/convert");
    xhr.responseType = "json";
    xhr.upload.onprogress = (e) => {
      if (!e.lengthComputable) return;
      const pct = Math.round((e.loaded / e.total) * 100);
      setProgress(pct < 100 ? "업로드 중… " + pct + "%" : "변환 중입니다… 잠시만 기다려주세요.",
                  pct < 100 ? pct : null);
    };
    xhr.onload = () => resolve({ status: xhr.status, body: xhr.response,
                                 retryAfter: parseInt(xhr.getResponseHeader("Retry-After"), 10) || 0 });
    xhr.onerror = () => resolve({ status: 0 });
    xhr.send(form);
  });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function convert() {
  const target = document.querySelector('input[name="target"]:checked');
  if (!selectedFile || !target) return;

  show("progress");
  setProgress("업로드 준비 중…", 0);

  let res = await sendOnce(selectedFile, target.value);
  // 요청이 너무 많으면(429) 서버가 알려준 시간만큼 기다렸다가 한 번 자동으로 다시 시도
  if (res.status === 429 && res.retryAfter > 0 && res.retryAfter <= 120) {
    for (let s = res.retryAfter; s > 0; s--) {
      setProgress("요청이 몰려 " + s + "초 뒤 자동으로 다시 시도합니다…", null);
      await sleep(1000);
    }
    setProgress("업로드 준비 중…", 0);
    res = await sendOnce(selectedFile, target.value);
  }

  if (res.status === 0) return showError("서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.");
  if (res.status < 200 || res.status >= 300) {
    const detail = res.body && res.body.detail;
    return showError(typeof detail === "string" ? detail : "변환 중 오류가 발생했습니다.");
  }
  const link = $("downloadLink");
  link.href = "/api/download/" + encodeURIComponent(res.body.token);
  link.setAttribute("download", res.body.filename);
  link.textContent = res.body.filename + " 다운로드";
  show("result");
  link.focus();
}

function reset() {
  selectedFile = null;
  $("fileInput").value = "";
  $("convertBtn").disabled = true;
  // Ctrl+V(클립보드의 파일 붙여넣기)로도 파일을 선택할 수 있게
document.addEventListener("paste", (e) => {
  if ($("dropzone").hidden) return;
  const files = e.clipboardData && e.clipboardData.files;
  if (files && files.length) { e.preventDefault(); pickFile(files[0]); }
});

show("idle");
}

const dz = $("dropzone");
dz.addEventListener("click", () => $("fileInput").click());
dz.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("fileInput").click(); }
});
dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("dragover"); });
dz.addEventListener("dragleave", () => dz.classList.remove("dragover"));
dz.addEventListener("drop", (e) => {
  e.preventDefault();
  dz.classList.remove("dragover");
  if (e.dataTransfer.files.length) pickFile(e.dataTransfer.files[0]);
});
$("fileInput").addEventListener("change", (e) => {
  if (e.target.files.length) pickFile(e.target.files[0]);
});
$("clearFile").addEventListener("click", (e) => { e.stopPropagation(); reset(); });
$("convertBtn").addEventListener("click", convert);
$("restartBtn").addEventListener("click", reset);
$("retryBtn").addEventListener("click", () => { $("error").hidden = true; });

// Ctrl+V(클립보드의 파일 붙여넣기)로도 파일을 선택할 수 있게
document.addEventListener("paste", (e) => {
  if ($("dropzone").hidden) return;
  const files = e.clipboardData && e.clipboardData.files;
  if (files && files.length) { e.preventDefault(); pickFile(files[0]); }
});

show("idle");
