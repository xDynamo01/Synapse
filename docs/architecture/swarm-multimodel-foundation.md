# Swarm: base de execução multimodelo

## Decisão — 2026-09-06

O Synapse governa agentes, memória, permissões e tarefas; modelos fornecem inferência.
Vários agentes não exigem vários modelos residentes. Começar com agentes que
compartilham um modelo reduz consumo e permite validar coordenação antes de
aumentar o paralelismo físico. ModelRouter já admite modelo/provider por agente.
SwarmRuntime, estratégias e workforce planner já existem; não foram substituídos.

Consulta primária: [arquitetura do llama-server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README-dev.md).
A documentação distingue slots de requisições paralelas no mesmo modelo de
instâncias de inferência separadas para modelos diferentes. O router nativo é
uma alternativa futura; sua compatibilidade com o binário instalado não foi
atestada, portanto não houve atualização ou integração de dependência.

## Slice implementado

Arquivos: `backend/synapse/model_providers/synapse_local.py` e
`tests/test_synapse_local_concurrency.py`; sem mudanças de UI ou APIs públicas.

- Um processo por nome canônico de modelo (nome e nome.gguf compartilham processo).
- Limite padrão: um modelo residente. Configuração de processo opcional:
  `SYNAPSE_LOCAL_MAX_LOADED_MODELS=2`, antes de iniciar o backend. Valores fora
  de 1–2 são rejeitados. Nenhuma variável real do computador foi alterada.
- Com limite dois, modelos diferentes podem gerar simultaneamente; inicializações
  são serializadas. Cada processo permanece com um slot de inferência.
- Pedidos ao mesmo modelo aguardam sua liberação, sem carregamento duplicado.
- Só modelos ociosos podem ser descarregados para abrir espaço. Confirma-se saída
  do processo antes de admitir substituto. Não há garantia de ordem FIFO.
- Espera por capacidade/carregamento consome o prazo do pedido. O tempo restante
  é passado ao transporte; não é garantia de interrupção física de uma inferência
  após timeout HTTP. Cancelamento por geração continua pendente.
- Falha de geração libera a reserva; falha de carregamento tenta parar/recolher o
  processo e mantém referência se a parada falhar. Shutdown impede reabertura.
- Identidade, contexto, provider e modelo de cada pedido são preservados.

O limite de quantidade não é orçamento de RAM/VRAM. Na inspeção havia cerca de
16 GiB de RAM total e 7,3 GiB livre; não foi iniciado teste com dois GGUF reais.
O padrão um foi mantido. O tamanho do arquivo sozinho não mede consumo de
inferência: contexto, buffers e backend também importam.

## Próxima sequência

1. Configuração por papel: coordenador (Primary), executor e revisor, reutilizando
   seleção por agente já existente. Separar modelo escolhido de modelo carregado.
2. Admissão por recursos: orçamento RAM/VRAM e concorrência global entre providers,
   sem alterar silenciosamente o modelo escolhido pelo usuário.
3. Uma execução explícita, limitada, com tarefas independentes e síntese do Primary.
   Compartilhar saídas como dados com origem, não como novas instruções superiores.
4. Cancelamento por tarefa e orçamento de turnos/tempo/ferramentas. Falha ou estado
   externo desconhecido exige reconciliação, nunca repetição automática de efeitos.
5. Projetar agentes/modelos realmente usados na Constelação. Não criar nós fictícios
   e não iniciar swarm invisível no chat comum.

## Limites de entrega

Decisão posterior (2026-09-06): MoM é exclusivo do Primary Agent e separado do
Swarm, que conserva um modelo atribuído por agente. A primeira implementação e
seus limites estão em [Primary MoM](primary-mom.md).

Testes usam processos e transporte substituídos por fixtures e barreiras reais
entre threads; provam coordenação do adaptador, não desempenho ou capacidade de
dois modelos reais nesta máquina. Esta base não constitui um swarm funcional
completo nem libera autonomia ou novas ferramentas.

### Gates desta entrega

- Concorrência e telemetria: 11 testes passaram; chat selecionado também passou
  (rodada combinada anterior: 20 passaram, 4 casos de configuração LM Studio
  não selecionados, já falhos e registrados na etapa anterior).
- Ruff local e Mypy global (793 arquivos): passaram.
- Arquitetura: 264 passaram, mesmas 4 falhas previamente observadas em helpers
  de API, resolução de runtime, tamanho do composition root e baseline OpenAPI.
  Esses módulos não foram modificados nesta etapa; backend global segue NOT READY.
- Build do backend concluído e presença do pool conferida no executável empacotado.
  O build anterior do destino governado foi substituído pelo processo normal de
  build; nenhuma pasta de modelos ou workspace de backup foi alterada.
- Diff check passou. Sem commit, push, nova dependência ou teste com LLM real.
