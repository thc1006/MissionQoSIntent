# ADR-0004：deferred-red 的範圍裁決（相對 GAIE 與 2026 前案）

- 狀態：**Accepted（高風險，須由 E3 實證支撐）**
- 日期：2026-06-25
- 決策者：Hsiu-Chi Tsai
- 諮詢：2026-06-25 對抗式交叉驗證（見 `docs/verification/cross-validation-ledger.md`）
- 知會：指導教授、論文委員

> **這是本套件最關鍵、也最脆弱的決策。請優先閱讀。**

## Context and Problem Statement 脈絡與問題

專題 B 的核心機制 deferred-red 的設想是：請求等待期間持續判斷能否在期限內被服務，對「注定逾時」者主動丟棄（提早讓位）。但 2026-06-25 的重查顯示，「丟掉達不到 deadline 的請求」已被多方做成既有技術。問題：deferred-red 還剩多少可辯護的新穎性？論文要把它定位成「新機制」還是別的？

### 重查證據（一手來源，2026-06-25）

**GAIE v1.5.0 官方 `config-text` 文件**明載 Flow Control 三個 ordering policy：
- `fcfs-ordering-policy`（預設）；
- `edf-ordering-policy`：**Earliest Deadline First，prioritizes requests with the closest expiration time (deadline)**；
- `slo-deadline-ordering-policy`：**orders requests by an SLO-based deadline, computed from the time the request is received by the server**。
- 另有 `defaultRequestTTL`（佇列內 flat timeout，到時丟棄或 client 取消前無限等待）、`latency-slo-admitter`（無任一 endpoint 能達 SLO 時即時拒 sheddable）、`utilization-detector`（queue depth + KV cache，且同時服務 Admission 與 Flow Control）。

**2026 學術前案**（皆已在重查中確認存在）：
- **SCORPIO**：TTFT Guard 採 **least-deadline-first reordering 並 rejects unattainable requests**；TPOT Guard 採 VBS-based admission control。goodput 提升至多 14.4×。
- **Niyama**：**hybrid prioritization + eager relegation policy**，過載下少 SLO 違規；serving capacity +32%。
- **arXiv 2604.06970「Scheduling the Unschedulable」**（2026-04）：把問題分解為 allocation / ordering / **overload control（explicit admit/defer/reject on a cost ladder）**——與 admit/defer/drop 三分法幾乎同構，但設定是 **client-side、針對 black-box LLM API**（半-clairvoyant，靠 token priors）。
- **arXiv 2603.00356「Token Management in Multi-Tenant AI Inference」**（2026-02，ACM AI & Agentic Systems）：多租戶、K8s + vLLM、priority-aware allocation + 服務分級 + debt-based fairness，**不改 inference runtime 或 cluster scheduler**，過載時選擇性節流 spot 流量以保證 P99。

→ **結論：「按 deadline 排序」「丟掉達不到 SLO 的請求」「admit/defer/reject 三分」在 2026 都已是既有技術。** deferred-red 作為「機制」幾乎沒有獨佔空間。

## Decision Drivers 決策驅動力

- **避免被 reviewer 視為既有機制重貼標籤**（最高優先）。
- 仍要保留 B 的價值，但定位要誠實、可辯護。
- 必須能用**實驗**把殘餘差異隔離出來，否則任何宣稱都站不住。

## Considered Options 考慮過的選項

1. **窄縫化 + 由 contract 編譯（採納）**：把 deferred-red 重新界定為「**在等待期間持續以 `remaining-slack < min-service-time` 判斷、提早放棄注定逾時者**，且**由宣告式 QoS 契約編譯而來、與 L2/L4/L5 一致並可驗證**」；新穎性主體移到編譯器/IR/跨層一致性，deferred-red 為其中一個被編譯出的機制。
2. **宣稱 deferred-red 為全新 admission 演算法**：堅持機制本身的新穎性。
3. **完全移除 deferred-red**：論文只談編譯器/IR/跨層一致性，不碰 admission 機制。

## Decision Outcome 決策結果

選擇 **「選項 1：窄縫化 + 由 contract 編譯」**。理由：

1. **主新穎性錨定在最少被佔據的軸**——「policy-guarded QoS-contract compiler + 型別化 IR + 跨層可驗證一致性」。前述所有前案都是「給定一個 scheduler/admission 邏輯」，**沒有一個是「從宣告式任務/租戶契約，經政策守門的型別化 IR，編譯出彼此一致的跨層 admission/quota/gateway 設定」**。
2. **deferred-red 降為窄縫**：它與 GAIE 的差異不是「會不會丟逾時請求」（會），而是：
   - GAIE `edf`/`slo-deadline` 只**重排**佇列，不在等待期間提早放棄；
   - GAIE `defaultRequestTTL` 是**固定逾時**，到時才丟、不問是否仍可達標；
   - GAIE `latency-slo-admitter` 是**入場瞬間**判斷，非等待期間持續判斷；
   - deferred-red 是**等待期間持續**以 `remaining-slack vs min-service-time` 判斷、對注定逾時者**提早**放棄，且**由 contract 編譯、跨層一致**。
3. **此差異必須由 E3 baseline (b) 實證**（見 ADR-0007）：對照「開 `edf-ordering-policy` + `slo-deadline-ordering-policy` + `defaultRequestTTL` 的 GAIE」，證明 deferred-red 的「提早放棄」帶來可歸因的 useful goodput / 高優先級 deadline 達成率增益。

### Consequences 後果

- 好處：新穎性主體穩固（編譯器/IR/一致性無前案佔據）；deferred-red 的宣稱誠實、範圍明確、可被實證；論文站位清楚。
- 壞處：deferred-red 的「賣點」被大幅縮小，篇幅與份量下降；E3 baseline (b) 設計與調參工作量大；若 (b) 打平甚至更好，deferred-red 須退為「整合工程」貢獻。
- 中性：最終 A（編譯器/mission）與 B（機制）的篇幅配比，待 E3 結果定（見 ADR-0001 後續複查）。

### Confirmation 確認

E3 必須對照 baseline (b)（非只 (a) FCFS/503）。通過判準：本系統 useful goodput 與高優先級 deadline 達成率**至少不劣於 (b)**，且差異可歸因於「slack-aware 提早放棄」而非 (b) 已具的重排/逾時機制。若不達標，觸發「退為整合工程貢獻」的備案。

## Pros and Cons of the Options 各選項利弊

### 選項 1：窄縫化 + 由 contract 編譯
- 優點：新穎性穩固且誠實；可實證；與整體編譯器論述一致。
- 缺點：deferred-red 份量縮小；E3 工作量大。

### 選項 2：宣稱全新演算法
- 優點：若成立則賣點大。
- 缺點：與 SCORPIO/Niyama/2604.06970/GAIE 高度重疊，極可能被 reviewer 直接打回「重貼標籤」；風險過高。

### 選項 3：完全移除
- 優點：論述最乾淨、最安全。
- 缺點：浪費 B 的既有工作；失去「契約能編譯出具體、可實證的 runtime 機制」這個有力示範；論文偏向純概念。

## More Information 更多資訊

- 一手來源：GAIE `config-text`（ordering policies、saturation detector、flow control、defaultRequestTTL）；SCORPIO（OpenReview）；Niyama（arXiv 2503.22562）；arXiv 2604.06970；arXiv 2603.00356。詳見 `references.md` 與 `docs/verification/cross-validation-ledger.md`。
- 相關：ADR-0006（GAIE 整合邊界）、ADR-0007（baseline）、SDD §6.2、§11 R-1。
- **後續複查（必做）**：E3 結果出爐後更新本 ADR 的最終裁決（窄縫成立 / 退為整合工程）。
