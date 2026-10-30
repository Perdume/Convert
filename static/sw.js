/* 서비스워커: 앱 셸을 캐시해 오프라인에서도 화면이 뜨게 한다.
   업로드/변환(POST)과 /api/* 는 절대 캐시하지 않고 항상 네트워크로 보낸다. */
"use strict";

const CACHE = "convert-v2";
const SHELL = [
  "/", "/index.html", "/style.css", "/app.js", "/offline.html",
  "/manifest.webmanifest",
  "/icons/icon-192.png", "/icons/icon-512.png", "/icons/apple-touch-icon.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;                       // 변환/비밀번호 POST는 건드리지 않음
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;             // 외부 요청 없음(그대로 통과)
  if (url.pathname.startsWith("/api/")) return;           // API·다운로드는 항상 네트워크

  if (req.mode === "navigate") {
    e.respondWith(
      fetch(req).catch(() =>
        caches.match("/index.html").then((r) => r || caches.match("/offline.html"))
      )
    );
    return;
  }

  e.respondWith(
    caches.match(req).then((cached) =>
      cached ||
      fetch(req).then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
        }
        return res;
      }).catch(() => cached)
    )
  );
});
