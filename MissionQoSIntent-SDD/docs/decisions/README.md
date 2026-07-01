# Architecture Decision Records (ADR)

本目錄收錄 MissionQoSIntent 的架構決策記錄，採 **MADR 4.0.0** 格式（2024-09 釋出之現行標準）。

## 為何 ADR 放這裡（而非 Confluence/Notion）

ThoughtWorks 2016 Tech Radar 起的共識：ADR 應與其所治理的程式碼**同 repo**、經 PR review、從程式碼反向連結。2026 業界回顧把「ADR 放工程師不看的地方」稱為 **Decision Documentation Theater**——寫了等於沒寫。故本專案 ADR 一律放 `docs/decisions/`，新增時走 PR，並在對應程式碼處留 `// see docs/decisions/000X-*.md` 註解。

## 狀態圖例

`Proposed`（提議中）→ `Accepted`（已採納）→ 可能 `Deprecated`（已棄用）或 `Superseded by 000X`（被取代）。

## 索引

| ADR | 標題 | 狀態 | 關鍵驅動力 |
|---|---|---|---|
| [0001](0001-integrate-project-a-and-b.md) | 整合專題 A（mission→QoS）與 B（機制）為單一論文 | **Accepted** | 一致研究問題、論文可完成性 |
| [0002](0002-typed-ir-as-single-source-of-truth.md) | 以型別化 IR 為單一事實來源 | **Accepted** | 跨層一致性、可追溯 |
| [0003](0003-policy-guard-opa-rego-gatekeeper.md) | 以 OPA/Rego（可選 Gatekeeper）為政策守門 | **Accepted** | 政策即程式碼、可測試 |
| [0004](0004-deferred-red-scope-vs-gaie.md) | **deferred-red 範圍裁決（相對 GAIE）** | **Accepted**（高風險，須實證） | 新穎性侵蝕、避免重貼標籤 |
| [0005](0005-kueue-dra-for-quota-and-devices.md) | 以 Kueue+DRA 作 L4 配額與裝置 | **Accepted** | 原生 K8s、填補 DAS 未覆蓋縫 |
| [0006](0006-gaie-integration-boundary.md) | 以 GAIE 為整合邊界（消費非重造） | **Accepted** | 不重造輪子、範圍收斂 |
| [0007](0007-evaluation-baselines.md) | 評估 baseline 必含 GAIE EDF/SLO 組態 | **Accepted** | 公平比較、可發表性 |
| [0008](0008-submission-venue-strategy.md) | 投稿場域策略（含時效） | **Accepted** | CFP 時程、成品導向 |

## 最該先讀

**[ADR-0004](0004-deferred-red-scope-vs-gaie.md)** ——它記錄了本研究最脆弱也最關鍵的判斷：deferred-red 機制在 2026 已近既有技術，新穎性必須轉移到「由 contract 編譯 + 跨層可驗證一致」，並用實驗 baseline (b)（開 GAIE EDF/SLO ordering）來證明窄縫的實證價值。

## 新增 ADR

複製 [`adr-template.md`](adr-template.md)（MADR 4.0 bare 模板）為 `000X-短標題.md`，遞增編號，更新本索引表，走 PR。
