# Rural Monitor Worker — v18

Executa automaticamente os monitores `ACTIVE`, compara registros normalizados e feições de snapshots publicados contra o último checkpoint, gera `rural.monitor_event`, notificação e evento outbox somente quando o hash do estado muda. Não classifica PRODES como infração nem converte mudança cadastral em conclusão jurídica.
