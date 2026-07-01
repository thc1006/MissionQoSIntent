# ADR-0007：評估 baseline 必含「開啟 EDF/SLO ordering 的 GAIE」

- 狀態：Accepted
- 日期：2026-06-25
- 決策者：Hsiu-Chi Tsai
- 諮詢：ADR-0004、2026-06-25 對抗式交叉驗證
- 知會：指導教授、論文委員

## Context and Problem Statement 脈絡與問題

E3 要證明 deferred-red 的「slack-aware 提早放棄」有實證價值。但若 baseline 只用「FCFS / 飽和即 503」這種最弱對照，任何增益都會被 reviewer 歸因於「GAIE 的 EDF/SLO-deadline ordering 早就會了」。問題：E3 的對照組該怎麼設，才能讓 deferred-red 的殘餘差異真正被隔離、且結論可發表？

## Decision Drivers 決策驅動力

- **公平比較**：對照組要是「強 baseline」，不是「稻草人」。
- **可發表性**：systems/cloud venue 的 reviewer 會直接質疑弱 baseline。
- **可歸因**：增益必須能歸因於 deferred-red 的獨有機制，而非 GAIE 已具的功能。

## Considered Options 考慮過的選項

1. **三組對照（採納）**：(a) FCFS/503；**(b) GAIE 開 `edf-ordering-policy` + `slo-deadline-ordering-policy` + `defaultRequestTTL`（強 baseline）**；(c) 本系統 deferred-red。
2. **只比 (a) FCFS/503**。
3. **只比 (c) 與「無 admission」**。

## Decision Outcome 決策結果

選擇 **「選項 1：三組對照，且 (b) 為必備強 baseline」**。理由：

- 重查確認 GAIE v1.5.0 官方 `config-text` 確實提供 `edf-ordering-policy`（最近期限優先）與 `slo-deadline-ordering-policy`（SLO 期限），加上 `defaultRequestTTL`（佇列逾時丟棄）與 `latency-slo-admitter`（無 endpoint 達 SLO 即拒 sheddable）。**這些就是「按 deadline 排序 + 逾時丟棄 + 達不到就拒」**。
- 因此唯有對照「開了這些的 GAIE（baseline b）」，才能證明 deferred-red 的**獨有差異**——「等待期間持續以 `remaining-slack < min-service-time` 提早放棄注定逾時者」——帶來可歸因的 useful goodput / 高優先級 deadline 達成率增益。
- 只比 (a) 會被直接打回；只比「無 admission」更弱。

### Consequences 後果

- 好處：結論可發表、可歸因；主動回應 reviewer 最可能的攻擊點。
- 壞處：baseline (b) 的 GAIE Flow Control 設定與調參工作量大（且 Flow Control 為 experimental、設定不可熱更新，需固定後重啟）；若 (b) 打平甚至更好，須誠實接受並觸發 ADR-0004 的「退為整合工程」備案。
- 中性：除 goodput 外，建議同時報 P95/P99、completion rate、deadline satisfaction、各優先級分層結果（對齊 2026 文獻的評估慣例：useful goodput、TTFT/TBT、graceful degradation under predictor noise）。

### Confirmation 確認

E3 報告中明確列出 (a)(b)(c) 三組在 1.0–1.5× 過載下的 useful goodput 與高優先級 deadline 達成率；並做 ablation 把「slack-aware 提早放棄」與「(b) 已具的重排/逾時」分離。

## Pros and Cons of the Options 各選項利弊

### 選項 1：三組對照（含強 baseline b）
- 優點：公平、可發表、可歸因、預先擋下主要攻擊。
- 缺點：工作量大；有打臉自己的風險（但這正是誠實研究該承擔的）。

### 選項 2：只比 FCFS/503
- 優點：省事。
- 缺點：稻草人 baseline；reviewer 直接打回；增益無法歸因。

### 選項 3：只比「無 admission」
- 優點：最省事。
- 缺點：對照更弱；幾乎無說服力。

## More Information 更多資訊

- 一手來源：GAIE `config-text`（ordering policies、`defaultRequestTTL`、`latency-slo-admitter`、saturation detector）。
- 評估慣例參考：SCORPIO、Niyama、arXiv 2604.06970（useful goodput、admit/defer/reject、predictor-noise sweep、completion/deadline 指標）。
- 相關：ADR-0004（新穎性裁決）、SDD §10.2（E1–E3）、§11 R-1/R-4。
