# R1 — summed guaranteed throughput must not exceed the tenant's entitled capacity.
package missionqos.guard

deny contains msg if {
	tenant := data.missionqos.tenants[input.metadata.tenant]
	floors := [f | some w in input.spec.workloads; f := w.throughputFloorRps]
	total := sum(floors)
	total > tenant.throughput_entitlement_rps
	msg := sprintf(
		"guaranteed throughput %v rps exceeds tenant %q entitlement %v rps",
		[total, input.metadata.tenant, tenant.throughput_entitlement_rps],
	)
}
