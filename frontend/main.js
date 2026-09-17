(function () {
  const TILE_SIZE = 256;
  const STACK_COUNT = 24;

  const map = new ol.Map({
    target: 'map',
    layers: [
      new ol.layer.Tile({
        source: new ol.source.OSM()
      })
    ],
    view: new ol.View({
      center: ol.proj.fromLonLat([-95, 39]),
      zoom: 3
    })
  });

  let webglLayer = null;
  let activeDataset = null;
  let activeBands = null;
  let activeDate = null;
  let activeEndDate = null;
  let activeStack = false;
  let tileRequestCount = 0;
  let playTimer = null;

  const debugLogsCheckbox = document.getElementById('debugLogs');
  const tileCountEl = document.getElementById('tileCount');
  const valueDisplay = document.getElementById('data-value');
  const presetSelect = document.getElementById('presetSelect');
  const stackHoursEl = document.getElementById('stackHours');
  const hourPanel = document.getElementById('hourPanel');
  const hourSlider = document.getElementById('hourSlider');
  const hourLabel = document.getElementById('hourLabel');
  const playHoursBtn = document.getElementById('playHoursBtn');

  const presets = {
    modis_ndvi: {
      dataset: 'MODIS/061/MOD13Q1',
      bands: 'NDVI',
      date: '2022-01-01',
      endDate: '2022-01-16',
      colormap: 'ndvi',
      minVal: 0,
      maxVal: 8000,
      stack: false
    },
    copernicus_landcover: {
      dataset: 'COPERNICUS/Landcover/100m/Proba-V-C3/Global',
      bands: 'discrete_classification',
      date: '2019-01-01',
      endDate: '2019-12-31',
      colormap: 'landcover',
      minVal: 0,
      maxVal: 200,
      stack: false
    },
    merra_temp: {
      dataset: 'NASA/GSFC/MERRA/flx/2',
      bands: 'TLML',
      date: '2022-02-01',
      endDate: '2022-02-02',
      colormap: 'thermal',
      minVal: 230,
      maxVal: 310,
      stack: true
    },
    merra_wind: {
      dataset: 'NASA/GSFC/MERRA/flx/2',
      bands: 'SPEED',
      date: '2022-02-01',
      endDate: '2022-02-02',
      colormap: 'wind',
      minVal: 0,
      maxVal: 25,
      stack: true
    }
  };

  const LANDCOVER_CLASSES = {
    0: "Unknown / No data",
    20: "Shrubs",
    30: "Herbaceous vegetation",
    40: "Cultivated / Agriculture",
    50: "Urban / Built up",
    60: "Bare / Sparse vegetation",
    70: "Snow and ice",
    80: "Permanent water bodies",
    90: "Herbaceous wetland",
    100: "Moss and lichen",
    111: "Closed forest, evergreen needle leaf",
    112: "Closed forest, evergreen broad leaf",
    113: "Closed forest, deciduous needle leaf",
    114: "Closed forest, deciduous broad leaf",
    115: "Closed forest, mixed",
    116: "Closed forest, other",
    121: "Open forest, evergreen needle leaf",
    122: "Open forest, evergreen broad leaf",
    123: "Open forest, deciduous needle leaf",
    124: "Open forest, deciduous broad leaf",
    125: "Open forest, mixed",
    126: "Open forest, other",
    200: "Oceans, seas"
  };

  function log(...args) {
    if (debugLogsCheckbox && debugLogsCheckbox.checked) {
      console.log(...args);
    }
  }

  function warn(...args) {
    if (debugLogsCheckbox && debugLogsCheckbox.checked) {
      console.warn(...args);
    }
  }

  function error(...args) {
    console.error(...args);
  }

  function incrementTileRequestCount() {
    tileRequestCount++;
    if (tileCountEl) {
      tileCountEl.textContent = tileRequestCount;
    }
  }

  function resetTileRequestCount() {
    tileRequestCount = 0;
    if (tileCountEl) {
      tileCountEl.textContent = '0';
    }
  }

  function isStackEnabled() {
    return !!(stackHoursEl && stackHoursEl.checked);
  }

  function currentHour() {
    return hourSlider ? parseInt(hourSlider.value, 10) || 0 : 0;
  }

  function formatHourLabel(hour) {
    const h = String(hour).padStart(2, '0');
    return `${h}:30 UTC`;
  }

  function stopHourPlayback() {
    if (playTimer) {
      clearInterval(playTimer);
      playTimer = null;
    }
    if (playHoursBtn) {
      playHoursBtn.textContent = 'Play';
    }
  }

  function syncHourPanel() {
    const stacked = isStackEnabled();
    if (hourPanel) {
      hourPanel.classList.toggle('visible', stacked);
    }
    if (hourLabel) {
      hourLabel.textContent = formatHourLabel(currentHour());
    }
    if (!stacked) {
      stopHourPlayback();
    }
  }

  function bandIndexForStyle() {
    return isStackEnabled() ? currentHour() + 1 : 1;
  }

  function buildStyle(colormap, minVal, maxVal, bandIndex) {
    log(`[Style Build] Colormap=${colormap}, Min=${minVal}, Max=${maxVal}, Band=${bandIndex}`);
    const sample = ['band', bandIndex];

    if (colormap === 'landcover') {
      return {
        color: [
          'case',
          ['==', sample, 0], ['color', 40, 40, 40],
          ['==', sample, 20], ['color', 255, 187, 34],
          ['==', sample, 30], ['color', 255, 255, 76],
          ['==', sample, 40], ['color', 240, 150, 255],
          ['==', sample, 50], ['color', 250, 0, 0],
          ['==', sample, 60], ['color', 180, 180, 180],
          ['==', sample, 70], ['color', 240, 240, 240],
          ['==', sample, 80], ['color', 0, 50, 200],
          ['==', sample, 90], ['color', 0, 150, 160],
          ['==', sample, 100], ['color', 250, 230, 160],
          ['==', sample, 111], ['color', 88, 72, 31],
          ['==', sample, 112], ['color', 0, 153, 0],
          ['==', sample, 113], ['color', 112, 102, 62],
          ['==', sample, 114], ['color', 0, 204, 0],
          ['==', sample, 115], ['color', 78, 117, 31],
          ['==', sample, 116], ['color', 0, 120, 0],
          ['==', sample, 121], ['color', 102, 96, 0],
          ['==', sample, 122], ['color', 141, 180, 0],
          ['==', sample, 123], ['color', 141, 116, 0],
          ['==', sample, 124], ['color', 160, 220, 0],
          ['==', sample, 125], ['color', 146, 153, 0],
          ['==', sample, 126], ['color', 100, 140, 0],
          ['==', sample, 200], ['color', 0, 0, 128],
          ['color', 40, 40, 40]
        ]
      };
    }

    if (colormap === 'grayscale') {
      const norm = ['/', ['-', sample, minVal], Math.max(1e-6, maxVal - minVal)];
      return {
        color: [
          'color',
          ['*', norm, 255],
          ['*', norm, 255],
          ['*', norm, 255],
          1
        ]
      };
    }

    let stops = [];
    if (colormap === 'wind') {
      stops = [
        minVal, ['color', 0, 17, 55],
        minVal + (maxVal - minVal) * 0.33, ['color', 1, 171, 171],
        minVal + (maxVal - minVal) * 0.66, ['color', 231, 235, 5],
        maxVal, ['color', 98, 5, 0]
      ];
    } else if (colormap === 'viridis') {
      stops = [
        minVal, ['color', 68, 1, 84],
        minVal + (maxVal - minVal) * 0.25, ['color', 59, 82, 139],
        minVal + (maxVal - minVal) * 0.5, ['color', 33, 145, 140],
        minVal + (maxVal - minVal) * 0.75, ['color', 94, 201, 98],
        maxVal, ['color', 253, 231, 37]
      ];
    } else if (colormap === 'thermal') {
      stops = [
        minVal, ['color', 0, 0, 255],
        minVal + (maxVal - minVal) * 0.5, ['color', 255, 255, 0],
        maxVal, ['color', 255, 0, 0]
      ];
    } else {
      stops = [
        minVal, ['color', 165, 0, 38],
        minVal + (maxVal - minVal) * 0.25, ['color', 254, 224, 139],
        minVal + (maxVal - minVal) * 0.5, ['color', 217, 239, 139],
        minVal + (maxVal - minVal) * 0.75, ['color', 102, 189, 99],
        maxVal, ['color', 0, 104, 55]
      ];
    }

    return {
      color: [
        'interpolate',
        ['linear'],
        sample,
        ...stops
      ]
    };
  }

  function createSource(dataset, bands, date, endDate, stack) {
    const numBands = stack ? STACK_COUNT : (bands.split(',').filter(Boolean).length || 1);
    log(`[Source Creation] dataset=${dataset}, bands=${bands}, date=${date}..${endDate}, stack=${stack}, numBands=${numBands}`);

    return new ol.source.DataTile({
      loader: function (z, x, y) {
        const worldSize = 1 << z;
        const wrappedX = ((x % worldSize) + worldSize) % worldSize;
        incrementTileRequestCount();
        let url = `/tiles/${z}/${wrappedX}/${y}?dataset=${encodeURIComponent(dataset)}&bands=${encodeURIComponent(bands)}`;
        if (date) {
          url += `&date=${encodeURIComponent(date)}`;
        }
        if (endDate) {
          url += `&end_date=${encodeURIComponent(endDate)}`;
        }
        if (stack) {
          url += `&stack=true&stack_count=${STACK_COUNT}`;
        }
        log(`[Loader] Fetching tile z=${z} x=${wrappedX} y=${y} (Total requests: ${tileRequestCount})`);

        return fetch(url, { cache: 'no-store' })
          .then(res => {
            if (!res.ok) {
              return res.text().then(body => {
                throw new Error(`HTTP ${res.status}: ${body.slice(0, 120)}`);
              });
            }
            const expectedBytes = TILE_SIZE * TILE_SIZE * numBands * 4;
            return res.arrayBuffer().then(buffer => {
              if (buffer.byteLength !== expectedBytes) {
                throw new Error(
                  `Wrong payload size z=${z} x=${wrappedX} y=${y}: ` +
                  `got ${buffer.byteLength} bytes, expected ${expectedBytes}`
                );
              }
              return buffer;
            });
          })
          .then(buffer => {
            const arr = new Float32Array(buffer);
            const expectedLen = TILE_SIZE * TILE_SIZE * numBands;

            let min = Infinity;
            let max = -Infinity;
            let nonZero = 0;
            for (let i = 0; i < arr.length; i++) {
              const v = arr[i];
              if (v < min) min = v;
              if (v > max) max = v;
              if (v !== 0) nonZero++;
            }

            log(
              `[Loader] Tile z=${z} x=${wrappedX} y=${y} | Bytes: ${buffer.byteLength} | Floats: ${arr.length} (Expected: ${expectedLen}) | ` +
              `Min: ${min.toFixed(2)}, Max: ${max.toFixed(2)}, Non-zero: ${nonZero}`
            );

            if (arr.length !== expectedLen) {
              throw new Error(
                `Tile size mismatch z=${z} x=${wrappedX} y=${y}: got ${arr.length} floats, expected ${expectedLen}`
              );
            }

            return arr;
          })
          .catch(err => {
            error(`[Loader] Tile z=${z} x=${wrappedX} y=${y} failed:`, err);
            throw err;
          });
      },
      tileSize: [TILE_SIZE, TILE_SIZE],
      bandCount: numBands,
      wrapX: true,
      maxZoom: 18
    });
  }

  function updateLayerOrStyle() {
    const dataset = document.getElementById('dataset').value.trim();
    const bands = document.getElementById('bands').value.trim();
    const date = document.getElementById('dateFilter').value.trim();
    const endDateEl = document.getElementById('endDateFilter');
    const endDate = endDateEl ? endDateEl.value.trim() : '';
    const colormap = document.getElementById('colormap').value;
    const minVal = parseFloat(document.getElementById('minVal').value) || 0;
    const maxVal = parseFloat(document.getElementById('maxVal').value) || 1;
    const stack = isStackEnabled();

    syncHourPanel();
    const style = buildStyle(colormap, minVal, maxVal, bandIndexForStyle());

    if (
      webglLayer &&
      activeDataset === dataset &&
      activeBands === bands &&
      activeDate === date &&
      activeEndDate === endDate &&
      activeStack === stack
    ) {
      log(`[Update Style ONLY] band=${bandIndexForStyle()} colormap=${colormap} min=${minVal} max=${maxVal}`);
      webglLayer.setStyle(style);
      return;
    }

    log(`[Update Layer & Source] dataset=${dataset}, bands=${bands}, date=${date}..${endDate}, stack=${stack}`);
    resetTileRequestCount();
    if (webglLayer) {
      map.removeLayer(webglLayer);
    }

    activeDataset = dataset;
    activeBands = bands;
    activeDate = date;
    activeEndDate = endDate;
    activeStack = stack;

    const source = createSource(dataset, bands, date, endDate, stack);
    webglLayer = new ol.layer.WebGLTile({
      source: source,
      style: style,
      cacheSize: 512
    });

    map.addLayer(webglLayer);
  }

  function applyPreset(key) {
    const p = presets[key];
    if (!p) return;
    document.getElementById('dataset').value = p.dataset;
    document.getElementById('bands').value = p.bands;
    document.getElementById('dateFilter').value = p.date;
    const endDateEl = document.getElementById('endDateFilter');
    if (endDateEl) {
      endDateEl.value = p.endDate || '';
    }
    document.getElementById('colormap').value = p.colormap;
    document.getElementById('minVal').value = p.minVal;
    document.getElementById('maxVal').value = p.maxVal;
    if (stackHoursEl) {
      stackHoursEl.checked = !!p.stack;
    }
    if (hourSlider) {
      hourSlider.value = '0';
    }
    stopHourPlayback();
    updateLayerOrStyle();
  }

  presetSelect.addEventListener('change', function () {
    applyPreset(presetSelect.value);
  });

  const resetTileCountBtn = document.getElementById('resetTileCountBtn');
  if (resetTileCountBtn) {
    resetTileCountBtn.addEventListener('click', resetTileRequestCount);
  }

  document.getElementById('updateBtn').addEventListener('click', updateLayerOrStyle);

  ['colormap', 'minVal', 'maxVal'].forEach(id => {
    document.getElementById(id).addEventListener('input', function () {
      if (webglLayer) {
        updateLayerOrStyle();
      }
    });
  });

  if (stackHoursEl) {
    stackHoursEl.addEventListener('change', function () {
      stopHourPlayback();
      updateLayerOrStyle();
    });
  }

  if (hourSlider) {
    hourSlider.addEventListener('input', function () {
      if (hourLabel) {
        hourLabel.textContent = formatHourLabel(currentHour());
      }
      if (webglLayer) {
        updateLayerOrStyle();
      }
    });
  }

  if (playHoursBtn) {
    playHoursBtn.addEventListener('click', function () {
      if (!isStackEnabled()) return;
      if (playTimer) {
        stopHourPlayback();
        return;
      }
      playHoursBtn.textContent = 'Pause';
      playTimer = setInterval(function () {
        const next = (currentHour() + 1) % STACK_COUNT;
        hourSlider.value = String(next);
        hourLabel.textContent = formatHourLabel(next);
        updateLayerOrStyle();
      }, 200);
    });
  }

  map.on('pointermove', function (evt) {
    if (evt.dragging || !webglLayer) return;

    try {
      const data = webglLayer.getData(evt.pixel);
      const hour = currentHour();
      const sampleIndex = isStackEnabled() ? hour : 0;
      if (data && data.length > sampleIndex && !isNaN(data[sampleIndex])) {
        const raw = data[sampleIndex];
        log(`[Hover] Pixel: (${evt.pixel[0]}, ${evt.pixel[1]}) hour=${hour} ->`, raw);
        const colormap = document.getElementById('colormap').value;
        const classId = Math.round(raw);
        let formatted = Number.isInteger(raw) ? raw.toString() : raw.toFixed(2);

        if (colormap === 'landcover' && LANDCOVER_CLASSES[classId] !== undefined) {
          formatted = `${classId} - ${LANDCOVER_CLASSES[classId]}`;
        }

        valueDisplay.textContent = formatted;
        document.title = `[${formatted}] GEE xee DataTile Viewer`;
      } else {
        valueDisplay.textContent = '--';
        document.title = 'GEE xee DataTile Viewer';
      }
    } catch (err) {
      warn('[Hover] getData failed:', err);
    }
  });

  updateLayerOrStyle();
})();
