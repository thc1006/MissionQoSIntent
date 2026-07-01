# Mission QoS 契約與型別化 IR — 範例（示意，非最終）

> 本檔為**示意性**範例，幫助 reviewer 理解契約欄位、IR 結構與跨層渲染對應。最終 schema 隨實作演進；欄位名與型別以實作 repo 為準。

## 1. 宣告式 QoS 契約（輸入）

四類衛星/邊緣工作負載示例：

```yaml
apiVersion: missionqos.dev/v0
kind: MissionQoSContract
metadata:
  tenant: city-ops
  mission: urban-edge-2026
spec:
  workloads:
    - name: emergency-routing          # 緊急路由：最高優先、最短期限
      priority: 100
      deadline: 500ms                   # 端到端
      assuranceRatio: 0.999             # 幾乎不可丟
      resourceClass: gpu-40g
      fallback: reject-with-reason      # 寧拒不誤
    - name: incident-verification       # 事件查證：高優先、可容忍稍長
      priority: 80
      deadline: 2s
      assuranceRatio: 0.99
      resourceClass: gpu-40g
      fallback: degrade-then-reject
    - name: city-monitoring             # 城市監測：中優先、串流式
      priority: 50
      deadline: 5s
      assuranceRatio: 0.95
      resourceClass: gpu-24g
      fallback: degrade
    - name: historical-analysis         # 歷史分析：可被搶占、sheddable
      priority: 10
      deadline: 60s
      assuranceRatio: 0.50
      resourceClass: gpu-24g
      fallback: shed                    # 過載優先丟（對齊 GAIE sheddable/負優先級）
```

## 2. 政策守門（OPA/Rego，示意）

```rego
package missionqos.guard

# 拒絕：deadline 低於系統最小可服務時間
deny[msg] {
    w := input.spec.workloads[_]
    to_ms(w.deadline) < data.system.min_service_time_ms
    msg := sprintf("workload %q deadline %v < min serviceable %vms",
                   [w.name, w.deadline, data.system.min_service_time_ms])
}

# 拒絕：租戶請求的保證率總和超出其授權配額
deny[msg] {
    sum_assured := sum([w.assuranceRatio | w := input.spec.workloads[_]])
    sum_assured > data.tenants[input.metadata.tenant].max_assured
    msg := sprintf("tenant %q over-subscribes assurance budget", [input.metadata.tenant])
}

allow { count(deny) == 0 }
```

## 3. 型別化 IR（單一事實來源，示意）

```jsonc
{
  "irVersion": "0.1.0",
  "tenant": "city-ops",
  "workloads": [
    {
      "id": "wl-emergency-routing",
      "priority": 100,
      "deadlineMs": 500,
      "assuranceRatio": 0.999,
      "deviceClass": "gpu-40g",
      "fallback": "reject",
      "provenance": {                       // 支撐 Q5 可追溯
        "contractField": "spec.workloads[0]",
        "missionSemantic": "emergency-routing",
        "source": "urban-edge-2026"
      }
    }
    // ... 其餘 workloads
  ]
}
```

## 4. 跨層渲染對應（IR → L2/L4/L5，示意）

`wl-emergency-routing`（priority=100, deadlineMs=500, deviceClass=gpu-40g, fallback=reject）渲染為：

**L2 — deferred-red gate 設定**
```yaml
gate:
  - workload: wl-emergency-routing
    slackBasisMs: 500              # = deadline
    dropWhen: "remaining_slack_ms < est_min_service_ms"
    onDrop: reject-with-reason
```

**L4 — Kueue + DRA（示意）**
```yaml
# Kueue：高優先級工作負載類別
apiVersion: kueue.x-k8s.io/v1beta2
kind: WorkloadPriorityClass
metadata: { name: emergency }
value: 100
---
# DRA：請求 40G 級 GPU（CEL 選擇器）
apiVersion: resource.k8s.io/v1
kind: ResourceClaim
metadata: { name: claim-emergency }
spec:
  devices:
    requests:
      - name: gpu
        deviceClassName: gpu-40g
        # 推論用共享裝置 → ResourceClaim（非 Template）
```

**L5 — GAIE EndpointPickerConfig（示意）**
```yaml
apiVersion: inference.networking.x-k8s.io/v1alpha1
kind: EndpointPickerConfig
flowControl:
  defaultRequestTTL: 500ms          # 對齊 deadline（注意：flat TTL，非 slack-aware）
  priorityBands:
    - priority: 100                  # 對齊契約 priority
      orderingPolicyRef: slo-deadline-ordering-policy   # baseline 對照用
      fairnessPolicyRef: global-strict-fairness-policy
featureGates:
  - flowControl                      # 實驗性，需明確開啟
```

## 5. 一致性不變式（golden test 會驗的對齊）

| 不變式 | 檢查 |
|---|---|
| priority 單調 | 契約 priority 排序 == L4 WorkloadPriorityClass value 排序 == L5 priority band 排序 |
| deadline 同源 | L2 `slackBasisMs` == 契約 deadline == L5 `defaultRequestTTL`（或 per-request deadline） |
| deviceClass 對齊 | L4 DRA `deviceClassName` == 契約 `resourceClass` == L5 後端池對應 |
| fallback 語意 | `reject`→L2 reject + L5 非 sheddable；`shed`→L2 drop + L5 負優先級 sheddable |

> **注意**：上表 L5 用 `slo-deadline-ordering-policy` + `defaultRequestTTL` 正是 ADR-0007 的 **baseline (b)** 設定。本系統的 L2 deferred-red 要證明的，是在此設定**之上**，「等待期間持續 slack 判斷、提早放棄」還能再帶來可歸因的 goodput 增益。
