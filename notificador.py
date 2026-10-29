"""Notificador de alertas de localizacao.

Ponte com o design do PetGo (specs): o design pede publicacao no AWS SNS
via boto3. Como o ambiente ainda nao tem conta/credenciais AWS, usamos um
notificador LOCAL por padrao (apenas registra e loga), mantendo a MESMA
interface do cliente SNS do design. Quando quiserem o SNS real, basta
implementar SNSNotificador com o mesmo metodo publish() e trocar a
instancia usada no app.

Mapeia para:
  - design.md > Componente 4: SNSNotificationClient
  - requirements.md > Requisito 3 (Alerta via SNS)
"""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod

log = logging.getLogger("notificador")


class Notificador(ABC):
    """Interface comum (mesmo contrato do SNSNotificationClient do design)."""

    @abstractmethod
    def publish(
        self, message: str, subject: str, attributes: dict[str, str] | None = None
    ) -> str:
        """Publica a mensagem e retorna um id (equivalente ao MessageId do SNS)."""
        raise NotImplementedError


class NotificadorLocal(Notificador):
    """Implementacao local: nao chama a AWS. Loga e devolve um id simulado.

    Suficiente para desenvolvimento e para o escopo do trabalho, sem exigir
    credenciais AWS. O historico do alerta e persistido pelo chamador (store).
    """

    def publish(
        self, message: str, subject: str, attributes: dict[str, str] | None = None
    ) -> str:
        message_id = "local-" + uuid.uuid4().hex
        log.info("[ALERTA] %s | %s | attrs=%s | id=%s",
                 subject, message, attributes or {}, message_id)
        return message_id


# --- Gancho para o futuro (SNS real) -------------------------------------
# class SNSNotificador(Notificador):
#     """Publica no AWS SNS via boto3. Requer boto3, um topic ARN e credenciais.
#
#         pip install boto3
#     """
#     def __init__(self, topic_arn: str, region: str):
#         import boto3
#         self._client = boto3.client("sns", region_name=region)
#         self._topic_arn = topic_arn
#
#     def publish(self, message, subject, attributes=None):
#         resp = self._client.publish(
#             TopicArn=self._topic_arn,
#             Message=message,
#             Subject=subject,
#             MessageAttributes={
#                 k: {"DataType": "String", "StringValue": v}
#                 for k, v in (attributes or {}).items()
#             },
#         )
#         return resp["MessageId"]


def criar_notificador_padrao() -> Notificador:
    """Fabrica o notificador usado pela aplicacao.

    Hoje devolve o local. Para usar SNS, troque por SNSNotificador(...) lendo
    SNS_TOPIC_ARN e AWS_REGION de variaveis de ambiente (nunca hardcode).
    """
    return NotificadorLocal()
