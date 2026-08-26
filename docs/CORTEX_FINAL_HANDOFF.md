# Cortex — handoff final para correção e publicação

Este documento é o ponto de entrada final para o Cortex. O branch de trabalho é `feature/v20-pre-cortex-quality-gates` (PR #68).

## Regra principal

Não obter PASS removendo ou enfraquecendo RLS, ACL tenant/public/temporal, legal hold, provenance, high-risk grounding, axe, carga, fault injection, Trivy, observabilidade, DR ou gates de release. Corrija a causa do erro e repita o gate.

`productionHomologated=false` continua obrigatório durante toda a qualificação local.

## 1. Preparar checkout limpo

```bash
git fetch --all --prune
git checkout feature/v20-pre-cortex-quality-gates
git pull --ff-only
git status --porcelain
```

O último comando deve ficar vazio antes de iniciar uma rodada de qualificação.

## 2. Rodar a qualificação curta

```bash
TRIVY_PULL=1 bash ops/cortex/qualify-local.sh ci
```

O harness cria uma stack Docker limpa, executa migrations, smoke, RLS, LGPD, Municipality Factory, AI/OpenSearch, AI red-team, quatro jornadas browser críticas, axe, security baseline, Trivy, k6, fault injection, observabilidade e backup/restore/DR local.

Em falha, a stack permanece rodando por padrão. Use os artefatos em `runtime-artifacts/cortex/<timestamp>/` e os logs da stack para corrigir o primeiro erro real.

Depois de qualquer alteração de código:

```bash
git add -A
git commit -m "fix(cortex): <causa corrigida>"
TRIVY_PULL=1 bash ops/cortex/qualify-local.sh ci
```

Não reutilize evidência de commit anterior.

## 3. Depois do `ci` PASS

Rode no **mesmo commit limpo**:

```bash
TRIVY_PULL=1 bash ops/cortex/qualify-local.sh soak
TRIVY_PULL=1 bash ops/cortex/qualify-local.sh capacity
```

Qualquer correção feita depois de um desses perfis invalida os três para fins de publicação. Nesse caso, rode novamente `ci`, `soak` e `capacity` no novo commit.

## 4. Verificar readiness de publicação local

Depois dos três perfis PASS:

```bash
python3 ops/cortex/publish-readiness.py --require-local
cat runtime-artifacts/cortex/publish-readiness.json
```

O resultado só libera `readyToMergeDevelop=true` quando:

- `ci`, `soak` e `capacity` têm `localQualificationStatus=PASS`;
- os três artefatos pertencem ao mesmo commit;
- o checkout estava limpo em cada evidence manifest;
- o commit qualificado é o HEAD atual.

Esse gate **não** libera produção. Sem evidência externa, `readyToPublishProduction=false` e `productionHomologated=false` são o resultado correto.

## 5. Publicar correções no PR

Após `readyToMergeDevelop=true`:

```bash
git push origin feature/v20-pre-cortex-quality-gates
```

O PR #68 deve então executar, com steps reais, os workflows:

- `ci`;
- `runtime-e2e`;
- `security-scan`;
- `homologation-contract`.

Falha do GitHub com `steps=[]`/sem logs é problema de alocação do runner e não conta como teste executado. Não converta isso em PASS.

Quando os workflows realmente executarem e ficarem verdes, o PR pode ser mergeado em `develop`.

## 6. Publicação em produção — gate separado

Publicação em produção só pode ser considerada quando os artefatos próprios estiverem promovidos por digest e assinados/atestados, e quando o bundle externo `lotediretor-production-homologation-v1` estiver completo.

Verificação de assinatura/provenance do candidato:

```bash
VERIFY_RELEASE_SIGNATURES=true \
COSIGN_PUBLIC_KEY=/path/to/cosign.pub \
bash ops/release/gate.sh
```

Alternativamente, use identidade keyless configurando `COSIGN_CERTIFICATE_IDENTITY` e `COSIGN_CERTIFICATE_OIDC_ISSUER`.

O release gate verifica assinatura e attestation `slsaprovenance1` dos mesmos `image@sha256` usados no deploy.

Depois de reunir evidências reais, copie e preencha — sem fixtures — o modelo:

`docs/ops/PRODUCTION_HOMOLOGATION_EVIDENCE.example.json`

Os nove gates externos obrigatórios são:

1. pentest independente e remediação;
2. red-team do provider/modelo real de IA;
3. staging production-like implantado;
4. assinatura/provenance dos artefatos de release;
5. canary/rollback real;
6. HA/PITR/DR de produção com RPO/RTO reais;
7. fontes/providers oficiais e respectivas licenças/credenciais;
8. revisões profissionais/institucionais aplicáveis;
9. proteção administrativa de `main`.

O bundle final deve apontar exatamente para o commit e digests publicados e possuir owner, timestamp e referência de evidência para cada gate.

Validação final:

```bash
PRODUCTION_HOMOLOGATION_EVIDENCE=/path/to/production-homologation.json \
PRODUCTION_HOMOLOGATED=true \
bash ops/security/production-security-gate.sh

PRODUCTION_HOMOLOGATION_EVIDENCE=/path/to/production-homologation.json \
python3 ops/cortex/publish-readiness.py --require-production
```

Somente o segundo comando terminando em PASS autoriza `readyToPublishProduction=true` e `productionHomologated=true`.

## 7. Invariantes que Cortex não pode alterar para obter PASS

- tráfego normal não usa owner/migration DB role;
- RLS e tenant isolation permanecem ativos;
- AI privada nunca cruza tenant; dados públicos exigem opt-in e vigência temporal;
- resposta legal high-risk sem fonte confirmada deve abster/rebaixar, nunca inventar;
- Município/Factory candidate não vira regra confirmada sem revisão humana;
- erasure LGPD respeita legal hold e preserva audit/legal/provenance;
- ausência de fonte/provider não significa ausência de ocorrência;
- OpenSearch single-node local pode ficar `yellow`; não declarar HA/green de produção por isso;
- fixtures sintéticos não são dados oficiais;
- `main` precisa de proteção administrativa real;
- `productionHomologated` não pode ser alterado manualmente para contornar os gates.

## Definição de conclusão do trabalho do Cortex

O ciclo local termina quando o mesmo commit limpo tem `ci`, `soak` e `capacity` PASS, `publish-readiness.py --require-local` passa e os workflows GitHub executados realmente ficam verdes. Depois disso, o PR #68 está tecnicamente pronto para merge em `develop`.

A publicação de produção continua sendo uma etapa separada e só termina após `publish-readiness.py --require-production` PASS com evidência real dos nove gates externos.
