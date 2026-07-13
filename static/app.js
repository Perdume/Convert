"use strict";

const MAX_BYTES = 50 * 1024 * 1024;
const EXT_TO_FMT = { hwp: "hwp", ppt: "ppt", pptx: "pptx", pdf: "pdf" };
const TARGETS = {
  hwp:  [{ value: "pdf", label: "PDF" }, { value: "pptx", label: "PPT (PPTX)" }],
  ppt:  [{ value: "pdf", label: "PDF" }, { value: "hwpx", label: "한글 (HWPX)" }],
  pptx: [{ value: "pdf", label: "PDF" }, { value: "hwpx", label: "한글 (HWPX)" }],
  pdf:  [{ value: "pptx", label: "PPT (PPTX)" }, { value: "hwpx", label: "한글 (HWPX)" }],
};

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
    if (i === 0) input.checked = true;
    label.appendChild(input);
    label.appendChild(document.createTextNode(t.label));
    opts.appendChild(label);
  });
  $("convertBtn").disabled = false;
  show("picked");
}

async function convert() {
  const target = document.querySelector('input[name="target"]:checked');
  if (!selectedFile || !target) return;

  show("progress");
  const form = new FormData();
  form.append("file", selectedFile);
  form.append("target", target.value);

  try {
    const res = await fetch("/api/convert", { method: "POST", body: form });
    if (!res.ok) {
      let msg = "변환 중 오류가 발생했습니다.";
      try {
        const body = await res.json();
        if (body.detail) msg = body.detail;
      } catch (_) { /* 응답이 JSON이 아닌 경우 */ }
      return showError(msg);
    }
    const body = await res.json();
    const link = $("downloadLink");
    link.href = "/api/download/" + encodeURIComponent(body.token);
    link.setAttribute("download", body.filename);
    link.textContent = body.filename + " 다운로드";
    show("result");
  } catch (_) {
    showError("서버에 연결할 수 없습니다.");
  }
}

function reset() {
  selectedFile = null;
  $("fileInput").value = "";
  $("convertBtn").disabled = true;
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

show("idle");
