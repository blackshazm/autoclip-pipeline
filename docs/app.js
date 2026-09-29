/**
 * AutoClip Pipeline Engine - Interactive Client App
 */

document.addEventListener('DOMContentLoaded', () => {
  initArchitectureSteps();
  initSimulator();
  initTabs();
  initCopyButtons();
  initMobileMenu();
});

/* =====================================================================
   1. Architecture Flow Interactive Steps
   ===================================================================== */
const modulesData = [
  {
    badge: 'MÓDULO 0: RADAR YOUTUBE',
    title: 'Detecção de Outliers e Extração Otimizada',
    text: 'O Radar escuta os feeds XML de canais cadastrados em <code>config/channels.json</code>. Ao detectar um novo upload, calcula a velocidade de visualizações por hora (VPH) comparada com a média histórica do canal.',
    codePreview: 'VPH = total_views / ((now - published_at_hours) || 1)',
    checklist: [
      'Ignora vídeos já registrados no banco local (anti-duplicidade).',
      'Download de vídeos longos somente se VPH ultrapassar o multiplicador (ex: 2.5x).',
      'Uso de rotação de user-agents e cookies.txt para evitar bloqueios.'
    ],
    json: {
      "video_id": "dQw4w9WgXcQ",
      "title": "Como Dominar IA em 2026",
      "channel_id": "UC_x5XG1OV2P6uZZ5FSM9Ttw",
      "vph_score": 4820.5,
      "threshold_vph": 1800.0,
      "is_outlier": true,
      "download_path": "data/videos_longos/dQw4w9WgXcQ.mp4"
    }
  },
  {
    badge: 'MÓDULO 1: INGESTOR & SUPACLIP',
    title: 'Transcrição ASR, Seleção de Cortes e Renderização 9:16',
    text: 'O Ingestor monitora o diretório de entrada, gera o hash criptográfico SHA-256 do arquivo e envia para o contêiner Supaclip. O modelo Whisper extrai a transcrição com marcações temporais por palavra.',
    codePreview: 'Job -> Whisper (ASR) -> LLM (Moment Detection) -> FFmpeg (9:16 Crop + Subtitles)',
    checklist: [
      'Cálculo de SHA-256 para idempotência e verificação de integridade.',
      'Detecção de momentos de pico emocional e ganchos de retenção com LLM.',
      'Renderização acelerada por GPU/CPU com legendas dinâmicas em estilo karaoke queimadas.'
    ],
    json: {
      "job_id": "job_984f1a23",
      "source_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "clips_generated": [
        {
          "clip_id": "clip_01",
          "start_sec": 42.5,
          "end_sec": 89.0,
          "aspect_ratio": "9:16",
          "output_file": "data/clips_exportados/clip_01_viralkit.mp4"
        }
      ],
      "status": "COMPLETED"
    }
  },
  {
    badge: 'MÓDULO 2: PUBLICADOR DETERMINÍSTICO',
    title: 'Fila Transacional, Copywriting e Publicação com Quota Control',
    text: 'O Publicador consome os cortes gerados através de uma fila em SQLite com Lease-Locking. Ele solicita copywriting dinâmico (título, descrição e tags) ao modelo de linguagem e faz upload com respeitabilidade de cotas diárias.',
    codePreview: 'Lease Lock (15m) -> Generate Metadata (LLM) -> Upload API (Quota Check) -> Notify',
    checklist: [
      'Garantia de lease transacional: impede que 2 workers publiquem o mesmo vídeo.',
      'Controle rígido de cota diária da YouTube Data API v3 (evita ban de cota).',
      'Webhooks de notificação em tempo real para Discord e Telegram com link do Short publicado.'
    ],
    json: {
      "publish_id": "pub_7721a",
      "platform": "youtube_shorts",
      "video_title": "O Segredo Revelado da IA 🚀 #shorts",
      "scheduled_time": "2026-09-29T18:00:00Z",
      "quota_cost": 1600,
      "quota_remaining": 8400,
      "status": "PUBLISHED",
      "video_url": "https://youtube.com/shorts/xyz123abc"
    }
  }
];

function initArchitectureSteps() {
  const cards = document.querySelectorAll('.flow-card');
  const badge = document.getElementById('archDetailBadge');
  const title = document.getElementById('archDetailTitle');
  const text = document.getElementById('archDetailText');
  const codePreview = document.getElementById('archCodePreview');
  const checklist = document.getElementById('archChecklist');
  const jsonCode = document.getElementById('archJsonCode');
  const copyBtn = document.getElementById('btnCopyJson');

  cards.forEach(card => {
    card.addEventListener('click', () => {
      const stepIndex = parseInt(card.dataset.step, 10);
      cards.forEach(c => c.classList.remove('active'));
      card.classList.add('active');

      const data = modulesData[stepIndex];
      badge.textContent = data.badge;
      title.textContent = data.title;
      text.innerHTML = data.text;
      codePreview.innerHTML = `<code>${data.codePreview}</code>`;
      checklist.innerHTML = data.checklist.map(item => `<li>${item}</li>`).join('');
      jsonCode.textContent = JSON.stringify(data.json, null, 2);
    });
  });

  if (copyBtn) {
    copyBtn.addEventListener('click', () => {
      navigator.clipboard.writeText(jsonCode.textContent).then(() => {
        const orig = copyBtn.textContent;
        copyBtn.textContent = 'Copiado!';
        setTimeout(() => copyBtn.textContent = orig, 1800);
      });
    });
  }
}

/* =====================================================================
   2. Interactive VPH Simulator
   ===================================================================== */
function initSimulator() {
  const inputViews = document.getElementById('inputViews');
  const inputHours = document.getElementById('inputHours');
  const inputAvgVph = document.getElementById('inputAvgVph');
  const inputMultiplier = document.getElementById('inputMultiplier');
  const btnRecalc = document.getElementById('btnRecalculateSim');

  const kpiCalculatedVph = document.getElementById('kpiCalculatedVph');
  const kpiThresholdVph = document.getElementById('kpiThresholdVph');
  const kpiRatio = document.getElementById('kpiRatio');

  const simStatusLight = document.getElementById('simStatusLight');
  const simStatusHeadline = document.getElementById('simStatusHeadline');
  const decisionBox = document.getElementById('decisionBox');
  const decisionIcon = document.getElementById('decisionIcon');
  const decisionTitle = document.getElementById('decisionTitle');
  const decisionDesc = document.getElementById('decisionDescription');

  const stepVph = document.getElementById('stepVph');
  const stepDownload = document.getElementById('stepDownload');
  const stepQueue = document.getElementById('stepQueue');

  function calculate() {
    const views = parseFloat(inputViews.value) || 0;
    const hours = Math.max(0.1, parseFloat(inputHours.value) || 1);
    const avgVph = Math.max(1, parseFloat(inputAvgVph.value) || 1);
    const multiplier = parseFloat(inputMultiplier.value) || 1.0;

    const calculatedVph = Math.round(views / hours);
    const thresholdVph = Math.round(avgVph * multiplier);
    const ratio = (calculatedVph / avgVph).toFixed(2);
    const isOutlier = calculatedVph >= thresholdVph;

    kpiCalculatedVph.textContent = `${calculatedVph.toLocaleString('pt-BR')}/h`;
    kpiThresholdVph.textContent = `${thresholdVph.toLocaleString('pt-BR')}/h`;
    kpiRatio.textContent = `${ratio}x`;

    if (isOutlier) {
      simStatusLight.className = 'status-indicator-light active-viral';
      simStatusHeadline.textContent = 'VIRAL DETECTADO! VPH ACIMA DO LIMIAR';
      decisionBox.className = 'decision-box';
      decisionIcon.textContent = '🔥';
      decisionTitle.textContent = 'Aprovação para Ingestão Imediata';
      decisionDesc.textContent = `O vídeo superou o limiar de outlier em ${ratio}x. O Módulo 0 iniciará o download em MP4 e enviará para o Supaclip.`;

      stepVph.classList.add('done');
      stepDownload.classList.add('done');
      stepQueue.classList.add('done');
    } else {
      simStatusLight.className = 'status-indicator-light normal';
      simStatusHeadline.textContent = 'RITMO REGULAR - MONITORAMENTO CONTÍNUO';
      decisionBox.className = 'decision-box normal';
      decisionIcon.textContent = '⏳';
      decisionTitle.textContent = 'Download Postergado';
      decisionDesc.textContent = `O vídeo está a ${ratio}x da média do canal (necessário ao menos ${multiplier}x). O Radar continuará monitorando nos próximos ciclos de RSS.`;

      stepVph.classList.remove('done');
      stepDownload.classList.remove('done');
      stepQueue.classList.remove('done');
    }
  }

  [inputViews, inputHours, inputAvgVph, inputMultiplier].forEach(inp => {
    inp.addEventListener('input', calculate);
  });

  if (btnRecalc) {
    btnRecalc.addEventListener('click', calculate);
  }

  // Initial calculation
  calculate();
}

/* =====================================================================
   3. Documentation Tabs
   ===================================================================== */
function initTabs() {
  const tabBtns = document.querySelectorAll('.tab-btn');
  const tabPanes = document.querySelectorAll('.tab-pane');

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetId = btn.dataset.tab;
      tabBtns.forEach(b => b.classList.remove('active'));
      tabPanes.forEach(p => p.classList.remove('active'));

      btn.classList.add('active');
      const targetPane = document.getElementById(targetId);
      if (targetPane) targetPane.classList.add('active');
    });
  });
}

/* =====================================================================
   4. Copy Buttons
   ===================================================================== */
function initCopyButtons() {
  const copyButtons = document.querySelectorAll('.copy-btn');

  copyButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetId = btn.dataset.target;
      const targetElem = document.getElementById(targetId);
      if (!targetElem) return;

      navigator.clipboard.writeText(targetElem.innerText).then(() => {
        const origText = btn.textContent;
        btn.textContent = '✓ Copiado!';
        btn.style.borderColor = 'var(--accent-emerald)';
        btn.style.color = 'var(--accent-emerald)';

        setTimeout(() => {
          btn.textContent = origText;
          btn.style.borderColor = '';
          btn.style.color = '';
        }, 2000);
      });
    });
  });
}

/* =====================================================================
   5. Mobile Menu Toggle
   ===================================================================== */
function initMobileMenu() {
  const toggleBtn = document.getElementById('mobileMenuToggle');
  const navLinks = document.getElementById('navLinks');

  if (toggleBtn && navLinks) {
    toggleBtn.addEventListener('click', () => {
      const isVisible = navLinks.style.display === 'flex';
      navLinks.style.display = isVisible ? 'none' : 'flex';
      if (!isVisible) {
        navLinks.style.flexDirection = 'column';
        navLinks.style.position = 'absolute';
        navLinks.style.top = '100%';
        navLinks.style.left = '0';
        navLinks.style.right = '0';
        navLinks.style.background = 'rgba(7, 9, 14, 0.98)';
        navLinks.style.padding = '1.5rem';
        navLinks.style.borderBottom = '1px solid var(--border-subtle)';
      }
    });
  }
}
