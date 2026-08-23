# LoteDiretor v19-rc.3 — relatório de implementação

## 1. Objetivo da RC3

A RC3 fecha o próximo incremento do núcleo definido pelo Blueprint: tornar A.I TEC mais geometry-aware e reproduzível, avançar Solar sem inventar engenharia, reforçar persistência/tenant boundaries e remover impedimentos artificiais do pipeline municipal de São Paulo.

## 2. A.I TEC

### 2.1 Site, acesso e viário conceitual
`services/aitec-engine/app/domain.py` incorpora `generate_access_road_layout`. A entrada exige `access_point`; o ponto pode ser ajustado à borda apenas dentro de tolerância controlada. O algoritmo testa conexão direta e dogleg ortogonal, gera centerline + buffer de road e rejeita colisão com footprints. A ausência de acesso não é preenchida por inferência.

### 2.2 Parking
O parking de superfície da RC2 permanece como geometria explícita. `PARKING_MIN` é hard constraint; shortfall impede status validado preliminar. A área impermeável usada na TP é a união geométrica de footprint/parking/road.

### 2.3 Lock, branch e regenerate
A API permite registrar locks em `aitec.solution_lock`. Ao ramificar, footprints `BUILDING_FOOTPRINT` travados são carregados da solução pai, convertidos para o CRS do solver e reinseridos invariavelmente antes da geração dos objetos livres. A nova solução registra `parent_solution_id` e evento de domínio.

### 2.4 Programa / unit mix
`allocate_unit_mix` trabalha com tipos explicitamente informados (`target_area_m2`, limites de quantidade e share). Mínimos de tipo e `min_total_units` funcionam como program gate. É um alocador conceitual de mix, não um Unit Solver de planta.

### 2.5 Terrain / cut-fill
`estimate_cut_fill_from_samples` só trabalha quando recebe amostras métricas XYZ suficientes. Usa elevação de platô conceitual e estima volumes por ponderação de área. Não representa TIN, geotecnia, drenagem ou terraplenagem executiva.

### 2.6 Building Stack
`solve_building_stack` deriva floor plate, core e faixa de circulação conceitual para os footprints. Calcula áreas e objetos geométricos, mas ainda não valida incêndio, acessibilidade normativa, estrutura, shafts ou plantas.

### 2.7 Persistência e export
Migration `195_v19_rc3_aitec_deepening.sql` adiciona integridade tenant-aware, `aitec.analysis_result` e associação de artefato a solution. A Platform API persiste análises TERRAIN_CUT_FILL/BUILDING_STACK e exporta solução em GeoJSON e quadro de métricas CSV para object storage.

## 3. Energia Solar

`electrical_string_design` exige parâmetros elétricos explícitos do módulo e inversor. Calcula Voc/Vmp com temperatura, número possível de módulos/string, distribuição por MPPT, corrente e relação DC/AC. Se algum parâmetro essencial está ausente, retorna `REQUIRES_INPUT`.

Migration `196_v19_rc3_solar_electrical.sql` adiciona `solar.electrical_design` com RLS/FORCE RLS e provenance. A mesma migration corrige a semântica de unicidade da tabela `solar.regulation_snapshot`: PostgreSQL permite múltiplos `NULL` em unique tradicional, então a RC3 usa índices parciais separados para escopo global e tenant.

## 4. São Paulo / Source Pipeline

O profile mantém lote fiscal `geoportal:lote_cidadao` e zoneamento `geoportal:perimetro_zona_lei_18177_24`, com CRS nativo registrado e pedido WFS em EPSG:4326. A publicação continua dataset-scoped antes da promoção canônica.

Foi corrigido o tooling de inspeção: HTTP/WFS pode ser inspecionado sem PostgreSQL, driver ou `PLATFORM_DATABASE_URL`. DB dependencies são lazy e obrigatórias somente em bootstrap/sync/promotion. A tentativa live neste ambiente falhou em DNS externo, portanto não houve ingestão fictícia nem alteração do status para homologado.

## 5. Validação

A RC3 adiciona testes específicos para:
- acesso/road sem colisão e lock invariance;
- branch com alternativas hard-valid;
- program/unit mix com shortfall explícito;
- terreno flat/sloped por amostras;
- Building Stack/core containment;
- Solar electrical missing-input e explicit-datasheet paths;
- inspeção municipal sem dependência de DB.

O gate também retém as regressões antigas e checagens estáticas de migrations/versões/CI.

## 6. Gates que permanecem externos

A RC3 não substitui evidência de runtime. Permanecem obrigatórios: npm lock/install/build, PostgreSQL/PostGIS real, RLS cross-tenant, Docker E2E, OpenSearch/model providers reais, GeoSampa live + golden lots, navegador/a11y, segurança/carga/canary e DR.

## 7. Próxima profundidade técnica

A sequência tecnicamente mais segura é: homologar o núcleo em runtime e São Paulo ponta a ponta; depois aprofundar A.I TEC com garagem avançada/TIN/Unit Solver e Solar com imagery/DSM/shadows/tariff/OCR/grid/calibration. Isso evita ampliar superfície funcional sobre dados e gates ainda não homologados.
