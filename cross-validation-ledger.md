# 交叉驗證帳本與對抗式 Review（Cross-Validation Ledger）

> **日期**：2026-06-25  ·  **方法**：每條 load-bearing 事實獨立上網重查一手來源（GitHub tag/atom、官方 docs、arXiv/ACM/OpenReview），標註裁決狀態。
> **目的**：讓任何 reviewer（含未來的你）能一眼看出「哪些事實已驗、來源為何、哪些先前判斷被推翻、哪些仍待人工確認」。**投稿/動工前必讀。**

## 裁決狀態圖例

- ✅ **CONFIRMED**：一手來源直接證實。
- 🔁 **CORRECTED**：先前文件曾誤，本次重查更正。
- ⛔ **RETRACTION-REJECTED**：先前曾「撤回」某正確事實，本次重查確認該撤回是錯的、事實成立。
- ➡️ **CARRIED**：沿用前一輪已驗結論（同日內）。
- ⚠️ **NEEDS-MANUAL-CONFIRM**：本次未能/不宜由模型確認，需作者手動查證。

---

## A. 文件方法論（SDD/ADR 格式）

| # | 事實 | 狀態 | 一手來源 |
|---|---|---|---|
| A1 | arc42 為 12 段架構文件模板；2025-11 已有官方中文版；§10 已重構為 overview(10.1)+details(10.2) | ✅ | arc42.org/overview、github.com/arc42/arc42-template |
| A2 | MADR 4.0.0 於 2024-09-17 釋出，為現行 ADR 標準；含 bare/minimal 模板 | ✅ | adr.github.io/madr |
| A3 | YAML ADR（YADR）於 2026-03 出現 | ✅ | ozimmer.ch（MADR primer，News March 2026） |
| A4 | Nygard 格式（Title/Status/Context/Decision/Consequences）為最小基準 | ✅ | adr.github.io/adr-templates |
| A5 | 業界最佳實踐：ADR 與程式碼同 repo、PR review、從程式碼反向連結，否則「Decision Documentation Theater」 | ✅ | hidekazu-konishi.com（2026-05） |

## B. Kubernetes DRA（L4 裝置）

| # | 事實 | 狀態 | 一手來源 |
|---|---|---|---|
| B1 | DRA API group `resource.k8s.io/v1`；v1 預設供應，v1beta1 為儲存版 | ✅ | kubernetes.io DRA concepts；enhancements KEP-4381 |
| B2 | 四種 kind：ResourceClaim（what）/ResourceClaimTemplate（per-Pod）/DeviceClass（blueprint, CEL）/ResourceSlice（where, driver 發布） | ✅ | kubernetes.io DRA concepts |
| B3 | DRA 核心於 v1.34 GA；v1.36（2026-04-22 發布）：prioritized list GA、Device Taints/Tolerations beta、DRA Admin Access GA、Extended Resource via DRA beta（`DRAExtendedResource` gate 預設開） | ✅ | kubernetes.io（FEATURE STATE v1.36）、cloudsmith/dev.to v1.36 報導 |
| B4 | v1.36 scheduler plugin 把 ResourceSlice 分 shared/per-node，降約 50% Filter 階段延遲 | ✅ | dev.to「Complete Guide to K8s 1.36」 |
| B5 | ResourceClaim 適合共享裝置（推論）；ResourceClaimTemplate 適合專屬（訓練） | ✅ | docs.cloud.google.com GKE DRA；rafay.co |
| B6 | preemption 雷：`ResourceClaim` 的 Pod 預設 `PreemptLowerPriority` 增 autoscaling 延遲 → 設 `preemptionPolicy: Never` | ✅ | docs.cloud.google.com（Non-preempting PriorityClass） |

## C. Kueue（L4 配額）

| # | 事實 | 狀態 | 一手來源 |
|---|---|---|---|
| C1 | Kueue 最新 v0.18.1；API `kueue.x-k8s.io/v1beta2`（v1beta1 deprecated） | ✅ | github.com/kubernetes-sigs/kueue（releases、v1beta1 ref 標 deprecated） |
| C2 | 核心物件：ClusterQueue（叢集級資源池/配額/fair-sharing）、LocalQueue（namespace 級/租戶）、ResourceFlavor（資源特徵）、Workload（admission 單位）、Cohort（互借配額群）、WorkloadPriorityClass | ✅ | kueue.sigs.k8s.io/docs/concepts |
| C3 | quota reservation（鎖配額）≠ admission（允許建 pod）≠ pod scheduling | ✅ | kueue.sigs.k8s.io/docs/concepts |
| C4 | v0.18：`KueueDRAIntegration` 升 beta（預設開，#10996）；ConcurrentAdmission alpha；PodSets 上限 8→10 | ✅ | github releases/tag/v0.18.0 |
| C5 | DRA 配額計帳自 v0.17 alpha；未開 `DRAExtendedResources` 會對同裝置雙重計費（requests + 自動 ResourceClaim） | ✅ | kueue.sigs.k8s.io/docs/tasks/manage/setup_dra |
| C6 | **release notes 含 `#12094, @thc1006`：「DRA: Fixed hot reconcile loops for inadmissible Workloads with deterministic DRA resolution failures」** | ✅（事實存在） / ⚠️（是否為作者本人 handle） | github.com/kubernetes-sigs/kueue/releases |

> **C6 行動**：若 `@thc1006` 為作者，這是直接的 upstream Kueue+DRA 貢獻證據，應入投稿 bio 與 ADR-0006。本帳本不假設其為真。

## D. GAIE（L5 閘道）— 本套件最關鍵的一手來源

| # | 事實 | 狀態 | 一手來源 |
|---|---|---|---|
| D1 | GAIE v1.5.0 為最新 stable（**非** v1.4.x） | ⛔→✅ | github tag；先前文件曾誤撤此判斷，本次確認 v1.5.0 成立 |
| D2 | 設定 kind `EndpointPickerConfig`，`apiVersion: inference.networking.x-k8s.io/v1alpha1`；**非 CRD**，僅啟動讀取、不可熱更新 | ✅ | gateway-api-inference-extension.sigs.k8s.io/guides/epp-configuration/config-text（明載 "NOTE: ... is NOT a Kubernetes CRD ... only read on startup"） |
| D3 | Flow Control 3-tier dispatch：Priority(band)→Fairness(flow)→Ordering(request) | ✅ | 同上 config-text |
| D4 | **三個 ordering policy**：`fcfs-ordering-policy`（預設）、`edf-ordering-policy`（"Earliest Deadline First, prioritizes requests with the closest expiration time (deadline)"）、`slo-deadline-ordering-policy`（"orders by an SLO-based deadline, computed from the time the request is received"） | ⛔→✅ | 同上（先前文件曾誤撤「GAIE 有 EDF/SLO ordering」，本次直接證實存在） |
| D5 | 兩個 fairness policy：`global-strict-fairness-policy`、`round-robin-fairness-policy` | ✅ | 同上 |
| D6 | 兩個 saturation detector：`utilization-detector`（預設；`queueDepthThreshold` 預設 5、`kvCacheUtilThreshold` 預設 0.8、`headroom` 預設 0.0）、`concurrency-detector`（`maxConcurrency` 預設 100） | ✅ | 同上 |
| D7 | `defaultRequestTTL`：佇列內 fallback timeout；若 0/省略 → 退回 client context deadline，可能無限等待 | ✅ | 同上 |
| D8 | Saturation Detector 行為：Flow Control **開** → gatekeeper 在記憶體緩衝排隊；Flow Control **關（預設）** → 飽和時即時 HTTP 503 拒 sheddable（負優先級） | ✅ | 同上 |
| D9 | `flowControl` 與 `dataLayer` 為 experimental feature gates（預設關） | ✅ | 同上（Feature Gates 段） |
| D10 | EPP 映像 `ghcr.io/llm-d/llm-d-inference-scheduler`；EPP/InferenceObjective/BBR 遷往 llm-d（issue #2430） | ✅ | 同上（Deployment 範例 image）、llm-d.ai |
| D11 | vLLM MSP 五核心指標：`vllm:num_requests_waiting`、`vllm:num_requests_running`、`vllm:kv_cache_usage_perc`、`vllm:lora_requests_info`、`vllm:cache_config_info` | ✅ | 同上（Data Layer 段） |

## E. 競品/前案（對抗式 review 核心）

| # | 事實 | 狀態 | 一手來源 |
|---|---|---|---|
| E1 | **SCORPIO**：SLO-oriented LLM serving；TTFT Guard = least-deadline-first reordering + **rejects unattainable requests**；TPOT Guard = VBS-based admission；goodput 至多 14.4× | ✅ | openreview.net（SCORPIO pdf） |
| E2 | **Niyama**（arXiv 2503.22562）：QoS-aware adaptive scheduling；**hybrid prioritization + eager relegation**；serving capacity +32% | ✅ | arxiv.org/pdf/2503.22562 |
| E3 | **arXiv 2604.06970「Scheduling the Unschedulable」**（2026-04）：allocation/ordering/**overload control（explicit admit/defer/reject on a cost ladder）**；但為 **client-side、black-box LLM API**（半-clairvoyant，token priors） | ✅ | arxiv.org/abs(html)/2604.06970 |
| E4 | **arXiv 2603.00356「Token Management in Multi-Tenant AI Inference」**（2026-02，ACM AI & Agentic Systems）：多租戶 K8s+vLLM；priority-aware allocation + 服務分級 + debt-based fairness；**不改 runtime/scheduler**；過載節流 spot 保 P99 | ✅ | arxiv.org/html/2603.00356 |
| E5 | **FairBatching**（arXiv 2510.14392）：fairness-aware batch formation + admission control；peak goodput +20%~90% | ✅ | arxiv.org/pdf/2510.14392 |
| E6 | **arXiv 2602.04900** 使用 **DAS（Dynamic Accelerator Slicer）而非 DRA**；走 ICPE'26（DOI 10.1145/3777884.3796983） | ➡️✅ | arXiv（前一輪已 6 來源交叉確認；本套件沿用） |

### E 區對抗式結論（最重要）

> **「按 deadline 排序」「丟掉達不到 SLO 的請求」「admit/defer/reject 三分」在 2026 已是既有技術**（SCORPIO/Niyama/2604.06970 + GAIE `edf`/`slo-deadline`/`latency-slo-admitter`/`defaultRequestTTL`）。deferred-red 作為「機制」幾乎無獨佔空間。
>
> **殘餘可辯護新穎性僅剩兩條**：(a) **policy-guarded QoS-contract compiler + 型別化 IR**；(b) **跨層可驗證一致性**。deferred-red 的窄縫＝「等待期間持續以 `remaining-slack < min-service-time` 提早放棄 + 由 contract 編譯 + 跨層一致」，且**必須以 E3 baseline (b)（開 GAIE EDF/SLO）實證隔離**，否則站不住。
>
> 詳見 ADR-0004、ADR-0007。**這比前一輪的結論更嚴格——前一輪尚未把 2604.06970 與 2603.00356 完全納入，本輪納入後新穎性空間更窄。**

## F. 政策即程式碼（L 守門）

| # | 事實 | 狀態 | 一手來源 |
|---|---|---|---|
| F1 | OPA 模型 input→policy→decision；Rego 受 Datalog 啟發、宣告式、set-based；CNCF graduated | ✅ | openpolicyagent.org/docs |
| F2 | OPA 內部把 Rego 編譯為 AST→IR（AOT，in-memory，單位數毫秒）——「契約→IR」設計前例 | ✅ | dev.to「OPA & kube-mgmt deep dive」（2026-04） |
| F3 | Gatekeeper = ConstraintTemplate（規則）+Constraint（範圍+值）+Controller；2026 K8s admission 事實標準 | ✅ | oneuptime.com（2026-02）、dev.to |
| F4 | Red Hat（2026-03）「Eliminating the Rego tax」以 LLM（Claude Code+MCP）自動生成 context-aware Gatekeeper 政策（Intent-as-Governance）——與本計畫相鄰但不同 | ✅ | next.redhat.com（2026-03-20） |
| F5 | PaC 最佳實踐：版本控制、`opa eval` 單元測試（known-good/known-bad）、1–2 週 dry-run、human-in-the-loop GitOps | ✅ | next.redhat.com、secure-pipelines.com（2026-03） |

## G. 投稿場域（時效）

| # | 事實 | 狀態 | 一手來源 |
|---|---|---|---|
| G1 | OSS EU 2026（Prague 10/7–9）CFP **06-24 已截止**（今日 06-25 已過） | ➡️✅ | events.linuxfoundation.org（前一輪確認） |
| G2 | OpenSSF Community Day EU CFP 開到 **7/12** | ➡️✅ | openssf.org（前一輪確認） |
| G3 | OSS Japan 2026（Tokyo 12/7–9）CFP **8/24** 23:59 JST | ➡️✅ | events.linuxfoundation.org |
| G4 | KubeCon EU 2027（Barcelona 3/15–18）CFP 預計 H2 2026 | ➡️✅ | LF calendar |
| G5 | Satellite Mission Compiler DOI 10.5281/zenodo.19391965，EUPL-1.2，422 tests | ➡️✅ | Zenodo（前一輪確認） |
| G6 | Sessionize 上 OpenSSF/OSS Japan 之 CFP **即時**開放狀態 | ⚠️ | 需作者投前手動查 |
| G7 | 學術場域 SoCC/Middleware/IC2E/CCGrid/IEEE SEC 之 2026–2027 deadline | ⚠️ | 需作者投前逐一查 |

## H. 本輪推翻/修正的先前判斷（透明聲明）

1. ⛔→✅ **GAIE 有 EDF/SLO-deadline ordering**：先前某修正文件曾「撤回」此事實，本輪由官方 config-text **直接證實存在**（D4）。撤回是錯的。
2. ⛔→✅ **GAIE v1.5.0 為最新**：先前曾誤改為 v1.4.x，本輪確認 v1.5.0（D1）。
3. ➡️ **新穎性空間比前一輪更窄**：本輪把 arXiv 2604.06970（admit/defer/reject cost ladder）與 2603.00356（多租戶 K8s token pools）完整納入後，deferred-red 的獨佔空間進一步縮小（E 區結論）。
4. ⚠️ **venue 重新定位（OSS EU → OSS Japan/OpenSSF）為推斷**：依「今日日期 + 作者既定近期目標」，非作者明示；若需保留 OSS EU 歷史框架請於 ADR-0008 修正（見該 ADR 透明聲明）。
5. ⚠️ **`@thc1006` 是否為作者**：release notes 事實存在，但身分需作者確認（C6）。

---

## 給 reviewer 的一句話

本套件的所有技術版本與機制宣稱，均可在上表一手來源逐條覆核。**最該挑戰的是 ADR-0004 的新穎性窄縫**——若你能指出 deferred-red 與 GAIE `edf`+`slo-deadline`+`defaultRequestTTL` 的差異不存在，整個 B 部分就該退為整合工程貢獻；本套件已預先承認此風險並設計 E3 baseline (b) 來實證。
