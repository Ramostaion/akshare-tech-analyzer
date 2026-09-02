const form = document.querySelector("#analyze-form");
const result = document.querySelector("#result");
const message = document.querySelector("#message");
const analyzeButton = document.querySelector("#analyze-button");
const downloadButton = document.querySelector("#download-button");
const autoRefresh = document.querySelector("#auto-refresh");
const refreshInterval = document.querySelector("#refresh-interval");
const assetType = document.querySelector("#asset-type");
const symbolInput = document.querySelector("#symbol");
const periodSelect = document.querySelector("#period");
const adjustSelect = document.querySelector("#adjust");
const quickInstruments = document.querySelector("#quick-instruments");
const favoriteButton = document.querySelector("#favorite-button");
const favoriteContextMenu = document.querySelector("#favorite-context-menu");
const removeFavoriteButton = document.querySelector("#remove-favorite");
const algorithmButtons = [...document.querySelectorAll(".algorithm-toggle")];
let refreshTimer = null;
let chartResizeObserver = null;
let chartResizeFrame = null;
let suggestionTimer = null;
let currentInstrument = null;
let contextFavorite = null;
let renderedChartContext = null;
const algorithmVisibility = { wave: true, gann: false };

const favoritesStorageKey = "akshare-tech-analyzer:favorites:v1";
const assetLabels = { stock: "A股", etf: "场内ETF", cn_stock: "A股", cn_etf: "场内ETF", us_stock: "美股", us_index: "美国指数", global_future: "外盘期货" };

function localDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

const today = new Date();
const twoYearsAgo = new Date(today);
twoYearsAgo.setFullYear(today.getFullYear() - 2);
document.querySelector("#end").value = localDate(today);
document.querySelector("#start").value = localDate(twoYearsAgo);

const marketRules = {
  auto: { hint: "示例：600011、510300", value: "600011", pattern: "[0-9]{6}", max: 6, periods: ["daily", "weekly", "monthly", "1m", "5m", "15m", "30m", "60m"], adjustments: ["qfq", "hfq", "none"], defaultAdjust: "qfq" },
  cn_stock: { hint: "示例：600011、600027", value: "600011", pattern: "[0-9]{6}", max: 6, periods: ["daily", "weekly", "monthly", "1m", "5m", "15m", "30m", "60m"], adjustments: ["qfq", "hfq", "none"], defaultAdjust: "qfq" },
  cn_etf: { hint: "示例：510300、510760", value: "510300", pattern: "[0-9]{6}", max: 6, periods: ["daily", "weekly", "monthly", "1m", "5m", "15m", "30m", "60m"], adjustments: ["qfq", "hfq", "none"], defaultAdjust: "qfq" },
  us_stock: { hint: "示例：AAPL、SPCX", value: "AAPL", pattern: "[A-Za-z0-9.-]{1,16}", max: 16, periods: ["daily", "weekly", "monthly", "1m"], adjustments: ["none", "qfq", "hfq"], defaultAdjust: "none" },
  us_index: { hint: "支持：.IXIC、.NDX、.INX、.DJI", value: ".IXIC", pattern: "\\.(IXIC|NDX|INX|DJI)", max: 5, periods: ["daily", "weekly", "monthly"], adjustments: ["none"], defaultAdjust: "none" },
  global_future: { hint: "支持：GC、SI、HG、CL、NG、OIL、XAU、XAG", value: "GC", pattern: "(GC|SI|HG|CL|NG|OIL|XAU|XAG)", max: 3, periods: ["daily", "weekly", "monthly"], adjustments: ["none"], defaultAdjust: "none" },
};

function normalizedAssetType(value) {
  if (value === "stock") return "cn_stock";
  if (value === "etf") return "cn_etf";
  return value;
}

function instrumentKey(item) {
  return `${normalizedAssetType(item.asset_type)}:${item.symbol.toUpperCase()}`;
}

function storedFavorites() {
  try {
    const parsed = JSON.parse(localStorage.getItem(favoritesStorageKey) || "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item) => (
      item && typeof item.symbol === "string" && typeof item.name === "string" &&
      marketRules[normalizedAssetType(item.asset_type)]
    )).slice(0, 30).map((item) => ({
      symbol: item.symbol.toUpperCase(),
      name: item.name,
      asset_type: normalizedAssetType(item.asset_type),
    }));
  } catch (_error) {
    return [];
  }
}

function saveFavorites(items) {
  try {
    localStorage.setItem(favoritesStorageKey, JSON.stringify(items.slice(0, 30)));
  } catch (_error) {
    showMessage("浏览器未允许本地存储，本次常用变更无法保存", true);
  }
}

function selectQuickInstrument(item) {
  assetType.value = normalizedAssetType(item.asset_type);
  applyMarketRules(true);
  symbolInput.value = item.symbol;
}

function closeFavoriteContextMenu() {
  favoriteContextMenu.classList.add("hidden");
  contextFavorite = null;
}

function openFavoriteContextMenu(event, item) {
  event.preventDefault();
  contextFavorite = item;
  favoriteContextMenu.classList.remove("hidden");
  const width = favoriteContextMenu.offsetWidth;
  const height = favoriteContextMenu.offsetHeight;
  favoriteContextMenu.style.left = `${Math.min(event.clientX, window.innerWidth - width - 8)}px`;
  favoriteContextMenu.style.top = `${Math.min(event.clientY, window.innerHeight - height - 8)}px`;
  removeFavoriteButton.focus();
}

function renderQuickInstruments() {
  const favorites = storedFavorites();
  closeFavoriteContextMenu();
  quickInstruments.replaceChildren();
  quickInstruments.classList.toggle("empty", favorites.length === 0);
  favorites.forEach((item) => {
    const wrapper = document.createElement("span");
    wrapper.className = "quick-item";
    const codeButton = document.createElement("button");
    codeButton.type = "button";
    codeButton.className = "quick-code";
    codeButton.textContent = item.symbol;
    codeButton.title = `${item.name} · ${assetLabels[item.asset_type]}`;
    codeButton.dataset.symbol = item.symbol;
    codeButton.dataset.asset = item.asset_type;
    codeButton.addEventListener("click", () => selectQuickInstrument(item));
    wrapper.addEventListener("contextmenu", (event) => openFavoriteContextMenu(event, item));
    wrapper.append(codeButton);
    quickInstruments.append(wrapper);
  });
}

function updateFavoriteButton() {
  if (!currentInstrument) return;
  const key = instrumentKey(currentInstrument);
  const isStored = storedFavorites().some((item) => instrumentKey(item) === key);
  favoriteButton.textContent = isStored ? "★" : "☆";
  favoriteButton.classList.toggle("active", isStored);
  favoriteButton.title = isStored ? "从常用移除" : "加入常用";
  favoriteButton.setAttribute("aria-label", favoriteButton.title);
}

favoriteButton.addEventListener("click", () => {
  if (!currentInstrument) return;
  const key = instrumentKey(currentInstrument);
  const favorites = storedFavorites();
  const existing = favorites.some((item) => instrumentKey(item) === key);
  saveFavorites(existing ? favorites.filter((item) => instrumentKey(item) !== key) : [...favorites, currentInstrument]);
  renderQuickInstruments();
  updateFavoriteButton();
});

removeFavoriteButton.addEventListener("click", () => {
  if (!contextFavorite) return;
  const key = instrumentKey(contextFavorite);
  saveFavorites(storedFavorites().filter((item) => instrumentKey(item) !== key));
  renderQuickInstruments();
  updateFavoriteButton();
});

document.addEventListener("click", (event) => {
  if (!favoriteContextMenu.contains(event.target)) closeFavoriteContextMenu();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeFavoriteContextMenu();
});
window.addEventListener("blur", closeFavoriteContextMenu);
window.addEventListener("resize", closeFavoriteContextMenu);
window.addEventListener("scroll", closeFavoriteContextMenu, true);

renderQuickInstruments();

function applyMarketRules(resetSymbol = true) {
  const rules = marketRules[assetType.value];
  const previousAdjust = adjustSelect.value;
  if (resetSymbol) symbolInput.value = rules.value;
  symbolInput.pattern = rules.pattern;
  symbolInput.maxLength = rules.max;
  symbolInput.inputMode = assetType.value.startsWith("cn") || assetType.value === "auto" ? "numeric" : "text";
  document.querySelector("#symbol-hint").textContent = rules.hint;
  Array.from(periodSelect.options).forEach((option) => { option.disabled = !rules.periods.includes(option.value); });
  if (!rules.periods.includes(periodSelect.value)) periodSelect.value = rules.periods[0];
  Array.from(adjustSelect.options).forEach((option) => { option.disabled = !rules.adjustments.includes(option.value); });
  adjustSelect.value = !resetSymbol && rules.adjustments.includes(previousAdjust) ? previousAdjust : rules.defaultAdjust;
  adjustSelect.disabled = rules.adjustments.length === 1;
}

assetType.addEventListener("change", () => applyMarketRules(true));
periodSelect.addEventListener("change", () => {
  if (assetType.value === "us_stock" && periodSelect.value === "1m") {
    adjustSelect.value = "none";
    adjustSelect.disabled = true;
  } else {
    applyMarketRules(false);
  }
});
symbolInput.addEventListener("input", () => {
  clearTimeout(suggestionTimer);
  const supported = ["us_stock", "us_index", "global_future"].includes(assetType.value);
  const query = symbolInput.value.trim();
  if (!supported || !query) return;
  suggestionTimer = setTimeout(async () => {
    try {
      const params = new URLSearchParams({ q: query, asset_type: assetType.value });
      const response = await fetch(`/api/instruments/search?${params}`);
      if (!response.ok) return;
      const data = await response.json();
      const datalist = document.querySelector("#symbol-suggestions");
      datalist.replaceChildren(...data.items.map((item) => {
        const option = document.createElement("option");
        option.value = item.symbol;
        option.label = item.name;
        return option;
      }));
    } catch (_error) {
      // 联想失败不影响手工输入和正式分析请求。
    }
  }, 250);
});

function showMessage(text, isError = false) {
  message.textContent = text;
  message.classList.remove("hidden", "error");
  if (isError) message.classList.add("error");
}

function setText(selector, value) {
  document.querySelector(selector).textContent = value ?? "--";
}

function number(value, digits = 2) {
  return value === null || value === undefined || Number.isNaN(value) ? "--" : Number(value).toFixed(digits);
}

function renderList(selector, items, emptyText = "暂无有效证据") {
  const target = document.querySelector(selector);
  target.replaceChildren();
  const values = items && items.length ? items : [emptyText];
  values.forEach((item) => {
    const li = document.createElement("li");
    li.textContent = item;
    target.append(li);
  });
}

function renderRows(selector, values) {
  const target = document.querySelector(selector);
  target.replaceChildren();
  (values.length ? values : ["暂无可用数据"]).forEach((value) => {
    const row = document.createElement("div");
    row.textContent = value;
    target.append(row);
  });
}

const setupLabels = {
  trend_pullback: "趋势回踩",
  breakout: "突破",
  support_reversal: "支撑反转",
  trend_breakdown: "趋势破位退出",
};

const wavePatternLabels = {
  impulse: "推动五浪",
  unfinished_impulse: "未完成推动浪",
  abc_zigzag: "ABC 锯齿调整",
  unfinished_abc: "未完成 ABC 调整",
};

function renderWaveCandidates(wave) {
  const target = document.querySelector("#wave-candidates");
  target.replaceChildren();
  const candidates = wave?.candidates || [];
  if (!candidates.length) {
    const empty = document.createElement("div");
    empty.className = "wave-note";
    empty.textContent = "暂无通过硬规则的浪形候选；等待更多已确认 Pivot。";
    target.append(empty);
  }
  candidates.forEach((candidate, index) => {
    const projection = candidate.projection || {};
    const fit = candidate.structural_fit ?? candidate.confidence ?? 0;
    const direction = candidate.direction === "down" ? "下行" : "上行";
    const pathDirection = projection.path_direction === "down" ? "向下" : "向上";
    const status = candidate.status === "developing" ? "进行中" : "已完成";
    const currentState = candidate.current_state_label || "等待更多行情确认";
    const validation = candidate.historical_validation || {};
    const currentStage = candidate.status === "developing"
      ? `当前处于${candidate.current_wave}浪形成阶段`
      : `${candidate.current_wave}浪端点已经右侧确认`;
    const zone = projection.primary_zone || [];
    const card = document.createElement(index === 0 ? "article" : "details");
    card.className = index === 0 ? "wave-card" : "wave-card wave-card-secondary";
    const head = document.createElement(index === 0 ? "div" : "summary");
    head.className = "wave-card-head";
    const title = document.createElement("strong");
    title.textContent = `候选 ${index + 1}${index === 0 ? " · 首选结构" : ""} · ${wavePatternLabels[candidate.pattern] || candidate.pattern}（${direction}）`;
    const score = document.createElement("span");
    score.className = "wave-fit";
    score.textContent = `结构匹配度 ${number(fit * 100, 1)}/100`;
    const meta = document.createElement("div");
    meta.className = "wave-meta";
    meta.textContent = `${status} · ${candidate.scale || "标准尺度"} · ${currentStage} · ${currentState}`;
    const targetScenario = document.createElement("div");
    targetScenario.className = "wave-scenario";
    targetScenario.textContent = zone.length === 2
      ? `情景 1（${pathDirection}）：确认后向${projection.target_label || "条件目标观察区"}推进，观察 ${zone.join("–")}`
      : "情景 1：当前结构暂不生成目标区";
    const confirmationScenario = document.createElement("div");
    confirmationScenario.className = "wave-scenario";
    confirmationScenario.textContent = projection.confirmation == null
      ? "确认门槛：等待新的已确认 Pivot"
      : `确认门槛：${projection.confirmation_label || "路径确认位"} ${number(projection.confirmation, 3)}；${projection.confirmation_rule || "确认后再观察目标区"}`;
    const invalidationScenario = document.createElement("div");
    invalidationScenario.className = "wave-scenario";
    invalidationScenario.textContent = projection.invalidation == null
      ? "情景 2：暂无可用失效位"
      : `情景 2：确认尝试失败并转向${projection.invalidation_label || "候选失效位"} ${number(projection.invalidation, 3)}；${projection.invalidation_rule || "失效后重新计浪"}`;
    const neutralScenario = document.createElement("div");
    neutralScenario.className = "wave-scenario";
    neutralScenario.textContent = "情景 3：确认位与失效位之间震荡，候选保持观察，不提前选择方向。";
    neutralScenario.classList.toggle("hidden", candidate.current_state !== "waiting");
    const history = document.createElement("div");
    history.className = "wave-history";
    history.textContent = validation.calibrated
      ? `历史逐根回放：已决样本 ${validation.resolved_count} 次，情景 1 目标先达率 ${number(validation.target_first_rate, 1)}%，目标中位用时 ${number(validation.median_target_bars, 1)} 根 K 线（最长观察 ${validation.lookahead_bars} 根）。`
      : `历史逐根回放：同类样本 ${validation.sample_count || 0} 次、已决 ${validation.resolved_count || 0} 次；样本不足，暂不展示概率。`;
    const corridorNote = document.createElement("div");
    corridorNote.className = "wave-note";
    corridorNote.textContent = "K 线图中的绿色半透明带为随路径扩张的 ATR 不确定性走廊；折线节点不是精确预测价。";
    const evidence = document.createElement("details");
    evidence.className = "wave-evidence";
    const evidenceSummary = document.createElement("summary");
    evidenceSummary.textContent = "历史验证与图表说明";
    evidence.append(evidenceSummary, history, corridorNote);
    head.append(title, score);
    card.append(head, meta, confirmationScenario, targetScenario, invalidationScenario, neutralScenario, evidence);
    target.append(card);
  });
  if (wave?.note) {
    const note = document.createElement("div");
    note.className = "wave-note";
    note.textContent = wave.note;
    target.append(note);
  }
}

function renderGann(gann) {
  const target = document.querySelector("#gann-analysis");
  target.replaceChildren();
  if (!gann || gann.status !== "active") {
    renderRows("#gann-analysis", [gann?.note || "暂无足够的已确认高低点。"]);
    return;
  }
  const anchor = gann.anchor || {};
  const scale = gann.scale || {};
  const history = gann.historical_validation || {};
  const direction = gann.direction === "down" ? "下行" : "上行";
  const anchorDate = anchor.timestamp ? new Date(anchor.timestamp).toLocaleDateString("zh-CN") : "--";
  const confirmedDate = anchor.confirmed_at
    ? new Date(anchor.confirmed_at).toLocaleDateString("zh-CN")
    : "--";
  const cycles = (gann.time_cycles || []).map((item) => `${item.bars}根`).join("、");
  const nearestLevels = [...(gann.price_levels || [])]
    .sort((left, right) => Math.abs(left.price - anchor.price) - Math.abs(right.price - anchor.price))
    .slice(0, 4)
    .map((item) => `${item.label}：${number(item.price, 3)}`)
    .join(" · ");
  renderRows("#gann-analysis", [
    `自动结构锚点：${anchorDate} ${number(anchor.price, 3)}；${confirmedDate} 完成右侧确认`,
    `方向：${direction} · 当前状态：${gann.current_state_label || "等待确认"}`,
    `归一化尺度：${scale.method || "ATR14/8 每根 K 线"}；1×1 单位 ${number(scale.unit_per_bar, 4)}`,
    `收盘确认位：${number(gann.confirmation, 3)} · 结构失效位：${number(gann.invalidation, 3)}`,
    `附近价格分割：${nearestLevels || "暂无"}`,
    `未来时间观察窗：${cycles || "当前锚点周期均已进入历史"}`,
    history.calibrated
      ? `历史逐根回放：已决 ${history.resolved_count} 次，目标先达率 ${number(history.target_first_rate, 1)}%，目标中位用时 ${number(history.median_target_bars, 1)} 根。`
      : `历史逐根回放：样本 ${history.sample_count || 0} 次、已决 ${history.resolved_count || 0} 次；样本不足，暂不展示概率。`,
    gann.note,
  ]);
}

function priceText(value, currency) {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  const symbols = { CNY: "¥", USD: "$", HKD: "HK$", EUR: "€", JPY: "¥" };
  return `${symbols[currency] || `${currency || ""} `}${number(value, 2)}`;
}

function renderQuant(quant, security) {
  const regime = quant?.market_regime || {};
  const signal = quant?.current_signal;
  const setups = quant?.current_setups || [];
  const activeSetup = signal
    ? `${setupLabels[signal.setup] || signal.setup}${signal.direction === "long" ? "确认" : ""}`
    : setups.length
      ? setups.map((item) => (
        `${setupLabels[item.setup] || item.setup}${item.triggered ? "确认" : "观察"}`
      )).join(" / ")
      : "暂无明确 Setup";
  const signalScore = signal?.score;
  setText("#overview-setup", activeSetup);
  setText("#overview-signal-score", signalScore == null ? "等待触发" : number(signalScore, 0));
  document.querySelector("#signal-score-fill").style.width = `${signalScore || 0}%`;
  renderRows("#quant-signal", [
    `市场状态：${regime.regime || "INSUFFICIENT_DATA"} · 置信度${number((regime.confidence || 0) * 100, 1)}%`,
    `当前交易形态：${setups.length ? setups.map((item) => `${setupLabels[item.setup] || item.setup}${item.triggered ? "（已触发）" : "（等待触发）"}`).join("、") : "无"}`,
    `信号质量分：${signal ? `${number(signal.score, 1)}/100（规则分，不是上涨概率）` : "无已触发信号"}`,
    ...(regime.evidence || []),
  ]);
  renderRows("#quant-risk", signal ? [
    `方向：${signal.direction === "long" ? "做多" : "退出"} · 收盘参考价 ${number(signal.entry_reference, 3)} · 默认下一交易日开盘执行`,
    `失效位：${number(signal.stop_price, 3)}`,
    `第一目标：${number(signal.target_1, 3)} · 第二目标：${number(signal.target_2, 3)}`,
    `潜在盈亏比：${number(signal.reward_risk_ratio, 2)}`,
  ] : []);
  const history = quant?.historical_similar || {};
  setText("#overview-samples", `${history.sample_count || 0} 次`);
  setText(
    "#overview-win-rate",
    history.win_rate == null ? "--" : `${number(history.win_rate, 1)}%`,
  );
  setText(
    "#overview-expected-r",
    history.expected_r == null
      ? "--"
      : `${history.expected_r >= 0 ? "+" : ""}${number(history.expected_r, 2)}R`,
  );
  const currency = security?.currency;
  const pendingText = "等待 Trigger 后计算";
  setText(
    "#overview-entry-zone",
    signal?.entry_zone_lower != null && signal?.entry_zone_upper != null
      ? `${priceText(signal.entry_zone_lower, currency)} – ${priceText(signal.entry_zone_upper, currency)}`
      : pendingText,
  );
  setText("#overview-stop", signal ? priceText(signal.stop_price, currency) : pendingText);
  setText("#overview-target-1", signal ? priceText(signal.target_1, currency) : pendingText);
  setText("#overview-target-2", signal ? priceText(signal.target_2, currency) : pendingText);
  setText(
    "#overview-reward-risk",
    signal?.reward_risk_ratio == null
      ? pendingText
      : `1 : ${number(signal.reward_risk_ratio, 1)}`,
  );
  renderRows("#quant-history", [
    `样本数：${history.sample_count || 0}`,
    `历史胜率：${history.win_rate == null ? "--" : `${number(history.win_rate)}%`}`,
    `历史期望：${number(history.expected_r, 3)}R`,
    `有利波动中位数：${number(history.median_mfe_r, 3)}R · 不利波动中位数：${number(history.median_mae_r, 3)}R`,
    history.note || "历史统计不代表未来收益。",
  ]);
  const wave = quant?.wave || {};
  renderWaveCandidates(wave);
  renderGann(quant?.gann || {});
  const factorTarget = document.querySelector("#factor-snapshot");
  factorTarget.replaceChildren();
  Object.entries(quant?.factor_snapshot || {}).forEach(([name, value]) => {
    const item = document.createElement("div");
    const label = document.createElement("span");
    label.textContent = name;
    const output = document.createElement("strong");
    output.textContent = number(value, 4);
    item.append(label, output);
    factorTarget.append(item);
  });
  const metrics = quant?.backtest?.metrics || {};
  renderRows("#quant-backtest", [
    `交易数：${metrics.trade_count || 0} · 胜率${metrics.win_rate == null ? "--" : `${number(metrics.win_rate)}%`}`,
    `每笔期望：${number(metrics.expectancy_r, 3)}R · 盈亏因子：${number(metrics.profit_factor, 3)}`,
    `累计收益：${metrics.cumulative_return == null ? "--" : `${number(metrics.cumulative_return)}%`} · 最大回撤${metrics.max_drawdown == null ? "--" : `${number(metrics.max_drawdown)}%`}`,
    `平均持有：${number(metrics.average_holding_bars, 1)}根 · 夏普比率：${number(metrics.sharpe, 3)}`,
  ]);
}

function captureChartView(graph) {
  if (!graph?.layout) return null;
  const view = {};
  Object.entries(graph.layout).forEach(([axisName, axis]) => {
    if (!/^[xy]axis\d*$/.test(axisName)) return;
    if (!Array.isArray(axis?.range) || axis.range.length !== 2 || axis.autorange === true) return;
    view[`${axisName}.range`] = [...axis.range];
    view[`${axisName}.autorange`] = false;
  });
  return Object.keys(view).length ? view : null;
}

function restoreChartView(graph, view) {
  if (!graph || !view) return;
  let attempts = 0;
  const applyView = () => {
    attempts += 1;
    if (!window.Plotly || !graph._fullLayout) {
      if (attempts < 60) requestAnimationFrame(applyView);
      return;
    }
    window.Plotly.relayout(graph, view).then(() => window.Plotly.Plots.resize(graph));
  };
  requestAnimationFrame(applyView);
}

function updateAlgorithmButtons() {
  algorithmButtons.forEach((button) => {
    const enabled = algorithmVisibility[button.dataset.algorithm];
    button.classList.toggle("active", enabled);
    button.setAttribute("aria-pressed", String(enabled));
  });
}

function fitPredictionView(graph) {
  const update = { "yaxis.autorange": true };
  const layout = graph?._fullLayout || graph?.layout || {};
  const xAxes = Object.keys(layout).filter((key) => /^xaxis\d*$/.test(key));
  (xAxes.length ? xAxes : ["xaxis"]).forEach((axis) => {
    update[`${axis}.autorange`] = true;
  });
  return window.Plotly.relayout(graph, update);
}

function setAlgorithmLayer(graph, algorithm, enabled, fitView = false) {
  if (!graph || !window.Plotly) return Promise.resolve();
  const traceIndices = [...(graph.data || [])]
    .map((trace, index) => trace.meta?.algorithm === algorithm ? index : -1)
    .filter((index) => index >= 0);
  const layoutUpdate = {};
  [...(graph.layout?.shapes || [])].forEach((shape, index) => {
    if (String(shape.name || "").startsWith(`algorithm-${algorithm}`)) {
      layoutUpdate[`shapes[${index}].visible`] = enabled;
    }
  });
  [...(graph.layout?.annotations || [])].forEach((annotation, index) => {
    if (String(annotation.name || "").startsWith(`algorithm-${algorithm}`)) {
      layoutUpdate[`annotations[${index}].visible`] = enabled;
    }
  });
  const undoState = graph.__akshareShapeUndo;
  if (undoState) undoState.applying = true;
  const operations = [];
  if (traceIndices.length) operations.push(window.Plotly.restyle(graph, { visible: enabled }, traceIndices));
  if (Object.keys(layoutUpdate).length) operations.push(window.Plotly.relayout(graph, layoutUpdate));
  return Promise.all(operations).then(() => {
    if (algorithm === "gann" && enabled && fitView) {
      return fitPredictionView(graph);
    }
    return undefined;
  }).finally(() => {
    if (undoState) undoState.applying = false;
  });
}

function applyAlgorithmLayers(graph) {
  let attempts = 0;
  const apply = () => {
    attempts += 1;
    if (!graph?._fullLayout || !window.Plotly) {
      if (attempts < 60) requestAnimationFrame(apply);
      return;
    }
    Object.entries(algorithmVisibility).forEach(([algorithm, enabled]) => {
      setAlgorithmLayer(graph, algorithm, enabled);
    });
  };
  requestAnimationFrame(apply);
}

algorithmButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const algorithm = button.dataset.algorithm;
    algorithmVisibility[algorithm] = !algorithmVisibility[algorithm];
    updateAlgorithmButtons();
    setAlgorithmLayer(
      document.querySelector("#chart .plotly-graph-div"),
      algorithm,
      algorithmVisibility[algorithm],
      true,
    );
  });
});
updateAlgorithmButtons();

function chartContext(data) {
  const request = data.request || {};
  const metadata = data.metadata || {};
  const security = metadata.security || {};
  return JSON.stringify([
    security.symbol,
    security.asset_type,
    metadata.period,
    metadata.adjust,
    request.start,
    request.end,
    request.show_kdj,
  ]);
}

function renderResult(data, preserveChartView = false) {
  const metadata = data.metadata;
  const security = metadata.security;
  const analysis = data.analysis;
  const latest = analysis.latest;
  setText("#security-code", security.symbol);
  setText("#security-name", security.name);
  setText("#asset-badge", assetLabels[security.asset_type] || security.asset_type);
  currentInstrument = {
    symbol: security.symbol,
    name: security.name,
    asset_type: normalizedAssetType(security.asset_type),
  };
  updateFavoriteButton();
  result.classList.toggle("global-market", ["us_stock", "us_index", "global_future"].includes(security.asset_type));
  setText("#latest-price", number(latest.close, 3));
  const changeNode = document.querySelector("#pct-change");
  changeNode.textContent = latest.pct_change === null ? "--" : `${number(latest.pct_change)}%`;
  changeNode.classList.remove("positive", "negative");
  if (latest.pct_change > 0) changeNode.classList.add("positive");
  if (latest.pct_change < 0) changeNode.classList.add("negative");
  setText("#trend-state", analysis.state);
  setText("#market-regime", analysis.market_regime?.label);
  setText("#score", `${analysis.score}/100`);
  setText("#score-ring", analysis.score);
  document.querySelector("#technical-score-fill").style.width = `${analysis.score}%`;
  setText("#support", data.levels.supports[0] ? number(data.levels.supports[0].price, 3) : "未识别");
  setText("#resistance", data.levels.resistances[0] ? number(data.levels.resistances[0].price, 3) : "未识别");
  setText("#atr-pct", latest.ATR_PCT === null ? "--" : `${number(latest.ATR_PCT)}%`);
  setText("#summary", analysis.summary);
  setText("#data-line", `来源：${security.data_source} · ${metadata.from_cache ? "缓存数据" : "本次获取"} · 更新：${new Date(metadata.fetched_at).toLocaleString("zh-CN", { timeZone: security.timezone || "Asia/Shanghai" })} · ${metadata.period}/${metadata.adjust} · ${metadata.rows}根K线 · ${security.exchange} · ${security.currency} · 成交量：${metadata.volume_unit} · 上游代码：${security.provider_symbol} · 识别：${security.detection_method}${security.series_type ? ` · ${security.series_type}` : ""}`);
  const snapshotLine = document.querySelector("#snapshot-line");
  if (metadata.snapshot) {
    const snapshot = metadata.snapshot;
    snapshotLine.textContent = `独立快照：最新价 ${number(snapshot.latest, 3)} · 涨跌幅 ${snapshot.pct_change == null ? "--" : `${number(snapshot.pct_change)}%`} · 数据时间 ${snapshot.source_timestamp || "未知"} · 采集时间 ${new Date(snapshot.captured_at).toLocaleString("zh-CN")}`;
    snapshotLine.classList.remove("hidden");
  } else {
    snapshotLine.classList.add("hidden");
  }

  renderList("#bullish-list", analysis.evidence.bullish);
  renderList("#bearish-list", analysis.evidence.bearish);
  renderList("#warning-list", analysis.warning);
  renderList("#formula-list", analysis.formula_notes);
  renderList("#quality-list", metadata.quality_notes, "数据规范化检查通过");
  renderQuant(data.quant || analysis.quant || {}, security);

  const backtest = analysis.backtest || {};
  const tenBar = backtest.results?.["10"]?.all;
  setText(
    "#backtest-summary",
    `${backtest.method || "暂无方法"} · 信号${backtest.signals || 0}次 · `
      + `成本${number(backtest.cost_rate, 2)}% · `
      + `10根胜率${tenBar?.win_rate == null ? "--" : `${number(tenBar.win_rate)}%`}`,
  );
  const backtestResults = document.querySelector("#backtest-results");
  backtestResults.replaceChildren();
  Object.entries(backtest.results || {}).forEach(([horizon, sides]) => {
    const metric = sides.all;
    const item = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = `${horizon}根K线`;
    const detail = document.createElement("span");
    detail.textContent = metric.samples
      ? `样本${metric.samples} · 平均${number(metric.average_return)}% · `
        + `中位数${number(metric.median_return)}% · 盈亏比${number(metric.payoff_ratio)}`
      : "有效样本不足";
    item.append(title, detail);
    backtestResults.append(item);
  });

  const cache = metadata.cache_status || {};
  const quality = metadata.data_quality || {};
  const cacheLabels = {
    network: "线上完整获取",
    exact_cache: "查询缓存命中",
    series_cache: "历史数据库覆盖",
    incremental_update: "数据库增量更新",
    stale_series: "历史数据库降级",
  };
  const qualitySummary = document.querySelector("#cache-quality");
  qualitySummary.replaceChildren();
  [
    `缓存模式：${cacheLabels[cache.mode] || cache.mode || "未知"}`,
    `覆盖区间：${cache.coverage_start || "--"} 至 ${cache.coverage_end || "--"}`,
    `数据库已有：${cache.existing_rows ?? "--"}根，本次新增：${cache.new_rows ?? 0}根`,
    `质量状态：${quality.status || "未知"}；有效K线${quality.rows || 0}根`,
    ...(quality.issues || []),
  ].forEach((value) => {
    const row = document.createElement("div");
    row.textContent = value;
    qualitySummary.append(row);
  });

  const componentList = document.querySelector("#component-list");
  componentList.replaceChildren();
  Object.values(analysis.components).forEach((component) => {
    const row = document.createElement("div");
    row.className = "component";
    const label = document.createElement("span");
    label.textContent = component.name;
    const track = document.createElement("div");
    track.className = "component-track";
    const bar = document.createElement("div");
    bar.className = "component-bar";
    bar.style.width = `${component.score}%`;
    bar.title = component.reasons.map((reason) => `${reason.points >= 0 ? "+" : ""}${reason.points} ${reason.reason}`).join("\n");
    track.append(bar);
    const value = document.createElement("strong");
    value.textContent = number(component.score, 0);
    row.append(label, track, value);
    componentList.append(row);
  });

  const indicatorList = document.querySelector("#indicator-list");
  indicatorList.replaceChildren();
  Object.entries(latest).forEach(([name, value]) => {
    if (name === "close" || name === "pct_change") return;
    const item = document.createElement("div");
    const label = document.createElement("span");
    label.textContent = name;
    const output = document.createElement("strong");
    output.textContent = number(value, 3);
    item.append(label, output);
    indicatorList.append(item);
  });

  const scenario = document.querySelector("#scenario");
  if (data.levels.scenario) {
    const value = data.levels.scenario;
    scenario.textContent = `参考情景：观察区间 ${number(value.observation_lower, 3)}–${number(value.observation_upper, 3)}，失效位 ${number(value.invalidation, 3)}，目标位 ${number(value.target, 3)}，潜在盈亏比 ${number(value.reward_risk_ratio)}。${value.note}`;
    scenario.classList.remove("hidden");
  } else {
    scenario.classList.add("hidden");
  }

  const chart = document.querySelector("#chart");
  const previousGraph = chart.querySelector(".plotly-graph-div");
  const nextChartContext = chartContext(data);
  const savedChartView = preserveChartView && renderedChartContext === nextChartContext
    ? captureChartView(previousGraph)
    : null;
  // Plotly 初始化时必须能测量到真实容器宽度，否则会回退到 700px。
  result.classList.remove("hidden");
  chart.innerHTML = data.chart_html;
  chart.querySelectorAll("script").forEach((oldScript) => {
    const script = document.createElement("script");
    Array.from(oldScript.attributes).forEach((attribute) => script.setAttribute(attribute.name, attribute.value));
    script.textContent = oldScript.textContent;
    oldScript.replaceWith(script);
  });
  renderedChartContext = nextChartContext;
  const graph = chart.querySelector(".plotly-graph-div");
  if (graph && window.Plotly) {
    const resizeChart = () => {
      cancelAnimationFrame(chartResizeFrame);
      chartResizeFrame = requestAnimationFrame(() => window.Plotly.Plots.resize(graph));
    };
    chartResizeObserver?.disconnect();
    chartResizeObserver = new ResizeObserver(resizeChart);
    chartResizeObserver.observe(chart);
    requestAnimationFrame(() => requestAnimationFrame(resizeChart));
    restoreChartView(graph, savedChartView);
    applyAlgorithmLayers(graph);
  }
  downloadButton.href = data.download_url;
  downloadButton.classList.remove("disabled");
  downloadButton.setAttribute("aria-disabled", "false");
}

function requestPayload(forceRefresh = false) {
  return {
    symbol: document.querySelector("#symbol").value.trim(),
    asset_type: document.querySelector("#asset-type").value,
    period: document.querySelector("#period").value,
    adjust: document.querySelector("#adjust").value,
    start: document.querySelector("#start").value,
    end: document.querySelector("#end").value,
    show_ma: document.querySelector("#show-ma").checked,
    show_boll: document.querySelector("#show-boll").checked,
    show_levels: document.querySelector("#show-levels").checked,
    show_kdj: document.querySelector("#show-kdj").checked,
    force_refresh: forceRefresh,
  };
}

async function runAnalysis(forceRefresh = false) {
  if (!form.reportValidity()) return;
  analyzeButton.disabled = true;
  showMessage(forceRefresh ? "正在刷新行情并重新计算…" : "正在获取行情、计算指标并生成离线报告…");
  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestPayload(forceRefresh)),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error?.message || "分析请求失败");
    renderResult(data, forceRefresh);
    showMessage(`分析完成：${data.metadata.security.symbol} ${data.metadata.security.name}`);
  } catch (error) {
    showMessage(error.message || "数据源异常，请稍后重试", true);
  } finally {
    analyzeButton.disabled = false;
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  runAnalysis(false);
});

autoRefresh.addEventListener("change", () => {
  clearInterval(refreshTimer);
  refreshInterval.disabled = !autoRefresh.checked;
  if (autoRefresh.checked) {
    const seconds = Math.max(60, Number(refreshInterval.value));
    refreshTimer = setInterval(() => runAnalysis(true), seconds * 1000);
  }
});

refreshInterval.addEventListener("change", () => {
  if (!autoRefresh.checked) return;
  autoRefresh.dispatchEvent(new Event("change"));
});
