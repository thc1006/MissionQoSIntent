# 參考來源（依信心分級）

> 2026-06-25 重查。**最高信心＝官方文件/規格**；其次 GitHub repo/release/KEP；再次同行評閱/arXiv 論文；最低為部落格（僅作背景）。標 ⚠️ 者為未取證、需人工確認。

## Tier 1 — 官方文件與規格（最高信心）

- **arc42**：https://arc42.org/overview ；模板 repo https://github.com/arc42/arc42-template （2025-11 中文版）
- **MADR 4.0.0**：https://adr.github.io/madr/ ；模板 https://github.com/adr/madr ；ADR 模板總覽 https://adr.github.io/adr-templates/
- **Kubernetes DRA**：https://kubernetes.io/docs/concepts/scheduling-eviction/dynamic-resource-allocation/ （FEATURE STATE v1.36）
- **Kubernetes KEP-4381（DRA structured parameters）**：https://github.com/kubernetes/enhancements/blob/master/keps/sig-node/4381-dra-structured-parameters/README.md
- **GKE DRA concepts**：https://docs.cloud.google.com/kubernetes-engine/docs/concepts/about-dynamic-resource-allocation
- **Kueue concepts**：https://kueue.sigs.k8s.io/docs/concepts/ ；ClusterQueue https://kueue.sigs.k8s.io/docs/concepts/cluster_queue/ ；Workload https://kueue.sigs.k8s.io/docs/concepts/workload/
- **Kueue Set Up DRA**：https://kueue.sigs.k8s.io/docs/tasks/manage/setup_dra/ ；Concurrent Admission https://kueue.sigs.k8s.io/docs/tasks/manage/setup_concurrent_admission/
- **GAIE EPP config-text（本套件最關鍵一手來源）**：https://gateway-api-inference-extension.sigs.k8s.io/guides/epp-configuration/config-text/
- **GAIE Flow Control / Priority and Capacity**：https://gateway-api-inference-extension.sigs.k8s.io/guides/flow-control/ ；https://gateway-api-inference-extension.sigs.k8s.io/concepts/priority-and-capacity/
- **OPA / Rego**：https://www.openpolicyagent.org/docs ；Policy Language https://www.openpolicyagent.org/docs/policy-language

## Tier 2 — GitHub repo / release / issue（高信心）

- **Kueue releases（v0.18.x；含 #12094 @thc1006、#10996 KueueDRAIntegration beta）**：https://github.com/kubernetes-sigs/kueue/releases ；tag v0.18.0 https://github.com/kubernetes-sigs/kueue/releases/tag/v0.18.0 ；repo https://github.com/kubernetes-sigs/kueue
- **GAIE repo / issue #2430（EPP 遷往 llm-d）**：https://github.com/kubernetes-sigs/gateway-api-inference-extension
- **llm-d-inference-scheduler / llm-d**：https://llm-d.ai/blog/intelligent-inference-scheduling-with-llm-d

## Tier 3 — 同行評閱 / arXiv / ACM 論文（競品與前案）

- **arXiv 2602.04900**（Kueue + **DAS** + GAIE；ICPE'26；DOI 10.1145/3777884.3796983）— 與本系統 Kueue+DRA+GAIE 互補
- **SCORPIO**（SLO-oriented LLM serving；TTFT/TPOT Guard；rejects unattainable；goodput ≤14.4×）：https://openreview.net/pdf/c4c70ba63b172ff62f5e8b5c935507bfe6903b63.pdf
- **Niyama**（arXiv 2503.22562；hybrid prioritization + eager relegation；+32% capacity）：https://arxiv.org/pdf/2503.22562
- **Scheduling the Unschedulable**（arXiv 2604.06970；allocation/ordering/overload-control admit-defer-reject；client-side black-box）：https://arxiv.org/abs/2604.06970
- **Token Management in Multi-Tenant AI Inference**（arXiv 2603.00356；ACM AI & Agentic Systems 2026；多租戶 K8s+vLLM token pools；debt-based fairness）：https://arxiv.org/html/2603.00356v1
- **FairBatching**（arXiv 2510.14392；fairness-aware batch + admission control；peak goodput +20%~90%）：https://arxiv.org/pdf/2510.14392
- **LLM Inference Scheduling Survey**（2025-10）：https://www.techrxiv.org/users/994660/articles/1355915

## Tier 4 — 部落格 / 技術文章（僅背景，需謹慎）

- K8s 1.36 綜述：dev.to「Complete Guide to Kubernetes 1.36」；cloudsmith.com「Kubernetes 1.36 — What you need to know」
- DRA 概念：rafay.co、Google Cloud Blog（device management with DRA）
- OPA 內部 IR / kube-mgmt：dev.to「OPA & kube-mgmt Deep Dive」（2026-04）
- Gatekeeper / Rego 實作：oneuptime.com（2026-02）、secure-pipelines.com（2026-03）、spacelift.io（PaC tools 2026）
- Red Hat「Eliminating the Rego tax」（Intent-as-Governance，2026-03）：https://next.redhat.com/2026/03/20/eliminating-the-rego-tax-how-ai-orchestrators-automate-kubernetes-compliance/
- ADR 營運實踐：hidekazu-konishi.com（2026-05）；MADR primer（ozimmer.ch，含 YADR 2026-03）

## 作者既有發表（地基）

- **Satellite Mission Compiler**：DOI **10.5281/zenodo.19391965**，授權 EUPL-1.2，方法學 Pydantic+OPA/Rego+typed IR+多目標 renderer，422 tests

## ⚠️ 需作者人工確認

- Sessionize 上 OpenSSF Community Day EU / OSS Japan 2026 之 CFP **即時**開放狀態（本套件依官網公告日期）
- 學術場域 SoCC / Middleware / IC2E / CCGrid / IEEE SEC 之 **2026–2027 deadline**（本次未逐一查）
- Kueue `#12094` 之 `@thc1006` **是否為作者本人** GitHub handle
- venue 由 OSS EU 重定位為 OSS Japan/OpenSSF 之框架（推斷，非作者明示）
