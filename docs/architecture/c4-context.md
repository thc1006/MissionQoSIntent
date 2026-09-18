# C4 Model — Level 1：System Context（系統脈絡）

> MissionQoSIntent 與其外部人員/系統的關係。C4 L1 回答：「這個系統服務誰、與哪些外部系統互動。」

```mermaid
C4Context
    title System Context — MissionQoSIntent

    Person(operator, "平台/任務營運者", "撰寫宣告式 QoS 契約")
    Person(tenant, "租戶 / 終端請求方", "送出推論請求（帶 priority/deadline）")

    System(mqi, "MissionQoSIntent", "把 QoS 契約經政策守門的型別化 IR，編譯為跨層、可驗證的 admission/scheduling 設定")

    System_Ext(opa, "OPA / Gatekeeper", "policy-as-code 守門引擎")
    System_Ext(k8s, "Kubernetes API (v1.36)", "DRA: resource.k8s.io/v1")
    System_Ext(kueue, "Kueue (v0.18.1)", "配額預留與 admission, v1beta2")
    System_Ext(gaie, "GAIE (v1.5.0) / EPP", "推論閘道與 endpoint picker")
    System_Ext(engines, "vLLM / Triton", "推論引擎（L1），匯出指標")
    System_Ext(base, "Satellite Mission Compiler", "既有發表，共用方法學 (DOI 10.5281/zenodo.19391965)")

    Rel(operator, mqi, "提交 QoS 契約")
    Rel(mqi, opa, "送契約驗證", "allow/deny + reason")
    Rel(mqi, k8s, "apply DRA 物件")
    Rel(mqi, kueue, "渲染配額 manifests")
    Rel(mqi, gaie, "渲染 EndpointPickerConfig")
    Rel(tenant, gaie, "送請求")
    Rel(gaie, engines, "轉發已入場請求")
    Rel(engines, gaie, "回報負載指標")
    Rel(base, mqi, "方法學地基（Pydantic+Rego+IR+renderer）")
```

## 邊界說明

- **系統負責**：契約 → 跨層設定（control path）；請求 → admit/defer/drop（入場決策）。
- **系統不負責**：token 生成的 data-path 吞吐最佳化（vLLM/Triton/llm-d 職責）。

## 與外部系統的契約（介面摘要）

| 外部系統 | MQI 對它做什麼 | 版本/API（2026-06-25） |
|---|---|---|
| OPA / Gatekeeper | 送契約 JSON 求 allow/deny | Rego；Gatekeeper `ConstraintTemplate`+`Constraint` |
| Kubernetes | apply DRA 物件 | `resource.k8s.io/v1`（DRA 核心 v1.34 GA） |
| Kueue | 渲染 `ClusterQueue`/`LocalQueue`/`ResourceFlavor` | `kueue.x-k8s.io/v1beta2`（v0.18.1） |
| GAIE | 渲染 `EndpointPickerConfig`/`InferencePool` | `inference.networking.x-k8s.io/v1alpha1`（非 CRD） |
| vLLM/Triton | 消費其指標（經 GAIE data layer） | vLLM MSP 五指標 |
