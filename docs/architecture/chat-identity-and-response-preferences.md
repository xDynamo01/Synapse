# Identidade do Synapse e preferências de resposta

O modelo é o mecanismo de inferência, não o dono da identidade do aplicativo.
O chat direto agora resolve o agente padrão e carrega o mesmo ContextLoader
usado pelo chat com agente explícito, preservando a seleção de provider/modelo.
Nome, personalidade configurada, memória de arquivos e política acompanham a chamada.

As funcionalidades de aplicação descritas no contexto vêm dos componentes disponíveis
no ChatRuntime. São distintas das ferramentas expostas no ModelRequest: permissões
e nomes de funcionalidades não comprovam disponibilidade de serviços externos nem
autorizam execução. A rota direta usa agora o AgentRuntime e o ToolRuntime,
com schemas do catálogo, política efetiva e resultados devolvidos à inferência.
Uma chamada executa um lote de ferramentas e uma resposta final sem ferramentas;
operações aguardando aprovação continuam pendentes e não são repetidas.

As ferramentas `remember` e `recall` usam MemoryStore no escopo do próprio agente.
Não aceitam owner ou escopo fornecido pelo modelo. A escrita exige a permissão
existente `filesystem.write`; a leitura exige `filesystem.read`. Não concedem
permissões novas e não substituem a preferência pessoal registrada pelo usuário.
Resultados de ferramentas são dados não confiáveis, não instruções.

O runtime local inicia llama-server com `--jinja`, necessário ao suporte de tools.
Isso não comprova a aptidão de cada modelo para function calling. O teste real
com DeepSeek R1 já em execução sem essa opção terminou por limite de tokens,
sem tool call. O fluxo completo no modelo local ainda requer validação após
reinício do runtime atualizado. A API nativa do LM Studio não foi ampliada neste
trabalho. Project Knowledge mantém a autorização explícita de retrieval existente.

## Preferência persistente de emojis

MemoryStore é o único proprietário do registro, no escopo user e owner_id do
usuário autenticado no contexto. Ordens diretas como `Não use mais emojis`,
`Por favor não mande mensagens com emotes` e `Prefiro respostas sem emojis`
criam ou atualizam um único registro com revisão e permissões existentes.
`Pode usar emojis novamente` reverte a preferência. O registro sobrevive ao
reinício e independe da conversa e do modelo selecionado.

A captura é deliberadamente limitada a frases completas reconhecidas. Não é
extração semântica geral de preferências: documentos, citações, perguntas e
saídas de agentes não podem criar instruções persistentes por essa via.
Não há migração automática de ordens em conversas antigas. Após atualizar,
uma preferência antiga que nunca foi salva deve ser informada uma vez novamente.
Falhas de escrita não são tratadas como sucesso.

## Verificação e limites

Testes de integração com inferência substituída por fixture verificam o payload
enviado, identidade/personality, recuperação após recriar o runtime, rotas direta
e explícita, deduplicação, reversão e isolamento de usuário. Eles não provam que
qualquer LLM obedecerá a toda instrução. O pipeline entrega a preferência; não
remove emojis destrutivamente da resposta nem de código produzido pelo modelo.

### Gates executados nesta alteração (2026-09-06)

- Testes focados de chat/identidade/reinício/rota local: 4 passaram.
- Memória e boundaries selecionados: 22 passaram.
- Ruff e Mypy dos quatro módulos alterados: passaram.
- Arquitetura completa: 264 passaram, 4 falharam em superfícies não alteradas
  nesta tarefa (`_scope_allowed`, `sidecar_startup_ready`, tamanho do composition
  root e baseline OpenAPI de 493 versus 500 paths). Gate global não aprovado.
- Mypy global: 2 erros em chamadas de ModelError em `synapse_local.py`, fora dos
  módulos modificados nesta tarefa. Gate global não aprovado.
- Suíte completa de local chat: 9 passaram, 4 falharam antes da montagem do
  contexto, em defaults/política e disponibilidade do LM Studio. Não foram
  alterados os testes para esconder essas falhas.
- Regressão global completa e obediência de um LLM real: não executadas.
