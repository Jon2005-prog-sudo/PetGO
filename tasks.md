# Implementation Plan: Aplicativo de Resgate de Animais (animal-rescue-app)

## Overview

Este plano converte o design técnico (NestJS + TypeScript + PostgreSQL + Prisma, armazenamento de objetos S3-compatível, autenticação JWT com RBAC, testes com Jest + fast-check) em uma sequência de tarefas de codificação incrementais. A ordem prioriza o **backend**: primeiro o setup e os tipos de domínio, depois o schema de persistência, autenticação/RBAC e, em seguida, cada serviço de domínio (usuários/protetores, animais, denúncias/resgate, adoção, moderação, notificações, mídia), terminando com a fiação da API REST e os testes de integração do fluxo completo. Cada tarefa constrói sobre as anteriores e termina integrando o código ao sistema, sem deixar partes órfãs.

Convenções:
- Tarefas de teste (unitárias, property-based com fast-check e integração) estão marcadas como opcionais com `*`.
- As tarefas de cliente web/mobile são opcionais/posteriores e marcadas com `*`.
- Os testes property-based referenciam diretamente as 10 Correctness Properties do design.
- Checkpoints garantem validação incremental ("Garantir que os testes passam").

## Tasks

- [ ] 1. Setup do projeto e infraestrutura base
  - [ ] 1.1 Inicializar projeto NestJS com TypeScript e estrutura de módulos
    - Criar a aplicação NestJS (estrutura `src/`), configurar `tsconfig`, `eslint`/`prettier` e scripts de build
    - Criar os módulos vazios por domínio: `auth`, `users`, `animals`, `rescue`, `adoption`, `moderation`, `notifications`, `media`, `prisma`
    - Configurar carregamento de configuração/env (porta, segredos JWT, conexão PostgreSQL, credenciais do object storage)
    - _Requirements: 1.1, 1.3_

  - [ ] 1.2 Configurar Prisma e conexão PostgreSQL
    - Adicionar Prisma, criar `schema.prisma` inicial com datasource PostgreSQL e gerador do client
    - Implementar `PrismaService` injetável e registrar o `PrismaModule` global
    - _Requirements: 1.1_

  - [ ]* 1.3 Configurar framework de testes (Jest + fast-check)
    - Configurar Jest para testes unitários e e2e/integração, com suporte a TypeScript
    - Adicionar fast-check como dependência de testes de propriedade e criar um teste "smoke" de verificação
    - _Requirements: 1.1_

- [ ] 2. Tipos de domínio, tabelas de transição e validação de transições
  - [ ] 2.1 Definir enums e tipos de domínio
    - Declarar `Role`, `AnimalStatus`, `AdoptionStatus`, `ReportStatus`, `ApplicationStatus` e interfaces centrais (`Animal`, `AnimalFilter`, etc.) em um módulo de tipos compartilhado
    - _Requirements: 3.7, 1.1_

  - [ ] 2.2 Implementar tabelas de transição e funções puras de validação
    - Implementar `ANIMAL_TRANSITIONS` e `ADOPTION_TRANSITIONS` conforme o design
    - Escrever funções puras `isValidAnimalTransition(current, next)` e `isValidAdoptionTransition(current, next)` que consultam as tabelas e tratam estados terminais
    - _Requirements: 3.5, 3.6, 3.7, 6.5, 6.6_

  - [ ]* 2.3 Escrever property test para transições de estado do animal
    - **Property 2: Transições de estado do animal são sempre válidas**
    - **Validates: Requirements 3.5, 3.6, 3.7**

  - [ ]* 2.4 Escrever property test para transições de pedido de adoção
    - **Property 9: Transições de pedido de adoção são válidas**
    - **Validates: Requirements 6.5, 6.6**

- [ ] 3. Schema de banco de dados e migrações
  - [ ] 3.1 Modelar entidades no schema Prisma e gerar migração
    - Definir modelos `USER`, `ANIMAL`, `ANIMAL_PHOTO`, `ADOPTION_REQUEST`, `RESCUE_REPORT`, `PROTECTOR_APPLICATION`, `NOTIFICATION` com relações, enums e timestamps conforme o ER do design
    - Aplicar restrição de unicidade em `USER.email` e índices para campos de filtro de animal (`status`, `species`, `size`, `sex`, `locationCity`, `ageMonths`) e para `ANIMAL_PHOTO.order`
    - Gerar e aplicar a migração inicial
    - _Requirements: 1.2, 5.3, 5.5, 10.3_

  - [ ]* 3.2 Escrever teste de integração do schema e constraints
    - Validar unicidade de e-mail (inserção duplicada falha) e presença dos índices de filtro usando um PostgreSQL efêmero
    - _Requirements: 1.2, 5.3_

- [ ] 4. Autenticação e RBAC
  - [ ] 4.1 Implementar hashing de senha e emissão de tokens
    - Implementar hash seguro de senha (argon2/bcrypt) e serviço de assinatura/verificação de JWT de acesso e refresh token
    - _Requirements: 1.1, 1.3, 1.5_

  - [ ] 4.2 Implementar register/login/refresh no AuthService
    - `register`: criar conta com papel inicial `ADOPTER`, armazenar `passwordHash`; rejeitar e-mail duplicado com conflito sem criar conta
    - `login`: validar credenciais e emitir access + refresh token; credenciais inválidas não emitem tokens
    - `refresh`: emitir novo access token a partir de refresh válido
    - Garantir que nenhuma resposta exponha `passwordHash` (serialização/DTO de saída)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.8_

  - [ ] 4.3 Implementar guard de autenticação JWT e guard/decorator de RBAC
    - Implementar guard que valida JWT e popula o ator da requisição
    - Implementar `authorize`/`RolesGuard` com decorator de papéis; operação sem papel exigido é rejeitada com `403 Forbidden` sem efeitos colaterais
    - _Requirements: 1.6, 1.7_

  - [ ]* 4.4 Escrever property test para autorização por papel
    - **Property 8: Autorização por papel é respeitada**
    - **Validates: Requirements 1.6, 1.7, 2.6, 3.4, 4.6, 7.1, 8.4**

  - [ ]* 4.5 Escrever testes unitários de autenticação
    - Cobrir registro com papel `ADOPTER`, conflito de e-mail, login inválido, refresh válido e não exposição de `passwordHash`
    - _Requirements: 1.1, 1.2, 1.4, 1.5, 1.8_

- [ ] 5. Usuários e verificação de protetor
  - [ ] 5.1 Implementar perfil de usuário no UserService
    - `getProfile`: retornar dados de perfil sem expor dados sensíveis de autenticação
    - `updateProfile`: persistir atualização válida e retornar perfil atualizado
    - _Requirements: 2.1, 2.2_

  - [ ] 5.2 Implementar solicitação e decisão de verificação de protetor
    - `requestProtectorVerification`: criar `ProtectorApplication` com status `PENDING` e documentos
    - `decideProtectorVerification`: exigir papel `ADMIN`; `APPROVE` define `APPROVED` e promove o usuário a `PROTECTOR`; `REJECT` define `REJECTED`, registra motivo e mantém o papel; ator sem `ADMIN` é rejeitado sem efeitos colaterais
    - Publicar evento de resultado de verificação direcionado ao usuário solicitante
    - _Requirements: 2.3, 2.4, 2.5, 2.6_

  - [ ]* 5.3 Escrever testes unitários de usuários e verificação
    - Cobrir atualização de perfil, criação de aplicação `PENDING`, aprovação com promoção de papel, rejeição com motivo e bloqueio de não-admin
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [ ] 6. Animais e ciclo de vida
  - [ ] 6.1 Implementar criação e atualização de animal
    - `createAnimal`: permitir apenas a protetor verificado; associar `protectorId`; rejeitar `description` vazia com erro de validação
    - `updateAnimal`: permitir apenas ao protetor dono ou admin; rejeitar ator não autorizado sem efeitos colaterais
    - `getAnimal`: retornar animal por id
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [ ] 6.2 Implementar changeAnimalStatus com validação de transição
    - Permitir apenas protetor dono ou admin; persistir somente quando `next ∈ ANIMAL_TRANSITIONS[status]`; caso contrário rejeitar com `INVALID_TRANSITION` sem gravar
    - Garantir que o status persistido seja sempre um valor válido do enum e que `AVAILABLE` só exista com `protectorId` de protetor verificado
    - _Requirements: 3.4, 3.5, 3.6, 3.7, 3.8_

  - [ ] 6.3 Implementar listAvailable com filtros e paginação
    - Retornar somente animais `AVAILABLE`; aplicar filtros `species`, `size`, `sex`, `locationCity`, `ageMonthsMax`; rejeitar `ageMonthsMax` negativo; retornar itens da página e total
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ]* 6.4 Escrever property test para listagem pública
    - **Property 1: Listagem pública expõe apenas animais disponíveis**
    - **Validates: Requirements 5.1, 5.2**

  - [ ]* 6.5 Escrever property test para protetores verificados publicarem animais
    - **Property 7: Apenas protetores verificados publicam animais**
    - **Validates: Requirements 2.4, 3.1, 3.8**

  - [ ]* 6.6 Escrever testes unitários de animais
    - Cobrir rejeição de `description` vazia, bloqueio de não-dono, transição inválida e aplicação de filtros/paginação
    - _Requirements: 3.2, 3.4, 3.6, 5.3, 5.4_

- [ ] 7. Checkpoint - Garantir que os testes passam
  - Garantir que todos os testes passam, perguntar ao usuário se surgirem dúvidas.

- [ ] 8. Denúncias e resgate
  - [ ] 8.1 Implementar reportAnimal com validação de entrada
    - Criar `RescueReport` com status `OPEN` quando descrição não vazia, coordenadas válidas e fotos; rejeitar `latitude` fora de [-90, 90] ou `longitude` fora de [-180, 180]; rejeitar descrição vazia
    - _Requirements: 4.1, 4.2, 4.3_

  - [ ] 8.2 Implementar listOpenReports e assumeRescue
    - `listOpenReports`: retornar apenas denúncias `OPEN` com filtros e paginação
    - `assumeRescue`: permitir apenas protetor verificado; criar/vincular animal com status inicial `NEEDS_RESCUE`/`IN_RESCUE` e marcar a denúncia como `ASSUMED`; rejeitar ator sem papel `PROTECTOR` sem efeitos colaterais
    - _Requirements: 4.4, 4.5, 4.6_

  - [ ]* 8.3 Escrever testes unitários de denúncias/resgate
    - Cobrir validação de coordenadas/descrição, listagem apenas de `OPEN` e bloqueio de não-protetor em `assumeRescue`
    - _Requirements: 4.2, 4.3, 4.5, 4.6_

- [ ] 9. Adoção com máquina de estados
  - [ ] 9.1 Implementar createRequest com regras de disponibilidade e unicidade
    - Criar `AdoptionRequest` com status `SENT` apenas para animal `AVAILABLE`, mantendo o animal em `AVAILABLE`; rejeitar com `ANIMAL_NOT_AVAILABLE` se indisponível; rejeitar se já existir pedido ativo (`SENT`/`UNDER_REVIEW`) do mesmo adotante para o mesmo animal
    - Publicar evento de domínio `ADOPTION_REQUEST_CREATED` direcionado ao protetor dono
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ] 9.2 Implementar cancelRequest e transições de status
    - `cancelRequest`: adotante cancela o próprio pedido em `SENT`/`UNDER_REVIEW` definindo `CANCELLED`
    - Validar toda mudança de status contra `ADOPTION_TRANSITIONS`; proibir transição a partir de estados terminais
    - _Requirements: 6.5, 6.6, 6.7_

  - [ ] 9.3 Implementar reviewRequest com aprovação transacional e auto-rejeição
    - Autorizar apenas protetor dono ou admin; exigir pedido em `SENT`/`UNDER_REVIEW`
    - `APPROVE` (animal `AVAILABLE`): em uma única transação, definir pedido `APPROVED`, auto-rejeitar os demais pedidos pendentes do animal (`REJECTED`) e marcar o animal `ADOPTED`
    - `REJECT`: definir apenas o pedido alvo como `REJECTED`, mantendo o animal `AVAILABLE`
    - Tratar concorrência via precondição `animal.status === "AVAILABLE"`: a segunda aprovação concorrente falha com erro de conflito
    - Publicar eventos de decisão para os adotantes afetados
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8_

  - [ ] 9.4 Implementar listRequestsForAnimal e listRequestsByAdopter
    - Retornar pedidos por animal e por adotante para acompanhamento
    - _Requirements: 6.1, 6.7_

  - [ ]* 9.5 Escrever property test para disponibilidade na criação de pedido
    - **Property 5: Pedidos de adoção só existem para animais disponíveis na criação**
    - **Validates: Requirements 6.1, 6.2**

  - [ ]* 9.6 Escrever property test para unicidade de pedido ativo
    - **Property 6: Unicidade de pedido ativo por adotante e animal**
    - **Validates: Requirements 6.3**

  - [ ]* 9.7 Escrever property test para exclusividade de aprovação por animal
    - **Property 3: Aprovação de adoção é mutuamente exclusiva por animal**
    - **Validates: Requirements 7.3, 7.4**

  - [ ]* 9.8 Escrever property test para aprovação implicar animal adotado
    - **Property 4: Aprovação implica animal adotado**
    - **Validates: Requirements 7.3, 7.5**

  - [ ]* 9.9 Escrever testes unitários de adoção
    - Cobrir `ANIMAL_NOT_AVAILABLE`, pedido ativo duplicado, cancelamento válido, rejeição mantendo `AVAILABLE` e bloqueio de revisor não autorizado
    - _Requirements: 6.2, 6.3, 6.7, 7.1, 7.2, 7.6_

- [ ] 10. Moderação e administração
  - [ ] 10.1 Implementar listPendingProtectorApplications
    - Retornar `ProtectorApplication` com status `PENDING` de forma paginada (apenas admin)
    - _Requirements: 8.1_

  - [ ] 10.2 Implementar flagContent e resolveFlag
    - `flagContent`: registrar `ModerationFlag` associada ao alvo com motivo
    - `resolveFlag`: exigir papel `ADMIN`; aplicar ação (ex.: ocultar animal definindo `UNAVAILABLE`, suspender usuário) e atualizar a sinalização; ator sem `ADMIN` é rejeitado sem efeitos colaterais
    - _Requirements: 8.2, 8.3, 8.4_

  - [ ]* 10.3 Escrever testes unitários de moderação
    - Cobrir listagem paginada de pendentes, registro de flag, aplicação de ação e bloqueio de não-admin em `resolveFlag`
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [ ] 11. Notificações assíncronas
  - [ ] 11.1 Implementar emissão e consumo de eventos de domínio
    - Definir o barramento/fila de eventos de domínio e o consumidor em `NotificationService.onDomainEvent`
    - Criar notificação direcionada exatamente ao usuário afetado para: novo pedido (protetor dono), decisão de adoção (adotante afetado) e resultado de verificação (solicitante); não endereçar a usuários não afetados
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [ ] 11.2 Implementar listForUser e markRead
    - `listForUser`: retornar apenas notificações do próprio usuário, paginadas
    - `markRead`: atualizar o campo `read` de notificação própria
    - _Requirements: 9.5, 9.6_

  - [ ]* 11.3 Escrever property test para destinatários de notificações
    - **Property 10: Notificações são entregues aos destinatários corretos**
    - **Validates: Requirements 9.1, 9.2, 9.3, 9.4**

  - [ ]* 11.4 Escrever testes unitários de notificações
    - Cobrir listagem restrita ao próprio usuário e marcação de leitura
    - _Requirements: 9.5, 9.6_

- [ ] 12. Upload e gestão de mídia
  - [ ] 12.1 Implementar cliente de object storage e upload de fotos
    - Implementar adaptador S3-compatível para upload; persistir apenas URLs/metadados no banco
    - Integrar o upload ao cadastro de animal e de denúncia; em falha de storage, reverter a operação de cadastro associada (transação) e não persistir URLs inválidas nem cadastros parciais
    - _Requirements: 10.1, 10.2, 10.4_

  - [ ] 12.2 Implementar addPhotos preservando a ordem
    - `addPhotos`: permitir ao protetor dono adicionar fotos a animal existente, associando-as preservando a ordem informada
    - _Requirements: 10.3_

  - [ ]* 12.3 Escrever testes unitários/integração de mídia
    - Cobrir reversão do cadastro em falha de upload e preservação de ordem em `addPhotos`
    - _Requirements: 10.2, 10.3, 10.4_

- [ ] 13. Checkpoint - Garantir que os testes passam
  - Garantir que todos os testes passam, perguntar ao usuário se surgirem dúvidas.

- [ ] 14. Fiação da API REST e integração do fluxo completo
  - [ ] 14.1 Implementar controllers e rotas REST com guards de RBAC
    - Expor rotas para auth, usuários/protetores, animais, denúncias, adoção, moderação, notificações e mídia, aplicando `JwtGuard`/`RolesGuard` por operação sensível e DTOs de saída que ocultam `passwordHash`
    - Conectar todos os serviços já implementados ao HTTP layer, sem deixar código órfão
    - _Requirements: 1.6, 1.7, 1.8_

  - [ ]* 14.2 Escrever teste de integração do fluxo completo
    - Com PostgreSQL efêmero, validar o fluxo denúncia → resgate → disponibilização → adoção de ponta a ponta
    - _Requirements: 4.1, 4.4, 3.5, 5.1, 6.1, 7.3_

  - [ ]* 14.3 Escrever teste de integração de concorrência de aprovação
    - Reproduzir duas aprovações concorrentes do mesmo animal; verificar que apenas a primeira conclui e a segunda falha com conflito, mantendo no máximo um `APPROVED` e o animal `ADOPTED`
    - _Requirements: 7.3, 7.4, 7.5, 7.7_

- [ ] 15. Checkpoint final - Garantir que os testes passam
  - Garantir que todos os testes passam, perguntar ao usuário se surgirem dúvidas.

- [ ]* 16. Clientes web e mobile (opcional/posterior)
  - [ ]* 16.1 Implementar cliente web (Next.js)
    - Consumir a API REST: autenticação, vitrine pública filtrável, detalhe do animal, pedido de adoção, reporte de resgate e painéis de protetor/admin
    - _Requirements: 5.1, 5.3, 6.1, 4.1_

  - [ ]* 16.2 Implementar cliente mobile (React Native/Expo)
    - Reaproveitar a camada de API para fluxos de campo: reporte de resgate, acompanhamento de pedidos e notificações
    - _Requirements: 4.1, 6.1, 9.5_

## Notes

- As tarefas marcadas com `*` são opcionais e podem ser puladas para um MVP mais rápido (testes unitários, property-based e de integração, além dos clientes web/mobile).
- Cada tarefa referencia requisitos específicos para rastreabilidade.
- Os testes property-based mapeiam diretamente as 10 Correctness Properties do design (fast-check).
- Os checkpoints asseguram validação incremental em pontos naturais de corte.
- A biblioteca de property-based testing é fast-check; os testes de integração usam PostgreSQL efêmero.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "2.1"] },
    { "id": 2, "tasks": ["2.2", "3.1"] },
    { "id": 3, "tasks": ["2.3", "2.4", "3.2", "4.1"] },
    { "id": 4, "tasks": ["4.2", "4.3"] },
    { "id": 5, "tasks": ["4.4", "4.5", "5.1", "5.2", "6.1"] },
    { "id": 6, "tasks": ["5.3", "6.2", "8.1"] },
    { "id": 7, "tasks": ["6.3", "8.2", "9.1"] },
    { "id": 8, "tasks": ["6.4", "6.5", "6.6", "8.3", "9.2", "10.1", "10.2", "11.1", "12.1"] },
    { "id": 9, "tasks": ["9.3", "9.4", "10.3", "11.2", "12.2"] },
    { "id": 10, "tasks": ["9.5", "9.6", "9.7", "9.8", "9.9", "11.3", "11.4", "12.3"] },
    { "id": 11, "tasks": ["14.1"] },
    { "id": 12, "tasks": ["14.2", "14.3", "16.1", "16.2"] }
  ]
}
```
