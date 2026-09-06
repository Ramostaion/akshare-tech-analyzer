# Codex 修改提示词：优化现有江恩模块

请基于当前已经实现的江恩模块做“定向优化”，不要推倒重写，也不要改变现有波浪、威科夫、基础指标和图表功能。

当前江恩模块已经具备：
- Anchor
- ATR 标准化的 2×1 / 1×1 / 1×2
- Gann Price Levels
- Time Window
- Scenario
- Trigger / Confirmation / Invalidation
- 初步 Confluence
- 前端图层显示

本次目标不是继续增加更多江恩线，而是提升：
1. 稳定性
2. 可解释性
3. 共振质量
4. 前端简洁度
5. 无未来函数可回测性

---

# 一、P0：冻结江恩价格单位，避免 Fan 漂移

请检查当前 1×1 / 2×1 / 1×2 是否使用“实时 ATR”不断重算斜率。

如果当前逻辑类似：

```python
price_unit = current_atr14 * 0.25
```

请改为：

```python
price_unit = atr_at_anchor_confirmation * 0.25
```

即当 Anchor 被正式确认时，冻结：
- anchor_price
- anchor_time
- confirmed_at
- ATR(14)
- price_unit

在当前 Gann Fan 生命周期内，price_unit 不再随每日 ATR 改变。

只有在：
- Anchor 失效
- Anchor 被新高质量 Anchor 替换
- 用户主动重新计算

时，才允许生成新的 Fan。

必须避免历史 Fan 因后续 ATR 改变而“旋转”或漂移。

---

# 二、P0：明确 Anchor 生命周期

为 Anchor 增加完整状态：

```text
candidate
confirmed
active
invalidated
replaced
```

至少保存：

```text
pivot_time
confirmed_at
anchor_price
anchor_atr
anchor_score
direction
invalidated_at
replacement_anchor_id
```

要求：

回测中，只能从 confirmed_at 以后使用该 Anchor。

前端可以把 Anchor 画在真实 pivot 位置，但必须在 hover 中显示：

```text
Pivot Time
Confirmed At
Anchor Score
ATR at Confirmation
```

---

# 三、P0：Time Window 增加名称和评分

当前时间窗口前端存在多个半透明竖区，但用户难以知道分别是什么。

请为每个 Time Window 增加：

```text
cycle_ratio
center_bar
start_bar
end_bar
score
source_cycle
```

例如：

```text
T/2
T
1.5T
2T
```

前端顶部显示简洁标签。

Hover 显示：

```text
Gann Time Window
Base Cycle: 18 bars
Projection: 1.0T
Window: 17~20 bars
Score: 78
Source: median recent swing durations
```

---

# 四、P0：Time Window 必须评分过滤

不要所有 Time Window 都默认显示。

实现 TimeWindowScore。

建议来源：

```text
cycle_strength
multiple_cycle_overlap
historical_hit_rate
higher_timeframe_alignment
nearby_price_confluence
trend_context
```

前端规则：

```text
score >= 70
正常显示

55 <= score < 70
降低透明度

score < 55
默认隐藏
```

低分窗口仍可参与后台统计，但不要污染主图。

---

# 五、P0：Price Level 进行聚类和过滤

当前 Gann Price Levels 水平虚线较密。

请实现 Price Level clustering。

如果多个价格分割距离小于：

```text
0.15 ~ 0.25 ATR
```

则合并为一个区域：

```text
Gann Price Zone
```

例如原来：

```text
39.42
39.48
39.55
39.61
```

可以聚合成：

```text
39.44 ~ 39.60
```

并计算 PriceLevelStrength。

前端默认只显示 Top 2~3 strongest levels/zones。

其余仅参与 Confluence。

---

# 六、P0：重点实现 Price-Time Confluence Ranking

这是本次最重要的算法升级。

不要继续增加 4×1、8×1、1×4 等更多线。

请将重点放到 Price-Time Confluence Engine。

对每一个候选区域计算共振分数。

建议因素：

```text
Gann angle proximity        20
Gann time window            20
Gann price level            15
horizontal S/R              15
Fibonacci                   10
higher timeframe            10
momentum confirmation        5
volume confirmation          5
```

总分 100。

允许根据现有项目因子调整。

---

# 七、Confluence 应输出“区域”而不是单点

例如：

```text
Price Zone:
39.50 ~ 39.65

Time Window:
+6 ~ +9 bars

Confluence Score:
91
```

同时输出：

```text
support_or_resistance
dominant_factors
confidence
```

示例数据：

```json
{
  "price_low": 39.50,
  "price_high": 39.65,
  "time_start_bar": 6,
  "time_end_bar": 9,
  "score": 91,
  "type": "resistance",
  "factors": [
    "Gann 1x1",
    "Gann T window",
    "R1",
    "Fib extension"
  ]
}
```

---

# 八、Confluence 前端只突出 Top-N

默认只显示 Top 2~3 Confluence Zones。

建议：

```text
score >= 80
高亮

65 ~ 80
弱化

< 65
默认隐藏
```

---

# 九、Scenario 改为“围绕共振区生成”

当前 Scenario 已经有 Trigger / Confirmation / Invalidation。

请进一步让 Scenario 与 Confluence 强绑定。

不要只写：

```text
突破 1×1
```

而应尽量表达：

```text
突破 1×1
+
突破高强度 Price-Time Confluence Zone
```

示例：

### Scenario A：1×1 突破延续

```text
Trigger：
收盘突破 1×1

Confirmation：
连续 2 根 K 站稳
并突破 39.50~39.65 共振区

Target：
下一高分 Confluence Zone

Invalidation：
重新跌回 1×1 下方
```

### Scenario B：1×1 拒绝

```text
Trigger：
触及 1×1 / 高分共振区后收盘转弱

Target：
1×2 + 支撑共振区

Invalidation：
有效站稳 1×1
```

---

# 十、Scenario 前端视觉分级

主情景与备选情景不要同等视觉权重。

建议：

```text
Main Scenario
最粗
最清晰

Secondary Scenario
稍细
降低透明度

Low Confidence Scenario
默认隐藏或极淡
```

可以根据 confidence 映射：

```text
line_width
opacity
dash_style
```

---

# 十一、缩短未来 Gann 线显示长度

数学上可以继续计算远期 Gann Fan。

但前端不要无限延伸。

## 日线

建议：

```text
主要显示：
未来 10 ~ 15 bars

15 ~ 20 bars：
明显 fade

20 bars 以后：
不再显示完整角度线
```

远期只保留：

```text
Potential Price-Time Target Zone
```

## 周线

建议：

```text
主要显示：
4 ~ 6 bars

6 ~ 8 bars：
fade

8 bars 以后：
只显示结构目标区
```

---

# 十二、增加 horizon confidence decay

远期 Gann 结构应自动降权。

例如：

```text
0~5 bars:
1.00

6~10 bars:
0.85

11~15 bars:
0.65

16~20 bars:
0.45
```

定义：

```python
effective_score = raw_score * horizon_decay
```

Confluence 和 Scenario 都应该考虑 horizon decay。

---

# 十三、优化顶部图例

当前江恩图例过高、过密。

请把江恩图例分组。

主图默认只显示：

```text
◆ Anchor
━ 1×1
┄ 2×1 / 1×2
░ Time Window
▓ Confluence
```

详细项放到：

```text
江恩结构 ▾
```

展开面板：

```text
[✓] Anchor
[✓] Fan
[✓] Price Levels
[✓] Time Windows
[✓] Confluence
[✓] Scenarios
```

不要让所有内部计算项都常驻顶部。

---

# 十四、缩短 Hover Tooltip

当前 Hover Tooltip 信息过多，会遮挡行情。

主图 Hover 只显示关键数据：

```text
Date
1×1
1×2
Time Window
Confluence Score
Main Scenario
```

不要把完整 Trigger / Confirmation / Invalidation 全部塞进去。

详细内容移到独立 Gann Status Card。

---

# 十五、增加 Gann Status Card

建议在图右侧或图下方增加固定状态卡。

显示：

```text
GANN STATUS

Anchor
36.68

Anchor Score
84

ATR at Anchor
0.62

Price Unit
0.155 / bar

Structure
Above 1×2
Below 1×1

Main Scenario
Break 1×1

Trigger
Close > 39.62

Confirmation
2 bars above

Target
40.20~40.50

Time Window
+6~+9 bars

Invalidation
< 38.87

Top Confluence
Score 91
```

图负责看走势。

状态卡负责看结论。

---

# 十六、Price Levels 不需要全部可视化

后台可以计算完整 Gann division。

但前端只显示 Top 2~3。

其他分割继续用于：
- Confluence
- Scenario
- Backtest

不要因为“算法算出来了”就必须全部画出来。

---

# 十七、Time Window 不需要全部可视化

后台可以计算：

```text
0.5T
T
1.5T
2T
3T
```

前端默认只显示高评分窗口。

如果多个窗口重叠，合并为：

```text
Multi-cycle Time Window
```

并提高 score。

---

# 十八、增加 Multi-Timeframe Confluence

如果已有日线 / 周线 Gann：

请支持：

```text
Daily Gann
+
Weekly Gann
```

例如：

```text
Daily 1×1
+
Weekly 1×2
+
Weekly Time Window
```

则：

```text
Confluence Score ↑
```

不要简单把日线参数转换成周线。

日线和周线必须独立计算 Anchor、ATR、Fan 和 Time Cycle。

---

# 十九、回测必须验证 Confluence 是否真的有效

新增统计：

```text
Confluence score >= 80
```

时未来：

```text
1 bar
3 bars
5 bars
10 bars
20 bars
```

的：

```text
direction
MFE
MAE
target_hit_rate
invalidation_rate
```

并按 score 分桶：

```text
60~70
70~80
80~90
90+
```

检查：

```text
score 越高
是否历史表现真的更强
```

如果没有单调关系，需要重新调整评分权重。

---

# 二十、回测 Time Window

Time Window 必须和随机窗口比较。

统计 Gann Time Window 附近 ±N bars 发生以下事件的概率：

```text
local high
local low
breakout
volatility expansion
reversal
```

与 random windows 对比。

不能只展示成功案例。

---

# 二十一、Prediction Snapshot 不可被覆盖

每次生成：

```text
Anchor
Fan
Price Levels
Time Windows
Confluence
Scenario
```

都保存 snapshot。

后续市场更新后：

禁止修改过去 snapshot。

新的计算生成新的 snapshot。

这样才能真实回测：

```text
当时系统到底看到了什么
```

---

# 二十二、前端最终视觉优先级

必须遵循：

```text
真实 K 线
>
当前 Gann 结构
>
高分 Confluence
>
主 Scenario
>
Time Window
>
备选 Scenario
>
低分 Price Levels
```

不能出现预测线比真实价格更抢眼。

---

# 二十三、不要做的事情

本次优化禁止：

1. 不要增加更多无必要 Gann Angle
2. 不要把全部 Price Levels 都画出来
3. 不要把全部 Time Windows 都画出来
4. 不要继续增大 tooltip
5. 不要让 ATR 每天改变历史 Fan 斜率
6. 不要用未来 pivot
7. 不要移动历史 Anchor 来拟合行情
8. 不要把远期 angle 当精确目标
9. 不要未经回测就把 score 写成真实概率
10. 不要重写整个项目
11. 不要破坏现有 Elliott / Wyckoff / Indicators

---

# 二十四、修改顺序

请按下面顺序执行。

## Phase 1
检查当前 Gann 实现：

- ATR 是否冻结
- Anchor 生命周期
- Time Window 来源
- Price Level 数量
- Confluence 当前评分
- Scenario 生成方式
- 是否存在 repaint

先输出分析。

## Phase 2
修复：

```text
Anchor ATR freeze
Anchor lifecycle
confirmed_at
snapshot
```

## Phase 3
实现：

```text
Time Window Score
Price Level clustering
Price Level Strength
```

## Phase 4
升级：

```text
Price-Time Confluence Ranking
Top-N selection
multi-factor explanation
```

## Phase 5
让 Scenario 围绕高分 Confluence 生成。

## Phase 6
加入：

```text
horizon decay
daily / weekly frontend cap
```

## Phase 7
优化前端：

```text
legend
tooltip
Gann Status Card
Top-N visualization
```

## Phase 8
补充：

```text
backtest
score bucket evaluation
random baseline
```

---

# 二十五、验收标准

完成后至少满足：

1. ATR Unit 在 Anchor 确认时冻结
2. 历史 Fan 不随当前 ATR 漂移
3. Anchor 有生命周期
4. Anchor 保存 confirmed_at
5. Time Window 有明确 T / 1.5T 等标签
6. Time Window 有 score
7. 低分 Time Window 默认隐藏
8. Price Levels 可以聚类
9. 默认只显示 Top 2~3 Price Zones
10. 有 Price-Time Confluence Score
11. 默认只突出 Top 2~3 Confluence Zones
12. Scenario 与高分共振区关联
13. 日线远期角度线不会无限延伸
14. 周线远期角度线不会无限延伸
15. 有 horizon decay
16. 顶部图例明显精简
17. Hover 不再遮挡大面积行情
18. 有独立 Gann Status Card
19. 历史 snapshot 不会被未来重算覆盖
20. Confluence 有历史回测
21. Time Window 与随机 baseline 对比
22. 原有功能不被破坏
23. 所有新增核心逻辑有测试

---

# 二十六、最终目标

不要把江恩模块继续做成：

```text
越来越多的线
+
越来越多的窗口
+
越来越大的 tooltip
```

最终应变成：

```text
稳定 Anchor
+
标准化 Gann Fan
+
少量高质量 Time Window
+
少量高质量 Price Zone
+
Price-Time Confluence Ranking
+
条件 Scenario
+
Trigger / Target / Invalidation
+
可验证历史统计
```

核心思想：

> 后台可以算很多，前端只展示最有决策价值的结果。

请先分析当前实现，再按 Phase 1 → Phase 8 渐进式修改。
