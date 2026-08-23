# ADR-013 — Transactional Outbox + NATS JetStream

**Status:** accepted — v14

Eventos derivados de mudanças de estado não são publicados diretamente durante a request. A mesma transação grava o dado de negócio e `event.outbox`. Um dispatcher dedicado publica no JetStream e confirma o outbox somente após ACK persistente.

Razões: evitar dual-write, preservar reprocessamento, permitir consumidores independentes e manter o modular monolith extraível por eventos.
