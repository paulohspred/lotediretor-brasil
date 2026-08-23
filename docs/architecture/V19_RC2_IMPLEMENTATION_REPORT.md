# v19-rc.2 — Implementation report

## Objetivo

A RC2 aprofunda a fase de Site Solver do A.I TEC sem avançar artificialmente para Building/Unit Solver. O foco é substituir uma simplificação perigosa: “área estimada para vagas” por uma verificação geométrica explícita de estacionamento de superfície.

## Mudança de domínio

Antes, `parking_area()` informava um orçamento de m² e o Site Solver podia considerar `surface_parking_fit` a partir de área aberta agregada. Na RC2, o solver:

1. gera as massas;
2. cria área livre legal excluindo as massas e clearance;
3. testa orientações determinísticas de módulos de estacionamento;
4. gera polígonos de vagas e faixas de circulação;
5. mede capacidade geométrica real;
6. registra `parking_shortfall`;
7. aplica `PARKING_MIN` como hard constraint;
8. desconta a área impermeável efetiva do cálculo de TP;
9. serializa/persiste `PARKING_STALL` e `DRIVE_AISLE`.

## Segurança semântica

`VALIDATED_PRELIMINARY` continua significando somente que as hard constraints que esta fase sabe avaliar passaram. A RC2 não interpreta silêncio do motor como conformidade de garagem. Não resolve rampas, subsolos, pilares, regras PCD/EV, acesso viário, incêndio ou estrutura.

## Reprodutibilidade

A geração permanece determinística para o mesmo envelope/programa/seed. O layout de estacionamento não usa aleatoriedade adicional; portanto integra-se à reprodução por snapshot + seed + versão de solver.

## Persistência

A migration 194 já oferecia `aitec.geometry_object`; a RC2 reutiliza essa estrutura e diferencia objetos por `object_type`:

- `BUILDING_FOOTPRINT`
- `PARKING_STALL`
- `DRIVE_AISLE`

Não foi criada tabela paralela desnecessária para a geometria desta fase.

## Próximos solvers

A sequência prevista é:

1. access/road geometry;
2. estacionamento avançado (rampas/subsolo/pilares e classes de vaga quando houver regra explícita);
3. terrain/cut-fill;
4. Building Solver;
5. Unit Solver;
6. lock + regenerate e branching mais completos;
7. desempenho/financeiro/BIM.
