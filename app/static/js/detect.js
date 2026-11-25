/* NusaVerse: alur deteksi (upload / foto / live).
   Satu skrip untuk tiga halaman; mode dibaca dari #detect-root[data-mode]. */
(() => {
  "use strict";

  const root = document.getElementById("detect-root");
  if (!root) return;

  const $ = (id) => document.getElementById(id);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const mode = root.dataset.mode; // upload | photo | live
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const URLS = {
    detect: root.dataset.detectUrl,
    status: root.dataset.statusUrl,
    log: root.dataset.logUrl,
    ethnicity: root.dataset.ethnicityUrl, // berisi "__slug__"
  };
  const MAX_BYTES = 5 * 1024 * 1024;

  let modelReady = false;
  let stream = null;

  // ------------------------------------------------------------------ UI
  const title = $("page-title");
  if (title) title.dataset.titleDefault = title.textContent;

  function setState(name) {
    root.dataset.state = name;
    root.querySelectorAll("[data-show]").forEach((el) => {
      el.hidden = !el.dataset.show.split(" ").includes(name);
    });
    if (title) {
      title.textContent = (name === "result" && title.dataset.titleResult) || title.dataset.titleDefault;
    }
  }

  function notice(message, kind = "error") {
    const box = $("notice");
    if (!box) return;
    if (!message) { box.hidden = true; return; }
    box.textContent = message;
    box.className = "notice notice-" + kind;
    box.hidden = false;
  }

  // ------------------------------------------------------------------ model siap?
  async function waitForModel() {
    for (let i = 0; i < 150; i++) {             // maksimal ±4 menit
      try {
        const res = await fetch(URLS.status, { credentials: "same-origin" });
        if (res.redirected && res.url.includes("/login")) { location.href = res.url; return false; }
        const s = await res.json();
        if (s.error) { notice("The detector is unavailable right now. Please try again later."); return false; }
        if (s.ready) { modelReady = true; return true; }
      } catch (_) { /* coba lagi */ }
      if (i === 1) notice("Preparing the detector… this can take up to a minute the first time.", "info");
      await sleep(1500);
    }
    notice("The detector is taking too long to start. Please reload the page.");
    return false;
  }
  const ready = waitForModel().then((ok) => { if (ok) notice(null); return ok; });

  // ------------------------------------------------------------------ gambar
  const dims = (src) => [src.naturalWidth || src.videoWidth || src.width, src.naturalHeight || src.videoHeight || src.height];

  async function fileToBitmap(file) {
    if ("createImageBitmap" in window) {
      try { return await createImageBitmap(file, { imageOrientation: "from-image" }); } catch (_) { /* fallback */ }
    }
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error("That file couldn't be read as an image."));
      img.src = URL.createObjectURL(file);
    });
  }

  // Perkecil + ubah ke JPEG (hemat data seluler; server tetap memeriksa ulang).
  async function toJpeg(source, maxSide, quality = 0.9) {
    const [w, h] = dims(source);
    const scale = Math.min(1, maxSide / Math.max(w, h));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(w * scale));
    canvas.height = Math.max(1, Math.round(h * scale));
    canvas.getContext("2d").drawImage(source, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((res, rej) =>
      canvas.toBlob((b) => (b ? res(b) : rej(new Error("Couldn't prepare the photo."))), "image/jpeg", quality));
    return { blob, canvas };
  }

  function faceThumb(canvas, box) {
    const [x1, y1, x2, y2] = box;
    const cx = (x1 + x2) / 2, cy = (y1 + y2) / 2;
    const side = Math.min(Math.max(x2 - x1, y2 - y1) * 1.4, canvas.width, canvas.height);
    const sx = Math.min(Math.max(cx - side / 2, 0), canvas.width - side);
    const sy = Math.min(Math.max(cy - side / 2, 0), canvas.height - side);
    const out = document.createElement("canvas");
    out.width = out.height = 220;
    out.getContext("2d").drawImage(canvas, sx, sy, side, side, 0, 0, 220, 220);
    return out.toDataURL("image/jpeg", 0.82);
  }

  // ------------------------------------------------------------------ server
  async function postDetect(blob, { frame = false, timeoutMs = 40000 } = {}) {
    const form = new FormData();
    form.append("image", blob, "photo.jpg");
    form.append("source", mode);
    if (frame) form.append("frame", "1");

    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const res = await fetch(URLS.detect, {
        method: "POST", body: form, signal: ctrl.signal,
        headers: { "X-CSRFToken": csrf }, credentials: "same-origin",
      });
      if (res.redirected && res.url.includes("/login")) { location.href = res.url; throw new Error("Your session expired."); }
      let data;
      try { data = await res.json(); }
      catch (_) { throw new Error("Unexpected response from the server (" + res.status + ")."); }
      if (!res.ok) throw new Error(data.message || "Something went wrong. Please try again.");
      return data;
    } catch (err) {
      if (err.name === "AbortError") throw new Error("The server took too long to respond. Please try again.");
      throw err;
    } finally {
      clearTimeout(timer);
    }
  }

  function showResult(info) {
    const slugUrl = URLS.ethnicity.replace("__slug__", encodeURIComponent(info.slug));
    $("result-label").textContent = info.name;
    $("explore-btn").setAttribute("href", slugUrl + (info.pid ? "?pid=" + encodeURIComponent(info.pid) : ""));
    try {
      sessionStorage.setItem("nusaverse:last", JSON.stringify({ slug: info.slug, name: info.name, thumb: info.thumb || null }));
    } catch (_) { /* penyimpanan dinonaktifkan: abaikan */ }
    setState("result");
    const note = $("result-note");
    if (info.note) { note.textContent = info.note; note.hidden = false; } else { note.hidden = true; }
  }

  // ------------------------------------------------------------------ kamera
  function stopStream() {
    if (stream) stream.getTracks().forEach((t) => t.stop());
    stream = null;
  }

  async function openCamera(video) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw Object.assign(new Error("insecure"), { name: "InsecureContext" });
    }
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 960 } }, audio: false,
    });
    video.srcObject = stream;
    await video.play();
  }

  function cameraMessage(err) {
    switch (err && err.name) {
      case "NotAllowedError": case "SecurityError":
        return "Camera access was blocked. Please allow camera permission in your browser settings and try again.";
      case "NotFoundError": case "OverconstrainedError":
        return "No camera was found on this device.";
      case "NotReadableError":
        return "The camera is being used by another app. Close it and try again.";
      case "InsecureContext":
        return "The camera needs a secure connection (HTTPS). Open the app through its https:// address.";
      default:
        return "We couldn't start the camera. Please try again.";
    }
  }

  function freeze(video, canvas) {            // tampilkan frame terakhir (kamera sudah dimatikan)
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    $("cam").classList.add("is-frozen");
  }
  const unfreeze = () => $("cam") && $("cam").classList.remove("is-frozen");

  // ------------------------------------------------------------------ MODE: upload
  function initUpload() {
    const input = $("file"), preview = $("preview"), analyze = $("analyze-btn");
    let file = null, objectUrl = null;

    const reset = () => {
      input.value = ""; file = null; analyze.disabled = true; notice(null); setState("select");
    };

    input.addEventListener("change", () => {
      const f = input.files && input.files[0];
      if (!f) return;
      notice(null);
      if (!["image/jpeg", "image/png"].includes(f.type)) { notice("Please choose a JPG or PNG photo."); input.value = ""; return; }
      if (f.size > MAX_BYTES) { notice("That photo is larger than 5 MB. Please choose a smaller one."); input.value = ""; return; }
      file = f;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      objectUrl = URL.createObjectURL(f);
      preview.src = objectUrl;
      analyze.disabled = false;
      setState("preview");
    });

    analyze.addEventListener("click", async () => {
      if (!file) return;
      notice(null);
      setState("busy");
      analyze.disabled = true;
      analyze.classList.add("is-busy");
      analyze.textContent = "Analyzing…";
      try {
        const bitmap = await fileToBitmap(file);
        const { blob } = await toJpeg(bitmap, 1280);
        const d = await postDetect(blob);
        if (d.status === "ok") {
          showResult({ slug: d.slug, name: d.display_name || d.label, pid: d.prediction_id, thumb: d.thumb, note: d.note });
        } else {
          notice(d.message || "We couldn't analyze this photo.");
          setState("preview");
        }
      } catch (err) {
        notice(err.message);
        setState("preview");
      } finally {
        analyze.disabled = false;
        analyze.classList.remove("is-busy");
        analyze.textContent = "Analyze Face";
      }
    });

    $("retry-btn").addEventListener("click", reset);
    reset();
  }

  // ------------------------------------------------------------------ MODE: photo
  function initPhoto() {
    const video = $("video"), shot = $("shot"), toggle = $("cam-toggle"), capture = $("capture-btn");

    const camOff = () => {
      stopStream(); video.srcObject = null; unfreeze();
      toggle.textContent = "Turn On Camera"; capture.disabled = true; setState("off");
    };
    const camOn = async () => {
      notice(null); unfreeze();
      try {
        await openCamera(video);
        toggle.textContent = "Turn Off Camera"; capture.disabled = false; setState("on");
      } catch (err) { notice(cameraMessage(err)); camOff(); }
    };

    toggle.addEventListener("click", () => (stream ? camOff() : camOn()));

    capture.addEventListener("click", async () => {
      if (!video.videoWidth) return;
      notice(null);
      capture.disabled = true;
      try {
        const { blob } = await toJpeg(video, 1280);
        freeze(video, shot);
        stopStream();
        setState("busy");
        const d = await postDetect(blob);
        if (d.status === "ok") {
          showResult({ slug: d.slug, name: d.display_name || d.label, pid: d.prediction_id, thumb: d.thumb, note: d.note });
        } else {
          notice(d.message || "We couldn't analyze this photo.");
          camOn();
        }
      } catch (err) {
        notice(err.message);
        camOn();
      }
    });

    $("retry-btn").addEventListener("click", camOn);
    camOff();
  }

  // ------------------------------------------------------------------ MODE: live
  function initLive() {
    const video = $("video"), shot = $("shot"), fill = $("progress-fill"), text = $("progress-text"), startBtn = $("live-start");
    const TARGET = 5, MAX_ATTEMPTS = 14, INTERVAL = 1000, MIN_VALID = 3;
    let token = 0;

    async function begin() {
      const my = ++token;
      notice(null); unfreeze(); startBtn.hidden = true;
      fill.style.width = "0%"; text.textContent = "Starting camera…"; setState("starting");
      try { await openCamera(video); }
      catch (err) { notice(cameraMessage(err)); startBtn.hidden = false; setState("idle"); return; }

      if (!modelReady) text.textContent = "Preparing the detector…";
      if (!(await ready)) { stopStream(); startBtn.hidden = false; setState("idle"); return; }
      if (my !== token) return;
      scan(my);
    }

    async function scan(my) {
      setState("scanning");
      text.textContent = "Looking for your face…";
      const votes = {}, info = {};
      let valid = 0, attempts = 0, last = null, scoreSum = 0;

      while (my === token && valid < TARGET && attempts < MAX_ATTEMPTS) {
        attempts++;
        const t0 = performance.now();
        try {
          if (!video.videoWidth) { await sleep(200); continue; }
          const { blob, canvas } = await toJpeg(video, 640, 0.8);
          const d = await postDetect(blob, { frame: true, timeoutMs: 15000 });
          if (my !== token) return;
          if (d.status === "ok") {
            valid++; scoreSum += d.detection_score || 0;
            votes[d.label] = (votes[d.label] || 0) + 1;
            info[d.label] = { slug: d.slug, name: d.display_name || d.label };
            last = { d, canvas };
            fill.style.width = (valid / TARGET) * 100 + "%";
            text.textContent = valid < TARGET ? "Hold still… " + (TARGET - valid) + "s" : "Done!";
          } else if (d.status === "no_face") {
            text.textContent = "Looking for your face…";
          } // "busy" / "error": coba lagi pada putaran berikutnya
        } catch (err) {
          if (my !== token) return;
          notice(err.message); break;
        }
        await sleep(Math.max(0, INTERVAL - (performance.now() - t0)));
      }
      if (my !== token) return;

      if (valid < MIN_VALID) {                      // gagal: wajah tidak terlihat cukup lama
        stopStream(); setState("idle"); startBtn.textContent = "Try Again"; startBtn.hidden = false;
        if ($("notice").hidden) notice("We couldn't see a face clearly. Face the camera in good light and try again.");
        return;
      }

      const winner = Object.keys(votes).sort((a, b) => votes[b] - votes[a])[0];
      freeze(video, shot);
      stopStream();
      const thumb = faceThumb(last.canvas, last.d.box);

      let pid = null;                                // catat SATU hasil akhir ke riwayat (bukan tiap frame)
      try {
        const res = await fetch(URLS.log, {
          method: "POST", credentials: "same-origin",
          headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
          body: JSON.stringify({
            source: "live", feature_method: "antro", face_count: 1, result_label: winner,
            detection_score: Math.min(1, scoreSum / valid), details: [{ votes }],
          }),
        });
        if (res.ok) pid = (await res.json()).id;
      } catch (_) { /* riwayat gagal dicatat: hasil tetap ditampilkan */ }

      showResult({ slug: info[winner].slug, name: info[winner].name, pid, thumb });
    }

    startBtn.addEventListener("click", begin);
    $("retry-btn").addEventListener("click", begin);
    begin();
  }

  // ------------------------------------------------------------------ mulai
  window.addEventListener("pagehide", stopStream);
  if (mode === "upload") initUpload();
  else if (mode === "photo") initPhoto();
  else if (mode === "live") initLive();
})();
