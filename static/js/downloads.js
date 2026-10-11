/**
 * downloads.js — Single media download page behaviour
 * Handles URL inspection, preview rendering, and form enablement.
 */

(function() {
  const urlInput    = document.getElementById('id_url');
  const inspectBtn  = document.getElementById('inspectBtn');
  const inspectSpinner = document.getElementById('inspectSpinner');
  const downloadBtn = document.getElementById('downloadBtn');
  const previewContent  = document.getElementById('previewContent');
  const previewPlaceholder = document.getElementById('previewPlaceholder');
  const formatSelect  = document.getElementById('id_output_format');
  const qualitySelect = document.getElementById('id_output_quality');
  const qualityInfo   = document.getElementById('qualityInfo');
  const qualityInfoText = document.getElementById('qualityInfoText');
  const audioOnlyCheck = document.getElementById('id_audio_only');

  // Enable inspect button when URL is typed
  if (urlInput) {
    urlInput.addEventListener('input', () => {
      const hasUrl = urlInput.value.trim().length > 8;
      inspectBtn.disabled = !hasUrl;
      downloadBtn.disabled = !hasUrl;
    });
  }

  // Quality info update
  function updateQualityInfo() {
    if (!formatSelect || !qualitySelect || !window.QUALITY_PRESETS) return;
    const fmt  = formatSelect.value;
    const qual = qualitySelect.value;
    const presets = QUALITY_PRESETS[fmt] || {};
    const preset  = presets[qual] || presets['best'] || {};
    const label   = preset.label || '';

    if (label) {
      qualityInfo.style.display = '';
      qualityInfoText.textContent = label;
    } else {
      qualityInfo.style.display = 'none';
    }

    // Disable quality for lossless formats
    if (fmt === 'flac' || fmt === 'wav') {
      qualitySelect.querySelectorAll('option').forEach(o => {
        o.disabled = o.value !== 'best';
      });
      qualitySelect.value = 'best';
    } else {
      qualitySelect.querySelectorAll('option').forEach(o => o.disabled = false);
    }
  }

  if (formatSelect) formatSelect.addEventListener('change', updateQualityInfo);
  if (qualitySelect) qualitySelect.addEventListener('change', updateQualityInfo);
  updateQualityInfo();

  // Audio-only toggle hides format selector for video mode
  if (audioOnlyCheck) {
    audioOnlyCheck.addEventListener('change', function() {
      // In video mode only mp4 is available; in audio mode show formats
      const row = document.querySelector('.row.g-3.mb-3');
      if (row) row.style.display = this.checked ? '' : 'none';
    });
  }

  // Format seconds to mm:ss
  function fmtDuration(secs) {
    if (!secs) return '';
    secs = Math.round(secs);
    const m = Math.floor(secs / 60), s = secs % 60;
    const h = Math.floor(m / 60);
    if (h) return `${h}:${String(m % 60).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
    return `${m}:${String(s).padStart(2,'0')}`;
  }

  function renderPreview(info) {
    previewPlaceholder.style.display = 'none';
    previewContent.style.display = '';

    const thumbEl = document.getElementById('previewThumb');
    const thumbContainer = document.getElementById('thumbContainer');
    if (info.thumbnail) {
      thumbEl.src = info.thumbnail;
      thumbEl.onerror = () => thumbContainer.style.display = 'none';
      thumbContainer.style.display = '';
    } else {
      thumbContainer.style.display = 'none';
    }

    const durEl = document.getElementById('previewDuration');
    if (durEl) durEl.textContent = fmtDuration(info.duration);

    document.getElementById('previewTitle').textContent = info.title || '';
    const uploaderEl = document.getElementById('previewUploader');
    if (uploaderEl) {
      uploaderEl.textContent = [info.uploader, info.extractor].filter(Boolean).join(' · ');
    }

    const extrasEl = document.getElementById('previewExtras');
    if (extrasEl) {
      const parts = [];
      if (info.upload_date) {
        const d = info.upload_date;
        parts.push(`Published: ${d.slice(0,4)}-${d.slice(4,6)}-${d.slice(6,8)}`);
      }
      if (info.view_count) parts.push(`${info.view_count.toLocaleString()} views`);
      if (info.is_live) parts.push('🔴 Live');
      extrasEl.textContent = parts.join(' · ');
    }

    const warnEl = document.getElementById('previewWarning');
    if (warnEl) {
      if (info.is_live) {
        warnEl.style.display = '';
        warnEl.innerHTML = '⚠️ This appears to be a live stream. Download quality may vary.';
      } else {
        warnEl.style.display = 'none';
      }
    }
  }

  // Inspect button
  if (inspectBtn) {
    inspectBtn.addEventListener('click', async () => {
      const url = urlInput.value.trim();
      if (!url) return;

      inspectBtn.disabled = true;
      inspectSpinner.style.display = '';
      previewContent.style.display = 'none';
      previewPlaceholder.style.display = '';

      try {
        const csrfToken = window.MF.getCsrf();
        const r = await fetch('/download/inspect/', {
          method: 'POST',
          headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
          body: JSON.stringify({url}),
        });
        const data = await r.json();
        if (data.ok && data.info) {
          renderPreview(data.info);
          downloadBtn.disabled = false;
          window.MF.toast('Media info loaded.', 'success', 2000);
        } else {
          window.MF.toast(data.error || 'Could not fetch media info.', 'error');
          previewPlaceholder.style.display = '';
        }
      } catch(e) {
        window.MF.toast('Network error. Is the server running?', 'error');
      } finally {
        inspectBtn.disabled = false;
        inspectSpinner.style.display = 'none';
      }
    });
  }

  // Allow pressing Enter in URL field to trigger inspect
  if (urlInput) {
    urlInput.addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        e.preventDefault();
        if (!inspectBtn.disabled) inspectBtn.click();
      }
    });
  }
})();
