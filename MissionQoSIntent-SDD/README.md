# MissionQoSIntent — 開發研究計畫書（SDD + ADR 套件）

> **作者**：Hsiu-Chi Tsai（NYCU）  ·  **撰寫日**：2026-06-25  ·  **版本**：v0.1.0
> **格式遵循**：arc42（架構文件）＋ MADR 4.0.0（架構決策記錄）＋ C4 model（視覺）＋ Keep a Changelog
> **狀態**：研究計畫（Work-in-Progress）。本套件描述「要建什麼、為什麼這樣建、怎麼驗證」，不宣稱已有生產系統。

---

## 這份套件是什麼

這是一份把先前「投稿決策報告」的結論，落地為**可執行、可審查、符合開發最佳實踐**的工程設計文件。核心研究問題：

> *Can declarative mission/tenant QoS contracts be compiled — through a policy-guarded, typed intermediate representation (IR) — into a **verifiable, cross-layer** admission-and-scheduling control plane for multi-tenant GenAI inference on Kubernetes?*

一句白話：把「任務/租戶的高階 QoS 契約（優先級、deadline、保證率、資源類別、降級策略）」，經過**政策守門（OPA/Rego）＋型別化 IR**，編譯成五層基礎設施（L1 推論引擎 → L5 閘道）彼此一致、且可被機器驗證的 admission/scheduling 設定。

## 為什麼用這個格式（符合最佳實踐）

| 採用 | 理由（依 2026-06-25 重查） |
|---|---|
| **arc42** | 軟體架構文件的事實標準模板，12 段、技術中立、可裁剪；2025-11 已有官方中文版。本 SDD 即依其 12 段組織。 |
| **MADR 4.0.0** | 現行 ADR 標準格式（2024-09 釋出）；強制「Considered Options + Pros/Cons」，避免事後無法回溯為何這樣決定。每個重大決策一個檔案。 |
| **ADR 與程式碼同 repo** | ThoughtWorks 2016 Tech Radar 起的共識；2026-05 業界回顧指出「ADR 放在工程師不看的地方（Confluence/Notion）＝寫了等於沒寫（Decision Documentation Theater）」。故 ADR 放 `docs/decisions/`。 |
| **C4 model** | 輕量視覺記法（Context/Container/Component/Code），與 arc42 互補：arc42 負責文字與品質/風險，C4 負責結構圖。 |

## 怎麼讀（建議順序）

1. **`SDD.md`** — 主文件（arc42 12 段）。先讀 §1 目標、§4 解決策略、§5 建構塊、§11 風險。**這是全套的核心。**
2. **`docs/decisions/`** — 八個架構決策記錄（ADR）。先讀 [`README.md`](docs/decisions/README.md)（索引＋狀態表），再依興趣讀個別 ADR。**最關鍵的是 [ADR-0004](docs/decisions/0004-deferred-red-scope-vs-gaie.md)（deferred-red 的窄縫裁決）。**
3. **`docs/verification/cross-validation-ledger.md`** — 對抗式交叉驗證帳本。**每一條 load-bearing 事實的一手來源與裁決，含「重查推翻了哪些先前判斷」。投稿/動工前必讀。**
4. **`docs/architecture/`** — C4 系統脈絡圖、容器圖、五層（L1–L5）對照圖（mermaid）。
5. **`ir/mission-qos-contract.schema.example.md`** — IR schema 與 QoS 契約的具體範例（示意，非最終）。
6. **`references.md`** — 依信心分級的完整來源清單。
7. **`CHANGELOG.md`** — 版本變更紀錄。

## 目錄結構

```
MissionQoSIntent-SDD/
├── README.md                     ← 你在這裡
├── SDD.md                        ← 主文件（arc42 12 段）
├── CHANGELOG.md
├── references.md
├── docs/
│   ├── decisions/                ← ADR（MADR 4.0 格式）
│   │   ├── README.md             ← ADR 索引 + 狀態表
│   │   ├── adr-template.md       ← 新 ADR 用的 MADR 4.0 模板
│   │   ├── 0001-integrate-project-a-and-b.md
│   │   ├── 0002-typed-ir-as-single-source-of-truth.md
│   │   ├── 0003-policy-guard-opa-rego-gatekeeper.md
│   │   ├── 0004-deferred-red-scope-vs-gaie.md      ← 最關鍵（新穎性裁決）
│   │   ├── 0005-kueue-dra-for-quota-and-devices.md
│   │   ├── 0006-gaie-integration-boundary.md
│   │   ├── 0007-evaluation-baselines.md
│   │   └── 0008-submission-venue-strategy.md
│   ├── architecture/
│   │   ├── c4-context.md         ← C4 L1 系統脈絡
│   │   ├── c4-container.md       ← C4 L2 容器
│   │   └── layers-L1-L5.md       ← 五層跨層對照
│   └── verification/
│       └── cross-validation-ledger.md   ← 對抗式 review + 事實帳本
└── ir/
    └── mission-qos-contract.schema.example.md
```

## 一頁版「最該記住的三件事」

1. **新穎性必須壓在編譯器/IR/政策守門與跨層可驗證一致性**，不要押在 admission 機制本身。2026 已有 SCORPIO（rejects unattainable）、Niyama（eager relegation）、arXiv 2604.06970（admit/defer/reject cost ladder）、GAIE 的 `edf`/`slo-deadline` ordering＋latency-slo-admitter，把「丟掉達不到 deadline 的請求」做成了既有技術。**「由宣告式 contract 編譯而來、且跨 L2/L4/L5 一致並可驗證」才是你尚未被佔據的縫。**
2. **實驗 baseline 一定要用「開啟 `edf-ordering-policy` ＋ `slo-deadline-ordering-policy` ＋ `defaultRequestTTL` 的 GAIE」**，不能只比預設 FCFS/503。否則 reviewer 會視為既有機制重貼標籤（見 [ADR-0007](docs/decisions/0007-evaluation-baselines.md)）。
3. **投稿用已發表、已 DOI、可展示的 Satellite Mission Compiler 談話**（DOI 10.5281/zenodo.19391965）；整合計畫的論文走 ICPE 2027 類學術 workshop。近期落點：OpenSSF Community Day EU（CFP 7/12）→ OSS Japan 2026（CFP 8/24）。注意 OSS EU 2026 CFP 已於 06-24 截止。（見 [ADR-0008](docs/decisions/0008-submission-venue-strategy.md)）

## 版本根據與時效

本套件所有技術版本與事實均經 **2026-06-25** 獨立上網重查（GitHub tag/atom feed、官方 docs、arXiv/ACM）。完整帳本見 `docs/verification/cross-validation-ledger.md`。關鍵版本：Kubernetes v1.36（DRA 核心 GA）、Kueue v0.18.1（`kueue.x-k8s.io/v1beta2`）、Gateway API Inference Extension v1.5.0。
