/* KHAO — hero scene + reveals.
   The subject is the ACTUAL logo asset (hand, tray, domed cover, question
   mark), not a reconstruction of it: assets/khao-mark-alpha.png on a plane in
   3D, with a gold light behind it, drifting dust, and pointer parallax.
   Degrades to a plain dark hero without WebGL or under reduced-motion. */
(function () {
  'use strict';

  var nav = document.getElementById('nav');
  function onScroll(){ nav.classList.toggle('scrolled', window.scrollY > 24); }
  window.addEventListener('scroll', onScroll, { passive:true }); onScroll();

  var rvs = [].slice.call(document.querySelectorAll('.rv'));
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } });
    }, { rootMargin:'0px 0px -8% 0px', threshold:0.05 });
    rvs.forEach(function (el) { io.observe(el); });
  }
  function revealVisible(){
    rvs.forEach(function (el) { if (el.getBoundingClientRect().top < innerHeight * 0.95) el.classList.add('in'); });
  }
  requestAnimationFrame(revealVisible);
  addEventListener('load', revealVisible);
  setTimeout(function(){ rvs.forEach(function(el){ el.classList.add('in'); }); }, 2400);

  var canvas = document.getElementById('scene');
  var reduced = matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (!canvas || reduced || typeof THREE === 'undefined') { if (canvas) canvas.style.display = 'none'; return; }

  var renderer;
  try { renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true }); }
  catch (e) { canvas.style.display = 'none'; return; }

  var hero = canvas.parentNode;
  var W = hero.clientWidth, H = hero.clientHeight;
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  renderer.setSize(W, H, false);

  var scene = new THREE.Scene();
  var camera = new THREE.PerspectiveCamera(40, W / H, 0.1, 120);
  camera.position.set(0, 0, 12);

  var rig = new THREE.Group();
  scene.add(rig);

  /* --- the glow behind the mark --- */
  function glowTexture() {
    var c = document.createElement('canvas'); c.width = c.height = 256;
    var g = c.getContext('2d');
    var r = g.createRadialGradient(128, 128, 0, 128, 128, 128);
    r.addColorStop(0.00, 'rgba(224,163,62,0.40)');
    r.addColorStop(0.35, 'rgba(198,81,46,0.15)');
    r.addColorStop(1.00, 'rgba(224,163,62,0)');
    g.fillStyle = r; g.fillRect(0, 0, 256, 256);
    return new THREE.CanvasTexture(c);
  }
  var glow = new THREE.Mesh(
    new THREE.PlaneGeometry(15, 15),
    new THREE.MeshBasicMaterial({ map: glowTexture(), transparent: true, depthWrite: false,
      blending: THREE.AdditiveBlending })
  );
  glow.position.z = -2.4;
  rig.add(glow);

  /* --- the real logo --- */
  var markGroup = new THREE.Group();
  rig.add(markGroup);

  new THREE.TextureLoader().load('assets/khao-mark-alpha.png', function (tex) {
    if (renderer.capabilities && renderer.capabilities.getMaxAnisotropy) {
      tex.anisotropy = renderer.capabilities.getMaxAnisotropy();
    }
    tex.minFilter = THREE.LinearFilter;
    var aspect = (tex.image && tex.image.width && tex.image.height)
      ? tex.image.width / tex.image.height : 1379 / 1703;
    var h = 6.6, w = h * aspect;

    // soft dark drop behind, for depth
    var shadow = new THREE.Mesh(
      new THREE.PlaneGeometry(w, h),
      new THREE.MeshBasicMaterial({ map: tex, transparent: true, color: 0x000000,
        opacity: 0.55, depthWrite: false })
    );
    shadow.position.set(0.16, -0.16, -0.5);
    markGroup.add(shadow);

    var mark = new THREE.Mesh(
      new THREE.PlaneGeometry(w, h),
      new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false })
    );
    markGroup.add(mark);
    frame();
  });

  /* --- drifting dust --- */
  var dustGeo = new THREE.BufferGeometry();
  var N = 220, pos = new Float32Array(N * 3), seed = new Float32Array(N);
  for (var i = 0; i < N; i++) {
    pos[i*3]   = (Math.random() - 0.5) * 26;
    pos[i*3+1] = (Math.random() - 0.5) * 16;
    pos[i*3+2] = (Math.random() - 0.5) * 10 - 1;
    seed[i] = Math.random() * Math.PI * 2;
  }
  dustGeo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  var dust = new THREE.Points(dustGeo, new THREE.PointsMaterial({
    color: 0xE0A33E, size: 0.055, transparent: true, opacity: 0.5, depthWrite: false
  }));
  scene.add(dust);

  /* --- framing --- */
  function frame() {
    var wide = W / H > 1.05;
    var s = wide ? Math.min(1, W / 1450) * 0.68 : 0.52;
    markGroup.scale.setScalar(s);
    glow.scale.setScalar(s * 0.92);
    rig.position.x = wide ? 4.15 : 0;
    rig.position.y = wide ? -0.15 : 2.0;
    camera.position.z = wide ? 12 : 14.5;
  }

  var tx = 0, ty = 0, cx = 0, cy = 0;
  addEventListener('pointermove', function (e) {
    tx = (e.clientX / innerWidth - 0.5) * 2;
    ty = (e.clientY / innerHeight - 0.5) * 2;
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
  addEventListener('resize', resize, { passive: true });

  function tick(now) {
    if (!running) return;
    var t = (now - t0) * 0.001;
    cx += (tx - cx) * 0.05;
    cy += (ty - cy) * 0.05;

    // it is a LOGO: it tilts and breathes, it never spins away from legibility
    markGroup.rotation.y = cx * 0.30 + Math.sin(t * 0.34) * 0.09;
    markGroup.rotation.x = cy * 0.20 + Math.sin(t * 0.27) * 0.05;
    markGroup.position.y = Math.sin(t * 0.55) * 0.13;

    glow.material.opacity = 0.82 + Math.sin(t * 0.9) * 0.16;
    glow.rotation.z = t * 0.03;

    var p = dustGeo.attributes.position.array;
    for (var i = 0; i < N; i++) {
      p[i*3+1] += 0.0035 + Math.sin(seed[i] + t * 0.4) * 0.0016;
      if (p[i*3+1] > 8) p[i*3+1] = -8;
    }
    dustGeo.attributes.position.needsUpdate = true;
    dust.rotation.y = cx * 0.05;

    renderer.render(scene, camera);
    requestAnimationFrame(tick);
  }
  resize();
  requestAnimationFrame(tick);
})();
