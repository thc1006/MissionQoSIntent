# Shared input builders for the policy-guard tests (package missionqos.guard_test).
# Entitlement/system data comes from policy/data.json (data.missionqos); tests vary only `input`.
package missionqos.guard_test

# A baseline workload that violates NO invariant under data.json for tenant city-ops.
default_workload := {
	"missionClass": "city-monitoring",
	"priority": 50,
	"slo": {"deadline": 5000},
	"throughputFloorRps": 100,
	"resourceClass": "gpu-24g",
	"assuranceRatio": 0.95,
	"fallback": "degrade",
	"adminAccess": false,
}

# default_workload with shallow field overrides.
wl(overrides) := object.union(default_workload, overrides)

# A contract document for the given tenant and workloads.
contract(tenant, workloads) := {
	"metadata": {"tenant": tenant, "mission": "urban-edge-2026"},
	"spec": {"workloads": workloads},
}
