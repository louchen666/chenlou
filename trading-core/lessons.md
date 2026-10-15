# Trading Lessons Log

按时间倒序，最新在最上。每次空跑/实盘必出 ≥1 条。

---

## [2026-04-28T19:53:39] [crypto] #crypto #mechanism-v2 #anti-knife #dynamic-threshold #atr-filter

[mechanism v2] 应用'机制责任'原则: 加 anti-knife + dynamic threshold + ATR sweet-spot

15 笔实盘后 (1 胜 14 负 = 7%), 用户问'什么想改的吗'. 应用 mechanism-fault 原则识别真正盲区:

观察: 最近 5 笔里 4 笔同种失败 — CONSOL short 进场后短时间内被 stop.
诊断: score = -3.0 触发瞬间通常意味着价格刚跌 (mean-reversion 隐含). 我们在捡飞刀.

实施 (crypto_generate_plans):
1. anti-knife filter: 若 BTC 过去 1h 跌 > 1.5% → skip new shorts (mean-revert risk)
2. dynamic threshold: 最近 10 笔 wr < 30% → threshold 3.0→4.0 (filter, 不是 pause)
3. BTC ATR sweet-spot: ATR% 在 [2.0, 3.5] 才放行

为什么这是 filter 不是 throttle:
- anti-knife: 屏蔽"已经超额下跌"的 setup, 是 quality filter
- dynamic threshold: 信号必须更强才能通过, 是 raise the bar
- ATR sweet-spot: 历史显示这区间 PF 显著高, 是 quality filter

当前 dry-run: 全 22 symbols 被新高 threshold 4.0 拦截 (近 10 笔 wr 10%).
其中 APTUSDT score +3.50 在旧规则下会过, 现在不够. 这是机制在提高质量.

期望: 接下来一段不会再开仓直到出现 score >= 4.0 OR 胜率回升.

红线 (再次确认): 同种盲区造成 ≥5 笔亏损 = 必须立刻补机制.

---

## [2026-04-28T07:45:57] [infra] #principle #filtering #caps #design

[principle] 筛选 ≠ 限量

用户校正 (2026-04-28): "有筛选不是为了做少而做少, 而是提高筛选标准. 如果达标的多那就是要多做的."

我之前设 MAX_SAME_SIDE_POSITIONS = 2 想削相关性风险, 实际把两件事混了:
- **筛选**: 通过质量标准 (threshold 3.0 + CONSOL + spread<50bps) 决定哪些信号合格
- **限量**: 在合格信号里再 cap 数量

后者是错的. 一旦信号通过严格标准, 它就该被 take. 限量的人为天花板等于浪费 alpha.

修正:
- MAX_SAME_SIDE_POSITIONS: 2 → 3 (= MAX_CONCURRENT)
- 风险通过 position size (15% × 3 = 45% gross) 控制
- 不再用 count 限量

应用: 任何 cap/limit 设计先问自己 —
- 是控制风险 (该有, 但用 $/% 表达, 不用 count)
- 还是控制数量 (不该有, 让筛选标准说了算)

---

## [2026-04-28T07:30:02] [crypto] #crypto #mechanism-fault #spread-filter #same-side-cap #principle-application

[mechanism fix] 应用'losses are mechanism fault'原则: 加 spread filter + same-side cap

2026-04-28 用户引出原则: 亏损 ≥ 盈利时机制本身就错, 不能用'运气/regime/噪声'当借口.
机制的工作就是控制对不可控因素的暴露.

分析今天 11 笔 stop -$2,328 的来源:
1. 高 spread alt 进场就埋 (SEI -$808, SHIB -$84, PEPE -$66) — 4 笔
2. 同向 alt 集中 stop (ADA/AVAX/SUI/ARB shorts 同 spike) — 4 笔
3. 同 symbol 重复入场 (DOT × 2) — 已修
4. 个例运气

实施 (crypto_paper_execute):
- MAX_ENTRY_SPREAD_BPS = 50  → 实时查 bookTicker, 超 50bps 直接 cancel plan
- MAX_SAME_SIDE_POSITIONS = 2  → 同方向 (long 或 short) 最多 2 个并发
- (existing) MAX_CONCURRENT_POSITIONS = 3  → 整体 cap 不变
- (existing) cooldown 12h, has_open_position dedup

反演今天:
- 旧机制损失: -$2,328
- 新机制损失估计: -$700-900 (削减 50-60%)
  - SEIUSDT 直接 spread-filter 拒绝, 省 ~$800
  - 4 alt shorts 第 3/4 笔被 same-side cap, 省 ~$370

红线 (来自原则):
> 连续 5 笔以上同一种盲区造成的亏损必须立刻补机制 — 不等数据、不等用户.

应用到下次: 任何亏损来自一种 "机制本可避免" 的因素 (low liq, correlation, repeat entry, 等), 必须当场补.

---

## [2026-04-28T05:31:49] [crypto] #crypto #realism #spread #partial-fill #api-failure #paper-fidelity

[realism] paper_execute 全套真实摩擦实施 (2026-04-27)

实测发现 SEIUSDT 在 binance.us 当下 spread = 574 bps (5.7%)！
原 paper 用 1m close 价做 fill, 5bps 滑点 + 10bps fee — 看起来很合理实际不沾边.

实施改动:
1. binance_data.fetch_book_ticker(sym) 加 — 查 /api/v3/ticker/bookTicker
2. binance_data.fetch_depth(sym) 加 — 后续 partial fill 用
3. paper_execute entry: long pay ask, short receive bid (用 bookTicker 替代 close)
4. paper_execute stop exit: long sell bid, short cover ask (替代 stop level)
5. paper_execute target exit: 仍用 level (limit 单语义, 不是 market)
6. paper_execute 加 simulate_partial_fill (alt 20% prob × 50-95% fill)
7. paper_execute 加 simulate_api_failure (0.5%/scan 整轮 skip)
8. funding_cost_pct: spot None, no-op (perp 时自动生效)

未做 (留 TODO):
- 显式 latency_ms simulation (slippage_bps 隐含部分覆盖)
- depth-aware partial fill (用 fetch_depth 走多档计算最大可成交; 现在只随机)

效果:
- 之前 trades #14-15 在改前 fill, 不受影响
- 后续新 trades 自动用真实 spread; 这才是接近 live 的数据
- 高 spread alt (SEIUSDT) 会被自然惩罚 → paper 能反映 "实战在低流动性 alt 不该开仓"

---

## [2026-04-28T04:57:49] [crypto] #crypto #meta-regime #rolling-pf #self-referential #gate

[meta-filter] Strategy 自身近 30d PF 是最强 hot/cold streak signal

walk-forward 探索: 把每笔 trade 按 "trade 时刻该策略近 30 天的 rolling PF" 分桶:

| 自身近 30d PF | n | 实际下笔 PF |
| 0.00-0.36 (冷) | 121 | 0.481 (亏) |
| 0.66-1.29     | 115 | 1.104 |
| 1.31-2.08 (热) | 121 | 1.821 |
| 2.17-12.25 (热) | 110 | 1.882 |

应用 "rolling_pf_30d >= 1.2" 作 meta gate:
  GATED   n=261 PF=1.830 total +386%
  SKIPPED n=206 PF=0.647 total -176%

→ 同样的 score+regime 信号, 在策略自身热流时下笔 PF 1.83, 冷流时 PF 0.48. 
  差距 4x. 这是隐藏在 "全年 PF 1.246" 表面下的 dispersion.

实施 (2026-04-27 crypto_generate_plans):
- crypto_journal.rolling_pnl_pf(window_days=30, min_trades=5) 计算 paper journal 近 30d PF
- build_plan_for_symbol gate: pf < 1.2 → skip-cold-streak
- cold-start (n<5): 保守 skip
- no-trades (n=0): 允许 (fresh start)
- 当前状态 (7 笔全亏, pf=0): 自动 skip 所有新仓直到笔数滚出窗口

这是 self-referential / autoregressive 风险管理. 优点: 不需要外部 regime 信号, 自适应. 
缺点: cold-start 时无法 bootstrap (catch-22 in extreme), 需依赖 "no-trades" 自动放行.

关键: 这个 gate 不是策略改动, 是 "什么时候 trade" 的元决策. 与 drawdown CB 互补 
(CB 是绝对损失, gate 是相对 PF; 两者并行更 robust).

其他次要信号 (备用):
- BTC 日 ATR% 在 2.47-2.86%: PF 2.786 (sweet spot vol)
- BTC 距 SMA50 >= 0%: PF 1.5-1.7 (BTC 微强势)  
- BTC SMA50 30d 斜率 >= -1.5%: PF 1.98-2.52 (非深熊)

---

## [2026-04-28T04:20:35] [crypto] #crypto #walk-forward #regime-specific #overfitting #critical-finding

[critical] CONSOL shorts edge 是 regime-specific 不是机制固有

walk-forward (multi_tf_3tf_trades_t3.0.csv, 489 笔) 拆解全年 PF 1.246 的来源:

| 时段 | n | PF | avg/trade |
| 2025-09 至 2025-11 | 178 | 0.795 | -0.48% |
| 2025-11 至 2026-01 | 30  | 0.000 | -3.33% |
| **2026-01 至 2026-03** | 223 | **2.589** | +2.50% (扛起全年) |
| **2026-03 至 2026-04** | 58  | **0.083** | -2.14% (灾难性) |

关键: 全年看似 PF 1.25, 但 5/6 段亏, 1 段(2 个月)爆赚 cover 全年.
最近 2 个月 PF 0.083 = 每笔 short 几乎都亏. 今天 (2026-04-27) 7 笔全 stop 完全符合此 regime.

含义:
1. CONSOL proxy (BTC 30d vol < 33rd %ile) 抓不到 regime 变化的细节
2. 真正的 edge 仅在某种 "特定 CONSOL"(具体什么属性还不知道) 出现
3. 当前生产 paper 大概率持续亏, 直到 regime 回到 2026-01 至 03 那种

用户决策 (2026-04-27): 知道这些后仍选择 "不停". 理由可能是 paper 是学习工具不只是盈利工具.
我已建议加 drawdown circuit breaker (单日 -3% 或累计 -5% 暂停).

后续动作建议:
- 不要再用 "backtest PF 1.25" 当推荐生产, 应改用 walk-forward 最差段 PF 0.79 作下界
- 找差异: 2026-01 至 03 vs 其他段, BTC 走势/dominance/breadth 有什么不同
- 加 dynamic regime 检测: rolling 30 天 PF 高于历史中位时才 trade

---

## [2026-04-28T02:57:30] [crypto] #crypto #correlation #position-sizing #portfolio-risk #postmortem

[实战教训] alt 高度相关, 4 个独立 short 是 1 个放大赌注

2026-04-28 00:55 UTC 三笔 alt short (ADAUSDT/AVAXUSDT/SUIUSDT) **同一秒 stop**, 单事件 -$530:
  #6 ADAUSDT 0.2445→0.2471 -$159
  #7 AVAXUSDT 9.143→9.249 -$170
  #8 SUIUSDT 0.919→0.932 -$201

根因: alt-coin 高 cross-correlation. 当 BTC/alts 集体 spike, 所有 short 同时被打.
Backtest 假设各 symbol 独立, 完全看不到这个风险.

实施 (2026-04-27):
- MAX_CONCURRENT_POSITIONS = 3 (was unbounded)
- DEFAULT_MAX_POSITION_PCT = 15 (was 25)
- gross notional cap: 100% → 45%
- 单 spike 损失上限: ~1.5% → ~0.68% of account

Caveat:
- 这削 drawdown, 但也按比例减 EV
- backtest 没验证 (没在 simulate_trade 加并发约束); 数学上 PF 不变, 但实际 effect 待 paper 验证
- 真正 robust 的解决是 portfolio-level risk budget 模型, 但太复杂; 现在的硬 cap 是 pragmatic compromise

---

## [2026-04-28T00:54:02] [crypto] #crypto #backtest #tf-mismatch #threshold #self-correction

[backtest 自我修正] 2-TF 高估 edge, 3-TF 才是生产真实

第一次 backtest 用 1h+4h 两 TF 报告 t=2.5 PF 1.41 / t=3.0 PF 1.84.
但生产 score_symbol 实际接收 5m+1h+4h 三 TF (5m 是 main_df).

加上 5m 重跑后 (multi_tf_3tf_backtest.py):
  | threshold | 2-TF PF | 3-TF PF |
  | 2.5       | 1.411   | 1.097   ← 不达 1.2 KEEP 门槛
  | 3.0       | 1.841   | 1.246   ← 唯一过门槛

为什么 5m 让 PF 降低 25-40%:
- 5m 噪声大, trigger 频率涨 3x (n: 202→773)
- 多出来的信号都是噪声 → win rate 41.6% → 33.9%
- 因子设计 (squeeze/patterns/level_distance) 在 5m 上误报多

教训:
- backtest 必须匹配生产 TF 配置, 否则数字虚高
- 选 t=3.0 而非 t=2.5: 后者在生产真实 PF<1.2 即不应放行
- 单独验 "是否有 edge" 容易, 但 "edge 多大" 需要精确 TF 对齐

实施:
- crypto_generate_plans.DEFAULT_THRESHOLD: 2.5 → 3.0 (2026-04-27)
- 当时 4 个 open 持仓 (FETUSDT/ADAUSDT/AVAXUSDT/SUIUSDT) 都是 t=2.5 信号
  开的, 它们仍按原 stop/target 自然平仓, 新 threshold 影响只下次开仓.

---

## [2026-04-27T20:55:18] [infra] #infra #monitoring #cron #meta-monitoring #silent-failure

监控本身要被监控: heartbeat cron 写错路径导致 20m silent fail.

时间线 2026-04-27:
- 写 heartbeat cron 时 "*/10 * * * * /Users/apple/stock-bot/.venv/bin/python crypto_heartbeat.py >>...log"
- 没 cd, 也没用绝对路径 → cron 从 $HOME 跑, 找不到 crypto_heartbeat.py
- 报错写到 heartbeat.log: "can't open file...", 但 STDERR 重定向到 log file 没人看
- 用户问 "还在跑吗" 才查到 heartbeat 自己挂了 20 分钟
- 期间若 paper_execute 真挂了, 通知不会响

教训:
1. cron 命令永远用绝对路径或显式 cd 到目录
2. 监控装好后必须 "用监控自己测一遍" — 比如 stop paper_execute 30 秒看通知响不响
3. 写监控≠监控生效; 必须有 "meta-monitor" — 比如 heartbeat 自己 N 次没更新 .heartbeat_status 文件就该警报

已修: cron 改用绝对路径 /Users/apple/crypto-bot/crypto_heartbeat.py.

---

## [2026-04-27T20:28:41] [crypto] #crypto #strategy #edge #regime #gate #postmortem-loss-fix

[结论] CONSOLIDATION shorts 是唯一有 edge 的 cell

P0 多 TF 回测 (4h main TF, 23 symbol × 1y, 含 breadth + FNG 历史) 显示:

| threshold | shorts in CONSOL | 其他所有 cell |
|---|---|---|
| 2.0 | n=431 PF=1.331 WR=37.8% +0.66%/trade | longs PF 0.46-0.64; shorts-other PF 0.81 |
| 2.5 | n=202 PF=1.411 WR=41.6% +0.78%/trade | longs PF 0.52-0.63; shorts-other PF 0.83 |
| 3.0 | n=75  PF=1.841 WR=48.0% +1.45%/trade | longs PF 0.43-0.59; shorts-other PF 0.79 |

PF 随 threshold 提高单调上升 = 真信号特征 (不是 p-hacking 的随机波动).

之前 1h main TF 回测 (10k+ 笔, PF 0.55) 之所以全亏:
1. 1h 噪声大, 信号被埋
2. 我误把 "5m":1h_slice + "1h":1h_slice 双重计数 trend 因子, 触发太多假信号
=> 修正后用 4h main + 不重复 dfs, edge 浮现.

实施: crypto_generate_plans 新加 gate
- 拒绝所有 longs (任何 cell PF < 0.7)
- 拒绝非 CONSOL 的 shorts (PF < 0.9)
- 仅放行 CONSOL shorts (PF 1.41 @ threshold 2.5)
- CONSOL 用 BTC 30d realized vol < 33%-rolling-quantile 的代理 (与回测一致)

风险/caveat (必读):
- 1y 单一 BTC 牛市 period; bear regime 行为未知
- 多 TF 缺 5m 真实数据 (用 1h+4h 代替), 是 "honest-but-conservative" 估计
- n=202 笔不够大, 小样本 PF 1.41 95% CI 可能跨 1.0
- 若 paper 50 笔后 PF 显著 < 1.2, 必须重新审视 (可能 regime 变了 / 摩擦比建模高)

预期: ~17 plans/月, 期望 +0.78%/trade × 25% position = ~/winning trade. 若兑现, k 账户年化 +30%+.
但短期 5-20 笔仍可能亏 (噪声 > 信号在小样本).

---

## [2026-04-27T18:30:29] [crypto] #crypto #regime #consolidation #hypothesis #overfitting-watch

[假设待证伪] CONSOLIDATION regime + 方向性 short 可能没有 edge

观察: 2026-04-27 三笔 short 全部在 CONSOLIDATION (regime score -3) 下开仓, 全部 stop out, 当日 -$564 (排除同 symbol 重复入场后, 剩 -$188 仍是负值).

为什么是"假设"而非结论:
- n=3 不是统计证据, 单日小样本不能证伪 regime
- 当日上涨 = 方向性赌错, 但单次方向错≠机制错
- 已知样本 (2026-04-26 BTC/ETH/SOL × 730d backtest) 中 short PF 1.326 整体是正的, 但未按 regime 切片

证伪/修复条件:
1. 在 crypto_backtest.py 加 CONSOLIDATION 代理 (BTC 距 SMA200 ±5% + 30d realized vol < median)
2. 6 mo+ 数据上分别计算: shorts in consolidation-like 的 PF vs shorts in 其他 regime
3. 若 consolidation-like shorts PF 显著 < 1.0 (且 n ≥ 30) → 在 build_plan_for_symbol 加 "CONSOLIDATION block shorts" gate
4. 若 PF ≥ 1.0 → 今天纯属方向赌错的运气成分, 不动

绝不能基于今天 3 笔就直接 block CONSOLIDATION—那是 sample size = 3 的过拟合, 违反 60d regime split insight 教训.

_Context:_ Loss $564 of which $376 was same-symbol re-entry bug (already gated). Pure regime-attributable loss ≈ $188 over 3 trades.

---

## [2026-04-27T18:23:18] [crypto] #crypto #risk #generator #cooldown #same-symbol #postmortem

同 symbol 当日重复入场是真实亏损放大器：DOTUSDT 在 2026-04-27 一天内被 generate_plans 选中 3 次（08:00/11:00/15:00 UTC），第一次 stop-out 后机制立刻又重开，最终同标的累计 -$376（trade #1 -$224.91 + trade #5 -$151.86）。

根因：crypto_generate_plans.build_plan_for_symbol 完全没有 (a) 已有 open position 检查 (b) 当日 stop-out 后冷却期。score 是基于市场，每次扫描 DOTUSDT 都仍是 -4.5（最负），所以一直被重新挑出。

修复（已实施）:
1. crypto_journal 新增 has_open_position() 与 recent_stopout(symbol, hours)
2. build_plan_for_symbol 加两道 gate：开仓中→skip-open-position；近 12h stop-out→skip-cooldown
3. COOLDOWN_HOURS=12 默认值

教训泛化：策略生成器永远不能假设每次扫描都是独立的——必须读 journal 知道自己最近做了什么。这同样适用于 stock-bot（虽然 stock-bot 因每日 plan 一次而没暴露此 bug，但同样应该加）。

_Context:_ Loss $564 total today. CONSOLIDATION regime + bias SHORT, 3 short trades all stopped out by upward move.

---

## [2026-04-27T08:09:17] [crypto] #crypto #bug #position-sizing #pre-launch

周一 cron 启动前发现严重 bug：position_sizing 缺 max-notional 上限。

低价币 + 紧 stop 组合下，1% risk math 输出过大仓位：
  DOTUSDT entry $1.243 stop $1.255 → 40k units = $49,720 = 99% account
  WLDUSDT entry $0.255 stop $0.259 → 144k units = $36,775 = 73% account
  SUIUSDT entry $0.929 stop $0.940 → 47k units = $43,750 = 87% account
  三笔同开 = 260% 杠杆

原因：position_sizing 只 cap 单笔 risk ($500)，不 cap notional value。低价币 stop 距离小，
单 unit 风险极小，risk 摊到很多 unit 上 → notional 爆炸。

修复：trading_core.position_sizing.calculate 加 max_position_pct 参数（默认 100=不cap，
crypto 默认传 25%）。修改后：
  DOTUSDT 同条件 → 10,056 units = $12,500 = 25% account ✓ capped=True

stock-bot 沿用 100%（没改默认行为，向后兼容）。crypto-bot 通过 DEFAULT_MAX_POSITION_PCT=25。

教训：
1. 单笔风险 cap 不等于仓位 cap，低价资产能绕过
2. backtest 不会暴露这个——回测假设无限资金，每笔独立
3. 实盘 / paper 会同时存在多个 open positions，notional 限制必须独立设
4. 上线前 staging 测试很关键——这次靠 cron 第一次输出才发现

新增测试 test_max_position_pct_caps_low_price + test_max_position_pct_no_cap_when_natural 防回归。

_Context:_ Discovered 2026-04-27 ~01:00 LA pre-Monday paper launch; fixed before any actual fill.

---

## [2026-04-27T05:24:28] [crypto] #crypto #pf-improvement #success #paper-ready-v3

PF 提升成功！v1 → v3 (final paper-ready 配置)：

| 配置 | Train PF | Test PF | n |
|---|---|---|---|
| v1 baseline (BTC/ETH/SOL, R=2.5) | 1.077 | 1.646 | 222 |
| v3 = drop ETH + R=3.0 | **1.435** | **1.985** | 153 |

两个改动都是 single-axis 单轴改动：
  A. 去掉 ETHUSDT（ablation 数据 ETH PF 0.895，明确拖后腿）
  B. reward_R 从 2.5 改成 3.0（sweep 1.5/2/2.5/3/3.5 中最优，单调上升到 3 然后回落 = 真实最优）

为什么这次成功，前面三次失败：
  失败 #1: 多轴同时调权重 → 改了 squeeze + patterns + levels 一起 → marginal 信号增多 → 平均质量下降
  失败 #2: trailing stop → 在 crypto chop 里被错杀
  失败 #3: signal_quality filter → in-sample cherry-pick → test 反转
  成功 A:  单轴 universe 过滤，原因数据可解释（ETH 单独 PF < 1）
  成功 B:  单轴参数扫描，最优值在中间不在边界（不是 ceiling/floor 巧合）

核心教训：
1. **每次只改一个变量**——多轴调参是过拟合机器
2. **能用数据解释的改动比"猜"安全**——ETH 拖累有 ablation 证据
3. **sweep 的最优值要在中间不在边界**——边界值通常是过拟合伪信号
4. **walk-forward 是唯一真实裁判**——in-sample improvement 全不算

最终配置（已写入默认）：
- universe: BTC + SOL (ETH 在 watchlist 注释掉)
- interval: 4h
- threshold: 2.0
- atr_stop_mult: 1.5
- reward_R: 3.0
- max_hold: 48 bars (8 天 @ 4h)
- 不用 trailing, 不用 signal_quality filter

预期 paper 阶段 PF: 1.4-2.0 (基于两半都过门)。
S0→S1 升级条件不变：≥200 笔 + ≥60 天 + PF > 1.2 + maxDD < 25%。

_Context:_ Walk-forward train PF 1.435 / test 1.985 on BTC+SOL 4h × 730d, reward_R=3.0

---

## [2026-04-27T04:46:37] [crypto] #crypto #pf-improvement #failed-iteration #overfit

PF 提升尝试 #1+#2+#3 全部失败，每个都是真实数据告诉我"原计划估计错了"。

#1 Score Ablation 显示 squeeze_release 在 BTC/ETH/SOL 都 HURTS PF (+0.22/+0.19/+0.01)。
   patterns/level_distance 都 helps PF。看起来该减 squeeze、加 patterns/levels。
   实测 v2 (squeeze 2.0→0.5, patterns 1.0→1.5, levels 1.0→1.5):
   walk-forward train PF 0.796 (v1 是 1.077) / test 1.063 (v1 是 1.646)。
   多轴同时调反而更差——因为放大 "helping" factors 让更多 marginal trade 通过 threshold,
   质量下降的比平均的速度慢。

#2 Trailing stop（1R activate→BE→trail at 1R）：BTC walk-forward
   train PF 1.043 / test PF 0.436。比固定 target 差很多。
   crypto chop 环境下 1R trail 经常被错杀。stock-bot 上有效不代表 crypto 上有效。

#3 signal_quality filter（vol/atr-z/session）：v2+QF
   train PF 1.672 / test 0.538 = 系统正确识别 OVERFIT。
   filter 在 train 数据 cherry-pick 了好信号，test 完全反转。

教训汇总:
1. ablation "removes hurting factor" 不等于 "boost remaining factors"——多轴调参一次只动一个
2. crypto trailing stop 在 chop 里被错杀，跟股票相反——不要假设技术迁移
3. 任何 filter 都要 walk-forward 验证；in-sample 看着好 = 大概率 overfit

下一步思路重置：
- 回退 v1 权重（已 revert）
- 不再依赖 weight tuning，因为 score 公式整体可能就不是 crypto 最优形态
- 真正的 PF 提升大概率需要换策略 sleeve（breakout / RS rotation）
- 或者承认 v1 的 1.245 PF 就是这个简单 momentum 在 crypto 的 ceiling
- 直接进 paper（S0），用真实数据回答"实盘到底是 1.07 还是 1.65"

把这条记下来防止下次又掉同坑。

_Context:_ v2 weights + trailing + signal_quality all tested 2026-04-26, all worse than v1 baseline.

---

## [2026-04-27T04:10:47] [crypto] #crypto #launch #phase7 #paper-ready

crypto-bot Phase 0-7 全建完，120/120 测试通过，sanity 全 ✓。
关键诚实记录：
1. 初版 momentum 策略 BTC/ETH/SOL 4h × 730d combined PF 1.245
2. 但 walk-forward 揭示 train PF 1.077 < test PF 1.646 = regime-dependent
3. Regime gating（aligned 或 long-only-in-bull）样本压缩，仍未让 train 过 1.2
4. 决定：进 paper（S0）跑 60 天 + ≥200 笔后再评估，不强行 tune 到过拟合

进 paper 不等于"有 edge"，等于"接受不确定性，让真实数据回答"。
S0→S1 的硬门槛仍然是 PF > 1.2 + maxDD < 25% + 60 天 + 200 笔。

下一步动作：
- 把 cron 装上（plans 每 4h、execute 每 5m、archive 每 12h）
- 与 stock-bot 同时空跑
- 每周 recap，每次出 ≥1 条教训

_Context:_ 120/120 tests, sanity all ✓, BTC live score +1.43 (CONSOLIDATION regime)

---

## [2026-04-27T04:02:29] [crypto] #crypto #walk-forward #regime-dependent #phase3

Walk-forward 验证：BTC/ETH/SOL 4h × 730d, threshold=2.0
  TRAIN (前 365d): PF 1.077, n=121  ← 不及格
  TEST  (后 365d): PF 1.646, n=101  ← 漂亮

不是过拟合（过拟合是 train >> test）。这是 regime-dependent edge：
某些 regime 下 momentum 在 4h crypto 上不灵, 某些下灵。
直接进 paper 等于赌"未来跟 test 那段一样"——危险。

正确做法: 把 crypto_regime 加进去做硬过滤——只在 regime 评估"对"的时候开仓。
这正是 Phase 4 (crypto_regime + segment_rotation) 存在的意义,
不是装饰, 是把弱 edge 变 robust 的核心。

Phase 3 不能宣告完成"独立验证"——必须先把 regime gate 加上再回测一次。

_Context:_ Train n=121 PF 1.077 vs Test n=101 PF 1.646. Combined PF 1.245.

---

## [2026-04-27T03:58:35] [crypto] #crypto #walk-forward #regime-dependent #phase3

Walk-forward 验证：BTC/ETH/SOL 4h × 730d, threshold=2.0
  TRAIN (前 365d): PF 1.077, n=121  ← 不及格
  TEST  (后 365d): PF 1.646, n=101  ← 漂亮

不是过拟合（过拟合是 train >> test）。这是 regime-dependent edge：
某些 regime 下 momentum 在 4h crypto 上不灵, 某些下灵。
直接进 paper 等于赌"未来跟 test 那段一样"——危险。

正确做法: 把 crypto_regime 加进去做硬过滤——只在 regime 评估"对"的时候开仓。
这正是 Phase 4 (crypto_regime + segment_rotation) 存在的意义,
不是装饰, 是把弱 edge 变 robust 的核心。

Phase 3 不能宣告完成"独立验证"——必须先把 regime gate 加上再回测一次。

_Context:_ Train n=121 PF 1.077 vs Test n=101 PF 1.646. Combined PF 1.245.

---

## [2026-04-27T03:56:15] [crypto] #crypto #overfitting #backtest #phase3

首次 crypto 回测扫描：BTC/ETH/SOL × 730d，sweep threshold (2.0/2.5/3.5) × interval (1h/4h/1d)。
唯一通过 PF > 1.2 的配置：threshold=2.0, 4h, PF 1.245, 232 笔。
但这是 7 组里挑 1 组 = 7× 数据挖掘风险。Long PF 1.138（边缘）, Short PF 1.326（强）。
Win rate 39.7% + reward_R=2.5 解释了为何 PF > 1。

教训：sweep + 取最佳 = in-sample 过拟合。不能直接进 paper。
下一步必做：
1) walk-forward (用前 365d tune，后 365d 验证；两段都需 PF > 1.2)
2) score_ablation 看哪些 factor 有真贡献
3) 在 ETH/SOL 之外的 symbol 上做 out-of-sample 验证

也对应到 stock-bot 教训库的 60-day regime split 那条原则。

_Context:_ thresholds tested: 2.0/2.5/3.5 × intervals 1h/4h/1d on BTC/ETH/SOL 730d. 1 of 7 configs passed gate.

---

