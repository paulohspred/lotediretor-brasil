-- v20 Municipality Factory curated reusable connector contracts.
-- Endpoint/typename/resource details remain municipal configuration; these rows only define reusable adapter contracts.

INSERT INTO source.connector_contract(code,version,adapter,media_class,schema_contract,discovery_profile,ingest_profile,qa_profile,status,created_by)
VALUES
 ('WFS_GIS',1,'WFS','GIS','{"output":"GeoJSON FeatureCollection"}'::jsonb,'{"request":"GetCapabilities"}'::jsonb,'{"requiredPins":["typeName","srsName"],"paged":true}'::jsonb,'{"required":["GIS","STRUCTURE","LICENSE","TEMPORAL"]}'::jsonb,'ACTIVE','system:v20-municipality-factory'),
 ('WMS_GIS',1,'WMS','GIS','{"output":"Raster image"}'::jsonb,'{"request":"GetCapabilities"}'::jsonb,'{"requiredPins":["layers","bbox","crs","width","height","format"]}'::jsonb,'{"required":["GIS","STRUCTURE","LICENSE","TEMPORAL"]}'::jsonb,'ACTIVE','system:v20-municipality-factory'),
 ('ARCGIS_GIS',1,'ARCGIS','GIS','{"output":"GeoJSON FeatureCollection"}'::jsonb,'{"request":"service metadata"}'::jsonb,'{"requiredPins":["layerId"],"paged":true}'::jsonb,'{"required":["GIS","STRUCTURE","LICENSE","TEMPORAL"]}'::jsonb,'ACTIVE','system:v20-municipality-factory'),
 ('CKAN_MIXED',1,'CKAN','MIXED','{"output":"Pinned CKAN resource"}'::jsonb,'{"request":"package/resource metadata"}'::jsonb,'{"requiredPins":["resourceUrl"]}'::jsonb,'{"required":["GIS","LEGAL","STRUCTURE","LICENSE","TEMPORAL"]}'::jsonb,'ACTIVE','system:v20-municipality-factory'),
 ('HTML_DOCUMENT',1,'HTML','DOCUMENT','{"output":"HTML document"}'::jsonb,'{"request":"GET"}'::jsonb,'{"requiredPins":["parserProfile"]}'::jsonb,'{"required":["LEGAL","STRUCTURE","LICENSE","TEMPORAL"]}'::jsonb,'ACTIVE','system:v20-municipality-factory'),
 ('PDF_DOCUMENT',1,'PDF','DOCUMENT','{"output":"PDF document"}'::jsonb,'{"request":"GET"}'::jsonb,'{"requiredPins":["parserProfile"]}'::jsonb,'{"required":["LEGAL","STRUCTURE","LICENSE","TEMPORAL"]}'::jsonb,'ACTIVE','system:v20-municipality-factory'),
 ('ZIP_MIXED',1,'ZIP','MIXED','{"output":"ZIP archive"}'::jsonb,'{"request":"GET"}'::jsonb,'{"requiredPins":["archiveProfile"]}'::jsonb,'{"required":["GIS","LEGAL","STRUCTURE","LICENSE","TEMPORAL"]}'::jsonb,'ACTIVE','system:v20-municipality-factory')
ON CONFLICT(code,version) DO NOTHING;

COMMENT ON TABLE source.connector_contract IS 'Curated reusable connector contracts. New behavior creates a new version; municipality configuration pins an exact contract version.';
