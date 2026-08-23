# São Paulo live-source gate

This gate verifies that the reviewed GeoSampa source profile still resolves against the official WFS at runtime.

It inspects the mapped parcel (`geoportal:lote_cidadao`) and current zoning (`geoportal:perimetro_zona_lei_18177_24`) type names, requests EPSG:4326 samples, records returned property keys and sample geometry types, and uploads the evidence as a GitHub Actions artifact.

A passing inspection means **live connectivity and source-schema evidence only**. It does not mean that the datasets were ingested, quality-approved, promoted into canonical parcel/zone tables, used in golden-lot analysis, or professionally homologated. Those are separate acceptance gates in issue #3.

The scheduled run is intentionally allowed to fail when the official upstream source is unavailable or changes schema. Such a failure is an operational signal and must not be silently converted into a pass.
