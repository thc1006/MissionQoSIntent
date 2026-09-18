# R2 — a tenant may not request a criticality band above its entitlement.
package missionqos.guard

# Criticality ordering (higher rank = more critical) for the four mission classes.
criticality_rank := {
	"historical-analysis": 1,
	"city-monitoring": 2,
	"incident-verification": 3,
	"emergency-routing": 4,
}

deny contains msg if {
	some w in input.spec.workloads
	tenant := data.missionqos.tenants[input.metadata.tenant]
	criticality_rank[w.missionClass] > criticality_rank[tenant.max_criticality]
	msg := sprintf(
		"workload criticality %q exceeds tenant %q entitlement %q",
		[w.missionClass, input.metadata.tenant, tenant.max_criticality],
	)
}
