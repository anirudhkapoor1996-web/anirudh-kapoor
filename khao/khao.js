/* KHAO — hero scene + reveals.
   The logo is a cloche: a covered dish held up on a hand. Here it is the
   object itself, in gold, turning slowly in the dark. Degrades to a plain
   dark hero if WebGL is missing or the visitor prefers reduced motion. */
(function () {
  'use strict';

  /* ---------- nav ---------- */
  var nav = document.getElementById('nav');
  function onScroll(){ nav.classList.toggle('scrolled', window.scrollY > 24); }
  window.addEventListener('scroll', onScroll, { passive:true }); onScroll();

  /* ---------- reveals ---------- */
  var rvs = [].slice.call(document.querySelectorAll('.rv'));
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } });
    }, { rootMargin:'0px 0px -8% 0px', threshold:0.05 });
    rvs.forEach(function (el) { io.observe(el); });
  }
  function revealVisible(){
    rvs.forEach(function (el) {
      if (el.getBoundingClientRect().top < window.innerHeight * 0.95) el.classList.add('in');
    });
  }
  requestAnimationFrame(revealVisible);
  window.addEventListener('load', revealVisible);
  setTimeout(function(){ rvs.forEach(function(el){ el.classList.add('in'); }); }, 2400);

  /* ---------- hero scene ---------- */
  var canvas = document.getElementById('scene');
  var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (!canvas || reduced || typeof THREE === 'undefined') { if (canvas) canvas.style.display = 'none'; return; }

  var renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
  } catch (e) { canvas.style.display = 'none'; return; }

  var hero = canvas.parentNode;
  var W = hero.clientWidth, H = hero.clientHeight;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(W, H, false);

  var scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x0B0A09, 0.055);

  var camera = new THREE.PerspectiveCamera(38, W / H, 0.1, 100);
  camera.position.set(0, 0.9, 8.2);
  camera.lookAt(0, 0.15, 0);

  /* framing: on wide screens the cloche sits right of the wordmark and stays
     whole; on narrow ones it centres and drops behind the type */
  function frame() {
    var wide = W / H > 1.05;
    var s = wide ? Math.min(1, W / 1500) * 0.95 : 0.74;
    rig.scale.setScalar(s);
    rig.position.x = wide ? 2.35 * s : 0;
    rig.position.z = wide ? 0 : -1.2;
    camera.position.z = wide ? 9.4 : 11.2;
    camera.position.y = wide ? 0.9 : 1.4;
    camera.lookAt(0, 0.15, 0);
  }

  /* a gradient environment, drawn on a canvas — gives the gold something to
     reflect without shipping an HDR file */
  function envTexture() {
    var c = document.createElement('canvas'); c.width = 512; c.height = 256;
    var g = c.getContext('2d');
    var grad = g.createLinearGradient(0, 0, 0, 256);
    grad.addColorStop(0.00, '#5a4526');
    grad.addColorStop(0.34, '#c98f39');
    grad.addColorStop(0.52, '#f6d79a');
    grad.addColorStop(0.68, '#3a2f22');
    grad.addColorStop(1.00, '#0b0a09');
    g.fillStyle = grad; g.fillRect(0, 0, 512, 256);
    // two warm hot-spots so the dome catches moving highlights
    [[128, 92, 74], [372, 66, 52]].forEach(function (s) {
      var r = g.createRadialGradient(s[0], s[1], 0, s[0], s[1], s[2]);
      r.addColorStop(0, 'rgba(255,236,196,0.95)');
      r.addColorStop(1, 'rgba(255,236,196,0)');
      g.fillStyle = r; g.fillRect(s[0] - s[2], s[1] - s[2], s[2] * 2, s[2] * 2);
    });
    var t = new THREE.CanvasTexture(c);
    t.mapping = THREE.EquirectangularReflectionMapping;
    return t;
  }
  var env = envTexture();

  var gold = new THREE.MeshStandardMaterial({
    color: 0xE0A33E, metalness: 0.98, roughness: 0.24, envMap: env, envMapIntensity: 1.5
  });
  var goldDark = new THREE.MeshStandardMaterial({
    color: 0xB07F2F, metalness: 0.95, roughness: 0.4, envMap: env, envMapIntensity: 1.0
  });

  var rig = new THREE.Group();
  rig.position.y = -0.15;
  scene.add(rig);

  // the dome
  var dome = new THREE.Mesh(new THREE.SphereGeometry(1.55, 96, 64, 0, Math.PI * 2, 0, Math.PI / 2), gold);
  dome.position.y = 0.16;
  rig.add(dome);

  // the knob on top
  var knob = new THREE.Mesh(new THREE.SphereGeometry(0.2, 40, 28), gold);
  knob.position.y = 1.86;
  rig.add(knob);

  // the tray it sits on
  var tray = new THREE.Mesh(new THREE.CylinderGeometry(2.0, 2.0, 0.1, 96), goldDark);
  tray.position.y = 0.09;
  rig.add(tray);
  var lip = new THREE.Mesh(new THREE.TorusGeometry(2.0, 0.055, 20, 120), gold);
  lip.rotation.x = Math.PI / 2; lip.position.y = 0.09;
  rig.add(lip);

  // faint meridian rings, echoing the gridded dome in the logo
  for (var i = 1; i <= 3; i++) {
    var y = i * 0.38;
    var rr = Math.sqrt(Math.max(1.55 * 1.55 - y * y, 0.01));
    var ring = new THREE.Mesh(new THREE.TorusGeometry(rr, 0.012, 10, 140), goldDark);
    ring.rotation.x = Math.PI / 2; ring.position.y = y + 0.16;
    rig.add(ring);
  }

  scene.add(new THREE.AmbientLight(0x51402c, 1.05));
  var key = new THREE.DirectionalLight(0xffd9a0, 2.5); key.position.set(4, 6, 5); scene.add(key);
  var rim = new THREE.DirectionalLight(0xE0A33E, 2.0); rim.position.set(-6, 2.2, -4); scene.add(rim);
  var fill = new THREE.PointLight(0xC6512E, 12, 22); fill.position.set(-2.6, -1.4, 3.4); scene.add(fill);

  /* mouse / tilt parallax */
  var tx = 0, ty = 0, cx = 0, cy = 0;
  window.addEventListener('pointermove', function (e) {
    tx = (e.clientX / window.innerWidth - 0.5) * 2;
    ty = (e.clientY / window.innerHeight - 0.5) * 2;
  }, { passive: true });

  var running = true, t0 = performance.now();
  document.addEventListener('visibilitychange', function () {
    running = !document.hidden;
    if (running) { t0 = performance.now(); requestAnimationFrame(tick); }
  });

  function resize() {
    W = hero.clientWidth; H = hero.clientHeight;
    camera.aspect = W / H; camera.updateProjectionMatrix();
    renderer.setSize(W, H, false);
    frame();
  }
  window.addEventListener('resize', resize, { passive: true });

  function tick(now) {
    if (!running) return;
    var t = (now - t0) * 0.001;
    cx += (tx - cx) * 0.045;
    cy += (ty - cy) * 0.045;

    rig.rotation.y = t * 0.16 + cx * 0.32;
    rig.rotation.x = -0.06 + cy * 0.10;
    rig.position.y = -0.15 + Math.sin(t * 0.62) * 0.055;   // slow float
    fill.position.x = Math.sin(t * 0.5) * 3.4;
    fill.position.z = 3.0 + Math.cos(t * 0.5) * 1.4;

    renderer.render(scene, camera);
    requestAnimationFrame(tick);
  }
  resize();
  requestAnimationFrame(tick);
})();
