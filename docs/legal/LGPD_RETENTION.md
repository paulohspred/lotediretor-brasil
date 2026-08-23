# LGPD / retention baseline — v13

This is an engineering baseline and must be approved by the controller/DPO/legal team before GA.

- Public official/legal/geospatial evidence: retain according to source license, evidentiary purpose and version lineage.
- Tenant private documents: configurable retention per contract/workspace; deletion workflow must remove active copies and schedule object-storage deletion while preserving legally required audit metadata.
- Auth/session data: minimum necessary TTL; no bearer token in browser localStorage.
- AI traces: minimize prompts/private content; tenant scope; retention configurable; model/provider transmission must follow contract and data classification.
- Billing/fiscal records: retention follows applicable fiscal/accounting requirements; do not use generic soft-delete to erase mandatory records.
- Support access: time-bounded, audited, least privilege.
- DSAR workflows: export, correction and deletion must distinguish customer content from immutable official-source provenance and legally retained records.
