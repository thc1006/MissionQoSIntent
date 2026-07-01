# Changelog

本檔遵循 [Keep a Changelog 1.0.0](https://keepachangelog.com/en/1.0.0/)；版本遵循 [Semantic Versioning 2.0.0](https://semver.org/lang/zh-TW/)。

## [0.1.0] - 2026-06-25

首次釋出：完整 SDD + ADR 開發研究計畫書套件。

### Added 新增
- `SDD.md`：arc42 完整 12 段軟體設計文件（含 mermaid 圖、五層模型、FR/NFR、五品質目標、E1–E3 評估計畫、R-1..8 風險、詞彙表）。
- `docs/decisions/`：八份 MADR 4.0.0 架構決策記錄（ADR-0001..0008）＋索引＋模板。
- `docs/architecture/`：C4 系統脈絡（L1）、容器（L2）、五層 L1–L5 跨層對照。
- `docs/verification/cross-validation-ledger.md`：對抗式交叉驗證帳本（逐條一手來源 + 裁決狀態）。
- `ir/mission-qos-contract.schema.example.md`：QoS 契約與型別化 IR 示意範例（四類衛星/邊緣工作負載）。
- `references.md`：依信心分級的完整來源清單。
- `README.md`：導覽與「最該記住的三件事」。

### Verified 已驗（2026-06-25 重查一手來源）
- Kubernetes v1.36（DRA 核心 v1.34 GA；prioritized list GA、Device Taints/Tolerations beta、DRA Admin Access GA、Extended Resource via DRA beta；scheduler 降約 50% Filter 延遲）。
- Kueue v0.18.1（`kueue.x-k8s.io/v1beta2`；`KueueDRAIntegration` beta；DRA 配額計帳 alpha；release notes 含 #12094 @thc1006）。
- GAIE v1.5.0（`EndpointPickerConfig` 非 CRD、僅啟動讀取；三 ordering policy `fcfs`/`edf`/`slo-deadline`；兩 fairness；兩 saturation detector；`defaultRequestTTL` 行為；Flow Control 3-tier；feature gates 預設關）。

### Corrected / Adversarial 更正與對抗式發現
- ⛔→✅ 確認 **GAIE 確有 `edf`/`slo-deadline` ordering**（先前曾誤撤）；確認 **GAIE v1.5.0 為最新**（先前曾誤改 v1.4.x）。
- 🔴 **新穎性裁決（ADR-0004）**：deferred-red 機制在 2026 已近既有技術（SCORPIO/Niyama/arXiv 2604.06970/2603.00356 + GAIE）；主新穎性轉移至「policy-guarded QoS-contract compiler + 型別化 IR + 跨層可驗證一致性」；deferred-red 窄縫須以 E3 baseline (b)（開 GAIE EDF/SLO）實證。比前一輪結論更嚴格。

### Pending / Needs-confirm 待確認
- `@thc1006` 是否為作者 handle；Sessionize CFP 即時狀態；學術場域 2026–2027 deadline；venue 重定位框架（推斷）。

[0.1.0]: # "首次釋出"
