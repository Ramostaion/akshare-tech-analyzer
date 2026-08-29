# 项目继续开发记录

更新日期：2026-08-29（Asia/Shanghai）

## 当前状态

- 项目版本：`0.2.0`
- 项目路径：`C:\Users\Elaina\Desktop\stock\akshare-tech-analyzer`
- 当前没有未完成的代码修改任务，最近一项“动态常用收藏与右键取消收藏”已经完成。
- 临时验证服务均已停止；正常启动端口仍为 `8000`。
- 当前目录没有 Git 元数据，无法通过 `git diff/status` 追踪改动。

## 已完成内容

### 基础平台

- FastAPI 工作台、JSON API、CLI、SQLite JSON 缓存、统一日志和单文件离线 HTML 报告。
- pandas/NumPy 指标、确定性趋势评分、支撑阻力聚类和 Plotly 多子图。
- Windows 自动环境启动脚本、Linux 启动脚本、Dockerfile 和 Compose 配置。
- Plotly 默认平移、绘图形状及 `Ctrl+Z` 撤销；桌面和移动端图表宽度问题已修复。

### 数据源与多市场

- 保留旧 `auto|stock|etf` 请求行为，并新增 `cn_stock`、`cn_etf`、`us_stock`、`us_index`、`global_future`。
- 美股通过 `stock_us_spot_em()` 代码表解析真实上游代码，不猜测市场前缀。
- 支持 `.IXIC/.NDX/.INX/.DJI` 美国指数，以及 `GC/SI/HG/CL/NG/OIL/XAU/XAG` 外盘期货。
- 期货使用连续参考序列，并单独获取短 TTL 快照；页面明确提示换月跳空风险。
- 元数据包含规范代码、上游代码、交易所、币种、时区、来源、能力、采集时间和单位。
- 中国市场红涨绿跌，海外市场绿涨红跌；缺少成交量时量能评分保持中性。

### 最近完成的 UI 工作

- “常用”列表不再写死任何证券，只读取浏览器 `localStorage`。
- 分析完成后可点击结果标题旁的 `☆/★` 添加或取消当前品种。
- 左键点击收藏项切换品种，悬停显示中文名称与市场。
- 右键收藏项显示自定义“取消收藏”菜单；点击空白、滚动、缩放、失焦或按 `Esc` 会关闭菜单。
- 首次使用显示“暂无收藏”，单个浏览器最多保存 30 项。
- `AGENTS.md` 已更新为当前多市场架构、测试边界和手动 UI 检查规则。

## 已执行验证

- `ruff check .`：通过。
- `pytest -q`：`51 passed`，仅有一条第三方 `StarletteDeprecationWarning`。
- FastAPI 导入、`/health`、首页和静态资源：通过。
- Playwright + 本机 Edge：1440px 桌面及 390px 移动端无重叠、无横向溢出、无控制台错误。
- 收藏浏览器验证：空列表、添加、刷新持久化、中文 tooltip、右键菜单和取消收藏均通过。
- 真实数据成功：`.IXIC`、`.NDX`、`.INX`、`GC`、`SI`、`CL`；期货快照成功。
- `docker compose config --quiet`：通过。

## 已知问题与外部限制

1. `AAPL`、`SPCX` 的真实验证未完成。本机代理访问 `72.push2.eastmoney.com` 时被远端断开；离线 mock 测试正常。不要把该代理错误判断为代码已失败或已成功。
2. 本机安装了 Docker CLI 和 Compose，但 Docker daemon 未启动，因此镜像尚未完成实际构建验证。
3. FastAPI TestClient 产生第三方 Starlette/httpx 弃用警告，不影响当前 51 项测试结果；升级相关依赖前需确认兼容性。
4. AKShare 上游可能发生限流、代理干扰或字段变化。自动化 pytest 必须继续使用 mock，真实网络只作为单独冒烟测试。
5. 收藏保存在当前浏览器和站点源的 `localStorage`，不会跨浏览器、主机或无痕会话同步。

## 下一步计划

1. 由用户在常用浏览器中验收星标收藏、悬停名称和右键取消操作。
2. 调整 VPN/代理直连策略后，重新真实验证 `stock_us_spot_em()`、`AAPL` 和 `SPCX`，并生成美股离线报告。
3. 启动 Docker Desktop/daemon 后执行 `docker build` 和 `docker compose up`，再检查容器 `/health`。
4. 为收藏交互增加不依赖行情网络的自动 Playwright 测试，覆盖损坏的 localStorage 数据和 30 项上限。
5. 若继续扩展市场，先更新 `models.py` 能力校验和 provider mock，再接入路由、图表与报告。

## 继续工作命令

```powershell
cd C:\Users\Elaina\Desktop\stock\akshare-tech-analyzer
.\启动平台.bat --check
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

前端布局修改后，在服务运行期间执行：

```powershell
.\.venv\Scripts\python.exe tests\ui_layout_check.py --url http://127.0.0.1:8000
```

所有结论仍须显示：仅为算法技术分析结果，不构成投资建议。
