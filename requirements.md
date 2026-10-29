# Requirements Document

Aplicativo de Resgate de Animais (animal-rescue-app)

## Introduction

O **animal-rescue-app** é uma plataforma web/mobile que conecta visitantes, adotantes, protetores (ONGs, abrigos e protetores independentes) e administradores em torno do resgate e da adoção responsável de animais. Estes requisitos foram derivados do documento de design existente e descrevem, no formato EARS (Easy Approach to Requirements Syntax), o comportamento esperado do sistema.

O escopo cobre: autenticação e autorização por papéis (RBAC); gestão de perfis e verificação de protetores pelo administrador; cadastro e ciclo de vida do animal; denúncia/reporte de animais que precisam de resgate; listagem, busca e filtro público de animais disponíveis; pedidos de adoção com máquina de estados e regras de concorrência; moderação administrativa; notificações assíncronas; e upload de mídia.

Os requisitos abaixo são a fonte de verdade para a implementação e para a rastreabilidade das propriedades de correção definidas no design.

## Glossary

- **Visitante (VISITOR):** usuário não autenticado ou autenticado sem papel elevado; pode navegar e pesquisar animais disponíveis.
- **Adotante (ADOPTER):** usuário autenticado que pode enviar pedidos de adoção e reportar animais para resgate.
- **Protetor (PROTECTOR):** usuário verificado por um administrador que pode cadastrar animais, assumir resgates e revisar pedidos de adoção dos seus animais.
- **Administrador (ADMIN):** usuário com permissões elevadas para verificar protetores e moderar conteúdo.
- **Pedido de adoção (AdoptionRequest):** solicitação de um adotante para adotar um animal, com estados `SENT`, `UNDER_REVIEW`, `APPROVED`, `REJECTED`, `CANCELLED`.
- **Denúncia/Reporte de resgate (RescueReport):** registro de um animal que precisa de resgate, com localização e fotos, com estados `OPEN`, `ASSUMED`, `CLOSED`.
- **Ciclo de vida do animal (AnimalStatus):** `NEEDS_RESCUE`, `IN_RESCUE`, `SHELTERED`, `AVAILABLE`, `ADOPTED`, `UNAVAILABLE`.
- **Verificação de protetor (ProtectorApplication):** solicitação para obter o papel `PROTECTOR`, com estados `PENDING`, `APPROVED`, `REJECTED`.
- **Auto-rejeição:** rejeição automática dos demais pedidos pendentes de um animal quando um pedido é aprovado.
- **RBAC:** controle de acesso baseado em papéis.
- **Operação sensível:** operação que exige papel específico (cadastrar/alterar animal, revisar pedido, verificar protetor, moderar).

## Requirements

### Requisito 1: Autenticação e autorização por papéis (RBAC)

**User Story:** Como usuário da plataforma, quero me registrar, autenticar e ter minhas permissões avaliadas por papel, para que apenas ações permitidas ao meu perfil sejam executadas.

#### Acceptance Criteria

1. WHEN um usuário envia dados de registro válidos THEN o sistema SHALL criar uma conta com papel inicial `ADOPTER` e armazenar a senha como hash seguro.
2. IF o e-mail informado no registro já existe THEN o sistema SHALL rejeitar o registro com erro de conflito e não criar a conta.
3. WHEN um usuário envia credenciais válidas no login THEN o sistema SHALL emitir um token de acesso (JWT) e um refresh token.
4. WHEN um usuário envia credenciais inválidas no login THEN o sistema SHALL rejeitar a autenticação sem emitir tokens.
5. WHEN um refresh token válido é apresentado THEN o sistema SHALL emitir um novo token de acesso.
6. WHEN um usuário solicita uma operação sensível THEN o sistema SHALL verificar o papel exigido antes de executar a operação.
7. IF o ator não possui o papel exigido para uma operação sensível THEN o sistema SHALL rejeitar a operação com `403 Forbidden` e não produzir efeitos colaterais.
8. The system SHALL NOT expor o `passwordHash` em nenhuma resposta da API.

### Requisito 2: Perfis de usuário e verificação de protetor

**User Story:** Como usuário, quero gerenciar meu perfil e solicitar verificação como protetor, para que, após aprovação do administrador, eu possa cadastrar e gerenciar animais.

#### Acceptance Criteria

1. WHEN um usuário autenticado solicita seu perfil THEN o sistema SHALL retornar seus dados de perfil sem expor dados sensíveis de autenticação.
2. WHEN um usuário autenticado envia uma atualização válida de perfil THEN o sistema SHALL persistir as alterações e retornar o perfil atualizado.
3. WHEN um usuário envia uma solicitação de verificação de protetor com documentos THEN o sistema SHALL criar uma `ProtectorApplication` com status `PENDING`.
4. WHEN um administrador aprova uma solicitação de verificação de protetor THEN o sistema SHALL definir a solicitação como `APPROVED` e promover o papel do usuário para `PROTECTOR`.
5. WHEN um administrador rejeita uma solicitação de verificação de protetor THEN o sistema SHALL definir a solicitação como `REJECTED`, registrar o motivo e manter o papel do usuário inalterado.
6. IF um usuário sem papel `ADMIN` tenta decidir uma solicitação de verificação THEN o sistema SHALL rejeitar a operação sem efeitos colaterais.

### Requisito 3: Cadastro e ciclo de vida do animal

**User Story:** Como protetor verificado, quero cadastrar animais e gerenciar seu status ao longo do ciclo de vida, para que o animal avance do resgate até a adoção de forma controlada.

#### Acceptance Criteria

1. WHEN um protetor verificado cadastra um animal com dados válidos THEN o sistema SHALL criar o animal e associá-lo ao `protectorId` do protetor.
2. IF o campo `description` do animal está vazio THEN o sistema SHALL rejeitar o cadastro com erro de validação.
3. WHEN um protetor dono (ou administrador) atualiza um animal THEN o sistema SHALL persistir as alterações.
4. IF um usuário que não é o protetor dono nem administrador tenta alterar o animal THEN o sistema SHALL rejeitar a operação sem efeitos colaterais.
5. WHEN uma transição de status `next` pertence às transições válidas de `ANIMAL_TRANSITIONS[statusAtual]` THEN o sistema SHALL persistir o novo status.
6. IF uma transição de status `next` não pertence às transições válidas do status atual THEN o sistema SHALL rejeitar com erro `INVALID_TRANSITION` e não gravar nenhuma mudança.
7. The system SHALL garantir que o `status` de qualquer animal seja sempre um valor válido do enum `AnimalStatus`.
8. WHEN um animal com `status === "AVAILABLE"` existe THEN o sistema SHALL garantir que ele possui um `protectorId` cujo usuário tem papel `PROTECTOR` resultante de verificação aprovada por administrador.

### Requisito 4: Denúncia/reporte de animal para resgate

**User Story:** Como usuário autenticado, quero reportar um animal que precisa de resgate informando localização e fotos, para que protetores possam assumir o resgate.

#### Acceptance Criteria

1. WHEN um usuário autenticado envia uma denúncia com descrição não vazia, coordenadas válidas e fotos THEN o sistema SHALL criar uma `RescueReport` com status `OPEN`.
2. IF a `latitude` não está em [-90, 90] ou a `longitude` não está em [-180, 180] THEN o sistema SHALL rejeitar a denúncia com erro de validação.
3. IF a descrição da denúncia está vazia THEN o sistema SHALL rejeitar a denúncia com erro de validação.
4. WHEN um protetor verificado assume uma denúncia aberta THEN o sistema SHALL criar/vincular um registro de animal com status inicial `NEEDS_RESCUE` ou `IN_RESCUE` e marcar a denúncia como `ASSUMED`.
5. WHEN o sistema lista denúncias abertas com filtros THEN o sistema SHALL retornar apenas denúncias com status `OPEN`.
6. IF um usuário sem papel `PROTECTOR` tenta assumir uma denúncia THEN o sistema SHALL rejeitar a operação sem efeitos colaterais.

### Requisito 5: Listagem, busca e filtro público de animais disponíveis

**User Story:** Como visitante, quero pesquisar e filtrar animais disponíveis para adoção, para que eu encontre animais que atendam aos meus critérios.

#### Acceptance Criteria

1. WHEN um usuário solicita a listagem pública de animais THEN o sistema SHALL retornar somente animais com `status === "AVAILABLE"`.
2. The system SHALL NOT retornar na vitrine pública qualquer animal em `NEEDS_RESCUE`, `IN_RESCUE`, `SHELTERED`, `ADOPTED` ou `UNAVAILABLE`.
3. WHEN filtros opcionais (`species`, `size`, `sex`, `locationCity`, `ageMonthsMax`) são informados THEN o sistema SHALL aplicar todos os filtros informados e retornar apenas animais correspondentes.
4. IF `ageMonthsMax` é informado com valor negativo THEN o sistema SHALL rejeitar a requisição com erro de validação.
5. WHEN a listagem é solicitada com paginação THEN o sistema SHALL retornar os itens da página e o total de resultados.

### Requisito 6: Pedidos de adoção com máquina de estados

**User Story:** Como adotante, quero enviar e acompanhar pedidos de adoção, para que eu possa solicitar a adoção de animais disponíveis dentro de regras claras.

#### Acceptance Criteria

1. WHEN um adotante não suspenso cria um pedido para um animal com `status === "AVAILABLE"` THEN o sistema SHALL criar um `AdoptionRequest` com status `SENT` e manter o animal em `AVAILABLE`.
2. IF o animal não está `AVAILABLE` no momento da criação THEN o sistema SHALL rejeitar a criação com erro `ANIMAL_NOT_AVAILABLE` sem persistir o pedido.
3. IF já existe um pedido ativo (`SENT` ou `UNDER_REVIEW`) do mesmo adotante para o mesmo animal THEN o sistema SHALL rejeitar a criação de um novo pedido.
4. WHEN um pedido é criado THEN o sistema SHALL publicar um evento de domínio `ADOPTION_REQUEST_CREATED` direcionado ao protetor dono do animal.
5. WHEN uma mudança de status de pedido é solicitada THEN o sistema SHALL persistir apenas se o novo estado pertencer a `ADOPTION_TRANSITIONS[estadoAnterior]`.
6. The system SHALL NOT permitir transição a partir de estados terminais (`APPROVED`, `REJECTED`, `CANCELLED`).
7. WHEN um adotante cancela seu próprio pedido em estado `SENT` ou `UNDER_REVIEW` THEN o sistema SHALL definir o pedido como `CANCELLED`.

### Requisito 7: Aprovação de adoção com auto-rejeição transacional

**User Story:** Como protetor verificado, quero aprovar ou rejeitar pedidos de adoção dos meus animais, para que a adoção seja concluída de forma consistente e sem conflitos.

#### Acceptance Criteria

1. IF o ator não é o protetor dono do animal nem administrador THEN o sistema SHALL rejeitar a revisão do pedido sem efeitos colaterais.
2. IF o pedido alvo não está em `SENT` ou `UNDER_REVIEW` THEN o sistema SHALL rejeitar a revisão com erro de estado.
3. WHEN um pedido é aprovado AND o animal está `AVAILABLE` THEN o sistema SHALL, em uma única transação, definir o pedido como `APPROVED`, rejeitar automaticamente todos os demais pedidos do mesmo animal em `SENT`/`UNDER_REVIEW` e definir o animal como `ADOPTED`.
4. The system SHALL garantir que, para qualquer animal, exista no máximo um `AdoptionRequest` com status `APPROVED`.
5. WHEN um pedido atinge `APPROVED` THEN o sistema SHALL garantir que o animal correspondente está `ADOPTED`, com ambos os efeitos aplicados atomicamente (ou todos, ou nenhum).
6. WHEN um pedido é rejeitado THEN o sistema SHALL definir apenas o pedido alvo como `REJECTED` e manter o animal em `AVAILABLE`.
7. IF duas aprovações concorrentes ocorrem para o mesmo animal THEN o sistema SHALL concluir apenas a primeira e rejeitar a segunda com erro de conflito, baseado na precondição `animal.status === "AVAILABLE"`.
8. WHEN uma decisão de adoção é tomada THEN o sistema SHALL publicar eventos de decisão para os adotantes afetados.

### Requisito 8: Moderação e administração

**User Story:** Como administrador, quero moderar conteúdo e visualizar itens pendentes, para que eu mantenha a plataforma segura e confiável.

#### Acceptance Criteria

1. WHEN um administrador solicita a lista de solicitações de verificação de protetor pendentes THEN o sistema SHALL retornar as `ProtectorApplication` com status `PENDING` de forma paginada.
2. WHEN um usuário sinaliza um conteúdo com um motivo THEN o sistema SHALL registrar uma `ModerationFlag` associada ao alvo informado.
3. WHEN um administrador resolve uma sinalização aplicando uma ação de moderação THEN o sistema SHALL aplicar a ação (ex.: ocultar animal definindo `UNAVAILABLE`, suspender usuário) e atualizar a sinalização.
4. IF um usuário sem papel `ADMIN` tenta resolver uma sinalização THEN o sistema SHALL rejeitar a operação sem efeitos colaterais.

### Requisito 9: Notificações assíncronas

**User Story:** Como usuário, quero receber notificações sobre eventos relevantes para mim, para que eu acompanhe decisões e atualizações dos meus pedidos e solicitações.

#### Acceptance Criteria

1. WHEN um evento de novo pedido de adoção ocorre THEN o sistema SHALL criar uma notificação direcionada exatamente ao protetor dono do animal.
2. WHEN um evento de decisão de adoção ocorre THEN o sistema SHALL criar uma notificação direcionada exatamente ao adotante afetado.
3. WHEN um evento de resultado de verificação de protetor ocorre THEN o sistema SHALL criar uma notificação direcionada exatamente ao usuário solicitante.
4. The system SHALL NOT endereçar notificações de um evento a usuários não afetados por esse evento.
5. WHEN um usuário solicita suas notificações THEN o sistema SHALL retornar apenas as notificações endereçadas a ele, de forma paginada.
6. WHEN um usuário marca uma notificação própria como lida THEN o sistema SHALL atualizar o campo `read` dessa notificação.

### Requisito 10: Upload e gestão de mídia

**User Story:** Como protetor ou usuário reportando um animal, quero anexar fotos, para que o animal e a denúncia tenham registro visual confiável.

#### Acceptance Criteria

1. WHEN fotos são enviadas no cadastro de animal ou de denúncia THEN o sistema SHALL armazenar os arquivos no armazenamento de objetos e persistir apenas URLs/metadados no banco.
2. IF o armazenamento de objetos falha durante o upload THEN o sistema SHALL reverter a operação de cadastro associada e não persistir URLs inválidas.
3. WHEN um protetor dono adiciona fotos a um animal existente THEN o sistema SHALL associar as fotos ao animal preservando a ordem informada.
4. The system SHALL NOT salvar cadastros parciais quando o upload de mídia falhar.
