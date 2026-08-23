# Importação automática da v19-rc.3

O repositório já está preparado para importar automaticamente o pacote oficial **LoteDiretor SaaS v19-rc.3**.

## Única ação manual necessária

1. No GitHub, abra a página principal deste repositório na branch `main`.
2. Clique em **Add file → Upload files**.
3. Arraste o arquivo **`LoteDiretor_SaaS_v19_RC3_FULL.zip`** para a página.
4. Confirme em **Commit changes**, diretamente na branch `main`.

Não renomeie o ZIP.

## O que acontece automaticamente

O workflow `Bootstrap RC3 from ZIP` irá:

- confirmar o SHA-256 esperado do ZIP;
- testar a integridade do arquivo;
- extrair `LoteDiretor_SaaS_v19_RC3` para a raiz do repositório;
- confirmar `VERSION = 19.0.0-rc.3`;
- verificar integralmente `FILE_MANIFEST.sha256` no pacote extraído;
- remover o ZIP e este arquivo de instruções do estado final do repositório;
- criar um commit de baseline da RC3;
- criar a branch `develop` a partir desse baseline;
- criar a tag `v19-rc.3`;
- remover a branch temporária `import/rc3`, se existir.

O workflow temporário de bootstrap permanece somente até a conferência final. Depois da importação, ele será removido e o CI normal será mantido.

SHA-256 esperado:

`d82e19f6122bc6231da92a22c47ff7b07b287598762684fa2388218383368fab`

Se o hash não corresponder, a importação para sem alterar o baseline.
