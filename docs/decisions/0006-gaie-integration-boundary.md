# ADR-0006：以 GAIE 為整合邊界（消費，非重造）

- 狀態：Accepted
- 日期：2026-06-25
- 決策者：Hsiu-Chi Tsai
- 知會：指導教授

## Context and Problem Statement 脈絡與問題

L5（閘道層）有兩條路：自建一個推論閘道/endpoint picker，或消費既有的 Gateway API Inference Extension（GAIE）。GAIE 已提供 `InferencePool`、EPP（endpoint picker）、Flow Control、saturation detector、ordering/fairness policy。問題：本系統應重造這些，還是把 GAIE 當整合邊界、只消費其 API 並由 IR 渲染其設定？

## Decision Drivers 決策驅動力

- **範圍收斂**（單人專題，見 SDD §11 R-6）。
- 避免重造已成熟的 upstream 元件。
- 新穎性不在閘道機制本身（GAIE 已做），而在「由契約編譯出一致的閘道設定」。
- 須誠實面對 GAIE 現況（experimental、設定非 CRD）。

## Considered Options 考慮過的選項

1. **消費 GAIE（採納）**：IR 渲染 `EndpointPickerConfig`（priority bands、ordering/fairness 參照、saturation detector 參數）與 `InferencePool`；本系統不改 GAIE 內部。
2. **自建閘道/picker**：從零實作 endpoint 選擇與佇列。
3. **fork GAIE 改造**：分叉 GAIE 並加入自家機制。

## Decision Outcome 決策結果

選擇 **「選項 1：消費 GAIE」**。理由：

- **範圍收斂**：閘道機制 GAIE 已做（priority-banded queuing、saturation detector、ordering policies、latency-slo-admitter），自建純屬重造輪子。
- **新穎性定位正確**：本系統貢獻是「**由契約編譯出與 L2/L4 一致的 L5 設定**」與「跨層可驗證一致性」，不是閘道演算法。
- **誠實面對現況（2026-06-25 重查）**：GAIE v1.5.0 的 Flow Control 為 experimental、`flowControl` feature gate 預設關閉；`EndpointPickerConfig`（`inference.networking.x-k8s.io/v1alpha1`）**不是 CRD、僅啟動時讀取、不可熱更新**；EPP/InferenceObjective/BBR 已遷往 `llm-d/llm-d-inference-scheduler`（issue #2430）。這些現況正好支持「**離線由 IR 渲染設定、apply 後重啟**」的設計（ADR-0002），而非依賴線上 reconcile。
- **與 2602.04900 互補**：該論文組合 Kueue + DAS + GAIE；本系統組合 Kueue + DRA + GAIE，貢獻在「組合後的可驗證一致性 + 由契約編譯」（見 ADR-0004、ADR-0005）。

### Consequences 後果

- 好處：範圍收斂；不重造；新穎性定位清楚；貼合 GAIE 現況。
- 壞處：受 GAIE 實驗性與設定限制（不可熱更新 → 改設定需重啟 EPP）；Flow Control 預設關，baseline 與本系統都須明確開啟並標注實驗性（見 SDD §11 R-4）。
- 中性：GAIE API 仍在 v1alpha1，演進可能影響 L5 renderer，需版本追蹤。

### Confirmation 確認

E3：本系統渲染的 `EndpointPickerConfig` 能正確部署到 GAIE EPP（`ghcr.io/llm-d/llm-d-inference-scheduler` 映像）；baseline (b) 與本系統皆以固定設定重啟、無熱更新依賴；L5 設定與 L2/L4 通過一致性檢查。

## Pros and Cons of the Options 各選項利弊

### 選項 1：消費 GAIE
- 優點：範圍收斂；不重造；定位正確；貼合現況；與既有論文互補。
- 缺點：受 GAIE 實驗性/不可熱更新限制。

### 選項 2：自建閘道
- 優點：完全可控。
- 缺點：重造成熟輪子；範圍爆炸；新穎性反而被「又做一個 picker」稀釋。

### 選項 3：fork 改造
- 優點：可注入自家機制。
- 缺點：維護分叉成本高；偏離「消費邊界」定位；upstream 不可見度反降。

## More Information 更多資訊

- 一手來源：GAIE `config-text`、`priority-and-capacity`、`flow-control`、`latency-based-predictor`、issue #2430；arXiv 2602.04900。詳見 `references.md`。
- 相關：ADR-0002、ADR-0004、ADR-0005、SDD §5.3、§7。
