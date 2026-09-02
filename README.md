# AKShare 多市场技术分析器

本项目是本地运行的多市场技术分析工作台，支持 A 股、场内 ETF、美股、美国指数和部分外盘期货。它通过统一的 AKShare 行情适配层获取 K 线，计算 pandas/NumPy 技术指标，以确定性规则生成趋势状态、量价证据、关键支撑阻力和风险提示，并导出内嵌 Plotly 的单文件 HTML 报告。

> 仅为算法技术分析结果，不构成投资建议。AKShare 聚合的第三方行情可能延迟、缺失或发生字段变化，请勿将本项目视为交易所实时行情或自动交易系统。

## 功能

- 支持六位代码的 A 股和场内 ETF，`auto` 模式先查询并缓存 ETF 列表，数据源不可用时才使用明确标记的代码前缀降级规则。
- 中国证券支持日、周、月和 1/5/15/30/60 分钟 K 线；国际市场按上表开放实际可用周期。
- 实现 SMA、EMA、MACD、Wilder RSI、KDJ、BOLL、Wilder ATR、量均线、量比和 OBV，不依赖 TA-Lib。
- Plotly K 线按市场切换涨跌颜色，包含成交量、MACD、RSI、可选 KDJ、关键位价格带和 MACD 事件标记。
- FastAPI 工作台、JSON API、CLI、SQLite JSON 缓存、离线单文件报告、Docker/Compose。
- 工作台可将当前分析品种加入“常用”，收藏保存在浏览器本地；悬停代码显示中文名称，右键可取消收藏。
- 新增因果 Factor、Market Regime、四类 Setup、结构化 Signal、独立执行模型、Triple Barrier、完整交易记录与按 Regime 分层的绩效统计。
- 新增时间序列研究工具、Elliott Wave Top-N 候选和 ATR 归一化江恩条件路径；所有预测图层均带确认与失效条件。
- 自动刷新默认关闭，开启后的最短间隔为 60 秒。AKShare 1 分钟历史通常仅覆盖最近若干交易日，并非交易所级推送。

## 市场与数据源

| 资产类型 | 输入示例 | AKShare 接口 | 周期与限制 |
|---|---|---|---|
| `auto/cn_stock/cn_etf` | `600011`、`510300` | `stock_zh_a_hist`、`fund_etf_hist_em` | 日/周/月及 1/5/15/30/60 分钟；支持前/后/不复权 |
| `us_stock` | `AAPL`、`SPCX` | `stock_us_spot_em` 匹配上游代码，再调用 `stock_us_hist` | 日/周/月；当前安装版另支持不复权 1 分钟线 |
| `us_index` | `.IXIC`、`.NDX`、`.INX`、`.DJI` | `index_us_stock_sina` | 日线；周/月线由日线聚合；无复权、换手率和分钟线 |
| `global_future` | `GC`、`SI`、`HG`、`CL`、`NG`、`OIL`、`XAU`、`XAG` | `futures_foreign_hist` 与独立实时快照接口 | 仅日线、不复权；品种连续参考序列，不是具体到期合约 |

美股输入使用不带市场前缀的 ticker。系统从 AKShare 代码表提取真实 `provider_symbol`，不会猜测 `105/106/107` 前缀。代码表缓存默认 4 小时，外盘期货快照缓存默认 20 秒。页面和报告同时显示规范代码、上游代码、市场、币种、时区、数据源与采集时间。

A 股成交量通常按“手”，美股按“股”；指数和外盘期货保留上游口径。缺少成交量时，量能评分保持中性而不是计为偏弱。外盘期货连续序列可能因换月产生非交易跳空，因此关键位可信度会降低并显示风险提示。中国市场使用红涨绿跌，海外市场使用绿涨红跌。

## 本地启动

Windows 用户可以直接双击项目根目录的 `启动平台.bat`，脚本会启动虚拟环境中的服务并打开浏览器。缺少 `.venv`、虚拟环境因更换系统而失效或运行依赖不完整时，脚本会使用本机 Python 3.11+ 自动重建环境并下载依赖。新系统尚未安装 Python 时会打开 Python 官方下载页。关闭命令窗口即可停止服务；如果 8000 端口已经有服务，脚本会直接打开现有页面。

只检查环境而不启动服务：

```powershell
.\启动平台.bat --check
```

Linux/macOS 或群晖可以运行：

```bash
chmod +x start.sh
./start.sh
```

需要 Python 3.11 或更高版本：

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

浏览器访问 <http://127.0.0.1:8000>。环境变量可从 `.env.example` 复制到 `.env` 后调整；本地未配置时，缓存、报告和日志分别写入项目内的 `cache/`、`reports/`、`logs/`。

## CLI 离线报告

```bash
python -m app.cli \
  --symbol 600011 \
  --asset-type auto \
  --period daily \
  --start 2024-01-01 \
  --end 2026-08-29 \
  --adjust qfq \
  --output reports/600011.html
```

美股、美国指数与外盘期货示例：

```bash
python -m app.cli --symbol AAPL --asset-type us_stock --period daily --start 2024-01-01 --end 2026-08-29 --adjust none --output reports/AAPL.html
python -m app.cli --symbol .IXIC --asset-type us_index --period daily --start 2024-01-01 --end 2026-08-29 --adjust none --output reports/IXIC.html
python -m app.cli --symbol GC --asset-type global_future --period daily --start 2024-01-01 --end 2026-08-29 --adjust none --output reports/GC.html
```

成功时会输出证券名称、数据条数、趋势状态、技术评分和 HTML 绝对路径。HTML 内嵌 Plotly 脚本、样式和全部分析文本，断网后可直接打开。

## API

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/health` | 健康检查 |
| `GET` | `/` | 浏览器工作台 |
| `GET` | `/api/security/{symbol}?asset_type=auto` | 识别证券 |
| `GET` | `/api/instruments/search?q=AAP&asset_type=us_stock` | 按代码或名称搜索国际品种 |
| `POST` | `/api/analyze` | 获取行情、分析并生成报告 |
| `GET` | `/api/report/{report_id}` | 查看服务端生成的报告 |
| `GET` | `/api/report/{report_id}/download` | 下载报告 |

错误响应固定为 `{"error":{"code":"...","message":"...","detail":...}}`。报告 ID 由服务端随机生成，接口不接受文件名或任意路径。

## 指标定义

- SMA 使用完整非居中滚动窗口；EMA 使用 `adjust=False` 的递归形式。
- `DIF=EMA12-EMA26`，`DEA=EMA(DIF,9)`，中国看盘习惯的 `MACD柱=2×(DIF-DEA)`。
- RSI(6/12/24) 与 ATR14 使用 Wilder 平滑，即 `alpha=1/周期`；无下跌且有上涨时 RSI 为 100，完全不波动时为 50。
- KDJ 的 RSV 使用 9 周期最高最低，K、D 从 50 开始以 `alpha=1/3` 递归平滑，`J=3K-2D`。最高价等于最低价时 RSV 为 50。
- BOLL 中轨为 SMA20，标准差固定使用样本标准差 `ddof=1`，上下轨为 `MID±2σ`。
- 量比为当前成交量除以此前 5 根 K 线平均成交量，避免当前量进入分母；OBV 从 0 开始累计。

所有滚动窗口仅使用当前和过去数据。停牌日不会被补成零成交 K 线。

## 评分规则

总分范围 0～100，50 为中性，按以下权重合成：趋势 40%、动量 30%、量能 15%、波动/风险 15%。每个分项从 50 开始，仅在指标有效时加减分，最后分别截断到 0～100；缺失值只记录“样本不足，未计分”，不会被当作利多或利空。

### 趋势 40%

- 收盘价高于/低于 MA20、MA60：每项 `±7`；高于/低于 MA120：`±5`。
- MA20、MA60、MA120 多头/空头排列：`±8`。
- MA20、MA60 近 5 根变化超过 `±0.3%`：每项 `±4`。
- 最近 20 根的后半段高点与低点同时抬高/降低：`±6`。

### 动量 30%

- DIF 位于零轴上/下：`±6`；DIF 高于/低于 DEA：`±7`；最新一根刚发生金叉/死叉：额外 `±5`。
- MACD 柱连续 3 根增强/减弱：`±4`。
- RSI12 在 50～70：`+4`，30～50：`-3`，超买区：`-4`，超卖区：`+3`（同时给出风险说明）。
- 只有最近 30 根内两个已由左右各 3 根确认的摆动点，与 RSI12 出现明确反向且超过阈值时，才认定背离并 `±6`。

### 量能 15%

- 当前量达到 VOL_MA5/VOL_MA10 均值的 1.5 倍：上涨 `+12`，下跌 `-12`。
- 当前量不足均量 65%：`-3`，表示趋势确认不足，不直接解释为看多或看空。
- OBV 近 5 根变化超过 `±1%`：`±5`。

### 波动/风险 15%

- ATR% ≤ 1.5%：`+8`；1.5%～3%：不加减；3%～5%：`-8`；超过 5%：`-15`。

总分状态：`≥70 偏强趋势`、`58～69 震荡偏强`、`43～57 中性震荡`、`30～42 震荡偏弱`、`<30 偏弱趋势`。少于 20 根 K 线固定显示“数据不足”。状态描述不等同于买入或卖出信号。

## 可回测量化信号架构

量化管线严格分层为：

```text
Indicator → Factor → Market Regime → Setup → Signal
          → Order → Execution → Position → Triple Barrier → TradeRecord → Statistics
```

- `indicators.py` 只计算原始技术指标。
- `factors.py` 输出连续特征，例如价格相对均线的 ATR 距离、收益、斜率、量比、波动率分位、最大回撤和因果关键位距离。窗口不足或分母无效时保持 `NaN`。
- `regime.py` 确定性识别 `UPTREND`、`DOWNTREND`、`RANGE`、`HIGH_VOLATILITY`、`LOW_VOLATILITY` 或 `INSUFFICIENT_DATA`。
- `setups.py` 只定义 Trend Pullback、Breakout、Support Reversal、Trend Breakdown 四类结构，Setup 与收盘 Trigger 分开。
- `signals.py` 生成统一 `TradingSignal`；页面展示的 Signal Quality Score 是规则质量分，不是上涨概率。只有历史样本达到最低数量时才单独显示历史概率。
- `execution.py` 处理下一根成交、手续费、滑点、T+1 和不可成交数据状态；当前 OHLCV 无法可靠区分所有涨跌停成交状态，因此保留明确 warning，不伪造成交规则。
- `backtest.py` 生成完整 `TradeRecord`，`metrics.py` 计算 Expectancy、Profit Factor、回撤、累计/年化收益、Sharpe、MFE 和 MAE，并按 Regime 分组。
- `research.py` 提供 Factor 分桶、训练集参数扫描、连续时间切分和基础 Walk Forward；禁止随机 shuffle，也不把全历史最优参数直接当作生产参数。
- `wave/` 使用短/标准/宽三种尺度的右侧确认 Swing、ATR ZigZag 和硬规则输出 Top-N 候选，覆盖上涨与下跌推动浪、进行中/已完成推动浪及 ABC。Fib 只参与结构匹配度评分，该分数不是方向概率。K 线图仅连接匹配度最高候选的已确认 Pivot；进行中结构展示条件目标区与收盘失效位，已完成结构展示下一阶段反向观察区。图中用“确认后延续”“尝试失败后失效”和“确认前震荡等待”表达三类条件路径，同时保留水平目标带、确认位、失效位和随路径扩张的 ATR 不确定性走廊；折线节点及横向距离仅为结构示意，不预测具体价格或到达时间。历史同类情景采用逐根无未来回放，收盘确认当根不能倒推使用盘中目标触及；已决样本少于 30 次时不展示概率。
- `gann/` 默认从查询范围内最近的右侧确认高低点自动起算，而不是机械使用开始日期。江恩扇形采用 `ATR14/8 每根 K 线` 的明确归一化尺度，绘制 `2×1`、`1×1`、`1×2` 条件路径、邻近价格分割、时间观察窗、确认位和失效位；屏幕角度不代表固定 45°，周期窗口也不是精确反转日期。历史验证逐时点重建确认锚点，同根目标与失效按失效优先处理，已决样本少于 30 次时不展示概率。
- K 线图上方的“波浪理论”和“江恩理论”按钮独立控制整套算法 trace、shape 与 annotation；切换不会重新请求行情或重置 Plotly 缩放，自动刷新会保留图层开关状态。默认开启波浪图层、关闭江恩图层，以控制信息密度。

现有 0～100 分已明确命名为 `Market / Technical State Score`，继续用于描述市场技术状态；`Signal Quality Score` 与历史胜率、Expected R 分开展示，85 分绝不表示 85% 上涨概率。

### 无未来函数与成交约定

- 所有滚动值只使用当前与此前数据；突破阈值使用 `rolling(...).max().shift(1)`。
- Swing/Pivot 只有右侧确认窗口完成后才发布，历史关键位 Factor 按该发布时间逐根计算。
- 收盘信号默认最早按下一交易日开盘成交，可通过 `EXECUTION_ENTRY_PRICE=next_close` 改为下一交易日收盘成交；不会在信号当根收盘成交。
- Triple Barrier 从可卖出的第一根开始逐根检查 Upper、Lower、Time Barrier，绝不使用整个未来窗口最高/最低直接贴标签。
- 同一根 K 线同时触及 Stop 和 Target 时，由于 OHLC 无法还原日内先后，统一采用保守规则：**按 Stop/Loss 处理**。
- A股/ETF 默认启用 T+1，海外市场默认关闭；零成交量、价格缺失或没有下一根时订单不成交。

执行参数可通过 `.env` 配置：

```text
EXECUTION_ENTRY_PRICE=next_open
EXECUTION_COMMISSION_RATE=0.0003
EXECUTION_SLIPPAGE_BPS=5
EXECUTION_T_PLUS_ONE_CN=true
EXECUTION_MAX_HOLDING_BARS=20
EXECUTION_TARGET_R=2.0
EXECUTION_ATR_STOP=2.0
```

## 支撑阻力

左右各 4 根 K 线确认 swing high/low，只有右侧窗口完整后才确认。聚类宽度取 `max(现价×0.8%, ATR14×0.5)`；触碰次数、相对成交量和指数时间衰减共同评分，低于阈值的候选会被过滤。最多返回距离现价最近的 3 个支撑和 3 个阻力。阈值可通过环境变量调整。没有可靠候选时明确返回“未识别出可靠关键位”。

当最近支撑、阻力与止损/目标方向都有效时，页面会显示纯算法“参考情景”和潜在盈亏比；该情景不会在条件无效时硬生成。

## 缓存与稳定性

- SQLite 行情缓存键包含资产类型、代码、周期、复权、开始和结束日期；内容为 JSON 行记录，不使用 pickle。
- 分钟 K 默认 TTL 60 秒，日/周/月 K 默认 7200 秒，ETF 列表默认 21600 秒。前复权缓存到期后重新拉取完整请求区间，避免把复权历史永久固化。
- 上游历史行情接口每次最多快速尝试一次；失败后短时熔断并切换备用源，避免连续查询时反复等待。进程内信号量默认最多 2 个并发请求；腾讯备用源最多重试 2 次。
- 个股和 ETF 日/周/月线优先使用东方财富历史接口；连接失败或返回空数据时，自动降级到腾讯 `stock_zh_a_hist_tx`，并在页面明确标注。腾讯成交量会从“股”转换为“手”，换手率会从小数转换为百分比。
- 个股和 ETF 分钟线优先使用 AKShare 的东方财富分钟接口。首次失败后会短时熔断该接口并降级到新浪分钟行情，避免连续请求反复等待；新浪成交量从“股”转换为“手”。选择前/后复权时，分钟 OHLC 使用腾讯未复权/复权日线收盘价计算的因子调整，页面会同时标注分钟数据源和复权因子来源。不会用日线伪造分钟 K 线。
- 当上游暂时不可用时，日/周/月线最多可使用 24 小时内的同请求过期缓存，分钟线最多 5 分钟，并在页面给出明确提示。可通过 `STALE_CACHE_MAX_AGE` 调整日线最大陈旧时间。
- 统一运行日志写入 `logs/app.log`，默认单文件 5 MB、保留 5 个轮转文件。日志记录上游异常、备用源切换、熔断、陈旧缓存和 API 错误；Docker/群晖路径为 `/data/logs/app.log`。
- 页面始终显示数据来源、更新时间、缓存状态、证券识别方法和单位。成交量按 AKShare 东方财富接口通常口径显示为“手”，成交额为“元”。
- 美股与外盘品种列表缓存键独立于中国 ETF 列表；历史缓存键包含资产类型、规范代码、周期、复权与起止日期。外盘期货实时快照使用独立短 TTL，不会被日线长缓存永久带住。

## Docker 与群晖

构建并启动：

```bash
mkdir -p data/cache data/reports data/logs
docker compose up -d --build
docker compose ps
curl -f http://127.0.0.1:8000/health
```

镜像基于 `python:3.11-slim`，以非 root 用户运行，不包含 Token、Cookie 或代理。官方 Python 多架构基础镜像可在 x86_64 和 ARM64 Linux 上构建。

群晖 Container Manager 可在“项目”中新增项目，选择本目录的 `docker-compose.yml`。部署前在项目目录建立 `data/cache` 和 `data/reports`，确认 Container Manager 对其有读写权限；端口冲突时将 Compose 左侧的 `8000` 改为其他 NAS 端口。界面部署后检查容器健康状态，再访问 `http://NAS地址:8000`。命令行部署与普通 Linux 相同，需在含 Compose 文件的目录运行上述命令。

## 质量检查

```bash
ruff check .
pytest -q
python -c "from app.main import app; print(app.title)"
```

测试使用固定 DataFrame 和 mock AKShare，不依赖实时网络。
