/**
 * downloads.js — Primary media download experience
 * Handles URL cleaning, inspection, preview rendering, and option configuration.
 */

(function() {
  const urlInput        = document.getElementById('id_url');
  const inspectBtn      = document.getElementById('inspectBtn');
  const inspectSpinner  = document.getElementById('inspectSpinner');
  const inspectBtnText  = document.getElementById('inspectBtnText');
  const pasteBtn        = document.getElementById('pasteBtn');
  const downloadBtn     = document.getElementById('downloadBtn');
  const downloadForm    = document.getElementById('downloadForm');
  const reviewPanel     = document.getElementById('reviewPanel');
  const playlistBanner  = document.getElementById('playlistBanner');
  const playlistInspectLink = document.getElementById('playlistInspectLink');
  
  const formatSelect    = document.getElementById('id_output_format');
  const qualitySelect   = document.getElementById('id_output_quality');
  const qualityHintBox  = document.getElementById('qualityHintBox');
  const qualityHintText = document.getElementById('qualityHintText');
  const audioOnlyInput  = document.getElementById('id_audio_only');
  const modeAudioRadio  = document.getElementById('modeAudio');
  const modeVideoRadio  = document.getElementById('modeVideo');
  const qualitySelectorCol = document.getElementById('qualitySelectorCol');
  const toggleSaveDir   = document.getElementById('toggleSaveDir');
  const saveDirWrapper  = document.getElementById('saveDirWrapper');

  let mediaReviewed = false;

  // Helper: Strip tracking parameters (si, feature, pp) from YouTube URLs
  function cleanMediaUrl(raw) {
    if (!raw) return raw;
    let val = raw.trim();
    try {
      const u = new URL(val);
      if (u.hostname.includes('youtube.com') || u.hostname === 'youtu.be') {
        u.searchParams.delete('si');
        u.searchParams.delete('pp');
        if (u.searchParams.get('feature') === 'share') {
          u.searchParams.delete('feature');
        }
        return u.toString();
      }
    } catch(e) {
      val = val.replace(/([?&])si=[^&]*(&|$)/, (m, p1, p2) => p2 === '&' ? p1 : '');
    }
    return val;
  }

  // Detect playlist URLs
  function checkPlaylistUrl(url) {
    if (!playlistBanner) return;
    const isPlaylist = url && (url.includes('list=') || url.includes('/playlist') || url.includes('/sets/'));
    if (isPlaylist) {
      playlistBanner.style.setProperty('display', 'flex', 'important');
      if (playlistInspectLink) {
        playlistInspectLink.href = `/playlist/?url=${encodeURIComponent(url)}`;
      }
    } else {
      playlistBanner.style.setProperty('display', 'none', 'important');
    }
  }

  // Enable/disable Review button when URL is entered
  function handleUrlInput() {
    if (!urlInput) return;
    const cleaned = cleanMediaUrl(urlInput.value);
    if (cleaned !== urlInput.value) {
      urlInput.value = cleaned;
    }
    const hasUrl = urlInput.value.trim().length > 6;
    if (inspectBtn) inspectBtn.disabled = !hasUrl;
    checkPlaylistUrl(urlInput.value.trim());
  }

  if (urlInput) {
    urlInput.addEventListener('input', handleUrlInput);
    urlInput.addEventListener('paste', () => setTimeout(handleUrlInput, 20));
    urlInput.addEventListener('change', handleUrlInput);
  }

  // Paste action button
  if (pasteBtn && urlInput) {
    pasteBtn.addEventListener('click', async () => {
      try {
        if (navigator.clipboard && navigator.clipboard.readText) {
          const text = await navigator.clipboard.readText();
          if (text) {
            urlInput.value = text.trim();
            handleUrlInput();
            if (inspectBtn) {
              inspectBtn.disabled = false;
              inspectBtn.click();
            }
          }
        } else {
          urlInput.focus();
        }
      } catch (err) {
        urlInput.focus();
      }
    });
  }

  // Format seconds to mm:ss or hh:mm:ss
  function fmtDuration(secs) {
    if (!secs) return '';
    secs = Math.round(secs);
    const m = Math.floor(secs / 60), s = secs % 60;
    const h = Math.floor(m / 60);
    if (h) return `${h}:${String(m % 60).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
    return `${m}:${String(s).padStart(2,'0')}`;
  }

  // Render media preview details
  function renderPreview(info) {
    if (!reviewPanel) return;
    mediaReviewed = true;
    reviewPanel.style.display = 'block';

    const thumbEl = document.getElementById('previewThumb');
    const thumbContainer = document.getElementById('thumbContainer');
    if (info.thumbnail && thumbEl) {
      thumbEl.src = info.thumbnail;
      thumbEl.onerror = () => { if (thumbContainer) thumbContainer.style.display = 'none'; };
      if (thumbContainer) thumbContainer.style.display = '';
    } else if (thumbContainer) {
      thumbContainer.style.display = 'none';
    }

    const durEl = document.getElementById('previewDuration');
    const metaDur = document.getElementById('metaDurationText');
    const metaDurTag = document.getElementById('metaDurationTag');
    const durStr = fmtDuration(info.duration);
    if (durEl) durEl.textContent = durStr;
    if (metaDur) metaDur.textContent = durStr;
    if (metaDurTag) metaDurTag.style.display = durStr ? '' : 'none';

    const titleEl = document.getElementById('previewTitle');
    if (titleEl) titleEl.textContent = info.title || 'Media ready';

    const uploaderEl = document.getElementById('previewUploader');
    if (uploaderEl) {
      uploaderEl.textContent = [info.uploader, info.extractor].filter(Boolean).join(' · ');
    }

    const viewsEl = document.getElementById('metaViewsText');
    const viewsTag = document.getElementById('metaViewsTag');
    if (viewsEl && info.view_count) {
      viewsEl.textContent = `${info.view_count.toLocaleString()} views`;
      if (viewsTag) viewsTag.style.display = '';
    } else if (viewsTag) {
      viewsTag.style.display = 'none';
    }

    const audioTag = document.getElementById('metaAudioTag');
    if (info.is_playlist) {
      if (audioTag) {
        audioTag.innerHTML = `<i class="bi bi-collection-play text-accent"></i> Playlist (${info.entry_count} tracks)`;
      }
      if (playlistBanner) {
        playlistBanner.style.setProperty('display', 'flex', 'important');
        if (playlistInspectLink) {
          playlistInspectLink.href = `/playlist/?url=${encodeURIComponent(urlInput.value.trim())}`;
        }
      }
      if (downloadBtn) {
        downloadBtn.innerHTML = `<i class="bi bi-cloud-arrow-down-fill me-1"></i> Download all tracks (${info.entry_count})`;
        downloadBtn.disabled = false;
      }
    } else {
      if (audioTag) {
        audioTag.innerHTML = `<i class="bi bi-soundwave text-accent"></i> Original stream`;
      }
      if (downloadBtn) {
        downloadBtn.innerHTML = `<i class="bi bi-cloud-arrow-down-fill me-1"></i> Start download`;
        downloadBtn.disabled = false;
      }
    }
  }

  // Inspect / Review button
  if (inspectBtn) {
    inspectBtn.addEventListener('click', async (e) => {
      if (e) {
        e.preventDefault();
        e.stopPropagation();
      }
      const rawUrl = urlInput ? urlInput.value.trim() : '';
      const url = cleanMediaUrl(rawUrl);
      if (urlInput) urlInput.value = url;
      if (!url) {
        if (window.MF) window.MF.toast('Please enter or paste a media link.', 'warning');
        return;
      }

      inspectBtn.disabled = true;
      if (inspectSpinner) inspectSpinner.style.display = 'inline-block';
      if (inspectBtnText) inspectBtnText.textContent = 'Reviewing…';

      try {
        const csrfToken = window.MF ? window.MF.getCsrf() : '';
        const r = await fetch('/download/inspect/', {
          method: 'POST',
          headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
          body: JSON.stringify({url}),
        });
        const data = await r.json();
        if (data.ok && data.info) {
          renderPreview(data.info);
          if (window.MF) window.MF.toast('Media reviewed successfully.', 'success', 2000);
        } else {
          if (window.MF) window.MF.toast(data.error || 'Could not inspect media link.', 'error');
        }
      } catch(e) {
        if (window.MF) window.MF.toast('Network error while reviewing media.', 'error');
      } finally {
        inspectBtn.disabled = false;
        if (inspectSpinner) inspectSpinner.style.display = 'none';
        if (inspectBtnText) inspectBtnText.textContent = 'Review media';
      }
    });
  }

  // Prevent form submission on Enter before reviewing
  if (downloadForm) {
    downloadForm.addEventListener('submit', (e) => {
      if (!mediaReviewed) {
        e.preventDefault();
        e.stopPropagation();
        if (inspectBtn) {
          inspectBtn.disabled = false;
          inspectBtn.click();
        }
        return false;
      }
    });
  }

  // Allow Enter key in URL input to trigger review
  if (urlInput) {
    urlInput.addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        e.preventDefault();
        e.stopPropagation();
        if (inspectBtn) {
          inspectBtn.disabled = false;
          inspectBtn.click();
        }
      }
    });
  }

  // Audio vs Video mode switches
  if (modeAudioRadio && modeVideoRadio && audioOnlyInput) {
    modeAudioRadio.addEventListener('change', () => {
      audioOnlyInput.value = 'true';
      if (qualitySelectorCol) qualitySelectorCol.style.display = '';
      if (qualityHintBox) qualityHintBox.style.display = '';
    });
    modeVideoRadio.addEventListener('change', () => {
      audioOnlyInput.value = 'false';
      if (qualitySelectorCol) qualitySelectorCol.style.display = 'none';
      if (qualityHintBox) qualityHintBox.style.display = 'none';
    });
  }

  // Quality explanation update
  function updateQualityInfo() {
    if (!formatSelect || !qualitySelect || !qualityHintText) return;
    const fmt  = formatSelect.value;
    const qual = qualitySelect.value;

    const descriptions = {
      'original': 'Preserves best available source audio stream without lossy re-encoding.',
      'mp3_320': 'Encodes to MP3 at maximum fixed 320 kbps bitrate for wide device compatibility.',
      'mp3_256': 'Encodes to MP3 at 256 kbps target bitrate for high quality and balanced file size.',
      'mp3_192': 'Encodes to MP3 at 192 kbps target bitrate for smaller, portable file size.',
      'mp3_vbr_high': 'Uses LAME VBR preset (-q:a 2) for optimal perceived quality with reduced file size.',
    };

    if (fmt === 'original') {
      qualitySelect.value = 'original';
      qualitySelect.querySelectorAll('option').forEach(o => {
        o.disabled = o.value !== 'original';
      });
      qualityHintText.textContent = descriptions['original'];
    } else {
      qualitySelect.querySelectorAll('option').forEach(o => {
        o.disabled = false;
      });
      qualityHintText.textContent = descriptions[qual] || (window.QUALITY_PRESETS && window.QUALITY_PRESETS[fmt] && window.QUALITY_PRESETS[fmt][qual] ? window.QUALITY_PRESETS[fmt][qual].label : 'Selected audio preset.');
    }
  }

  if (formatSelect) formatSelect.addEventListener('change', updateQualityInfo);
  if (qualitySelect) qualitySelect.addEventListener('change', updateQualityInfo);
  updateQualityInfo();

  // Collapsible custom save folder
  if (toggleSaveDir && saveDirWrapper) {
    toggleSaveDir.addEventListener('click', () => {
      const isHidden = saveDirWrapper.style.display === 'none';
      saveDirWrapper.style.display = isHidden ? 'block' : 'none';
      toggleSaveDir.textContent = isHidden ? 'Hide folder' : 'Change folder';
    });
  }

})();
