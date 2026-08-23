# V19 Beta — Implementation Report

## Objective

Close safety and reproducibility gaps in the territorial/legal/AI core before increasing product breadth.

## Legal / territorial changes

- `legal.rule.condition` is now reserved for executable applicability conditions.
- parser provenance is stored separately in `legal.rule.extraction_metadata`.
- `legal.rule.source_article_id` links a rule candidate/confirmed rule back to the parsed article when available.
- rule applicability supports explicit logical/comparison operators and returns `MATCH`, `NO_MATCH` or `UNKNOWN`.
- an applicable confirmed-rule conflict is exposed and blocks the affected automatic calculation.
- a confirmed conditional rule whose required technical context is missing forces analysis `NEEDS_REVIEW`.
- deterministic calculations were expanded beyond CA/TO/TP where a confirmed applicable numeric rule exists.
- `planning.zone_use_permission` creates a dedicated path for use permissions rather than overloading numeric urban parameters.

## AI Core changes

- lexical BM25 and optional vector retrieval remain tenant/ACL scoped before retrieval.
- a `baseDate` adds `valid_from`/`valid_to` filters to evidence retrieval.
- RRF fusion is followed by deterministic term-coverage reranking.
- conditional legal rules are grounding only when their condition evaluation is `MATCH`.
- a provider response citing an evidence ID outside the allowed retrieved/verified context is rejected.
- document-version validity is propagated into the evidence index.

## Source/data changes

- WFS ingestion requests output CRS explicitly and validates coordinate ranges before publishing WGS84 geometry.
- source access modes distinguish REST/WFS/CKAN-SHP/authenticated Conecta instead of pretending all sources are generic GeoJSON.
- SIGEF is kept out of generic public ingestion and remains an authenticated institutional connector.
- PRODES WFS requires a pinned reviewed `typeName` before activation.
- São Paulo keeps exact core-layer mapping separate from live ingestion/homologation.
- golden-lot selection creates candidate cases only; no case can become PASS without human review.

## Release policy

`19.0.0-beta.1` passes the static/domain/contract gate in `validate-v19-beta.sh`. It does not claim runtime or production homologation. The release cannot be promoted until reproducible npm build, real DB migrations, live source ingestion, runtime E2E and security/operational gates have been executed.
