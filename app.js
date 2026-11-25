/* MathTutor : JS léger, sans dépendance. */
(function () {
  "use strict";
  var meta = document.querySelector('meta[name="csrf-token"]');
  var CSRF = meta ? meta.content : "";
  var T = window.I18N || {};
  function tr(s) { return T[s] || s; }

  function api(path, body) {
    return fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": CSRF },
      body: JSON.stringify(body),
      credentials: "same-origin",
    });
  }

  /* ---- PWA ---- */
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () { navigator.serviceWorker.register("/sw.js").catch(function () {}); });
  }

  /* ---- Notifications temps réel (SSE) ---- */
  var bell = document.getElementById("bell-badge");
  function bump() {
    if (!bell) return;
    var n = (parseInt(bell.textContent, 10) || 0) + 1;
    bell.textContent = n; bell.hidden = false;
  }
  function toast(title, body, url) {
    var d = document.createElement("div");
    d.className = "flash"; d.style.cssText = "position:fixed;right:12px;bottom:12px;max-width:320px;z-index:9;background:var(--card)";
    var a = document.createElement(url ? "a" : "span");
    if (url) a.href = url;
    a.textContent = title + (body ? " — " + body : "");
    d.appendChild(a); document.body.appendChild(d);
    setTimeout(function () { d.remove(); }, 7000);
  }
  var feed = document.getElementById("live-feed");
  function onEvent(ev) {
    var p; try { p = JSON.parse(ev.data); } catch (e) { return; }
    if (p.type === "notification") { bump(); toast(p.title, p.body, p.url); }
    if (p.type === "activity" && feed) {
      var li = document.createElement("li");
      var mark = p.event === "attempt" ? (p.correct ? "✔ " : "✘ ") : "? ";
      li.textContent = mark + p.student + " — " + (p.text || "");
      feed.insertBefore(li, feed.firstChild);
      while (feed.children.length > 20) feed.removeChild(feed.lastChild);
    }
  }
  if (document.body.dataset.auth === "1" && "EventSource" in window) {
    var es = new EventSource("/api/events");
    es.onmessage = onEvent;
  }

  /* ---- Exercices (avec file d'attente hors ligne) ---- */
  var QKEY = "mt_queue";
  function queue() { try { return JSON.parse(localStorage.getItem(QKEY) || "[]"); } catch (e) { return []; } }
  function saveQueue(q) { try { localStorage.setItem(QKEY, JSON.stringify(q)); } catch (e) {} }
  function flush() {
    var q = queue(); if (!q.length || !navigator.onLine) return;
    var item = q[0];
    api("/api/attempts", item).then(function (r) {
      if (r.ok || r.status === 422 || r.status === 404) { q.shift(); saveQueue(q); if (q.length) flush(); }
    }).catch(function () {});
  }
  window.addEventListener("online", flush);
  flush();

  document.querySelectorAll("form.ex-form").forEach(function (f) {
    f.addEventListener("submit", function (e) {
      e.preventDefault();
      var input = f.querySelector("input[name=answer]"), out = f.querySelector(".res"), hint = f.querySelector(".hint");
      var payload = { exercise_id: parseInt(f.dataset.ex, 10), answer: input.value.trim() };
      if (!payload.answer) return;
      out.className = "res"; out.textContent = "…";
      api("/api/attempts", payload).then(function (r) { return r.json().then(function (j) { return { s: r.status, j: j }; }); })
        .then(function (x) {
          if (x.s === 422) { out.className = "res no"; out.textContent = x.j.message; return; }
          if (x.s >= 400) { out.className = "res no"; out.textContent = x.j.error || "Erreur"; return; }
          if (x.j.correct) { out.className = "res ok"; out.textContent = tr("Correct !"); }
          else { out.className = "res no"; out.textContent = tr("Pas encore. Réessaie."); if (hint && x.j.hint) { hint.hidden = false; hint.textContent = tr("Indice") + " : " + x.j.hint; } }
        })
        .catch(function () {
          var q = queue(); q.push(payload); saveQueue(q);
          out.className = "res"; out.textContent = tr("Enregistré hors ligne, envoi dès le retour du réseau.");
        });
    });
  });

  /* ---- Chat tuteur IA ---- */
  var cf = document.getElementById("chat-form");
  if (cf) {
    var box = document.getElementById("chat-box"), inp = cf.querySelector("textarea"), btn = cf.querySelector("button");
    box.scrollTop = box.scrollHeight;
    function add(role, text, extra) {
      var d = document.createElement("div"); d.className = "msg " + role; d.textContent = text;
      if (extra && extra.verified) {
        var v = document.createElement("span"); v.className = "tag";
        var r = extra.verified;
        v.textContent = "✔ " + tr("Vérifié par le moteur de calcul") + " : " +
          (r.solutions ? r.solutions.join(" ; ") : r.value !== undefined ? r.value : String(r.truth));
        d.appendChild(v);
      }
      if (extra && extra.sources && extra.sources.length) {
        var s = document.createElement("span"); s.className = "src";
        s.textContent = tr("Sources") + " : " + extra.sources.map(function (x) { return "[" + x.n + "] " + x.title; }).join(" · ");
        d.appendChild(s);
      }
      box.appendChild(d); box.scrollTop = box.scrollHeight; return d;
    }
    cf.addEventListener("submit", function (e) {
      e.preventDefault();
      var text = inp.value.trim(); if (!text) return;
      add("user", text); inp.value = ""; btn.disabled = true;
      var wait = add("assistant", "…");
      api("/api/chat", { message: text }).then(function (r) { return r.json().then(function (j) { return { s: r.status, j: j }; }); })
        .then(function (x) {
          wait.remove();
          if (x.s >= 400) { add("assistant", x.j.error || "Erreur"); return; }
          add("assistant", x.j.content, x.j);
          var q = document.getElementById("quota"); if (q) q.textContent = x.j.used + " / " + x.j.quota;
        })
        .catch(function () { wait.remove(); add("assistant", tr("Vous êtes hors ligne")); })
        .then(function () { btn.disabled = false; inp.focus(); });
    });
    inp.addEventListener("keydown", function (e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); cf.requestSubmit(); } });
  }

  /* ---- Inscription : niveaux selon le pays ---- */
  var cs = document.getElementById("country-select"), ls = document.getElementById("level-select"), ld = document.getElementById("levels-data");
  if (cs && ls && ld) {
    var data = JSON.parse(ld.textContent);
    function fill() {
      var cur = ls.dataset.current || "";
      ls.innerHTML = ""; var o = document.createElement("option"); o.value = ""; o.textContent = "—"; ls.appendChild(o);
      (data[cs.value] || []).forEach(function (l) {
        var op = document.createElement("option"); op.value = l.id; op.textContent = l.name;
        if (String(l.id) === cur) op.selected = true; ls.appendChild(op);
      });
    }
    cs.addEventListener("change", function () { ls.dataset.current = ""; fill(); }); fill();
  }
  var rs = document.getElementById("role-select");
  if (rs) {
    function roleUi() {
      document.querySelectorAll("[data-roles]").forEach(function (el) {
        el.hidden = el.dataset.roles.split(" ").indexOf(rs.value) < 0;
      });
    }
    rs.addEventListener("change", roleUi); roleUi();
  }
})();
